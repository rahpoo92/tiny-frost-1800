"""Split a cropped plate image into individual character images.

Handles both common polarities (dark characters on a light plate -- private,
taxi, government plates -- and light characters on a dark plate -- some
government/diplomatic plates) by trying both and keeping whichever produces
a character count closest to the 8 glyphs a standard plate has (2 digits +
1 letter + 3 digits + 2-digit province code).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

EXPECTED_CHAR_COUNT = 8


@dataclass
class CharacterCrop:
    image: np.ndarray  # binary, glyph=255 on background=0, tightly cropped
    bbox: tuple[int, int, int, int]  # x, y, w, h within the (possibly upscaled) plate crop


class CharacterSegmenter:
    def __init__(
        self,
        min_height_ratio: float = 0.30,
        max_height_ratio: float = 0.80,
        max_width_ratio: float = 0.55,
        min_width_px: int = 3,
        upscale_target_height: int = 140,
    ):
        self.min_height_ratio = min_height_ratio
        self.max_height_ratio = max_height_ratio
        self.max_width_ratio = max_width_ratio
        self.min_width_px = min_width_px
        self.upscale_target_height = upscale_target_height

    def _boxes_for_polarity(self, binary: np.ndarray) -> list[tuple[int, int, int, int]]:
        h, w = binary.shape
        n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        boxes = []
        for i in range(1, n):
            x0, y0, w0, h0, _area = stats[i]
            if w0 > self.max_width_ratio * w or h0 > self.max_height_ratio * h:
                continue
            height_ratio = h0 / h
            if height_ratio < self.min_height_ratio or height_ratio > self.max_height_ratio:
                continue
            if w0 < self.min_width_px:
                continue
            boxes.append((x0, y0, w0, h0))
        boxes.sort(key=lambda b: b[0])
        return boxes

    def segment(self, plate_bgr: np.ndarray) -> list[CharacterCrop]:
        h, w = plate_bgr.shape[:2]
        if h < self.upscale_target_height:
            factor = self.upscale_target_height / h
            plate_bgr = cv2.resize(plate_bgr, (int(w * factor), int(h * factor)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 7, 40, 40)

        best_boxes: list[tuple[int, int, int, int]] = []
        best_binary: np.ndarray | None = None
        best_diff = None
        for flag in (cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY):
            binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)[1]
            boxes = self._boxes_for_polarity(binary)
            diff = abs(len(boxes) - EXPECTED_CHAR_COUNT)
            if best_diff is None or diff < best_diff or (diff == best_diff and len(boxes) > len(best_boxes)):
                best_diff, best_boxes, best_binary = diff, boxes, binary

        assert best_binary is not None
        crops = []
        for x0, y0, w0, h0 in best_boxes:
            glyph = best_binary[y0 : y0 + h0, x0 : x0 + w0]
            crops.append(CharacterCrop(image=glyph, bbox=(x0, y0, w0, h0)))
        return crops
