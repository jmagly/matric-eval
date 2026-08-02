"""Video-MME-v2 with official media configurations and grouped scoring."""

from __future__ import annotations

import ast
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentImage, ContentText, GenerateConfig
from inspect_ai.scorer import (
    Metric,
    SampleScore,
    Score,
    Scorer,
    Target,
    accuracy,
    metric,
    scorer,
)
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path
from matric_eval.tasks.registry import register_benchmark

VIDEOMME_DATASET = "MME-Benchmarks/Video-MME-v2"
VIDEOMME_DATASET_REVISION = "31ca5db7bc5ccfc3033a1075efc7858e783c6203"
VIDEOMME_EVALUATOR_REVISION = "28fc3bcfbd4d162594c8e4bad866b694d9b035aa"
VALID_ANSWERS = frozenset("ABCDEFGH")
DEFAULT_MAX_FRAMES = 64
PROVIDER_FRAME_CAPS = {"ollama": 16, "openrouter": 32}
ACADEMIC_USE_NOTICE = (
    "Video-MME-v2 permits academic research use only and prohibits commercial use, "
    "redistribution, publication, copying, dissemination, or modification without approval."
)


def _extract_answer(text: str) -> str:
    """Extract A-H using the standalone upstream evaluator semantics."""
    for prefix in (
        "Final Answer:",
        "The best answer is",
        "The correct answer is",
        "The answer is",
        "The answer",
        "The best option is",
        "The correct option is",
        "Best answer:",
        "Best option:",
        "Answer:",
        "Option:",
    ):
        text = text.replace(prefix, "")
    if len(text.split()) > 10 and not re.search("[A-H]", text):
        return ""
    match = re.search("[A-H]", text.strip().upper())
    return match.group(0) if match else ""


def relevance_rating(scores: list[bool]) -> float:
    """Official nonlinear consistency score for a four-question group."""
    if len(scores) != 4:
        raise ValueError("Video-MME-v2 groups must contain exactly four questions")
    count = sum(scores)
    return {0: 0.0, 1: 100.0 / 16, 2: 25.0, 3: 56.25, 4: 100.0}[count]


def logic_rating(scores: list[bool], group_structure: str | list[Any]) -> float:
    """Official nonlinear coherence score for a four-question group."""
    if len(scores) != 4:
        raise ValueError("Video-MME-v2 groups must contain exactly four questions")
    structure = (
        ast.literal_eval(group_structure) if isinstance(group_structure, str) else group_structure
    )
    last_correct = -1
    for index, correct in enumerate(scores):
        if not correct:
            break
        last_correct = index
    if structure == [1, 2, 3, 4]:
        score_map = {0: 0.0, 1: 100.0 / 16, 2: 25.0, 3: 56.25, 4: 100.0}
    elif structure == [1, [2, 3], 4]:
        score_map = {0: 0.0, 1: 100.0 / 12, 2: 100.0 / 3, 3: 700.0 / 12, 4: 100.0}
        if last_correct == 0 and scores[2]:
            last_correct += 1
    elif structure == [[1, 2], 3, 4]:
        score_map = {0: 0.0, 1: 10.0, 2: 20.0, 3: 50.0, 4: 100.0}
        if last_correct == -1 and scores[1]:
            last_correct += 1
    else:
        raise ValueError(f"Unknown Video-MME-v2 group structure: {structure!r}")
    return score_map[last_correct + 1]


@metric
def grouped_rating() -> Metric:
    """Average official nonlinear group rating on a 0-100 scale."""

    def calculate(scores: list[SampleScore]) -> float:
        groups: dict[str, list[SampleScore]] = {}
        for sample_score in scores:
            metadata = sample_score.sample_metadata or {}
            groups.setdefault(str(metadata.get("group_id", "")), []).append(sample_score)
        ratings = []
        for group in groups.values():
            group.sort(key=lambda item: int((item.sample_metadata or {})["group_position"]))
            correctness = [item.score.as_float() == 1.0 for item in group]
            metadata = group[0].sample_metadata or {}
            if metadata["group_type"] == "relevance":
                ratings.append(relevance_rating(correctness))
            else:
                ratings.append(logic_rating(correctness, metadata["group_structure"]))
        return sum(ratings) / len(ratings) if ratings else 0.0

    return calculate


@scorer(metrics=[accuracy(), grouped_rating()])
def videomme_scorer() -> Scorer:
    """Raw question accuracy plus official grouped nonlinear rating."""

    async def score(state: TaskState, target: Target) -> Score:
        predicted = _extract_answer(state.output.completion)
        expected = target.text.strip().upper()
        return Score(
            value=1.0 if predicted == expected else 0.0,
            answer=predicted,
            explanation=f"Predicted {predicted or '<unparsed>'}; expected {expected}",
        )

    return score


def _probe_video(path: Path) -> tuple[float, float, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=avg_frame_rate,nb_frames,nb_read_frames:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr[-1000:]}")
    payload = json.loads(result.stdout)
    numerator, denominator = payload["streams"][0]["avg_frame_rate"].split("/")
    stream = payload["streams"][0]
    duration = float(payload["format"]["duration"])
    source_fps = float(numerator) / float(denominator)
    raw_count = stream.get("nb_read_frames") or stream.get("nb_frames")
    frame_count = int(raw_count) if raw_count not in {None, "N/A"} else round(duration * source_fps)
    return duration, source_fps, frame_count


