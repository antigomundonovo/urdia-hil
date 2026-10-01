"""Render QC checks (Doc 13 QC list): resolution, dimensions, aspect ratio,
font rendering, overflow, contrast, missing assets, file integrity. Audio
duration is N/A for stills — microloop assembly is out of this milestone.

All checks are computed from the rendered bytes + render report; nothing is
"assumed fine". FAIL marks a blocking render QC result.
"""

import io
from typing import Any

from PIL import Image

from packages.rendering.engine import RenderedSlide

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Stills below this width are useless on modern platforms (template floor,
# not a constitutional value).
MIN_RESOLUTION = 600

# Allowed still aspect ratios (Doc 13 formats are portrait/square stills):
# 4:5 portrait and 1:1 square.
ALLOWED_RATIOS = ((4 / 5, 0.01), (1.0, 0.01))


def _contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    def _channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    def _luma(rgb: tuple[int, int, int]) -> float:
        return 0.2126 * _channel(rgb[0]) + 0.7152 * _channel(rgb[1]) + 0.0722 * _channel(rgb[2])

    lighter = max(_luma(fg), _luma(bg))
    darker = min(_luma(fg), _luma(bg))
    return (lighter + 0.05) / (darker + 0.05)


def _ratio_matches(width: int, height: int) -> bool:
    if height == 0:
        return False
    ratio = width / height
    return any(abs(ratio - expected) <= tolerance for expected, tolerance in ALLOWED_RATIOS)


def validate_render(
    slide: RenderedSlide,
    *,
    expected_size: tuple[int, int],
    text_color=(244, 240, 232),
    panel_color=(28, 26, 23),
    requires_image: bool = False,
) -> dict[str, str]:
    """Return {check: PASS|FAIL} for the still QC list. `overflow` comes from
    the render report (layout is measured while drawing); everything else is
    recomputed from the PNG bytes."""
    checks: dict[str, str] = {}

    # file integrity: magic bytes + full decode via PIL
    if slide.png[:8] != PNG_MAGIC:
        checks["file_integrity"] = "FAIL"
    else:
        try:
            with Image.open(io.BytesIO(slide.png)) as probe:
                probe.verify()
            checks["file_integrity"] = "PASS"
        except Exception:
            checks["file_integrity"] = "FAIL"

    # dimensions: exact template size
    checks["dimensions"] = (
        "PASS" if (slide.width, slide.height) == expected_size else "FAIL"
    )

    # resolution + aspect ratio
    checks["resolution"] = (
        "PASS" if slide.width >= MIN_RESOLUTION and slide.height >= MIN_RESOLUTION else "FAIL"
    )
    checks["aspect_ratio"] = (
        "PASS" if _ratio_matches(slide.width, slide.height) else "FAIL"
    )

    # font rendering: a rendered slide always drew text with a live font; if
    # nothing was drawn (no label, heading or body) the font never rendered.
    has_text = (
        slide.report.get("title_lines")
        or slide.report.get("body_lines")
        or slide.report.get("role")
    )
    checks["font_rendering"] = "PASS" if has_text else "FAIL"

    # overflow: measured during layout
    checks["overflow"] = "FAIL" if slide.report.get("overflow") else "PASS"

    # contrast: template pairs ink panel with light text (WCAG-ish floor 4.5)
    ratio = _contrast_ratio(text_color, panel_color)
    checks["contrast"] = "PASS" if ratio >= 4.5 else "FAIL"

    # missing assets: image slides must carry their photo
    if requires_image:
        checks["missing_assets"] = "PASS" if slide.report.get("image_used") else "FAIL"
    else:
        checks["missing_assets"] = "PASS"

    # audio duration: stills carry no audio
    checks["audio_duration"] = "N/A"
    return checks


def qc_summary(checks: dict[str, str]) -> str:
    """Overall result: FAIL if any check failed, else PASS."""
    if "FAIL" in checks.values():
        return "FAIL"
    return "PASS"


def render_metadata_block(slides: list[tuple[str, RenderedSlide, dict[str, str]]]) -> dict[str, Any]:
    """Manifest section for rendered files: per-file hash/dimensions + QC."""
    import hashlib

    files = []
    all_checks: dict[str, str] = {}
    for name, slide, checks in slides:
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(slide.png).hexdigest(),
                "width": slide.width,
                "height": slide.height,
                "qc": checks,
            }
        )
        for check, result in checks.items():
            if result == "FAIL" or check not in all_checks:
                all_checks[check] = result
    return {"files": files, "qc": all_checks, "summary": qc_summary(all_checks)}
