"""Selection semantics only; no dataset acquisition or provider execution."""

import json

import pytest

from matric_eval.data.adapters import project_samples
from matric_eval.data.evidence import make_evidence_record
from matric_eval.data.selection import (
    SelectionError,
    SelectionRequest,
    json_pointer,
    read_selection,
    select_records,
    verify_selection,
    write_selection,
)


def row(index, source="one", cluster=None, **changes):
    payload = {
        "prompt": f"question {index}",
        "answer": f"answer {index}",
        "kind": "chosen",
        **changes,
    }
    return make_evidence_record(
        payload,
        source_id=source,
        source_revision="revision-1",
        artifact_path=f"{source}.jsonl",
        artifact_sha256="a" * 64,
        row_index=index,
        split="original-train",
        cluster_id=cluster,
    )


def request(quotas=None, filters=None, seed=37, role="final_test"):
    return SelectionRequest.model_validate(
        {
            "version": "1",
            "seed": seed,
            "role": role,
            "sources": [
                {"source_id": source, "quota": quota, "filters": filters or {}}
                for source, quota in (quotas or {"one": 2}).items()
            ],
        }
    )


def test_mixing_is_deterministic_order_invariant_and_lossless():
    population = [
        row(index, source, source_marker=source) for source in ["one", "two"] for index in range(6)
    ]
    first = select_records(population, request({"two": 3, "one": 2}))
    second = select_records(list(reversed(population)), request({"one": 2, "two": 3}))
    assert first == second
    assert len(first.records) == 5
    assert len({item.selection_id for item in first.records}) == 5
    assert all(item.evidence.split == "original-train" for item in first.records)
    assert first.request.role == "final_test"
    assert "cross_manifest_role_ledger_required" in first.limitations
    assert read_selection(write_selection(first)) == first
    verify_selection(first, population)
    # Selection snapshots do not alias mutable caller payloads.
    population[0].payload["prompt"] = "changed after selection"
    assert all(
        item.evidence.payload["prompt"] != "changed after selection" for item in first.records
    )
    with pytest.raises(ValueError):
        verify_selection(first, population)


def test_seed_and_unselected_population_are_bound_by_replay():
    population = [row(index) for index in range(8)]
    first = select_records(population, request())
    changed = select_records(population, request(seed=38))
    assert changed.manifest_sha256 != first.manifest_sha256
    with pytest.raises(SelectionError, match="selection_replay_mismatch"):
        verify_selection(first, [*population, row(100)])
    document = first.model_dump()
    document["request"]["seed"] = 99
    with pytest.raises(SelectionError):
        read_selection(json.dumps(document))
    with pytest.raises(SelectionError):
        read_selection('{"selection_schema_version":"1","\\u0073election_schema_version":"1"}')


def test_filters_use_exact_scalars_and_preserve_scores_rubrics():
    population = [row(0, flag=True), row(1, flag=1), row(2, flag=None), row(3)]
    for expected, index in [(True, 0), (1, 1), (None, 2)]:
        selected = select_records(population, request({"one": 1}, {"/flag": expected}))
        assert selected.records[0].evidence.row_index == index
    evidence = row(9, rubric={"points": [1, 2]}, response="existing response", score=0)
    selected = select_records([evidence], request({"one": 1}))
    assert selected.records[0].evidence.payload == evidence.payload
    assert selected.records[0].evidence.payload["score"] == 0


def test_cluster_and_duplicate_content_boundaries_are_not_split():
    population = [row(0, cluster="shared"), row(1, cluster="shared")]
    with pytest.raises(SelectionError, match="quota_unavailable_without_cluster_split"):
        select_records(population, request({"one": 1}))
    assert len(select_records(population, request()).records) == 2
    with pytest.raises(SelectionError, match="filter_splits_cluster"):
        select_records(population, request({"one": 1}, {"/prompt": "question 0"}))
    duplicate = row(1, prompt="question 0", answer="answer 0")
    with pytest.raises(SelectionError, match="quota_unavailable_without_cluster_split"):
        select_records([row(0), duplicate], request({"one": 1}))
    with pytest.raises(SelectionError, match="duplicate_content_across_sources"):
        select_records([row(0), row(0, "two")], request({"one": 1, "two": 1}))
    with pytest.raises(SelectionError, match="duplicate_evidence_identity"):
        select_records([row(0), row(0)], request())


