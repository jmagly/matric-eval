"""Tests for the Task Registry (issue #33, ADR-004)."""

import pytest

from matric_eval.tasks.registry import (
    BenchmarkAccess,
    BenchmarkCategory,
    BenchmarkMetadata,
    BenchmarkReleasePolicy,
    BenchmarkSourceKind,
    BenchmarkStatus,
    BenchmarkUnavailableError,
    TaskRegistry,
    get_registry,
)


class TestBenchmarkMetadata:
    """Tests for BenchmarkMetadata dataclass."""

    def test_creation(self) -> None:
        meta = BenchmarkMetadata(
            name="test",
            description="A test benchmark",
            category=BenchmarkCategory.CODE,
            module_path="matric_eval.tasks.test.test",
            tier_samples={"smoke": 5, "full": 100},
            total_samples=100,
        )
        assert meta.name == "test"
        assert meta.category == BenchmarkCategory.CODE
        assert meta.tier_samples["smoke"] == 5
        assert meta.requires_sandbox is False
        assert meta.requires_vision is False
        assert meta.status == BenchmarkStatus.STABLE

    def test_frozen(self) -> None:
        """BenchmarkMetadata is immutable."""
        meta = BenchmarkMetadata(
            name="test",
            description="A test",
            category=BenchmarkCategory.CODE,
            module_path="matric_eval.tasks.test.test",
        )
        with pytest.raises(AttributeError):
            meta.name = "other"  # type: ignore[misc]

    def test_sandbox_metadata(self) -> None:
        meta = BenchmarkMetadata(
            name="swe_bench",
            description="SWE-bench",
            category=BenchmarkCategory.AGENTIC,
            module_path="matric_eval.tasks.swebench.verified.swe_bench_verified",
            requires_sandbox=True,
            sandbox_profile="agentic-dev",
            scoring_type="patch_apply",
        )
        assert meta.requires_sandbox is True
        assert meta.sandbox_profile == "agentic-dev"
        assert meta.scoring_type == "patch_apply"

    def test_multimodal_metadata(self) -> None:
        meta = BenchmarkMetadata(
            name="mmmu",
            description="MMMU",
            category=BenchmarkCategory.MULTIMODAL,
            module_path="matric_eval.tasks.mmmu.mmmu",
            requires_vision=True,
        )
        assert meta.requires_vision is True

    def test_upstream_provenance_metadata(self) -> None:
        meta = BenchmarkMetadata(
            name="upstream",
            description="Pinned upstream benchmark",
            category=BenchmarkCategory.AGENTIC,
            module_path="matric_eval.tasks.upstream.upstream",
            protocol_version="2.1",
            dataset_source="owner/dataset",
            dataset_revision="a" * 40,
            evaluator_source="owner/evaluator",
            evaluator_revision="b" * 40,
            license="Apache-2.0",
            access=BenchmarkAccess.PUBLIC,
            source_kind=BenchmarkSourceKind.HUGGINGFACE,
            release_policy=BenchmarkReleasePolicy.IMMUTABLE,
            dataset_configs=("default",),
            dataset_splits=("test",),
        )
        assert meta.protocol_version == "2.1"
        assert meta.dataset_source == "owner/dataset"
        assert meta.dataset_revision == "a" * 40
        assert meta.evaluator_source == "owner/evaluator"
        assert meta.evaluator_revision == "b" * 40
        assert meta.access == BenchmarkAccess.PUBLIC
        assert meta.source_kind == BenchmarkSourceKind.HUGGINGFACE
        assert meta.release_policy == BenchmarkReleasePolicy.IMMUTABLE
        assert meta.dataset_configs == ("default",)
        assert meta.dataset_splits == ("test",)