def _extract_frames(
    video_path: Path,
    cache_dir: Path,
    *,
    frame_mode: Literal["64frame", "1fps"],
) -> tuple[list[Path], list[float], float]:
    duration, source_fps, source_frames = _probe_video(video_path)
    if frame_mode == "64frame":
        count = 64
        step_size = source_frames / (count + 1)
        indices = [int(index * step_size) for index in range(1, count + 1)]
    else:
        count = int((source_frames / source_fps) * 1.0)
        indices = [int(index * source_fps) for index in range(count)]
    timestamps = [index / source_fps for index in indices]
    destination = cache_dir / video_path.stem / frame_mode
    destination.mkdir(parents=True, exist_ok=True)
    paths = [destination / f"frame_{index:04d}.jpg" for index in range(1, count + 1)]
    if not all(path.exists() for path in paths):
        selection = "+".join(f"eq(n\\,{index})" for index in indices)
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"select={selection}",
                "-vsync",
                "0",
                "-frames:v",
                str(count),
                "-q:v",
                "2",
                str(destination / "frame_%04d.jpg"),
                "-y",
            ],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed for {video_path}: {result.stderr[-1000:]}")
    if not all(path.exists() for path in paths):
        raise RuntimeError(
            f"Video-MME-v2 frame extraction produced fewer than {count} frames for {video_path}"
        )
    return paths, timestamps, duration


def _load_subtitles(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Video-MME-v2 subtitle file not found: {path}")
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _subtitle_segments(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return []
    segments = []
    current = [entries[0]]
    for previous, item in zip(entries, entries[1:]):
        gap = float(item["start_time"]) - float(previous["end_time"])
        if gap > 0.5 or (str(previous["text"]).rstrip().endswith((".", "!", "?")) and gap > 0.1):
            segments.append(
                {
                    "text": " ".join(str(word["text"]) for word in current),
                    "start_time": current[0]["start_time"],
                    "end_time": current[-1]["end_time"],
                }
            )
            current = [item]
        else:
            current.append(item)
    segments.append(
        {
            "text": " ".join(str(word["text"]) for word in current),
            "start_time": current[0]["start_time"],
            "end_time": current[-1]["end_time"],
        }
    )
    return segments


def record_to_sample(
    record: dict[str, Any],
    *,
    frame_paths: list[str | Path] | None = None,
    frame_timestamps: list[float] | None = None,
    video_duration: float | None = None,
    subtitles: list[dict[str, Any]] | None = None,
    subtitle_mode: Literal["none", "concat", "interleave"] = "none",
    frame_mode: Literal["64frame", "1fps"] = "64frame",
    reasoning: bool = False,
) -> Sample:
    """Build an official Video-MME-v2 prompt with actual ordered frames."""
    frame_paths = frame_paths or record.get("frames", [])
    content: list[Any] = []
    if subtitle_mode == "interleave":
        if not subtitles or not frame_timestamps or video_duration is None:
            raise ValueError("Interleaved Video-MME-v2 requires frames, timestamps, and subtitles")
        segments = _subtitle_segments(subtitles)
        for index, (frame, start) in enumerate(zip(frame_paths, frame_timestamps)):
            end = (
                frame_timestamps[index + 1] if index + 1 < len(frame_timestamps) else video_duration
            )
            content.append(ContentImage(image=str(frame)))
            content.extend(
                ContentText(
                    text=(
                        f"[Subtitle {segment['start_time']:.2f}s - "
                        f"{segment['end_time']:.2f}s]: {segment['text']}"
                    )
                )
                for segment in segments
                if float(segment["end_time"]) >= start and float(segment["start_time"]) < end
            )
        media_prompt = (
            "These are the frames of a video with corresponding subtitles shown between frames."
        )
    else:
        content.extend(ContentImage(image=str(frame)) for frame in frame_paths)
        if subtitle_mode == "concat":
            if subtitles is None:
                raise ValueError("Concatenated Video-MME-v2 requires subtitles")
            subtitle_text = " ".join(str(entry["text"]) for entry in subtitles)
            media_prompt = (
                "These are the frames of a video. This video's subtitles are "
                f"listed below:\n{subtitle_text}"
            )
        else:
            media_prompt = "These are the frames of a video."
    content.append(ContentText(text=media_prompt))
    response_prompt = (
        "Perform detailed reasoning and provide the final response strictly as "
        "'Final Answer: <letter>'."
        if reasoning
        else "Respond with only the letter (A, B, C, D, E, F, G, or H)."
    )
    content.append(
        ContentText(text=f"Question: {record['question']}\n{record['options']}\n{response_prompt}")
    )
    video_id = str(record["video_id"])
    question_id = str(record.get("question_id", record.get("id", "")))
    return Sample(
        input=[ChatMessageUser(content=content)],
        target=str(record["answer"]).strip().upper(),
        id=question_id,
        metadata={
            "video_id": video_id,
            "group_id": video_id,
            "group_position": int(question_id.rsplit("-", 1)[-1]),
            "group_type": record["group_type"],
            "group_structure": record["group_structure"],
            "level": int(record["level"]),
            "second_head": record["second_head"],
            "third_head": record["third_head"],
            "frame_mode": frame_mode,
            "frame_count": len(frame_paths),
            "subtitle_mode": subtitle_mode,
            "reasoning": reasoning,
            "dataset_revision": VIDEOMME_DATASET_REVISION,
            "evaluator_revision": VIDEOMME_EVALUATOR_REVISION,
        },
    )


def load_videomme(
    tier: str = "smoke",
    *,
    frame_mode: Literal["64frame", "1fps"] = "64frame",
    subtitle_mode: Literal["none", "concat", "interleave"] = "none",
    reasoning: bool = False,
) -> list[Sample]:
    """Load complete four-question groups and materialize their official media input."""
    root_value = get_dataset_path("videomme")
    if not root_value:
        raise FileNotFoundError(
            "Video-MME-v2 media is not auto-downloaded because its terms prohibit redistribution. "
            "Set MATRIC_EVAL_VIDEOMME_DATA_PATH to an accepted local snapshot."
        )
    root = Path(root_value)
    parquet = root / "test.parquet"
    if not parquet.exists():
        raise FileNotFoundError(f"Video-MME-v2 test.parquet not found: {parquet}")
    from datasets import load_dataset

    records = list(load_dataset("parquet", data_files=str(parquet), split="train"))
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record["video_id"]), []).append(record)
    if any(len(group) != 4 for group in groups.values()):
        raise ValueError("Video-MME-v2 snapshot contains incomplete four-question groups")
    sample_count = get_sample_count("videomme", tier)
    group_count = (
        len(groups) if sample_count <= 0 else min(len(groups), math.ceil(sample_count / 4))
    )
    selected_ids = sorted(groups)
    if group_count < len(selected_ids):
        import random

        selected_ids = sorted(random.Random(get_seed()).sample(selected_ids, group_count))

    samples = []
    cache_dir = root / ".frame_cache"
    for video_id in selected_ids:
        video_path = root / "videos" / f"{video_id}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"Video-MME-v2 video not found: {video_path}")
        frames, timestamps, duration = _extract_frames(video_path, cache_dir, frame_mode=frame_mode)
        subtitles = (
            _load_subtitles(root / "subtitles" / f"{video_id}.jsonl")
            if subtitle_mode != "none"
            else None
        )
        for record in sorted(groups[video_id], key=lambda row: row["question_id"]):
            samples.append(
                record_to_sample(
                    record,
                    frame_paths=frames,
                    frame_timestamps=timestamps,
                    video_duration=duration,
                    subtitles=subtitles,
                    subtitle_mode=subtitle_mode,
                    frame_mode=frame_mode,
                    reasoning=reasoning,
                )
            )
    return samples


