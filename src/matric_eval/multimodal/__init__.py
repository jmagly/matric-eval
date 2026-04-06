"""
matric_eval.multimodal — multimodal input pipeline.

Provides image loading, video frame extraction, subtitle parsing,
content assembly, and vision capability detection for multimodal
benchmark evaluation (MMMU, RealWorldQA, OmniDocBench, Video-MME).

Public API::

    from matric_eval.multimodal import (
        ModalInput,
        FrameBudget,
        FrameExtractor,
        build_multimodal_content,
        parse_srt,
        parse_vtt,
        supports_vision,
    )
"""

from matric_eval.multimodal.capability import supports_vision
from matric_eval.multimodal.content import build_multimodal_content
from matric_eval.multimodal.frames import FrameBudget, FrameExtractor
from matric_eval.multimodal.inputs import ModalInput
from matric_eval.multimodal.subtitles import SubtitleEntry, parse_srt, parse_vtt

__all__ = [
    "ModalInput",
    "FrameBudget",
    "FrameExtractor",
    "SubtitleEntry",
    "build_multimodal_content",
    "parse_srt",
    "parse_vtt",
    "supports_vision",
]