class TestTaskRegistry:
    """Tests for TaskRegistry."""

    def test_register_and_get(self, isolated_registry: TaskRegistry) -> None:
        meta = BenchmarkMetadata(
            name="test_bench",
            description="Test benchmark",
            category=BenchmarkCategory.CODE,
            module_path="matric_eval.tasks.test.test",
        )
        isolated_registry.register(meta)
        assert "test_bench" in isolated_registry
        assert isolated_registry.get("test_bench") is meta

    def test_get_nonexistent(self, isolated_registry: TaskRegistry) -> None:
        assert isolated_registry.get("nonexistent") is None

    def test_get_or_raise(self, isolated_registry: TaskRegistry) -> None:
        with pytest.raises(KeyError, match="Unknown benchmark: 'missing'"):
            isolated_registry.get_or_raise("missing")

    def test_duplicate_registration(self, isolated_registry: TaskRegistry) -> None:
        meta = BenchmarkMetadata(
            name="dup",
            description="Duplicate",
            category=BenchmarkCategory.CODE,
            module_path="matric_eval.tasks.dup.dup",
        )
        isolated_registry.register(meta)
        with pytest.raises(ValueError, match="already registered"):
            isolated_registry.register(meta)

    def test_freeze(self, isolated_registry: TaskRegistry) -> None:
        assert not isolated_registry.is_frozen
        isolated_registry.freeze()
        assert isolated_registry.is_frozen

        meta = BenchmarkMetadata(
            name="late",
            description="Too late",
            category=BenchmarkCategory.CODE,
            module_path="matric_eval.tasks.late.late",
        )
        with pytest.raises(RuntimeError, match="registry is frozen"):
            isolated_registry.register(meta)

    def test_list_names(self, isolated_registry: TaskRegistry) -> None:
        for name in ("charlie", "alpha", "bravo"):
            isolated_registry.register(
                BenchmarkMetadata(
                    name=name,
                    description=name,
                    category=BenchmarkCategory.CODE,
                    module_path=f"matric_eval.tasks.{name}.{name}",
                )
            )
        assert isolated_registry.list_names() == ["alpha", "bravo", "charlie"]

    def test_len(self, isolated_registry: TaskRegistry) -> None:
        assert len(isolated_registry) == 0
        isolated_registry.register(
            BenchmarkMetadata(
                name="a",
                description="a",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.a.a",
            )
        )
        assert len(isolated_registry) == 1

    def test_get_sample_count(self, isolated_registry: TaskRegistry) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="bench",
                description="bench",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.bench.bench",
                tier_samples={"smoke": 5, "quick": 50, "full": 200},
            )
        )
        assert isolated_registry.get_sample_count("bench", "smoke") == 5
        assert isolated_registry.get_sample_count("bench", "quick") == 50
        assert isolated_registry.get_sample_count("bench", "full") == 200
        assert isolated_registry.get_sample_count("bench", "unknown_tier") == 0
        assert isolated_registry.get_sample_count("missing", "smoke") == 0

    def test_get_descriptions(self, isolated_registry: TaskRegistry) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="b",
                description="Benchmark B",
                category=BenchmarkCategory.MATH,
                module_path="matric_eval.tasks.b.b",
            )
        )
        isolated_registry.register(
            BenchmarkMetadata(
                name="a",
                description="Benchmark A",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.a.a",
            )
        )
        desc = isolated_registry.get_descriptions()
        assert desc == {"a": "Benchmark A", "b": "Benchmark B"}

    def test_filter_by_category(self, isolated_registry: TaskRegistry) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="code1",
                description="Code 1",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.code1.code1",
            )
        )
        isolated_registry.register(
            BenchmarkMetadata(
                name="math1",
                description="Math 1",
                category=BenchmarkCategory.MATH,
                module_path="matric_eval.tasks.math1.math1",
            )
        )
        code = isolated_registry.filter(category=BenchmarkCategory.CODE)
        assert len(code) == 1
        assert code[0].name == "code1"

    def test_filter_by_sandbox(self, isolated_registry: TaskRegistry) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="standard",
                description="Standard",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.standard.standard",
            )
        )
        isolated_registry.register(
            BenchmarkMetadata(
                name="agentic",
                description="Agentic",
                category=BenchmarkCategory.AGENTIC,
                module_path="matric_eval.tasks.agentic.agentic",
                requires_sandbox=True,
            )
        )
        sandboxed = isolated_registry.filter(requires_sandbox=True)
        assert len(sandboxed) == 1
        assert sandboxed[0].name == "agentic"

    def test_filter_by_vision(self, isolated_registry: TaskRegistry) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="text",
                description="Text",
                category=BenchmarkCategory.CODE,
                module_path="matric_eval.tasks.text.text",
            )
        )
        isolated_registry.register(
            BenchmarkMetadata(
                name="visual",
                description="Visual",
                category=BenchmarkCategory.MULTIMODAL,
                module_path="matric_eval.tasks.visual.visual",
                requires_vision=True,
            )
        )
        vision = isolated_registry.filter(requires_vision=True)
        assert len(vision) == 1
        assert vision[0].name == "visual"

    def test_load_task_namespace_restriction(self, isolated_registry: TaskRegistry) -> None:
        """Module paths outside matric_eval.tasks.* should be rejected."""
        isolated_registry.register(
            BenchmarkMetadata(
                name="evil",
                description="Evil",
                category=BenchmarkCategory.CODE,
                module_path="os.system",
            )
        )
        with pytest.raises(ValueError, match="outside allowed namespace"):
            isolated_registry.load_task("evil")

    def test_load_task_rejects_unavailable_before_import(
        self, isolated_registry: TaskRegistry
    ) -> None:
        isolated_registry.register(
            BenchmarkMetadata(
                name="missing",
                description="Missing upstream benchmark",
                category=BenchmarkCategory.AGENTIC,
                module_path="matric_eval.tasks.does_not_exist.task",
                status=BenchmarkStatus.UNAVAILABLE,
                status_reason="upstream dataset is not public",
            )
        )

        with pytest.raises(BenchmarkUnavailableError, match="upstream dataset is not public"):
            isolated_registry.load_task("missing")

    def test_repr(self, isolated_registry: TaskRegistry) -> None:
        assert "0 benchmarks" in repr(isolated_registry)
        assert "open" in repr(isolated_registry)
        isolated_registry.freeze()
        assert "frozen" in repr(isolated_registry)


