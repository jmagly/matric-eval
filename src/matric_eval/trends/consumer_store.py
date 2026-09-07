"""Immutable nullable v2 history, isolated from unverified legacy trend tables."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from matric_eval.results.comparison import require_comparable
from matric_eval.results.consumer import ConsumerError, canonical_json, read_consumer_result
from matric_eval.results.contract import ResultEnvelope


class ConsumerTrendStore:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        tables = {
            row[0]
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not tables <= {
            "evaluations",
            "consumer_sources_v1",
            "consumer_metrics_v1",
            "sqlite_sequence",
        }:
            self.connection.close()
            raise ConsumerError("unsupported_database_schema")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS consumer_sources_v1 (
                source_sha256 TEXT PRIMARY KEY, run_id TEXT NOT NULL, model_id TEXT NOT NULL,
                source_text TEXT NOT NULL, UNIQUE(run_id,model_id)
            );
            CREATE TABLE IF NOT EXISTS consumer_metrics_v1 (
                source_sha256 TEXT NOT NULL REFERENCES consumer_sources_v1(source_sha256),
                benchmark_id TEXT NOT NULL, metric_id TEXT NOT NULL, comparison_sha256 TEXT,
                value REAL, metric_json TEXT NOT NULL,
                PRIMARY KEY(source_sha256,benchmark_id,metric_id)
            );
        """)

    def close(self) -> None:
        self.connection.close()

    def ingest(self, source: str) -> str:
        result = read_consumer_result(source)
        if not isinstance(result, ResultEnvelope):
            raise ConsumerError("trend_requires_result_v2")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with self.connection:
            existing = self.connection.execute(
                "SELECT source_sha256 FROM consumer_sources_v1 WHERE run_id=? AND model_id=?",
                (result.run_id, result.model_id),
            ).fetchone()
            if existing is not None:
                if existing[0] == digest:
                    return digest
                raise ConsumerError("conflicting_source_identity")
            self.connection.execute(
                "INSERT INTO consumer_sources_v1 VALUES (?,?,?,?)",
                (digest, result.run_id, result.model_id, source),
            )
            for benchmark in result.benchmarks:
                for mid, metric in benchmark.metrics.items():
                    self.connection.execute(
                        "INSERT INTO consumer_metrics_v1 VALUES (?,?,?,?,?,?)",
                        (
                            digest,
                            benchmark.benchmark_id,
                            mid,
                            result.comparability.sha256 if result.comparability else None,
                            metric.estimate.value,
                            canonical_json(metric.model_dump()),
                        ),
                    )
        return digest

    def history(self, model_id: str, benchmark_id: str, metric_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT s.source_sha256,s.source_text FROM consumer_sources_v1 s
            JOIN consumer_metrics_v1 m ON s.source_sha256=m.source_sha256
            WHERE s.model_id=? AND m.benchmark_id=? AND m.metric_id=? ORDER BY s.source_sha256""",
            (model_id, benchmark_id, metric_id),
        ).fetchall()
        points = []
        for digest, text in rows:
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
                raise ConsumerError("stored_source_digest_mismatch")
            result = read_consumer_result(text)
            if not isinstance(result, ResultEnvelope):
                raise ConsumerError("stored_source_schema_mismatch")
            benchmark = next(
                item for item in result.benchmarks if item.benchmark_id == benchmark_id
            )
            metric = benchmark.metrics[metric_id]
            try:
                timestamp = datetime.fromisoformat(result.created_at.replace("Z", "+00:00"))
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    raise ValueError("naive timestamp")
                utc = timestamp.astimezone(timezone.utc).isoformat()
            except ValueError:
                utc = None
            points.append(
                {
                    "created_at_utc": utc,
                    "time_eligibility": {
                        "eligible": utc is not None,
                        "reasons": [] if utc is not None else ["timestamp_unverified"],
                    },
                    "source_sha256": digest,
                    "source": result.model_dump(),
                    "created_at": result.created_at,
                    "value": metric.estimate.value,
                    "metric": metric.model_dump(),
                    "execution": benchmark.execution,
                    "eligibility": metric.estimate.eligibility.model_dump(),
                    "model_snapshot_identity": None,
                    "model_snapshot_reason": "native_model_snapshot_unavailable",
                }
            )
        return sorted(
            points,
            key=lambda item: (
                item["created_at_utc"] is None,
                item["created_at_utc"] or "",
                item["source_sha256"],
            ),
        )

    def comparable_series(
        self,
        model_id: str,
        benchmark_id: str,
        metric_id: str,
        comparison_sha256: str,
        *,
        require_unchanged_model: bool = True,
    ) -> dict[str, Any]:
        history = self.history(model_id, benchmark_id, metric_id)
        included, excluded = [], []
        reference: ResultEnvelope | None = None
        for point in history:
            source = ResultEnvelope.model_validate(point["source"])
            reasons = []
            if not point["time_eligibility"]["eligible"]:
                reasons.append("timestamp_unverified")
            if require_unchanged_model:
                reasons.append("native_model_snapshot_unavailable")
            if source.comparability is None or source.comparability.sha256 != comparison_sha256:
                reasons.append("comparison_scope_mismatch")
            try:
                require_comparable(reference or source, source)
            except ValueError:
                reasons.append("comparison_identity_ineligible")
            if (
                point["value"] is None
                or not point["eligibility"]["eligible"]
                or point["execution"] != "completed"
            ):
                reasons.append("metric_measurement_ineligible")
            if reasons:
                excluded.append({**point, "reasons": reasons})
            else:
                reference = source
                included.append(point)
        return {
            "trend_series_schema_version": "1",
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "metric_id": metric_id,
            "comparison_sha256": comparison_sha256,
            "require_unchanged_model": require_unchanged_model,
            "points": included,
            "excluded": excluded,
            "status": "available" if included else "no_comparable_points",
            "limitations": [
                "descriptive_measurements_only",
                "no_model_snapshot_attestation",
                "no_interpolation_across_exclusions",
            ],
        }
