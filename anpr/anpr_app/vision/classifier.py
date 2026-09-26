"""Character recognition by nearest-template matching.

There is no bundled trained OCR model -- training one needs a labeled
dataset of real, local camera footage that doesn't exist yet on a fresh
install. Instead:

1. At first run, ``generate_bootstrap_templates`` renders every digit and
   Persian plate letter from a system font into a synthetic reference
   template, so the software works immediately, at moderate accuracy.
2. ``tools/enroll.py`` lets the operator label real characters captured by
   the actual camera; those enrolled templates are tried first and, being
   real examples from the exact camera/lighting/plate font in use, quickly
   dominate recognition accuracy as a handful get added per label. This is
   the path to the high accuracy the software aims for -- see the README.

Multiple templates can exist per label; classification takes the best match
against any of them.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .plate_letters import ALL_LABELS, DIGITS, LETTERS

CANON_W, CANON_H = 40, 70
_CONTENT_THRESHOLD = 20

DIGIT_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\tahomabd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

LETTER_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\tahomabd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def _find_font(candidates: list[str]) -> str | None:
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _to_canonical(glyph: np.ndarray) -> np.ndarray:
    ys, xs = np.where(glyph > _CONTENT_THRESHOLD)
    if len(xs) == 0:
        return np.zeros((CANON_H, CANON_W), np.uint8)
    cropped = glyph[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return cv2.resize(cropped, (CANON_W, CANON_H), interpolation=cv2.INTER_AREA)


def _render_glyph(text: str, font_path: str, font_size: int = 90) -> np.ndarray | None:
    font = ImageFont.truetype(font_path, font_size)
    bbox = font.getbbox(text)
    w, h = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    img = Image.new("L", (w + 10, h + 10), color=0)
    draw = ImageDraw.Draw(img)
    draw.text((5 - bbox[0], 5 - bbox[1]), text, font=font, fill=255)
    arr = np.array(img)
    if not (arr > _CONTENT_THRESHOLD).any():
        return None
    return arr


class TemplateStore:
    def __init__(self, templates_dir: str | Path):
        self.dir = Path(templates_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def is_empty(self) -> bool:
        return not any(self.dir.iterdir())

    def _label_dir(self, label: str) -> Path:
        d = self.dir / label
        d.mkdir(parents=True, exist_ok=True)
        return d

    def enroll(self, label: str, glyph: np.ndarray) -> Path:
        canon = _to_canonical(glyph)
        label_dir = self._label_dir(label)
        idx = len(list(label_dir.glob("*.png")))
        path = label_dir / f"{label}_{idx:03d}.png"
        cv2.imwrite(str(path), canon)
        return path

    def count_by_label(self) -> dict[str, int]:
        counts = {}
        if not self.dir.exists():
            return counts
        for label_dir in self.dir.iterdir():
            if label_dir.is_dir():
                counts[label_dir.name] = len(list(label_dir.glob("*.png")))
        return counts

    def load_all(self) -> dict[str, list[np.ndarray]]:
        templates: dict[str, list[np.ndarray]] = {}
        if not self.dir.exists():
            return templates
        for label_dir in self.dir.iterdir():
            if not label_dir.is_dir():
                continue
            imgs = []
            for f in sorted(label_dir.glob("*.png")):
                img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    imgs.append(img)
            if imgs:
                templates[label_dir.name] = imgs
        return templates


def generate_bootstrap_templates(store: TemplateStore, force: bool = False) -> int:
    """Seed the (usually empty, on a fresh install) template store from system fonts.

    Returns the number of labels seeded. Silently seeds nothing for a
    category (digits or letters) whose font isn't found on this machine --
    the classifier still works for whatever labels do exist, and
    tools/enroll.py can fill in the rest from real footage regardless.
    """
    if not force and not store.is_empty():
        return 0

    seeded = 0
    digit_font = _find_font(DIGIT_FONT_CANDIDATES)
    if digit_font:
        for d in DIGITS:
            glyph = _render_glyph(d, digit_font)
            if glyph is not None:
                store.enroll(d, glyph)
                seeded += 1

    letter_font = _find_font(LETTER_FONT_CANDIDATES)
    if letter_font:
        for slug, ch in LETTERS.items():
            glyph = _render_glyph(ch, letter_font)
            if glyph is not None:
                store.enroll(slug, glyph)
                seeded += 1

    return seeded


class TemplateClassifier:
    def __init__(self, store: TemplateStore, min_confidence: float = 0.30):
        self.store = store
        self.min_confidence = min_confidence
        self.templates = store.load_all()

    def reload(self) -> None:
        self.templates = self.store.load_all()

    def known_labels(self) -> set[str]:
        return set(self.templates.keys())

    def classify(self, glyph: np.ndarray) -> tuple[str | None, float]:
        canon = _to_canonical(glyph)
        best_label: str | None = None
        best_score = -1.0
        for label in ALL_LABELS:
            for tmpl in self.templates.get(label, []):
                score = float(cv2.matchTemplate(canon, tmpl, cv2.TM_CCOEFF_NORMED)[0][0])
                if score > best_score:
                    best_score, best_label = score, label
        if best_label is None or best_score < self.min_confidence:
            return None, max(best_score, 0.0)
        return best_label, best_score
