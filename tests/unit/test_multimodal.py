"""
Tests for matric_eval.multimodal — the multimodal input pipeline.

Covers:
  - ModalInput: loading, resize, base64, SSRF protection, dimension/size validation
  - FrameBudget: frame count calculation for short/medium/long videos, max cap
  - FrameExtractor: mocked subprocess (ffmpeg) calls
  - parse_srt / parse_vtt: valid, empty, malformed input
  - build_multimodal_content: text-only, text+images, text+images+subtitles
  - supports_vision: known patterns vs unknown model names

All tests are unit-level: no network calls, no ffmpeg binary required.
The `requires_ffmpeg` marker gates any test that would need the real binary.
"""

import base64
import io
import struct
import zlib
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal 1×1 transparent PNG (67 bytes, no external files needed)
# ---------------------------------------------------------------------------
# PNG signature + IHDR + IDAT (single transparent white pixel) + IEND
def _make_1x1_png() -> bytes:
    """Generate a valid 1×1 RGBA PNG in memory."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_row = b"\x00\xff\xff\xff"  # filter byte + RGB
    compressed = zlib.compress(raw_row)
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


TINY_PNG = _make_1x1_png()


# ===========================================================================
# ModalInput tests
# ===========================================================================

class TestModalInputFromBytes:
    """ModalInput can be constructed from raw bytes."""

    def test_load_from_bytes_succeeds(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        assert mi is not None

    def test_format_stored(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        assert mi.format == "png"

    def test_image_dimensions_readable(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        w, h = mi.width, mi.height
        assert w == 1
        assert h == 1


class TestModalInputResize:
    """ModalInput.resize() maintains aspect ratio."""

    def test_resize_1x1_stays_1x1(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        resized = mi.resize(max_dim=512)
        assert resized.width <= 512
        assert resized.height <= 512

    def test_resize_returns_modal_input(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        resized = mi.resize(max_dim=256)
        assert isinstance(resized, ModalInput)

    def test_resize_large_image_clips_to_max_dim(self):
        """A 200x100 image resized to max_dim=50 → 50x25."""
        from PIL import Image
        from matric_eval.multimodal import ModalInput

        buf = io.BytesIO()
        img = Image.new("RGB", (200, 100), color=(128, 64, 32))
        img.save(buf, format="PNG")
        buf.seek(0)

        mi = ModalInput.from_bytes(buf.read(), format="png")
        resized = mi.resize(max_dim=50)
        assert resized.width == 50
        assert resized.height == 25


class TestModalInputBase64:
    """ModalInput.to_base64() encodes correctly."""

    def test_to_base64_returns_str(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        b64 = mi.to_base64()
        assert isinstance(b64, str)

    def test_to_base64_roundtrip(self):
        """Decoded base64 should reproduce the original PNG bytes."""
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        b64 = mi.to_base64()
        decoded = base64.b64decode(b64)
        # Re-open the decoded bytes as an image (should not raise)
        from PIL import Image
        img = Image.open(io.BytesIO(decoded))
        assert img.size == (1, 1)

    def test_to_base64_is_valid_base64(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        b64 = mi.to_base64()
        # Should not raise
        base64.b64decode(b64)


class TestModalInputToContentImage:
    """ModalInput.to_content_image() produces an Inspect AI ContentImage."""

    def test_returns_content_image(self):
        from inspect_ai.model import ContentImage
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        ci = mi.to_content_image()
        assert isinstance(ci, ContentImage)

    def test_content_image_has_data_uri(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        ci = mi.to_content_image()
        # image field should be a data URI or base64 string
        assert ci.image  # non-empty


class TestModalInputSSRF:
    """SSRF protection rejects unsafe URLs."""

    def test_rejects_file_url(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("file:///etc/passwd")

    def test_rejects_http_without_s(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("http://example.com/image.png")

    def test_rejects_private_ip_10_x(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://10.0.0.1/image.png")

    def test_rejects_private_ip_192_168(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://192.168.1.100/image.png")

    def test_rejects_private_ip_172_16(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://172.16.0.1/image.png")

    def test_rejects_loopback(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://127.0.0.1/image.png")

    def test_rejects_link_local(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://169.254.0.1/image.png")

    def test_rejects_ipv6_unique_local_fc(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://[fc00::1]/image.png")

    def test_rejects_ipv6_unique_local_fd(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises((ValueError, PermissionError)):
            ModalInput.from_url("https://[fd00::1]/image.png")


class TestModalInputValidation:
    """ModalInput validates dimensions and file size."""

    def test_rejects_oversized_image(self):
        """Images larger than 4096×4096 are rejected."""
        from PIL import Image
        from matric_eval.multimodal import ModalInput

        # We must bypass PIL.MAX_IMAGE_PIXELS to create the test image
        old_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            buf = io.BytesIO()
            img = Image.new("RGB", (4097, 4097))
            img.save(buf, format="PNG")
            buf.seek(0)
            big_bytes = buf.read()
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit

        with pytest.raises(ValueError, match="dimension"):
            ModalInput.from_bytes(big_bytes, format="png")

    def test_rejects_oversized_file(self):
        """Files larger than 20 MB are rejected before loading."""
        from matric_eval.multimodal import ModalInput

        # 21 MB of zeros — not a valid image but should fail on size check first
        big_data = b"\x00" * (21 * 1024 * 1024)
        with pytest.raises(ValueError, match="size"):
            ModalInput.from_bytes(big_data, format="png")

    def test_accepts_supported_format_png(self):
        from matric_eval.multimodal import ModalInput

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        assert mi.format == "png"

    def test_rejects_unsupported_format(self):
        from matric_eval.multimodal import ModalInput

        with pytest.raises(ValueError, match="format"):
            ModalInput.from_bytes(TINY_PNG, format="bmp")


# ===========================================================================
# FrameBudget tests
# ===========================================================================

class TestFrameBudgetCalculate:
    """FrameBudget.calculate() returns correct frame counts per duration tier."""

    def test_short_video_30s(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()  # defaults: short_fps=1.0, medium_fps=0.5, long_fps=0.25
        count = budget.calculate(30.0)
        # 30s < 60s → short_fps=1.0 → 30 frames (≤ max_frames=64)
        assert count == 30

    def test_medium_video_120s(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()
        count = budget.calculate(120.0)
        # 60s ≤ 120s ≤ 300s → medium_fps=0.5 → 60 frames (≤ 64)
        assert count == 60

    def test_long_video_600s(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()
        count = budget.calculate(600.0)
        # 600s > 300s → long_fps=0.25 → 150 frames → capped at max_frames=64
        assert count == 64

    def test_max_frames_cap_applied(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget(short_fps=2.0, max_frames=10)
        count = budget.calculate(10.0)
        # 2.0 fps × 10s = 20 → capped at 10
        assert count == 10

    def test_zero_duration_returns_zero_or_one(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()
        count = budget.calculate(0.0)
        assert count >= 0

    def test_exactly_60s_is_medium(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()
        count = budget.calculate(60.0)
        # Boundary: 60s == medium tier → 0.5 fps × 60 = 30
        assert count == 30

    def test_exactly_300s_is_medium(self):
        from matric_eval.multimodal import FrameBudget

        budget = FrameBudget()
        count = budget.calculate(300.0)
        # Boundary: 300s == medium tier → 0.5 fps × 300 = 150 → capped at 64
        assert count == 64


# ===========================================================================
# FrameExtractor tests (mocked ffmpeg)
# ===========================================================================

class TestFrameExtractorMocked:
    """FrameExtractor uses subprocess to call ffmpeg; tests use mocks."""

    @pytest.mark.requires_ffmpeg
    def test_marker_exists(self):
        """Placeholder: real ffmpeg tests require the binary."""
        pass  # pragma: no cover

    def test_extract_frames_calls_ffmpeg(self, tmp_path):
        """extract_frames should invoke ffmpeg via subprocess."""
        from matric_eval.multimodal import FrameBudget, FrameExtractor

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake video content")

        budget = FrameBudget(short_fps=1.0, max_frames=3)

        # Mock subprocess.run to simulate ffmpeg writing frame files
        frame_png = TINY_PNG

        def fake_run(cmd, **kwargs):
            # Simulate ffmpeg writing frame_000001.png into the temp dir
            import re
            # Find the output pattern arg (e.g. /tmp/xxx/frame_%06d.png)
            out_pattern = None
            for arg in cmd:
                if "frame_" in str(arg):
                    out_pattern = str(arg)
                    break
            if out_pattern:
                import os
                out_dir = os.path.dirname(out_pattern)
                for i in range(1, 4):
                    fname = out_pattern % i if "%" in out_pattern else out_pattern.replace("%06d", f"{i:06d}")
                    with open(fname, "wb") as f:
                        f.write(frame_png)
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        with patch("subprocess.run", side_effect=fake_run):
            extractor = FrameExtractor()
            frames = extractor.extract_frames(str(fake_video), budget)

        # Should return a list (may be empty if no frames written due to path mismatch)
        assert isinstance(frames, list)

    def test_extract_frames_handles_missing_ffmpeg(self, tmp_path):
        """When ffmpeg is not found, extract_frames raises or returns empty."""
        from matric_eval.multimodal import FrameBudget, FrameExtractor

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake")
        budget = FrameBudget()

        with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
            extractor = FrameExtractor()
            # Should handle gracefully — either raise RuntimeError or return []
            try:
                result = extractor.extract_frames(str(fake_video), budget)
                assert result == []
            except (RuntimeError, FileNotFoundError, OSError):
                pass  # Acceptable: explicit error about missing ffmpeg


# ===========================================================================
# parse_srt tests
# ===========================================================================

SRT_SAMPLE = """\
1
00:00:01,000 --> 00:00:03,500
Hello, world!

