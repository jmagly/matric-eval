"""
Tests for extended dataset management functions (issue #37).

Covers:
- get_dataset_path(): per-benchmark env var overrides
- reservoir_sample(): streaming-compatible reservoir sampling
- compute_checksum() / verify_checksum(): SHA-256 integrity checks
- generate_checksum_manifest(): directory-wide checksums
- load_hf_dataset(): HuggingFace Hub loading with mocks
- load_parquet(): local Parquet file loading with mocks
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest
from inspect_ai.dataset import Sample


# =============================================================================
# get_dataset_path() Tests
# =============================================================================


@pytest.mark.unit
class TestGetDatasetPath:
    """Tests for get_dataset_path() — per-benchmark env var overrides."""

    def test_returns_none_when_no_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None when no MATRIC_EVAL_{BENCHMARK}_DATA_PATH is set."""
        monkeypatch.delenv("MATRIC_EVAL_HUMANEVAL_DATA_PATH", raising=False)

        from matric_eval.datasets import get_dataset_path

        result = get_dataset_path("humaneval")
        assert result is None

    def test_returns_path_when_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return path when MATRIC_EVAL_HUMANEVAL_DATA_PATH is set."""
        monkeypatch.setenv("MATRIC_EVAL_HUMANEVAL_DATA_PATH", "/custom/path/humaneval")

        from matric_eval.datasets import get_dataset_path

        result = get_dataset_path("humaneval")
        assert result == "/custom/path/humaneval"

    def test_returns_path_for_mbpp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return path when MATRIC_EVAL_MBPP_DATA_PATH is set."""
        monkeypatch.setenv("MATRIC_EVAL_MBPP_DATA_PATH", "/data/evals/mbpp")

        from matric_eval.datasets import get_dataset_path

        result = get_dataset_path("mbpp")
        assert result == "/data/evals/mbpp"

    def test_case_insensitive_benchmark_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle mixed-case benchmark names (normalises to uppercase for env lookup)."""
        monkeypatch.setenv("MATRIC_EVAL_HUMANEVAL_DATA_PATH", "/custom/path")

        from matric_eval.datasets import get_dataset_path

        # Both lowercase and uppercase should work
        assert get_dataset_path("humaneval") == "/custom/path"
        assert get_dataset_path("HUMANEVAL") == "/custom/path"
        assert get_dataset_path("HumanEval") == "/custom/path"

    def test_returns_none_for_unknown_benchmark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None for benchmarks with no override set."""
        monkeypatch.delenv("MATRIC_EVAL_UNKNOWNBENCH_DATA_PATH", raising=False)

        from matric_eval.datasets import get_dataset_path

        result = get_dataset_path("unknownbench")
        assert result is None

    def test_different_benchmarks_independent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting one benchmark path should not affect others."""
        monkeypatch.setenv("MATRIC_EVAL_HUMANEVAL_DATA_PATH", "/path/to/humaneval")
        monkeypatch.delenv("MATRIC_EVAL_MBPP_DATA_PATH", raising=False)

        from matric_eval.datasets import get_dataset_path

        assert get_dataset_path("humaneval") == "/path/to/humaneval"
        assert get_dataset_path("mbpp") is None


# =============================================================================
# reservoir_sample() Tests
# =============================================================================


@pytest.mark.unit
class TestReservoirSample:
    """Tests for reservoir_sample() — Vitter's Algorithm R for streaming datasets."""

    def test_correct_count_from_large_iterator(self) -> None:
        """Should return exactly k items from a large iterator."""
        from matric_eval.datasets import reservoir_sample

        large_iter = range(10_000)
        result = reservoir_sample(large_iter, k=100, seed=42)

        assert len(result) == 100

    def test_reproducible_with_same_seed(self) -> None:
        """Should return the same items when called twice with the same seed."""
        from matric_eval.datasets import reservoir_sample

        data = list(range(1_000))
        result1 = reservoir_sample(iter(data), k=50, seed=42)
        result2 = reservoir_sample(iter(data), k=50, seed=42)

        assert result1 == result2

    def test_different_results_with_different_seed(self) -> None:
        """Should return different items with different seeds."""
        from matric_eval.datasets import reservoir_sample

        data = list(range(1_000))
        result1 = reservoir_sample(iter(data), k=50, seed=42)
        result2 = reservoir_sample(iter(data), k=50, seed=99)

        # With 50 samples from 1000, same seed produces same result
        # Different seeds should produce different selections
        assert result1 != result2

    def test_k_greater_than_iterator_length(self) -> None:
        """Should return all items when k >= len(iterator)."""
        from matric_eval.datasets import reservoir_sample

        data = [1, 2, 3, 4, 5]
        result = reservoir_sample(iter(data), k=100, seed=42)

        assert sorted(result) == sorted(data)

    def test_k_equals_zero(self) -> None:
        """Should return empty list when k=0."""
        from matric_eval.datasets import reservoir_sample

        result = reservoir_sample(range(100), k=0, seed=42)
        assert result == []

    def test_k_equals_one(self) -> None:
        """Should return exactly one item when k=1."""
        from matric_eval.datasets import reservoir_sample

        result = reservoir_sample(range(100), k=1, seed=42)
        assert len(result) == 1
        assert result[0] in range(100)

    def test_empty_iterator(self) -> None:
        """Should return empty list for empty iterator."""
        from matric_eval.datasets import reservoir_sample

        result = reservoir_sample(iter([]), k=10, seed=42)
        assert result == []

    def test_items_are_from_original_data(self) -> None:
        """All returned items should come from the original data."""
        from matric_eval.datasets import reservoir_sample

        data = list(range(500))
        result = reservoir_sample(iter(data), k=50, seed=42)

        for item in result:
            assert item in data

    def test_no_duplicates(self) -> None:
        """Reservoir sampling should not produce duplicates."""
        from matric_eval.datasets import reservoir_sample

        data = list(range(500))
        result = reservoir_sample(iter(data), k=100, seed=42)

        assert len(result) == len(set(result))


