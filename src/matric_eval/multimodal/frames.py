"""
Frame extraction for video inputs in multimodal evaluation.

FrameBudget  — computes how many frames to extract given video duration.
FrameExtractor — calls ffmpeg via subprocess to extract frames as images.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matric_eval.multimodal.inputs import ModalInput


@dataclass
class FrameBudget:
    """
    Determines the target frame count for a video of a given duration.

    Duration tiers:
        short  : < 60s   → short_fps
        medium : 60–300s → medium_fps
        long   : > 300s  → long_fps

    The raw frame count is always capped at max_frames.
    """

    short_fps: float = 1.0
    """Frames per second for videos shorter than 60 seconds."""

    medium_fps: float = 0.5
    """Frames per second for videos 60–300 seconds."""

    long_fps: float = 0.25
    """Frames per second for videos longer than 300 seconds."""

    max_frames: int = 64
    """Hard upper bound on the number of frames returned."""

    def calculate(self, duration_seconds: float) -> int:
        """
        Compute target frame count for a video of the given duration.

        Args:
            duration_seconds: Total video duration in seconds.

        Returns:
            Number of frames to extract (capped at max_frames).
        """
        if duration_seconds <= 0:
            return 0

        if duration_seconds < 60:
            fps = self.short_fps
        elif duration_seconds <= 300:
            fps = self.medium_fps
        else:
            fps = self.long_fps

        raw = int(duration_seconds * fps)
        return min(raw, self.max_frames)


class FrameExtractor:
    """
    Extracts video frames using the system ffmpeg binary (via subprocess).

    Does NOT use the ffmpeg-python library — only the CLI binary.

    Usage::

        extractor = FrameExtractor()
        budget = FrameBudget()
        frames = extractor.extract_frames("/path/to/video.mp4", budget)
        # frames is a list[ModalInput]
    """

    def extract_frames(
        self,
        video_path: str,
        budget: FrameBudget,
    ) -> list["ModalInput"]:
        """
        Extract frames from a video file.

        The frame count is determined by first probing the video duration
        with ffprobe, then using FrameBudget.calculate() to set the
        target frame count. Frames are written to a temporary directory
        and returned as ModalInput objects.

        Args:
            video_path: Path to the video file.
            budget:     FrameBudget that controls frame sampling.

        Returns:
            List of ModalInput objects (one per extracted frame),
            ordered by timestamp. Returns an empty list if ffmpeg is
            not available.

        Raises:
            RuntimeError: If ffmpeg exits with a non-zero return code.
        """
        from matric_eval.multimodal.inputs import ModalInput

        duration = self._probe_duration(video_path)
        n_frames = budget.calculate(duration)

        if n_frames == 0:
            return []

        with tempfile.TemporaryDirectory(prefix="matric_frames_") as tmp_dir:
            out_pattern = os.path.join(tmp_dir, "frame_%06d.png")
            # Use the fps filter to sample n_frames evenly across the video.
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vf",
                f"fps={n_frames / max(duration, 1):.6f}",
                "-frames:v",
                str(n_frames),
                "-q:v",
                "2",
                out_pattern,
                "-y",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=300,
                )
            except FileNotFoundError:
                # ffmpeg binary not installed
                return []

            if result.returncode != 0:
                stderr = result.stderr
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {stderr}")

            # Collect extracted frames in sorted order
            frame_files = sorted(Path(tmp_dir).glob("frame_*.png"))
            frames: list[ModalInput] = []
            for frame_file in frame_files:
                data = frame_file.read_bytes()
                try:
                    mi = ModalInput.from_bytes(data, format="png")
                    frames.append(mi)
                except (ValueError, Exception):
                    # Skip corrupt frames
                    continue

            return frames

    def _probe_duration(self, video_path: str) -> float:
        """
        Use ffprobe to get video duration in seconds.

        Falls back to 0.0 if ffprobe is unavailable or fails.
        """
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0