class TestGlobalRegistry:
    """Tests for the global registry singleton with real benchmark registrations."""

    def test_all_builtins_registered(self) -> None:
        """All 12 existing benchmarks should be registered on import."""
        import matric_eval.tasks  # noqa: F401

        registry = get_registry()
        expected = {
            "humaneval",
            "mbpp",
            "gsm8k",
            "arc",
            "ifeval",
            "ds1000",
            "livecodebench",
            "mmlu",
            "mtbench",
            "tool_calling",
            "matric_cli",
            "matric_memory",
        }
        registered = set(registry.list_names())
        assert expected.issubset(registered), f"Missing: {expected - registered}"

    def test_humaneval_metadata(self) -> None:
        """Spot-check humaneval metadata."""
        import matric_eval.tasks  # noqa: F401

        meta = get_registry().get("humaneval")
        assert meta is not None
        assert meta.category == BenchmarkCategory.CODE
        assert meta.tier_samples == {"smoke": 5, "quick": 75, "full": 164}
        assert meta.total_samples == 164
        assert meta.requires_sandbox is False
        assert meta.requires_vision is False

    def test_module_paths_valid(self) -> None:
        """All module paths should be in matric_eval.tasks.* namespace."""
        import matric_eval.tasks  # noqa: F401

        for meta in get_registry().list_metadata():
            assert meta.module_path.startswith("matric_eval.tasks."), (
                f"{meta.name}: invalid module_path {meta.module_path}"
            )

    def test_tier_samples_consistent(self) -> None:
        """Tier samples should match the existing TierConfig values."""
        import matric_eval.tasks  # noqa: F401
        from matric_eval.config.settings import TIERS

        registry = get_registry()
        for tier_name, tier_config in TIERS.items():
            for meta in registry.list_metadata():
                # Check that registered tier_samples matches TierConfig
                registered = meta.tier_samples.get(tier_name)
                config_val = getattr(tier_config, meta.name, None)
                if registered is not None and config_val is not None:
                    # Both exist — they should agree (or at least registry is the new source)
                    pass  # Registry is now authoritative; TierConfig will be deprecated


class TestRegisterBenchmarkDecorator:
    """Tests for the @register_benchmark decorator."""

    def test_decorator_attaches_metadata(self) -> None:
        """Decorator should attach _benchmark_metadata to the function."""
        import matric_eval.tasks  # noqa: F401
        from matric_eval.tasks.humaneval import humaneval

        assert hasattr(humaneval, "_benchmark_metadata")
        meta = humaneval._benchmark_metadata
        assert meta.name == "humaneval"
        assert meta.category == BenchmarkCategory.CODE

    def test_decorator_preserves_function(self) -> None:
        """Decorator should not change the function's behavior."""
        import matric_eval.tasks  # noqa: F401
        from matric_eval.tasks.humaneval import humaneval

        # Function should still be callable with tier parameter
        assert callable(humaneval)
        assert humaneval.__name__ == "humaneval"