# =============================================================================
# compute_checksum() / verify_checksum() Tests
# =============================================================================


@pytest.mark.unit
class TestChecksums:
    """Tests for compute_checksum() and verify_checksum()."""

    def test_checksum_of_known_content(self, tmp_path: Path) -> None:
        """Checksum of known content should match expected SHA-256."""
        from matric_eval.datasets import compute_checksum

        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(content)

        result = compute_checksum(test_file)
        assert result == expected

    def test_checksum_accepts_string_path(self, tmp_path: Path) -> None:
        """compute_checksum should accept both str and Path."""
        from matric_eval.datasets import compute_checksum

        content = b"test data"
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(content)

        result_path = compute_checksum(test_file)
        result_str = compute_checksum(str(test_file))
        assert result_path == result_str

    def test_checksum_returns_hex_string(self, tmp_path: Path) -> None:
        """compute_checksum should return a 64-character hex string (SHA-256)."""
        from matric_eval.datasets import compute_checksum

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"some content")

        result = compute_checksum(test_file)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_verify_checksum_passes_for_correct_checksum(self, tmp_path: Path) -> None:
        """verify_checksum should return True for matching checksum."""
        from matric_eval.datasets import compute_checksum, verify_checksum

        content = b"matric eval test data"
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(content)

        checksum = compute_checksum(test_file)
        assert verify_checksum(test_file, checksum) is True

    def test_verify_checksum_fails_for_wrong_checksum(self, tmp_path: Path) -> None:
        """verify_checksum should return False for non-matching checksum."""
        from matric_eval.datasets import verify_checksum

        content = b"matric eval test data"
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(content)

        wrong_checksum = "a" * 64
        assert verify_checksum(test_file, wrong_checksum) is False

    def test_verify_checksum_accepts_string_path(self, tmp_path: Path) -> None:
        """verify_checksum should accept both str and Path."""
        from matric_eval.datasets import compute_checksum, verify_checksum

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"content")

        checksum = compute_checksum(test_file)
        assert verify_checksum(str(test_file), checksum) is True

    def test_different_files_have_different_checksums(self, tmp_path: Path) -> None:
        """Different file contents should produce different checksums."""
        from matric_eval.datasets import compute_checksum

        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_bytes(b"content one")
        file2.write_bytes(b"content two")

        assert compute_checksum(file1) != compute_checksum(file2)

    def test_empty_file_checksum(self, tmp_path: Path) -> None:
        """Empty file should have a valid (and known) SHA-256 checksum."""
        from matric_eval.datasets import compute_checksum

        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")

        result = compute_checksum(empty_file)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected


