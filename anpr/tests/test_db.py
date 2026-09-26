import pytest

from anpr_app.database.db import Database
from anpr_app.vision.plate_letters import PlateNumber


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def test_person_crud(db):
    pid = db.add_person("محمدی", title="دکتر")
    person = db.get_person(pid)
    assert person.display_name == "دکتر محمدی"

    db.update_person(pid, full_name="محمدی", title="دکتر", notes=None)
    assert db.get_person(pid).notes is None

    db.delete_person(pid)
    assert db.get_person(pid) is None


def test_plate_linked_to_person_and_lookup_by_key(db):
    pid = db.add_person("رضایی")
    plate = PlateNumber("12", "b", "345", "22")
    db.add_plate(plate, person_id=pid)

    found = db.find_plate_by_key(plate.to_key())
    assert found is not None
    assert found.person_id == pid
    assert found.plate_number() == plate


def test_update_plate_can_clear_owner(db):
    pid = db.add_person("رضایی")
    plate = PlateNumber("12", "b", "345", "22")
    plate_id = db.add_plate(plate, person_id=pid, notes="یادداشت")

    db.update_plate(plate_id, person_id=None, notes=None)

    record = db.find_plate_by_key(plate.to_key())
    assert record.person_id is None
    assert record.notes is None


def test_access_log_ordering_and_query_filters(db):
    plate = PlateNumber("12", "b", "345", "22")
    db.insert_access_log(plate.to_key(), plate.to_display(), "entry")
    db.insert_access_log(plate.to_key(), plate.to_display(), "exit")

    last = db.get_last_log_for_plate(plate.to_key())
    assert last.direction == "exit"

    logs = db.query_logs(plate_key=plate.to_key())
    assert [log.direction for log in logs] == ["exit", "entry"]  # newest first


def test_unknown_plate_lookup_returns_none(db):
    assert db.find_plate_by_key("99s99910") is None
