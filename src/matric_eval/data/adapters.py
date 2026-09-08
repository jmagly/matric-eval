"""Explicit, lossless-evidence-backed projections; no task or scorer inference."""

from __future__ import annotations

from typing import Literal

from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessage, ChatMessageAssistant, ChatMessageSystem, ChatMessageUser

from matric_eval.data.selection import SelectionError, SelectionManifest, json_pointer
from matric_eval.results.contract import Record, Text


class InspectProjection(Record):
    version: Literal["1"] = "1"
    input_pointer: Text
    target_pointer: Text
    input_format: Literal["text", "chat"] = "text"


def _chat(value: object) -> list[ChatMessage]:
    if not isinstance(value, list) or not value:
        raise SelectionError("chat_input_requires_nonempty_message_list")
    messages: list[ChatMessage] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"role", "content"}:
            raise SelectionError("chat_message_fields_unrepresentable")
        role, content = item["role"], item["content"]
        if not isinstance(content, str):
            raise SelectionError("chat_content_requires_text")
        if role == "system":
            messages.append(ChatMessageSystem(content=content))
        elif role == "user":
            messages.append(ChatMessageUser(content=content))
        elif role == "assistant":
            messages.append(ChatMessageAssistant(content=content))
        else:
            raise SelectionError("chat_role_unrepresentable")
    return messages


def project_samples(
    manifest: SelectionManifest,
    input_pointer: str,
    target_pointer: str,
    input_format: Literal["text", "chat"] = "text",
) -> list[Sample]:
    """Project explicit fields, retaining full evidence beside the Inspect sample.

    This validates the manifest's internal binding. Replay against the original
    population additionally requires ``verify_selection``. An intended role is
    not evidence of training eligibility or independent cross-manifest splits.
    """
    manifest = SelectionManifest.model_validate(manifest.model_dump())
    projection = InspectProjection(
        input_pointer=input_pointer, target_pointer=target_pointer, input_format=input_format
    )
    samples: list[Sample] = []
    for selected in manifest.records:
        payload = selected.evidence.payload
        source_input = json_pointer(payload, projection.input_pointer)
        target = json_pointer(payload, projection.target_pointer)
        if not (
            isinstance(target, str)
            or (
                isinstance(target, list)
                and bool(target)
                and all(isinstance(item, str) for item in target)
            )
        ):
            raise SelectionError("target_requires_text_or_text_list")
        sample_input: str | list[ChatMessage]
        if projection.input_format == "chat":
            sample_input = _chat(source_input)
        elif isinstance(source_input, str):
            sample_input = source_input
        else:
            raise SelectionError("input_requires_text")
        samples.append(
            Sample(
                id=selected.selection_id,
                input=sample_input,
                target=target,
                metadata={
                    "selection_manifest_sha256": manifest.manifest_sha256,
                    "intended_role": manifest.request.role,
                    "projection": projection.model_dump(),
                    "evidence": selected.evidence.model_dump(),
                },
            )
        )
    return samples