# =============================================================================
# generate_checksum_manifest() Tests
# =============================================================================


@pytest.mark.unit
class TestGenerateChecksumManifest:
    """Tests for generate_checksum_manifest()."""

    def test_generates_checksums_for_all_files(self, tmp_path: Path) -> None:
        """Should generate checksums for all files in directory."""
        from matric_eval.datasets import compute_checksum, generate_checksum_manifest

        (tmp_path / "file1.txt").write_bytes(b"content1")
        (tmp_path / "file2.txt").write_bytes(b"content2")
        (tmp_path / "file3.jsonl").write_bytes(b"content3")

        manifest = generate_checksum_manifest(tmp_path)

        assert len(manifest) == 3
        # Keys should be relative file names or full paths
        file_names = {Path(k).name for k in manifest.keys()}
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names
        assert "file3.jsonl" in file_names

    def test_checksums_match_individual_computations(self, tmp_path: Path) -> None:
        """Manifest checksums should match individually computed checksums."""
        from matric_eval.datasets import compute_checksum, generate_checksum_manifest

        content = b"some test content"
        test_file = tmp_path / "data.jsonl"
        test_file.write_bytes(content)

        manifest = generate_checksum_manifest(tmp_path)
        expected = compute_checksum(test_file)

        # Find the checksum for our file
        file_checksum = None
        for key, checksum in manifest.items():
            if Path(key).name == "data.jsonl":
                file_checksum = checksum
                break

        assert file_checksum == expected

    def test_empty_directory_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty directory should return empty dict."""
        from matric_eval.datasets import generate_checksum_manifest

        manifest = generate_checksum_manifest(tmp_path)
        assert manifest == {}

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Should accept both str and Path arguments."""
        from matric_eval.datasets import generate_checksum_manifest

        (tmp_path / "test.txt").write_bytes(b"hello")

        manifest_path = generate_checksum_manifest(tmp_path)
        manifest_str = generate_checksum_manifest(str(tmp_path))

        assert manifest_path == manifest_str

    def test_subdirectories_handled(self, tmp_path: Path) -> None:
        """Should handle directories with subdirectories (flat files only, or recursive)."""
        from matric_eval.datasets import generate_checksum_manifest

        (tmp_path / "file1.txt").write_bytes(b"top level")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_bytes(b"nested")

        manifest = generate_checksum_manifest(tmp_path)
        # At minimum, top-level file should be included
        file_names = {Path(k).name for k in manifest.keys()}
        assert "file1.txt" in file_names


# =============================================================================
# load_hf_dataset() Tests
# =============================================================================


