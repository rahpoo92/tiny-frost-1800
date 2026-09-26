"""Background camera capture + recognition thread.

Runs entirely off the GUI thread so a slow frame, a stalled camera, or the
recognition pipeline itself never freezes the window -- the whole point of
this being a QThread rather than a plain loop in the GUI code. It emits
frames for display and AccessEvents when a plate is confirmed and logged;
the GUI only ever reacts to signals, it never touches OpenCV or the
database from its own thread.
"""

from __future__ import annotations

import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from ..config import CameraConfig, RecognitionConfig
from .access_control import AccessControl
from ..vision.classifier import TemplateClassifier
from ..vision.detector import PlateDetector
from ..vision.reader import PlateReader
from ..vision.segmenter import CharacterSegmenter

RECONNECT_DELAY_SECONDS = 2.0


class CameraWorker(QThread):
    frame_ready = Signal(np.ndarray, object)  # (frame_bgr, bbox: tuple|None)
    access_event = Signal(object)  # AccessEvent
    status_changed = Signal(str, str)  # (camera_name, status_text)

    def __init__(
        self,
        camera_config: CameraConfig,
        classifier: TemplateClassifier,
        recognition_config: RecognitionConfig,
        access_control: AccessControl,
        parent=None,
    ):
        super().__init__(parent)
        self.camera_config = camera_config
        self.classifier = classifier
        self.recognition_config = recognition_config
        self.access_control = access_control
        self._running = False

    def stop(self) -> None:
        self._running = False

    def _sleep_while_running(self, seconds: float, step: float = 0.1) -> None:
        remaining = seconds
        while self._running and remaining > 0:
            time.sleep(min(step, remaining))
            remaining -= step

    def run(self) -> None:
        self._running = True
        name = self.camera_config.name
        cap = cv2.VideoCapture(self.camera_config.source)

        detector = PlateDetector(detection_width=self.camera_config.detection_width)
        segmenter = CharacterSegmenter()
        reader = PlateReader(
            detector,
            segmenter,
            self.classifier,
            frames_to_confirm=self.recognition_config.frames_to_confirm,
            reading_window_seconds=self.recognition_config.reading_window_seconds,
            min_char_confidence=self.recognition_config.min_char_confidence,
            min_plate_confidence=self.recognition_config.min_plate_confidence,
        )

        if not cap.isOpened():
            self.status_changed.emit(name, "اتصال برقرار نشد؛ در حال تلاش مجدد...")

        frame_idx = 0
        step = max(1, self.camera_config.process_every_n_frames)
        was_connected = cap.isOpened()
        if was_connected:
            self.status_changed.emit(name, "متصل")

        while self._running:
            if not cap.isOpened():
                self._sleep_while_running(RECONNECT_DELAY_SECONDS)
                cap.release()
                cap = cv2.VideoCapture(self.camera_config.source)
                if cap.isOpened():
                    was_connected = True
                    self.status_changed.emit(name, "متصل")
                continue

            ok, frame = cap.read()
            if not ok:
                if was_connected:
                    self.status_changed.emit(name, "قطع اتصال؛ در حال تلاش مجدد...")
                    was_connected = False
                cap.release()
                cap = cv2.VideoCapture(self.camera_config.source)
                self._sleep_while_running(RECONNECT_DELAY_SECONDS)
                continue

            frame_idx += 1
            if frame_idx % step == 0:
                reading = reader.process_frame(frame)
                if reading is not None:
                    event = self.access_control.process_reading(reading, name, self.camera_config.role)
                    if event is not None:
                        self.access_event.emit(event)

            self.frame_ready.emit(frame, reader.last_bbox)

        cap.release()
