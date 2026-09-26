"""Turns a confirmed plate reading into a logged, named entry/exit event.

Matches the plate against the plate bank (so a registered car can be
attributed to a person), decides whether this is an entry or an exit, saves
a snapshot, writes the access_log row, and produces the Persian message the
GUI announces (e.g. "دکتر محمدی وارد شد").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from ..database.db import AccessLogEntry, Database, Person
from ..jalali import format_jalali_datetime
from ..vision.plate_letters import PlateNumber
from ..vision.reader import PlateReading


@dataclass
class AccessEvent:
    plate: PlateNumber
    plate_key: str
    direction: str  # "entry" | "exit"
    person: Person | None
    confidence: float
    camera_name: str
    occurred_at: datetime
    snapshot_path: str | None
    message: str
    is_known: bool


class AccessControl:
    def __init__(
        self,
        db: Database,
        cooldown_seconds: float = 45.0,
        save_snapshots: bool = True,
        snapshots_dir: str | Path | None = None,
    ):
        self.db = db
        self.cooldown_seconds = cooldown_seconds
        self.save_snapshots = save_snapshots
        self.snapshots_dir = Path(snapshots_dir) if snapshots_dir else None

    def process_reading(self, reading: PlateReading, camera_name: str, camera_role: str) -> AccessEvent | None:
        plate_key = reading.plate.to_key()
        last = self.db.get_last_log_for_plate(plate_key)
        now = datetime.now()

        if last is not None and self._seconds_since(last, now) < self.cooldown_seconds:
            return None  # same plate seen again too recently: treat as the same pass, not a new event

        direction = self._determine_direction(camera_role, last)

        plate_record = self.db.find_plate_by_key(plate_key)
        person = None
        if plate_record and plate_record.person_id:
            person = self.db.get_person(plate_record.person_id)

        snapshot_path = self._save_snapshot(reading, plate_key, now) if self.save_snapshots and self.snapshots_dir else None

        self.db.insert_access_log(
            plate_key=plate_key,
            plate_display=reading.plate.to_display(),
            direction=direction,
            person_id=person.id if person else None,
            person_name_snapshot=person.display_name if person else None,
            confidence=reading.confidence,
            camera_name=camera_name,
            snapshot_path=snapshot_path,
            occurred_at=now,
        )

        return AccessEvent(
            plate=reading.plate,
            plate_key=plate_key,
            direction=direction,
            person=person,
            confidence=reading.confidence,
            camera_name=camera_name,
            occurred_at=now,
            snapshot_path=snapshot_path,
            message=self._build_message(reading.plate, person, direction, now),
            is_known=person is not None,
        )

    @staticmethod
    def _seconds_since(last: AccessLogEntry, now: datetime) -> float:
        return (now - datetime.fromisoformat(last.occurred_at)).total_seconds()

    @staticmethod
    def _determine_direction(camera_role: str, last: AccessLogEntry | None) -> str:
        if camera_role in ("entry", "exit"):
            return camera_role
        # toggle mode (one camera, both directions): flip relative to this plate's last
        # direction; a plate seen for the very first time is assumed to be an entry.
        if last is None or last.direction == "exit":
            return "entry"
        return "exit"

    def _save_snapshot(self, reading: PlateReading, plate_key: str, now: datetime) -> str | None:
        if self.snapshots_dir is None:
            return None
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{plate_key}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
        path = self.snapshots_dir / filename
        cv2.imwrite(str(path), reading.snapshot)
        return str(path)

    @staticmethod
    def _build_message(plate: PlateNumber, person: Person | None, direction: str, now: datetime) -> str:
        verb = "وارد شد" if direction == "entry" else "خارج شد"
        when = format_jalali_datetime(now)
        if person:
            return f"{person.display_name} {verb} — {when}"
        return f"پلاک {plate.to_display()} {verb} (ناشناس - در بانک اطلاعاتی ثبت نیست) — {when}"