@pytest.mark.unit
class TestLoadHFDataset:
    """Tests for load_hf_dataset() with mocked HuggingFace datasets library."""

    def _make_hf_record(self, idx: int) -> dict:
        return {
            "task_id": f"task_{idx}",
            "prompt": f"prompt_{idx}",
            "canonical_solution": f"solution_{idx}",
            "entry_point": f"func_{idx}",
            "test": f"assert func_{idx}() == {idx}",
        }

    def _make_mock_dataset(self, n: int) -> MagicMock:
        """Create a mock HF dataset with n records."""
        records = [self._make_hf_record(i) for i in range(n)]
        mock_ds = MagicMock()
        mock_ds.__iter__ = Mock(return_value=iter(records))
        mock_ds.__len__ = Mock(return_value=n)
        # Support indexing
        mock_ds.__getitem__ = Mock(side_effect=lambda k: records[k] if isinstance(k, int) else records)
        return mock_ds

    def test_basic_loading_returns_samples(self) -> None:
        """Should return list of Sample objects from HF dataset."""
        from matric_eval.datasets import load_hf_dataset

        mock_ds = self._make_mock_dataset(10)

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = Mock(return_value=mock_ds)

            def simple_converter(record: dict) -> Sample:
                return Sample(
                    input=record["prompt"],
                    target=record["canonical_solution"],
                    id=record["task_id"],
                )

            result = load_hf_dataset(
                "openai/humaneval",
                split="test",
                record_to_sample=simple_converter,
            )

        assert isinstance(result, list)
        assert all(isinstance(s, Sample) for s in result)

    def test_sample_count_limiting(self) -> None:
        """Should limit results to sample_count when specified."""
        from matric_eval.datasets import load_hf_dataset

        mock_ds = self._make_mock_dataset(100)

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = Mock(return_value=mock_ds)

            def simple_converter(record: dict) -> Sample:
                return Sample(
                    input=record["prompt"],
                    target=record["canonical_solution"],
                    id=record["task_id"],
                )

            result = load_hf_dataset(
                "openai/humaneval",
                split="test",
                sample_count=10,
                record_to_sample=simple_converter,
            )

        assert len(result) == 10

    def test_record_to_sample_conversion(self) -> None:
        """Should apply record_to_sample converter to each record."""
        from matric_eval.datasets import load_hf_dataset

        converted_records = []

        def tracking_converter(record: dict) -> Sample:
            converted_records.append(record)
            return Sample(
                input=record["prompt"],
                target=record["canonical_solution"],
                id=record["task_id"],
            )

        mock_ds = self._make_mock_dataset(5)

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = Mock(return_value=mock_ds)

            result = load_hf_dataset(
                "openai/humaneval",
                split="test",
                record_to_sample=tracking_converter,
            )

        assert len(converted_records) == 5

    def test_default_record_conversion_without_converter(self) -> None:
        """Should handle records without a custom converter (basic Sample creation)."""
        from matric_eval.datasets import load_hf_dataset

        # Records with 'input' and 'target' keys — standard Inspect AI format
        records = [{"input": f"q{i}", "target": f"a{i}"} for i in range(3)]
        mock_ds = MagicMock()
        mock_ds.__iter__ = Mock(return_value=iter(records))
        mock_ds.__len__ = Mock(return_value=3)

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = Mock(return_value=mock_ds)

            result = load_hf_dataset(
                "some/dataset",
                split="test",
                record_to_sample=None,
            )

        assert isinstance(result, list)

    def test_import_error_when_datasets_not_installed(self) -> None:
        """Should raise ImportError with helpful message when datasets lib is not installed."""
        from matric_eval.datasets import load_hf_dataset

        with patch.dict("sys.modules", {"datasets": None}):
            with pytest.raises((ImportError, ModuleNotFoundError)) as exc_info:
                load_hf_dataset("openai/humaneval", split="test")

        # Should mention how to install
        error_msg = str(exc_info.value).lower()
        assert "datasets" in error_msg or "install" in error_msg or "pip" in error_msg

    def test_subset_parameter_passed_to_load_dataset(self) -> None:
        """Should pass subset/config name to datasets.load_dataset."""
        from matric_eval.datasets import load_hf_dataset

        mock_ds = self._make_mock_dataset(5)
        captured_kwargs: dict = {}

        def capture_load_dataset(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_ds

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = capture_load_dataset

            load_hf_dataset(
                "some/dataset",
                split="train",
                subset="subset_name",
                record_to_sample=lambda r: Sample(input=r.get("input", ""), target=r.get("target", "")),
            )

        # Subset should be passed as 'name' or 'config_name' to load_dataset
        assert "subset_name" in (
            captured_kwargs.get("name", "")
            or captured_kwargs.get("config_name", "")
            or str(captured_kwargs)
        )

    def test_split_parameter_passed_to_load_dataset(self) -> None:
        """Should pass split to datasets.load_dataset."""
        from matric_eval.datasets import load_hf_dataset

        mock_ds = self._make_mock_dataset(3)
        captured_kwargs: dict = {}

        def capture_load_dataset(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_ds

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = capture_load_dataset

            load_hf_dataset(
                "some/dataset",
                split="validation",
                record_to_sample=lambda r: Sample(input=r.get("input", ""), target=r.get("target", "")),
            )

        assert captured_kwargs.get("split") == "validation"

    def test_streaming_mode_uses_reservoir_sampling(self) -> None:
        """Should use reservoir sampling when streaming=True and sample_count is given."""
        from matric_eval.datasets import load_hf_dataset

        records = [{"input": f"q{i}", "target": f"a{i}"} for i in range(1000)]
        mock_ds = MagicMock()
        mock_ds.__iter__ = Mock(return_value=iter(records))

        with patch.dict("sys.modules", {"datasets": MagicMock()}):
            import datasets as mock_datasets_module
            mock_datasets_module.load_dataset = Mock(return_value=mock_ds)

            result = load_hf_dataset(
                "some/dataset",
                split="test",
                sample_count=50,
                streaming=True,
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        assert len(result) == 50

    def test_revision_auth_cache_and_provenance(self, tmp_path: Path) -> None:
        """Pinned authenticated loads must not retain credentials in metadata."""
        from matric_eval.datasets import load_hf_dataset

        revision = "a" * 40
        mock_module = MagicMock()
        mock_module.load_dataset = Mock(
            return_value=[{"input": "question", "target": "answer"}]
        )
        with patch.dict("sys.modules", {"datasets": mock_module}):
            result = load_hf_dataset(
                "owner/dataset",
                subset="config",
                split="validation",
                revision=revision,
                token="secret-token",
                cache_dir=tmp_path,
                require_immutable_revision=True,
            )

        mock_module.load_dataset.assert_called_once_with(
            "owner/dataset",
            split="validation",
            name="config",
            revision=revision,
            token="secret-token",
            cache_dir=str(tmp_path),
        )
        assert result[0].metadata == {
            "dataset_source": "owner/dataset",
            "dataset_revision": revision,
            "dataset_config": "config",
            "dataset_split": "validation",
        }
        assert "secret-token" not in repr(result)

    @pytest.mark.parametrize("revision", [None, "main", "v1.0", "abc123"])
    def test_immutable_revision_requirement(self, revision: str | None) -> None:
        from matric_eval.datasets import DatasetRevisionError, load_hf_dataset

        with pytest.raises(DatasetRevisionError, match="immutable full commit"):
            load_hf_dataset(
                "owner/dataset",
                revision=revision,
                require_immutable_revision=True,
            )

    def test_offline_loading_uses_local_cache_only(self, tmp_path: Path) -> None:
        from matric_eval.datasets import load_hf_dataset

        download_config = object()
        mock_module = MagicMock()
        mock_module.DownloadConfig = Mock(return_value=download_config)
        mock_module.load_dataset = Mock(return_value=[])
        with patch.dict("sys.modules", {"datasets": mock_module}):
            load_hf_dataset(
                "owner/dataset",
                revision="b" * 40,
                cache_dir=tmp_path,
                offline=True,
            )

        mock_module.DownloadConfig.assert_called_once_with(
            cache_dir=str(tmp_path), local_files_only=True
        )
        assert mock_module.load_dataset.call_args.kwargs["download_config"] is download_config

    @pytest.mark.parametrize(
        ("exception_name", "expected_error"),
        [
            ("GatedRepoError", "DatasetAccessError"),
            ("RevisionNotFoundError", "DatasetRevisionError"),
            ("RepositoryNotFoundError", "DatasetSourceError"),
        ],
    )
    def test_remote_failures_are_classified(
        self, exception_name: str, expected_error: str
    ) -> None:
        import matric_eval.datasets as dataset_module

        error_type = type(exception_name, (RuntimeError,), {})
        mock_module = MagicMock()
        mock_module.load_dataset = Mock(side_effect=error_type("upstream detail"))
        with patch.dict("sys.modules", {"datasets": mock_module}):
            with pytest.raises(getattr(dataset_module, expected_error)) as exc_info:
                dataset_module.load_hf_dataset(
                    "owner/dataset", revision="c" * 40
                )
        assert "upstream detail" not in str(exc_info.value)

    def test_offline_failure_is_classified(self) -> None:
        from matric_eval.datasets import DatasetOfflineError, load_hf_dataset

        mock_module = MagicMock()
        mock_module.DownloadConfig = Mock(return_value=object())
        mock_module.load_dataset = Mock(side_effect=FileNotFoundError("cache path"))
        with patch.dict("sys.modules", {"datasets": mock_module}):
            with pytest.raises(DatasetOfflineError, match="offline cache"):
                load_hf_dataset(
                    "owner/dataset", revision="d" * 40, offline=True
                )


# =============================================================================
# load_parquet() Tests
# =============================================================================


@pytest.mark.unit
class TestLoadParquet:
    """Tests for load_parquet() with mocked pyarrow/parquet reading."""

    def _make_parquet_file(self, tmp_path: Path, n_rows: int = 10) -> Path:
        """Create a temporary parquet file for testing."""
        parquet_file = tmp_path / "test.parquet"
        # We'll mock pyarrow, so just create a placeholder file
        parquet_file.write_bytes(b"mock parquet data")
        return parquet_file

    def test_basic_loading_returns_list(self, tmp_path: Path) -> None:
        """Should return a list of Sample objects from parquet file."""
        from matric_eval.datasets import load_parquet

        parquet_file = self._make_parquet_file(tmp_path, n_rows=5)
        records = [{"input": f"q{i}", "target": f"a{i}"} for i in range(5)]

        mock_table = MagicMock()
        mock_table.to_pylist = Mock(return_value=records)

        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result = load_parquet(
                parquet_file,
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        assert isinstance(result, list)
        assert len(result) == 5
        assert all(isinstance(s, Sample) for s in result)

    def test_sample_count_limiting(self, tmp_path: Path) -> None:
        """Should limit to sample_count rows."""
        from matric_eval.datasets import load_parquet

        parquet_file = self._make_parquet_file(tmp_path, n_rows=100)
        records = [{"input": f"q{i}", "target": f"a{i}"} for i in range(100)]

        mock_table = MagicMock()
        mock_table.to_pylist = Mock(return_value=records)

        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result = load_parquet(
                parquet_file,
                sample_count=20,
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        assert len(result) == 20

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Should accept str path as well as Path."""
        from matric_eval.datasets import load_parquet

        parquet_file = self._make_parquet_file(tmp_path)
        records = [{"input": "q", "target": "a"}]

        mock_table = MagicMock()
        mock_table.to_pylist = Mock(return_value=records)

        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result = load_parquet(
                str(parquet_file),
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        assert isinstance(result, list)

    def test_no_converter_returns_list(self, tmp_path: Path) -> None:
        """Should handle records without custom converter."""
        from matric_eval.datasets import load_parquet

        parquet_file = self._make_parquet_file(tmp_path)
        records = [{"input": "q0", "target": "a0"}]

        mock_table = MagicMock()
        mock_table.to_pylist = Mock(return_value=records)

        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result = load_parquet(parquet_file, record_to_sample=None)

        assert isinstance(result, list)

    def test_reproducible_sampling_with_seed(self, tmp_path: Path) -> None:
        """Should produce the same subset with the same seed."""
        from matric_eval.datasets import load_parquet

        parquet_file = self._make_parquet_file(tmp_path)
        records = [{"input": f"q{i}", "target": f"a{i}"} for i in range(100)]

        mock_table = MagicMock()
        mock_table.to_pylist = Mock(return_value=records)

        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result1 = load_parquet(
                parquet_file,
                sample_count=10,
                seed=42,
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        mock_table.to_pylist = Mock(return_value=records)
        with patch("matric_eval.datasets._read_parquet_table", return_value=mock_table):
            result2 = load_parquet(
                parquet_file,
                sample_count=10,
                seed=42,
                record_to_sample=lambda r: Sample(input=r["input"], target=r["target"]),
            )

        assert [s.input for s in result1] == [s.input for s in result2]
