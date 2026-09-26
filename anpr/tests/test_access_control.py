import numpy as np
import pytest

from anpr_app.core.access_control import AccessControl
from anpr_app.database.db import Database
from anpr_app.vision.plate_letters import PlateNumber
from anpr_app.vision.reader import PlateReading


def make_reading(plate: PlateNumber, confidence: float = 0.9) -> PlateReading:
    return PlateReading(
        plate=plate,
        confidence=confidence,
        char_confidences=[confidence] * 8,
        frame_count=5,
        snapshot=np.zeros((40, 150, 3), dtype=np.uint8),
    )


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def test_first_sighting_is_an_entry_and_names_the_person(db):
    person_id = db.add_person("محمدی", title="دکتر")
    plate = PlateNumber("12", "b", "345", "22")
    db.add_plate(plate, person_id=person_id)

    ac = AccessControl(db, cooldown_seconds=0, save_snapshots=False)
    event = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")

    assert event.direction == "entry"
    assert event.is_known
    assert "دکتر محمدی" in event.message
    assert "وارد شد" in event.message


def test_toggle_mode_alternates_direction(db):
    plate = PlateNumber("12", "b", "345", "22")
    ac = AccessControl(db, cooldown_seconds=0, save_snapshots=False)

    first = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")
    second = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")

    assert first.direction == "entry"
    assert second.direction == "exit"


def test_cooldown_suppresses_immediate_repeat(db):
    plate = PlateNumber("12", "b", "345", "22")
    ac = AccessControl(db, cooldown_seconds=1000, save_snapshots=False)

    first = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")
    second = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")

    assert first is not None
    assert second is None


def test_unregistered_plate_is_still_logged_but_unnamed(db):
    plate = PlateNumber("99", "s", "999", "10")
    ac = AccessControl(db, cooldown_seconds=0, save_snapshots=False)

    event = ac.process_reading(make_reading(plate), "دوربین ۱", "toggle")

    assert event.person is None
    assert not event.is_known
    assert "ناشناس" in event.message
    # still written to the log, just without a person attached
    assert db.get_last_log_for_plate(plate.to_key()) is not None


def test_fixed_camera_role_overrides_toggle(db):
    plate = PlateNumber("12", "b", "345", "22")
    ac = AccessControl(db, cooldown_seconds=0, save_snapshots=False)

    event = ac.process_reading(make_reading(plate), "دوربین خروجی", "exit")

    assert event.direction == "exit"
