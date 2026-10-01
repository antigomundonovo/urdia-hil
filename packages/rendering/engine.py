"""Deterministic still-image renderer (Doc 13).

Scope of this milestone: PHOTO_POST and CAROUSEL stills. MICROLOOP assembly
(movement/audio, 5-12s) needs an FFmpeg decision and stays out of V1 render —
exports keep their pre-render behaviour.

Determinism (Doc 13): the same inputs produce byte-identical PNGs on the same
Pillow build. Template version, renderer version and font identity are recorded
next to every rendered file. Font: Pillow's bundled scalable default — its
license/redistribution is governed by Pillow's own license (known to the
project, Doc 13 font rule); no system font is loaded.

Security: rendering is pure in-process Pillow — no shell, no external tools,
no network. The Doc 08 structured-arguments rule applies to future external
tools (FFmpeg) and is trivially satisfied here.
"""

import io
from dataclasses import dataclass, field
from typing import Any

import PIL
from PIL import Image, ImageDraw, ImageFont

RENDERER_VERSION = "renderer-1.0"
TEMPLATE_VERSION = "anm-still-1.0"

# Template defaults (recorded in manifests; not constitutional values).
DEFAULT_SIZE = (1080, 1350)  # 4:5 portrait
CANVAS_BG = (244, 240, 232)  # warm paper
PANEL_BG = (28, 26, 23)  # ink panel behind text (image slides)
TEXT_COLOR = (244, 240, 232)
ACCENT_COLOR = (146, 64, 14)
TITLE_SIZE = 72
BODY_SIZE = 40
LABEL_SIZE = 28
MARGIN = 72
LINE_SPACING = 1.25

CAROUSEL_SLIDES: tuple[str, ...] = (
    "HOOK",
    "ORIENTATION",
    "EVIDENCE",
    "CONTEXT",
    "DISCOVERY",
    "MEANING",
    "SOURCE / QUESTION",
)


@dataclass
class SlideSpec:
    """One carousel slide: fixed Doc 13 role + deterministic text content."""

    role: str
    heading: str = ""
    body: str = ""
    image_bytes: bytes | None = None


@dataclass
class RenderedSlide:
    png: bytes
    width: int
    height: int
    report: dict[str, Any] = field(default_factory=dict)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    *,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    max_width: int,
    color=TEXT_COLOR,
    line_gap: int = 8,
) -> int:
    """Draw wrapped lines left-aligned; returns the bottom y (for overflow)."""
    line_height = int(font.size * LINE_SPACING) + line_gap
    cursor = y
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=color)
        cursor += line_height
    return cursor