@pytest.mark.parametrize(
    "change",
    [{"seed": True}, {"seed": -1}, {"role": "test"}, {"role": ["training"]}, {"unknown": 1}],
)
def test_request_is_strict(change):
    value = request().model_dump()
    value.update(change)
    with pytest.raises(ValueError):
        SelectionRequest.model_validate(value)


def test_explicit_projection_preserves_full_evidence_and_never_coerces():
    evidence = row(0, response="old response", rubric={"text": "retained"}, score=0)
    manifest = select_records([evidence], request({"one": 1}))
    samples = project_samples(manifest, "/prompt", "/answer")
    assert samples[0].input == "question 0"
    assert samples[0].target == "answer 0"
    assert samples[0].metadata["evidence"] == evidence.model_dump()
    assert samples[0].metadata["intended_role"] == "final_test"
    for input_pointer, target_pointer in [("/missing", "/answer"), ("/prompt", "/score")]:
        with pytest.raises(SelectionError):
            project_samples(manifest, input_pointer, target_pointer)
    for value in [None, 0, False, [], {"value": "answer"}]:
        bad = select_records([row(0, answer=value)], request({"one": 1}))
        with pytest.raises(SelectionError, match="target_requires"):
            project_samples(bad, "/prompt", "/answer")


def test_explicit_chat_input_and_json_pointer_escaping():
    payload = {"a/b": {"~name": ["target"]}}
    assert json_pointer(payload, "/a~1b/~0name/0") == "target"
    for pointer in ["a", "/a~2b", "/a~1b/~0name/01"]:
        with pytest.raises(SelectionError):
            json_pointer(payload, pointer)
    chat = [{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}]
    manifest = select_records([row(0, prompt=chat, answer=["one", "two"])], request({"one": 1}))
    samples = project_samples(manifest, "/prompt", "/answer", "chat")
    assert [message.role for message in samples[0].input] == ["system", "user"]
    assert samples[0].target == ["one", "two"]
    for invalid in [
        [{"role": "tool", "content": "answer"}],
        [{"role": "user", "content": "x", "name": "lost"}],
        [{"role": "user", "content": None}],
    ]:
        bad = select_records([row(0, prompt=invalid)], request({"one": 1}))
        with pytest.raises(SelectionError):
            project_samples(bad, "/prompt", "/answer", "chat")


def test_explicit_configuration_and_original_split_selectors():
    first = row(0)
    second = make_evidence_record(
        {"prompt": "different", "answer": "value"},
        source_id="one",
        source_revision="revision-1",
        artifact_path="second.jsonl",
        artifact_sha256="b" * 64,
        row_index=0,
        split="original-test",
        configuration="task-b",
    )
    selection = request({"one": 1})
    selection.sources[0].configurations = ["task-b"]
    selection.sources[0].splits = ["original-test"]
    selected = select_records([first, second], selection)
    assert selected.records[0].evidence == second
    assert selected.request.role == "final_test"
    selection.sources[0].configurations = [None]
    selection.sources[0].splits = ["original-train"]
    assert select_records([first, second], selection).records[0].evidence == first


def test_duplicate_content_connects_clusters_transitively():
    first = row(0, cluster="alpha")
    duplicate = row(1, cluster="beta", prompt="question 0", answer="answer 0")
    peer = row(2, cluster="beta")
    with pytest.raises(SelectionError, match="quota_unavailable_without_cluster_split"):
        select_records([first, duplicate, peer], request({"one": 2}))
    assert len(select_records([first, duplicate, peer], request({"one": 3})).records) == 3


def test_configuration_selector_cannot_split_declared_cluster():
    first = row(0, cluster="same")
    second = make_evidence_record(
        {"prompt": "second", "answer": "second"},
        source_id="one",
        source_revision="revision-1",
        artifact_path="second.jsonl",
        artifact_sha256="b" * 64,
        row_index=0,
        split="test",
        configuration="different",
        cluster_id="same",
    )
    selection = request({"one": 1})
    selection.sources[0].configurations = [None]
    with pytest.raises(SelectionError, match="filter_splits_cluster"):
        select_records([first, second], selection)
