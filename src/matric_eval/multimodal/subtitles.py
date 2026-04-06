"""
Subtitle parsing for multimodal video evaluation.

Supports SRT (SubRip Text) and WebVTT formats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SubtitleEntry:
    """A single subtitle cue with timing and text."""

    start_ms: int
    """Start time in milliseconds."""

    end_ms: int
    """End time in milliseconds."""

    text: str
    """Subtitle text (HTML tags stripped)."""


# ---------------------------------------------------------------------------
# SRT parser
# ---------------------------------------------------------------------------

# SRT timestamp pattern: 00:00:01,000
_SRT_TS = r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
_SRT_ARROW = r"\s*-->\s*"
_SRT_LINE_RE = re.compile(
    rf"^{_SRT_TS}{_SRT_ARROW}{_SRT_TS}\s*$",
    re.MULTILINE,
)


def _srt_ts_to_ms(h: str, m: str, s: str, ms: str) -> int:
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def parse_srt(content: str) -> list[SubtitleEntry]:
    """
    Parse an SRT subtitle string into a list of SubtitleEntry objects.

    Invalid or unparseable blocks are silently skipped.

    Args:
        content: Full SRT file contents as a string.

    Returns:
        Ordered list of SubtitleEntry objects.
    """
    if not content.strip():
        return []

    entries: list[SubtitleEntry] = []

    # Split on blank lines to get blocks
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue

        # Find the timestamp line (skip sequence number line)
        ts_line_idx = None
        for i, line in enumerate(lines):
            if _SRT_LINE_RE.match(line):
                ts_line_idx = i
                break

        if ts_line_idx is None:
            continue

        ts_line = lines[ts_line_idx]
        m = _SRT_LINE_RE.match(ts_line)
        if not m:
            continue

        start_ms = _srt_ts_to_ms(*m.group(1, 2, 3, 4))
        end_ms = _srt_ts_to_ms(*m.group(5, 6, 7, 8))

        # Text is everything after the timestamp line
        text_lines = [l for l in lines[ts_line_idx + 1:] if l.strip()]
        if not text_lines:
            continue

        text = _strip_html(" ".join(text_lines))
        entries.append(SubtitleEntry(start_ms=start_ms, end_ms=end_ms, text=text))

    return entries


# ---------------------------------------------------------------------------
# VTT parser
# ---------------------------------------------------------------------------

# WebVTT timestamp: 00:00:01.000 or 00:01.000
_VTT_TS = r"(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})"
_VTT_LINE_RE = re.compile(
    rf"^{_VTT_TS}\s*-->\s*{_VTT_TS}",
    re.MULTILINE,
)


def _vtt_ts_to_ms(h: str | None, m: str, s: str, ms: str) -> int:
    hours = int(h) if h is not None else 0
    return hours * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def parse_vtt(content: str) -> list[SubtitleEntry]:
    """
    Parse a WebVTT subtitle string into a list of SubtitleEntry objects.

    Ignores the WEBVTT header, NOTE blocks, and STYLE blocks.
    Invalid or unparseable cues are silently skipped.

    Args:
        content: Full WebVTT file contents as a string.

    Returns:
        Ordered list of SubtitleEntry objects.
    """
    if not content.strip():
        return []

    # Strip the WEBVTT header block (everything before the first blank line)
    # then process cues
    entries: list[SubtitleEntry] = []

    # Split into blocks separated by blank lines
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # Skip WEBVTT header line, NOTE blocks, STYLE blocks
        first = lines[0].strip()
        if first.startswith("WEBVTT") or first.startswith("NOTE") or first.startswith("STYLE"):
            continue

        # Find timestamp line
        ts_line_idx = None
        for i, line in enumerate(lines):
            if _VTT_LINE_RE.match(line):
                ts_line_idx = i
                break

        if ts_line_idx is None:
            continue

        ts_line = lines[ts_line_idx]

        # Full match to extract both timestamps
        full_re = re.compile(
            rf"^{_VTT_TS}\s*-->\s*{_VTT_TS}",
        )
        m = full_re.match(ts_line)
        if not m:
            continue

        start_ms = _vtt_ts_to_ms(m.group(1), m.group(2), m.group(3), m.group(4))
        end_ms = _vtt_ts_to_ms(m.group(5), m.group(6), m.group(7), m.group(8))

        text_lines = [l for l in lines[ts_line_idx + 1:] if l.strip()]
        if not text_lines:
            continue

        text = _strip_html(" ".join(text_lines))
        entries.append(SubtitleEntry(start_ms=start_ms, end_ms=end_ms, text=text))

    return entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from subtitle text."""
    return _HTML_TAG_RE.sub("", text).strip()