def _cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale-crop to exactly fill width x height (pure math, deterministic)."""
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    resized = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _new_canvas(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), CANVAS_BG)


def render_photo_post(
    *,
    heading: str,
    body: str = "",
    image_bytes: bytes | None = None,
    size: tuple[int, int] = DEFAULT_SIZE,
) -> RenderedSlide:
    """PHOTO_POST still: strong image, text on a bottom ink panel (Doc 13 ANM
    visual defaults: image-first, little text on the art)."""
    width, height = size
    overflow = False
    if image_bytes:
        base = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        canvas = _cover_crop(base, width, height)
        image_used = True
    else:
        canvas = _new_canvas(width, height)
        image_used = False

    draw = ImageDraw.Draw(canvas, "RGBA")
    title_font = _font(TITLE_SIZE)
    body_font = _font(BODY_SIZE)
    max_width = width - 2 * MARGIN

    title_lines = _wrap(heading, title_font, max_width) if heading else []
    body_lines = _wrap(body, body_font, max_width) if body else []
    title_h = len(title_lines) * int(title_font.size * LINE_SPACING)
    body_h = len(body_lines) * int(body_font.size * LINE_SPACING + 8)
    panel_h = min(height, title_h + body_h + 3 * MARGIN // 2)
    panel_top = height - panel_h

    draw.rectangle((0, panel_top, width, height), fill=(*PANEL_BG, 235))
    draw.rectangle((0, panel_top, width, panel_top + 8), fill=ACCENT_COLOR)

    bottom = _draw_text_block(
        draw,
        lines=title_lines,
        font=title_font,
        x=MARGIN,
        y=panel_top + MARGIN // 2,
        max_width=max_width,
    )
    if body_lines:
        bottom = _draw_text_block(
            draw, lines=body_lines, font=body_font, x=MARGIN, y=bottom + 16, max_width=max_width
        )
    overflow = bottom > height - MARGIN // 4

    png = _encode(canvas)
    return RenderedSlide(
        png=png,
        width=width,
        height=height,
        report={
            "image_used": image_used,
            "overflow": overflow,
            "title_lines": len(title_lines),
            "body_lines": len(body_lines),
        },
    )


def render_carousel_slide(spec: SlideSpec, size: tuple[int, int] = DEFAULT_SIZE) -> RenderedSlide:
    """One carousel slide: role label + heading + body; image slides draw the
    photo under a bottom panel, text slides stay on the paper background."""
    width, height = size
    overflow = False
    if spec.image_bytes:
        base = Image.open(io.BytesIO(spec.image_bytes)).convert("RGB")
        canvas = _cover_crop(base, width, height)
        image_used = True
        panel_color = (*PANEL_BG, 235)
        text_color = TEXT_COLOR
    else:
        canvas = _new_canvas(width, height)
        image_used = False
        panel_color = None
        text_color = (28, 26, 23)

    draw = ImageDraw.Draw(canvas, "RGBA")
    label_font = _font(LABEL_SIZE)
    title_font = _font(TITLE_SIZE)
    body_font = _font(BODY_SIZE)
    max_width = width - 2 * MARGIN

    if panel_color is not None:
        heading = spec.heading
        lines = _wrap(heading, title_font, max_width) if heading else []
        body_lines = _wrap(spec.body, body_font, max_width) if spec.body else []
        panel_h = (
            len(lines) * int(title_font.size * LINE_SPACING)
            + len(body_lines) * int(body_font.size * LINE_SPACING + 8)
            + 2 * MARGIN
        )
        panel_top = height - min(height, panel_h)
        draw.rectangle((0, panel_top, width, height), fill=panel_color)
        draw.rectangle((0, panel_top, width, panel_top + 8), fill=ACCENT_COLOR)
        bottom = _draw_text_block(
            draw, lines=lines, font=title_font, x=MARGIN, y=panel_top + MARGIN // 2, max_width=max_width, color=text_color
        )
        if body_lines:
            bottom = _draw_text_block(
                draw, lines=body_lines, font=body_font, x=MARGIN, y=bottom + 16, max_width=max_width, color=text_color
            )
        overflow = bottom > height - MARGIN // 4
    else:
        top = MARGIN
        draw.rectangle((MARGIN, top, MARGIN + 96, top + 10), fill=ACCENT_COLOR)
        cursor = _draw_text_block(
            draw, lines=[spec.role], font=label_font, x=MARGIN, y=top + 32, max_width=max_width, color=ACCENT_COLOR
        )
        if spec.heading:
            cursor = _draw_text_block(
                draw,
                lines=_wrap(spec.heading, title_font, max_width),
                font=title_font,
                x=MARGIN,
                y=cursor + 24,
                max_width=max_width,
                color=text_color,
            ) + 20
        if spec.body:
            cursor = _draw_text_block(
                draw,
                lines=_wrap(spec.body, body_font, max_width),
                font=body_font,
                x=MARGIN,
                y=cursor,
                max_width=max_width,
                color=text_color,
            )
        overflow = cursor > height - MARGIN

    png = _encode(canvas)
    return RenderedSlide(
        png=png,
        width=width,
        height=height,
        report={"image_used": image_used, "overflow": overflow, "role": spec.role},
    )


def build_carousel_specs(
    *,
    title: str,
    caption: str,
    key_message: str = "",
    editorial_angle: str = "",
    source_labels: list[str] | None = None,
    first_image: bytes | None = None,
    claim_texts: list[str] | None = None,
) -> list[SlideSpec]:
    """Map available editorial data onto the fixed Doc 13 carousel structure.
    Deterministic distribution; sections without data stay empty (never
    invented)."""
    sentences = [s.strip() for s in (caption or "").split(".") if s.strip()]
    orientation = ". ".join(sentences[:2])
    if orientation:
        orientation += "."
    remaining = sentences[2:]
    meaning = ". ".join(remaining[:2])
    if meaning:
        meaning += "."
    sources = source_labels or []

    def _claim_text(index: int) -> str:
        texts = claim_texts or []
        return texts[index] if index < len(texts) else ""

    specs = [
        SlideSpec(role="HOOK", heading=title, body="", image_bytes=first_image),
        SlideSpec(role="ORIENTATION", heading="O que aconteceu", body=orientation),
        SlideSpec(role="EVIDENCE", heading="A evidência", body=_claim_text(0)),
        SlideSpec(role="CONTEXT", heading="O contexto", body=editorial_angle),
        SlideSpec(role="DISCOVERY", heading="A descoberta", body=key_message),
        SlideSpec(role="MEANING", heading="O que significa", body=meaning),
        SlideSpec(
            role="SOURCE / QUESTION",
            heading="Fonte",
            body="\n".join(sources) if sources else "Fontes registradas no manifesto do pacote.",
        ),
    ]
    return specs


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def render_version_block() -> dict[str, Any]:
    """Doc 13 determinism record — goes verbatim into export manifests."""
    return {
        "renderer_version": RENDERER_VERSION,
        "template_version": TEMPLATE_VERSION,
        "font": {"id": "pillow-load-default", "version": PIL.__version__},
    }