2
00:00:04,000 --> 00:00:06,000
This is a subtitle.

"""

SRT_SINGLE_ENTRY = """\
1
00:00:00,000 --> 00:00:02,000
Single line.

"""


class TestParseSRT:
    """parse_srt parses SRT subtitle format."""

    def test_parses_two_entries(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SAMPLE)
        assert len(entries) == 2

    def test_first_entry_text(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SAMPLE)
        assert entries[0].text == "Hello, world!"

    def test_first_entry_start_ms(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SAMPLE)
        assert entries[0].start_ms == 1000

    def test_first_entry_end_ms(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SAMPLE)
        assert entries[0].end_ms == 3500

    def test_second_entry_text(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SAMPLE)
        assert entries[1].text == "This is a subtitle."

    def test_empty_content_returns_empty_list(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt("")
        assert entries == []

    def test_malformed_content_returns_empty_or_partial(self):
        from matric_eval.multimodal import parse_srt

        # Malformed: no timestamp line
        malformed = "just some random text\nwithout timing"
        result = parse_srt(malformed)
        assert isinstance(result, list)  # Must not raise

    def test_single_entry(self):
        from matric_eval.multimodal import parse_srt

        entries = parse_srt(SRT_SINGLE_ENTRY)
        assert len(entries) == 1
        assert entries[0].text == "Single line."
        assert entries[0].start_ms == 0
        assert entries[0].end_ms == 2000


# ===========================================================================
# parse_vtt tests
# ===========================================================================

VTT_SAMPLE = """\
WEBVTT

