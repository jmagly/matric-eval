"""
SQLite-based time-series store for evaluation results.

Stores evaluation points with scores, timestamps, and metadata
for historical analysis and regression detection.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class EvaluationPoint:
    """A single evaluation data point."""

    model: str
    benchmark: str
    score: float
    tier: str = "smoke"
    model_version: Optional[str] = None
    run_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.run_id is None:
            self.run_id = str(uuid.uuid4())[:8]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    model_version TEXT,
    benchmark TEXT NOT NULL,
    tier TEXT NOT NULL,
    score REAL NOT NULL,
    timestamp TEXT NOT NULL,
    run_id TEXT NOT NULL,
    metadata TEXT,
    UNIQUE(run_id, model, benchmark)
);

CREATE INDEX IF NOT EXISTS idx_model_benchmark ON evaluations(model, benchmark);
CREATE INDEX IF NOT EXISTS idx_timestamp ON evaluations(timestamp);
CREATE INDEX IF NOT EXISTS idx_run_id ON evaluations(run_id);
"""


class EvalStore:
    """
    SQLite-backed store for evaluation time-series data.

    Args:
        db_path: Path to SQLite database file
    """

    def __init__(self, db_path: str | Path = "results/evaluations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def add(self, point: EvaluationPoint) -> None:
        """
        Add an evaluation point to the store.

        Args:
            point: EvaluationPoint to store
        """
        import json

        conn = self._get_conn()
        point_id = f"{point.run_id}-{point.model}-{point.benchmark}"
        conn.execute(
            """INSERT OR REPLACE INTO evaluations
            (id, model, model_version, benchmark, tier, score, timestamp, run_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                point_id,
                point.model,
                point.model_version,
                point.benchmark,
                point.tier,
                point.score,
                point.timestamp.isoformat(),
                point.run_id,
                json.dumps(point.metadata) if point.metadata else None,
            ),
        )
        conn.commit()

    def add_batch(self, points: list[EvaluationPoint]) -> None:
        """Add multiple evaluation points."""
        for point in points:
            self.add(point)

    def get_history(
        self,
        model: str,
        benchmark: str,
        limit: int = 100,
    ) -> list[EvaluationPoint]:
        """
        Get evaluation history for a model/benchmark pair.

        Args:
            model: Model name
            benchmark: Benchmark name
            limit: Maximum number of results

        Returns:
            List of EvaluationPoints ordered by timestamp (newest first)
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT model, model_version, benchmark, tier, score,
                      timestamp, run_id, metadata
            FROM evaluations
            WHERE model = ? AND benchmark = ?
            ORDER BY timestamp DESC
            LIMIT ?""",
            (model, benchmark, limit),
        ).fetchall()

        return [self._row_to_point(row) for row in rows]

    def get_latest_scores(
        self,
        benchmark: Optional[str] = None,
    ) -> dict[str, float]:
        """
        Get the latest score for each model, optionally filtered by benchmark.

        Args:
            benchmark: Optional benchmark filter

        Returns:
            Dict mapping model name to latest score
        """
        conn = self._get_conn()
        if benchmark:
            rows = conn.execute(
                """SELECT model, score FROM evaluations
                WHERE benchmark = ?
                GROUP BY model
                HAVING timestamp = MAX(timestamp)
                ORDER BY score DESC""",
                (benchmark,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT model, AVG(score) as score FROM evaluations
                GROUP BY model
                HAVING timestamp = MAX(timestamp)
                ORDER BY score DESC""",
            ).fetchall()

        return {row["model"]: row["score"] for row in rows}

    def get_models(self) -> list[str]:
        """Get all unique model names in the store."""
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT model FROM evaluations ORDER BY model").fetchall()
        return [row["model"] for row in rows]

    def get_benchmarks(self) -> list[str]:
        """Get all unique benchmark names in the store."""
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT benchmark FROM evaluations ORDER BY benchmark").fetchall()
        return [row["benchmark"] for row in rows]

    def count(self) -> int:
        """Get total number of evaluation points."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM evaluations").fetchone()
        return row["cnt"]

    def _row_to_point(self, row: sqlite3.Row) -> EvaluationPoint:
        """Convert a database row to an EvaluationPoint."""
        import json

        metadata = {}
        if row["metadata"]:
            metadata = json.loads(row["metadata"])

        return EvaluationPoint(
            model=row["model"],
            model_version=row["model_version"],
            benchmark=row["benchmark"],
            tier=row["tier"],
            score=row["score"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            run_id=row["run_id"],
            metadata=metadata,
        )
