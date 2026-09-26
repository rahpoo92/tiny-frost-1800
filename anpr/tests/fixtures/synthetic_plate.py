"""Builds a synthetic Iranian-style plate image for repeatable, offline tests.

Not a substitute for testing against real photos (which was done manually
during development, see the README) but it lets the detector/segmenter/
classifier pipeline be exercised end to end in CI without depending on, or
committing, a photo of anyone's real vehicle or plate.

Every glyph (digits and the letter alike) is rendered from its font, cropped
to content, and rescaled to the same height before being composited onto the
plate. Drawing straight from font metrics instead left the letter visibly
smaller/lighter than the digits (normal for body text, not for a plate face
where every character is stamped at the same height), which produced a real
gap in edge density that split plate detection in two -- rescaling every
glyph to a common height is what a real plate's uniform embossing gives you
for free.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from anpr_app.vision.plate_letters import LETTERS

_DIGIT_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_LETTER_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
]

_RENDER_SIZE = 200
_CONTENT_THRESHOLD = 30


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return p
    return None


def _render_glyph_bitmap(text: str, font_path: str, target_height: int) -> np.ndarray:
    """Renders text to a tightly-cropped grayscale bitmap of the given height (glyph bright on black)."""
    font = ImageFont.truetype(font_path, _RENDER_SIZE)
    bbox = font.getbbox(text)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("L", (w + 20, h + 20), color=0)
    draw = ImageDraw.Draw(img)
    draw.text((10 - bbox[0], 10 - bbox[1]), text, font=font, fill=255)
    arr = np.array(img)

    ys, xs = np.where(arr > _CONTENT_THRESHOLD)
    arr = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    scale = target_height / arr.shape[0]
    new_w = max(1, round(arr.shape[1] * scale))
    return cv2.resize(arr, (new_w, target_height), interpolation=cv2.INTER_AREA)


def make_plate_image(part1: str = "12", letter_slug: str = "b", part2: str = "345", province: str = "22") -> np.ndarray:
    digit_font_path = _first_existing(_DIGIT_FONT_CANDIDATES)
    letter_font_path = _first_existing(_LETTER_FONT_CANDIDATES)
    if not digit_font_path or not letter_font_path:
        raise RuntimeError("no suitable font found to render a synthetic test plate")

    height = 112
    glyph_height = int(height * 0.62)
    y0 = (height - glyph_height) // 2
    strip_w = int(height * 1.4)
    gap, divider_gap = 6, 8

    glyphs = [
        _render_glyph_bitmap(part1, digit_font_path, glyph_height),
        _render_glyph_bitmap(LETTERS[letter_slug], letter_font_path, glyph_height),
        _render_glyph_bitmap(part2, digit_font_path, glyph_height),
        _render_glyph_bitmap(province, digit_font_path, glyph_height),
    ]
    content_width = sum(g.shape[1] for g in glyphs) + gap * 2 + divider_gap * 2 + 4
    width = strip_w + 20 + content_width

    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (3, 3), (strip_w, height - 3), (140, 60, 30), -1)

    x = strip_w + 10
    for i, glyph in enumerate(glyphs):
        gh, gw = glyph.shape
        mask = glyph > _CONTENT_THRESHOLD
        canvas[y0 : y0 + gh, x : x + gw][mask] = (0, 0, 0)
        x += gw + gap
        if i == 2:  # a plain wider gap before the province code (no hard divider
            x += divider_gap  # line: at this render scale it forms its own tall,
            # narrow blob that the segmenter's height-ratio filter mistakes for
            # a 9th character, which a real plate's much subtler divider does not)

    cv2.rectangle(canvas, (1, 1), (width - 2, height - 2), (0, 0, 0), 2)
    return canvas


def pad_like_a_camera_crop(plate: np.ndarray, pad_ratio: float = 0.08) -> np.ndarray:
    """Adds the kind of margin PlateDetector leaves around a real crop (see its pad_ratio)."""
    pad = int(plate.shape[0] * pad_ratio)
    return cv2.copyMakeBorder(plate, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(180, 180, 180))


def make_scene_with_plate(**plate_kwargs) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Embeds the plate in a larger neutral scene. Returns (scene_bgr, plate_bbox)."""
    plate = make_plate_image(**plate_kwargs)
    ph, pw = plate.shape[:2]

    rng = np.random.default_rng(0)
    scene = np.full((ph * 4, pw * 2, 3), 180, dtype=np.uint8)
    noise = rng.integers(-8, 8, scene.shape, dtype=np.int16)
    scene = np.clip(scene.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    x0, y0 = pw // 2, ph
    scene[y0 : y0 + ph, x0 : x0 + pw] = plate

    # a light blur so the scene resembles an actual camera frame rather than
    # flat, perfectly sharp vector art -- a real lens/sensor/JPEG pass never
    # produces perfectly crisp edges.
    scene = cv2.GaussianBlur(scene, (3, 3), 0)
    return scene, (x0, y0, pw, ph)
