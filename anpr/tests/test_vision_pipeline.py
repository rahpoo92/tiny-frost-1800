"""Vision pipeline tests.

Detector, segmenter, and classifier are exercised here against a synthetic,
cleanly-rendered plate (see tests/fixtures/synthetic_plate.py) rather than a
real photo -- committing a photo of anyone's actual vehicle/plate to the repo
isn't appropriate, even though that is exactly what was used for the manual
accuracy validation described in the README during development (a real,
photographed plate localized correctly, segmented into all 8 characters, and
read correctly after enrolling two real character samples).

The detector specifically is a classical CV algorithm (blackhat + gradient,
see detector.py) tuned and validated against that real, noisy, JPEG-compressed
photograph; a flat, razor-sharp vector rendering is a harder case for it than
actual camera footage is, and it can legitimately split a synthetic plate into
more than one region. So detector coverage here is a lenient smoke test, while
segmenter/classifier are tested against a directly-supplied, realistically
padded plate crop -- their actual real-world input contract -- rather than
depending on the synthetic detector output. PlateReader's own session/voting/
debounce logic is independent of what detector/segmenter/classifier actually
are, so it's tested against small fakes instead, isolating it from the
synthetic-image concerns above entirely.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from anpr_app.vision.classifier import TemplateClassifier, TemplateStore, generate_bootstrap_templates
from anpr_app.vision.detector import PlateDetector
from anpr_app.vision.plate_letters import PlateNumber
from anpr_app.vision.reader import PlateReader
from anpr_app.vision.segmenter import EXPECTED_CHAR_COUNT, CharacterSegmenter

from .fixtures.synthetic_plate import make_plate_image, make_scene_with_plate, pad_like_a_camera_crop

EXPECTED_LABELS = ["1", "2", "b", "3", "4", "5", "2", "2"]


@pytest.fixture(scope="module")
def classifier(tmp_path_factory):
    store = TemplateStore(tmp_path_factory.mktemp("templates"))
    seeded = generate_bootstrap_templates(store)
    if seeded == 0:
        pytest.skip("no system font available to build bootstrap templates in this environment")
    return TemplateClassifier(store)


@pytest.fixture(scope="module")
def segmented_chars():
    plate = make_plate_image(part1="12", letter_slug="b", part2="345", province="22")
    padded = pad_like_a_camera_crop(plate)
    chars = CharacterSegmenter().segment(padded)
    assert len(chars) == EXPECTED_CHAR_COUNT
    return chars


def test_detector_finds_a_region_overlapping_the_plate():
    scene, expected_bbox = make_scene_with_plate()
    candidates = PlateDetector().detect(scene, max_candidates=5)
    assert candidates, "expected at least one plate candidate"

    ex, ey, ew, eh = expected_bbox

    def overlap_ratio(bbox: tuple[int, int, int, int]) -> float:
        bx, by, bw, bh = bbox
        ox = max(0, min(ex + ew, bx + bw) - max(ex, bx))
        oy = max(0, min(ey + eh, by + bh) - max(ey, by))
        return (ox * oy) / (ew * eh)

    assert max(overlap_ratio(c.bbox) for c in candidates) > 0.3


def test_segmenter_splits_a_plate_crop_into_eight_characters(segmented_chars):
    assert len(segmented_chars) == EXPECTED_CHAR_COUNT


def test_classifier_recognizes_digits_from_bootstrap_templates_alone(classifier, segmented_chars):
    # every position except the letter (index 2) is a digit rendered with the same
    # font the bootstrap templates use, so this should be reliable out of the box
    for i, expected in enumerate(EXPECTED_LABELS):
        if i == 2:
            continue
        label, score = classifier.classify(segmented_chars[i].image)
        assert label == expected
        assert score > 0.7


def test_enrolling_a_character_fixes_its_recognition(tmp_path, segmented_chars):
    # bootstrap templates are synthetic and don't cover every letter equally well;
    # this is what the enrollment tool (tools/enroll.py) is for, and is exactly
    # the improvement seen in practice on a real photographed plate (see README).
    store = TemplateStore(tmp_path / "templates")
    generate_bootstrap_templates(store)
    classifier = TemplateClassifier(store)

    letter_glyph = segmented_chars[2].image
    store.enroll("b", letter_glyph)
    classifier.reload()

    label, score = classifier.classify(letter_glyph)
    assert label == "b"
    assert score > 0.9


# ---- PlateReader: tested against fakes, independent of real CV -----------------


class _FakeCandidate:
    def __init__(self, bbox, crop):
        self.bbox = bbox
        self.crop = crop


class _FakeDetector:
    """Reports a plate present for the first `frames_present` calls, then gone."""

    def __init__(self, frames_present: int = 999):
        self.frames_present = frames_present
        self.calls = 0

    def detect(self, frame, max_candidates=1):
        self.calls += 1
        if self.calls > self.frames_present:
            return []
        return [_FakeCandidate((0, 0, 10, 10), frame)]


class _FakeCharCrop:
    def __init__(self, image):
        self.image = image


class _FakeSegmenter:
    def segment(self, crop):
        return [_FakeCharCrop(np.zeros((5, 5), dtype=np.uint8)) for _ in range(EXPECTED_CHAR_COUNT)]


def _make_reader(detector, labels=EXPECTED_LABELS, **kwargs):
    class _PositionalFakeClassifier:
        def __init__(self):
            self._n = 0

        def classify(self, glyph):
            label = labels[self._n % EXPECTED_CHAR_COUNT]
            self._n += 1
            return label, 0.9

    defaults = dict(frames_to_confirm=3, min_char_confidence=0.5, min_plate_confidence=0.5)
    defaults.update(kwargs)
    return PlateReader(detector, _FakeSegmenter(), _PositionalFakeClassifier(), **defaults)


def test_reader_confirms_once_after_enough_consistent_frames():
    reader = _make_reader(_FakeDetector())
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    results = [reader.process_frame(frame) for _ in range(6)]
    confirmed = [r for r in results if r is not None]

    assert len(confirmed) == 1  # confirmed once, then suppressed while still in frame
    assert confirmed[0].plate == PlateNumber("12", "b", "345", "22")


def test_reader_starts_a_new_session_after_the_plate_leaves_and_returns():
    detector = _FakeDetector(frames_present=3)
    reader = _make_reader(detector, session_gap_seconds=0.01)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    first_pass = [reader.process_frame(frame) for _ in range(3)]
    assert sum(r is not None for r in first_pass) == 1

    time.sleep(0.05)  # let the session expire, as if the car had driven off
    detector.calls, detector.frames_present = 0, 3  # the same plate returns later

    second_pass = [reader.process_frame(frame) for _ in range(3)]
    assert sum(r is not None for r in second_pass) == 1