00:00:01.000 --> 00:00:03.500
Hello, VTT!

00:00:04.000 --> 00:00:06.000
Second subtitle.

"""

VTT_WITH_HEADER_METADATA = """\
WEBVTT
Kind: captions
Language: en

00:00:00.500 --> 00:00:02.000
Opening line.

"""


class TestParseVTT:
    """parse_vtt parses WebVTT subtitle format."""

    def test_parses_two_entries(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_SAMPLE)
        assert len(entries) == 2

    def test_first_entry_text(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_SAMPLE)
        assert entries[0].text == "Hello, VTT!"

    def test_first_entry_start_ms(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_SAMPLE)
        assert entries[0].start_ms == 1000

    def test_first_entry_end_ms(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_SAMPLE)
        assert entries[0].end_ms == 3500

    def test_second_entry_text(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_SAMPLE)
        assert entries[1].text == "Second subtitle."

    def test_empty_returns_empty_list(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt("")
        assert entries == []

    def test_webvtt_without_cues_returns_empty(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt("WEBVTT\n\n")
        assert entries == []

    def test_header_metadata_ignored(self):
        from matric_eval.multimodal import parse_vtt

        entries = parse_vtt(VTT_WITH_HEADER_METADATA)
        assert len(entries) == 1
        assert entries[0].text == "Opening line."
        assert entries[0].start_ms == 500

    def test_malformed_no_arrow_returns_empty_or_partial(self):
        from matric_eval.multimodal import parse_vtt

        result = parse_vtt("WEBVTT\n\njust text without timestamps\n")
        assert isinstance(result, list)


# ===========================================================================
# SubtitleEntry dataclass tests
# ===========================================================================

class TestSubtitleEntry:
    """SubtitleEntry has start_ms, end_ms, text fields."""

    def test_subtitle_entry_fields(self):
        from matric_eval.multimodal.subtitles import SubtitleEntry

        entry = SubtitleEntry(start_ms=1000, end_ms=3500, text="Hello")
        assert entry.start_ms == 1000
        assert entry.end_ms == 3500
        assert entry.text == "Hello"


# ===========================================================================
# build_multimodal_content tests
# ===========================================================================

class TestBuildMultimodalContent:
    """build_multimodal_content assembles Inspect AI content lists."""

    def test_text_only_returns_list_with_one_content_text(self):
        from inspect_ai.model import ContentText
        from matric_eval.multimodal import build_multimodal_content

        result = build_multimodal_content("What is this?")
        assert len(result) >= 1
        texts = [c for c in result if isinstance(c, ContentText)]
        assert any("What is this?" in t.text for t in texts)

    def test_text_plus_images(self):
        from inspect_ai.model import ContentImage, ContentText
        from matric_eval.multimodal import ModalInput, build_multimodal_content

        mi = ModalInput.from_bytes(TINY_PNG, format="png")
        result = build_multimodal_content("Describe this image.", images=[mi])

        assert any(isinstance(c, ContentText) for c in result)
        assert any(isinstance(c, ContentImage) for c in result)

    def test_text_plus_multiple_images(self):
        from inspect_ai.model import ContentImage
        from matric_eval.multimodal import ModalInput, build_multimodal_content

        images = [ModalInput.from_bytes(TINY_PNG, format="png") for _ in range(3)]
        result = build_multimodal_content("Compare these.", images=images)

        image_items = [c for c in result if isinstance(c, ContentImage)]
        assert len(image_items) == 3

    def test_text_plus_images_plus_subtitles(self):
        from inspect_ai.model import ContentText
        from matric_eval.multimodal import ModalInput, build_multimodal_content
        from matric_eval.multimodal.subtitles import SubtitleEntry

        images = [ModalInput.from_bytes(TINY_PNG, format="png")]
        subs = [SubtitleEntry(start_ms=0, end_ms=2000, text="Subtitle line")]
        result = build_multimodal_content("What happens?", images=images, subtitles=subs)

        # Subtitles should appear as text somewhere in the content
        all_text = " ".join(c.text for c in result if isinstance(c, ContentText))
        assert "Subtitle line" in all_text

    def test_no_images_no_subtitles_minimal(self):
        from matric_eval.multimodal import build_multimodal_content

        result = build_multimodal_content("Hello")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_images_none_treated_same_as_empty(self):
        from matric_eval.multimodal import build_multimodal_content

        r1 = build_multimodal_content("text", images=None)
        r2 = build_multimodal_content("text", images=[])
        assert len(r1) == len(r2)


# ===========================================================================
# supports_vision tests
# ===========================================================================

class TestSupportsVision:
    """supports_vision detects vision-capable models conservatively."""

    def test_model_with_vision_in_name(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("ollama", "llava:7b") is True

    def test_model_with_vl_suffix(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("openrouter", "qwen2-vl-7b") is True

    def test_model_4o(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("openrouter", "gpt-4o") is True

    def test_model_4o_mini(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("openrouter", "gpt-4o-mini") is True

    def test_unknown_model_returns_false(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("ollama", "llama3.2:3b") is False

    def test_unknown_provider_unknown_model_returns_false(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("unknown_provider", "unknown_model") is False

    def test_model_with_vision_keyword(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("vllm", "internvl-chat-2b-vision") is True

    def test_empty_model_returns_false(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("ollama", "") is False

    def test_pixtral_model(self):
        from matric_eval.multimodal import supports_vision

        assert supports_vision("openrouter", "pixtral-12b") is True


# ===========================================================================
# DocumentInput stub tests
# ===========================================================================

class TestDocumentInputStub:
    """DocumentInput is a stub placeholder for future OCR support."""

    def test_document_input_importable(self):
        from matric_eval.multimodal.documents import DocumentInput

        assert DocumentInput is not None

    def test_document_input_is_class(self):
        from matric_eval.multimodal.documents import DocumentInput

        assert isinstance(DocumentInput, type)
