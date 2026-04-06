"""
Builds Inspect AI message content lists for multimodal evaluation tasks.

build_multimodal_content() assembles a list of ContentText and ContentImage
objects that can be passed to Inspect AI's ChatMessageUser.content field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matric_eval.multimodal.inputs import ModalInput
    from matric_eval.multimodal.subtitles import SubtitleEntry


def build_multimodal_content(
    text: str,
    images: list["ModalInput"] | None = None,
    subtitles: list["SubtitleEntry"] | None = None,
) -> list:
    """
    Build an Inspect AI content list combining text, images, and subtitles.

    The content list is ordered as:
        1. One ContentText with the main prompt text
        2. ContentImage objects (one per image, in order)
        3. If subtitles are provided, one additional ContentText block
           with the subtitle context appended.

    Args:
        text:      Main text prompt.
        images:    Optional list of ModalInput images to include.
        subtitles: Optional list of SubtitleEntry objects to include as
                   a subtitle context block.

    Returns:
        List of ContentText and ContentImage objects suitable for use as
        the content field of an Inspect AI ChatMessageUser.
    """
    from inspect_ai.model import ContentImage, ContentText

    content = []

    # 1. Main text prompt
    content.append(ContentText(text=text))

    # 2. Images
    if images:
        for image in images:
            content.append(image.to_content_image())

    # 3. Subtitle context (appended as a separate text block)
    if subtitles:
        subtitle_lines = [
            f"[{_ms_to_timecode(s.start_ms)} --> {_ms_to_timecode(s.end_ms)}] {s.text}"
            for s in subtitles
        ]
        subtitle_block = "Subtitles:\n" + "\n".join(subtitle_lines)
        content.append(ContentText(text=subtitle_block))

    return content


def _ms_to_timecode(ms: int) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    h = ms // 3_600_000
    ms -= h * 3_600_000
    m = ms // 60_000
    ms -= m * 60_000
    s = ms // 1_000
    ms -= s * 1_000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
