"""Turns a stream of video frames into confirmed plate readings.

A single video frame is not trusted on its own: the same tracked plate must
be read consistently across several consecutive frames (``frames_to_confirm``)
before it is "confirmed", with each character decided by a confidence-weighted
majority vote across those frames. This is what actually makes a live-video
ANPR pipeline accurate in practice -- a lot more than any single frame's OCR
call, however good -- because it cancels out the occasional bad frame (motion
blur, glare, a moment of bad focus).

Call ``process_frame`` once per video frame; it returns a PlateReading only
once a plate has just been confirmed, and returns None on every other frame
(including all the frames it's still busy building consensus over).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .classifier import TemplateClassifier
from .detector import PlateDetector
from .plate_letters import PlateNumber
from .segmenter import EXPECTED_CHAR_COUNT, CharacterSegmenter


@dataclass
class PlateReading:
    plate: PlateNumber
    confidence: float
    char_confidences: list[float]
    frame_count: int
    snapshot: np.ndarray


class _Session:
    def __init__(self, now: float, snapshot: np.ndarray):
        self.started = now
        self.last_seen = now
        self.snapshot = snapshot
        self.readings: list[tuple[list[str], list[float]]] = []
        self.finalized = False


class PlateReader:
    def __init__(
        self,
        detector: PlateDetector,
        segmenter: CharacterSegmenter,
        classifier: TemplateClassifier,
        frames_to_confirm: int = 5,
        reading_window_seconds: float = 2.5,
        min_char_confidence: float = 0.45,
        min_plate_confidence: float = 0.55,
        session_gap_seconds: float = 1.0,
    ):
        self.detector = detector
        self.segmenter = segmenter
        self.classifier = classifier
        self.frames_to_confirm = frames_to_confirm
        self.reading_window_seconds = reading_window_seconds
        self.min_char_confidence = min_char_confidence
        self.min_plate_confidence = min_plate_confidence
        self.session_gap_seconds = session_gap_seconds
        self._session: _Session | None = None
        self.last_bbox: tuple[int, int, int, int] | None = None

    def process_frame(self, frame_bgr: np.ndarray) -> PlateReading | None:
        now = time.monotonic()
        candidates = self.detector.detect(frame_bgr, max_candidates=1)
        self.last_bbox = candidates[0].bbox if candidates else None
        if not candidates:
            self._expire_if_gone(now)
            return None

        chars = self.segmenter.segment(candidates[0].crop)
        if len(chars) != EXPECTED_CHAR_COUNT:
            self._expire_if_gone(now)
            return None

        labels: list[str] = []
        confs: list[float] = []
        for char in chars:
            label, score = self.classifier.classify(char.image)
            labels.append(label or "?")
            confs.append(score)

        if any(label == "?" or conf < self.min_char_confidence for label, conf in zip(labels, confs)):
            self._expire_if_gone(now)
            return None

        if self._session is None or (now - self._session.last_seen) > self.session_gap_seconds:
            self._session = _Session(now, candidates[0].crop)
        session = self._session
        session.last_seen = now
        session.snapshot = candidates[0].crop

        if session.finalized:
            return None
        session.readings.append((labels, confs))

        elapsed = now - session.started
        if len(session.readings) >= self.frames_to_confirm or elapsed >= self.reading_window_seconds:
            result = self._finalize(session)
            if result is not None:
                session.finalized = True
            return result
        return None

    def _expire_if_gone(self, now: float) -> None:
        if self._session and (now - self._session.last_seen) > self.session_gap_seconds:
            self._session = None

    def _finalize(self, session: _Session) -> PlateReading | None:
        final_labels: list[str] = []
        final_confs: list[float] = []
        for pos in range(EXPECTED_CHAR_COUNT):
            votes: dict[str, float] = {}
            for labels, confs in session.readings:
                votes[labels[pos]] = votes.get(labels[pos], 0.0) + confs[pos]
            winner = max(votes, key=votes.get)
            support = sum(1 for labels, _ in session.readings if labels[pos] == winner)
            final_labels.append(winner)
            final_confs.append(votes[winner] / support)

        plate = PlateNumber.from_labels(final_labels)
        overall_confidence = sum(final_confs) / len(final_confs)
        if plate is None or not plate.is_valid() or overall_confidence < self.min_plate_confidence:
            return None

        return PlateReading(
            plate=plate,
            confidence=overall_confidence,
            char_confidences=final_confs,
            frame_count=len(session.readings),
            snapshot=session.snapshot,
        )