@register_benchmark(
    name="videomme",
    description="Video-MME-v2 - 800 videos / 3,200 questions with grouped nonlinear scoring",
    category="multimodal",
    tier_samples={"smoke": 12, "quick": 120, "full": 3200},
    total_samples=3200,
    requires_vision=True,
    scoring_type="official_grouped_rating",
    provider_requirements=("ffmpeg", "64_images_per_request"),
    status="gated",
    status_reason=ACADEMIC_USE_NOTICE,
    protocol_version="v2",
    dataset_source=VIDEOMME_DATASET,
    dataset_revision=VIDEOMME_DATASET_REVISION,
    dataset_configs=("default",),
    dataset_splits=("test",),
    license="MIT metadata; academic-use media terms",
    access="gated",
    source_kind="huggingface",
    release_policy="immutable",
    evaluator_source="MME-Benchmarks/Video-MME-v2",
    evaluator_revision=VIDEOMME_EVALUATOR_REVISION,
)
@task
def videomme(
    tier: str = "smoke",
    frame_mode: Literal["64frame", "1fps"] = "64frame",
    subtitle_mode: Literal["none", "concat", "interleave"] = "none",
    reasoning: bool = False,
) -> Task:
    """Run one explicitly named official Video-MME-v2 configuration."""
    config_name = f"{frame_mode}_{subtitle_mode}" + ("_reasoning" if reasoning else "")
    return Task(
        dataset=load_videomme(
            tier,
            frame_mode=frame_mode,
            subtitle_mode=subtitle_mode,
            reasoning=reasoning,
        ),
        solver=[system_message("Analyze the complete ordered video input."), generate()],
        scorer=videomme_scorer(),
        config=GenerateConfig(temperature=0),
        name=f"videomme_v2_{config_name}",
        metadata={
            "protocol_version": "v2",
            "configuration": config_name,
            "dataset_revision": VIDEOMME_DATASET_REVISION,
            "evaluator_revision": VIDEOMME_EVALUATOR_REVISION,
            "license_notice": ACADEMIC_USE_NOTICE,
        },
    )
