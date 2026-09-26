"""Classical computer-vision license-plate localization.

No trained model is required: this looks for the rectangular, high
horizontal-gradient-density regions that a dense block of plate characters
produces (the standard "blackhat + gradient" ANPR recipe), then filters
candidates by the aspect ratio and size a plate is expected to have. It was
tuned and verified against a real photographed Iranian plate (see the
project README for how to re-tune it against your own camera if needed).

This module has no dependency on any specific camera or GUI code, so it can
be unit-tested with plain image files.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PlateCandidate:
    bbox: tuple[int, int, int, int]  # x, y, w, h in the original frame's coordinates
    crop: np.ndarray  # BGR pixels of the candidate region, cropped from the original frame
    score: float


class PlateDetector:
    def __init__(
        self,
        detection_width: int = 960,
        min_aspect: float = 1.5,
        max_aspect: float = 6.5,
        min_area_ratio: float = 0.0004,
        max_area_ratio: float = 0.30,
        ideal_aspect: float = 4.3,
        pad_ratio: float = 0.08,
    ):
        self.detection_width = detection_width
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.ideal_aspect = ideal_aspect
        self.pad_ratio = pad_ratio
        self._rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
        self._close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 15))

    def detect(self, frame_bgr: np.ndarray, max_candidates: int = 5) -> list[PlateCandidate]:
        h0, w0 = frame_bgr.shape[:2]
        scale = 1.0
        work = frame_bgr
        if w0 > self.detection_width:
            scale = self.detection_width / w0
            work = cv2.resize(frame_bgr, (self.detection_width, int(h0 * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, self._rect_kernel)

        grad_x = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        grad_x = np.absolute(grad_x)
        min_val, max_val = float(np.min(grad_x)), float(np.max(grad_x))
        grad_x = (255 * (grad_x - min_val) / (max_val - min_val + 1e-6)).astype("uint8")
        grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
        grad_x = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, self._rect_kernel)
        thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._close_kernel)
        closed = cv2.erode(closed, None, iterations=2)
        closed = cv2.dilate(closed, None, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        work_h, work_w = gray.shape
        frame_area = float(work_w * work_h)

        scored: list[tuple[float, tuple[int, int, int, int]]] = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if h == 0:
                continue
            aspect = w / float(h)
            area_ratio = (w * h) / frame_area
            if not (self.min_aspect <= aspect <= self.max_aspect):
                continue
            if not (self.min_area_ratio <= area_ratio <= self.max_area_ratio):
                continue
            aspect_score = 1.0 - min(1.0, abs(aspect - self.ideal_aspect) / self.ideal_aspect)
            score = 0.6 * aspect_score + 0.4 * min(1.0, area_ratio / 0.05)
            scored.append((score, (x, y, w, h)))

        scored.sort(key=lambda t: t[0], reverse=True)

        candidates = []
        for score, (x, y, w, h) in scored[:max_candidates]:
            # map back to the original (full-resolution) frame and pad a little
            ox, oy, ow, oh = (v / scale for v in (x, y, w, h))
            pad_x, pad_y = ow * self.pad_ratio, oh * self.pad_ratio
            x0 = max(0, int(ox - pad_x))
            y0 = max(0, int(oy - pad_y))
            x1 = min(w0, int(ox + ow + pad_x))
            y1 = min(h0, int(oy + oh + pad_y))
            if x1 <= x0 or y1 <= y0:
                continue
            crop = frame_bgr[y0:y1, x0:x1]
            candidates.append(PlateCandidate(bbox=(x0, y0, x1 - x0, y1 - y0), crop=crop, score=score))

        return candidates
