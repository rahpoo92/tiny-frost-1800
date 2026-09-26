"""Application configuration: dataclasses + a YAML loader with sane defaults.

Only config.example.yaml is committed to the repository; each installation
copies it to config.yaml and edits it locally (see .gitignore), so a real
camera address or file paths on someone's machine never end up in git.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_ROLES = ("toggle", "entry", "exit")


@dataclass
class CameraConfig:
    name: str = "دوربین ۱"
    source: int | str = 0  # 0/1/.. for a local webcam index, or an RTSP/HTTP URL
    role: str = "toggle"  # toggle: one camera sees both directions, alternating
    process_every_n_frames: int = 2
    detection_width: int = 960

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"camera role must be one of {VALID_ROLES}, got {self.role!r}")


@dataclass
class RecognitionConfig:
    min_char_confidence: float = 0.45
    min_plate_confidence: float = 0.55
    frames_to_confirm: int = 5
    reading_window_seconds: float = 2.5
    cooldown_seconds: float = 45.0


@dataclass
class PathsConfig:
    database: str = "data/anpr.db"
    templates_dir: str = "data/templates"
    snapshots_dir: str = "data/snapshots"
    save_snapshots: bool = True

    def resolve(self, base_dir: Path) -> "PathsConfig":
        resolved = PathsConfig(
            database=str((base_dir / self.database).resolve()),
            templates_dir=str((base_dir / self.templates_dir).resolve()),
            snapshots_dir=str((base_dir / self.snapshots_dir).resolve()),
            save_snapshots=self.save_snapshots,
        )
        return resolved

    def ensure_dirs(self) -> None:
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        Path(self.templates_dir).mkdir(parents=True, exist_ok=True)
        if self.save_snapshots:
            Path(self.snapshots_dir).mkdir(parents=True, exist_ok=True)


@dataclass
class AppConfig:
    window_title: str = "سامانه پلاک‌خوان هوشمند"


@dataclass
class Config:
    cameras: list[CameraConfig] = field(default_factory=lambda: [CameraConfig()])
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    app: AppConfig = field(default_factory=AppConfig)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    if "cameras" in raw:
        cameras_raw = raw["cameras"]
    elif "camera" in raw:
        cameras_raw = [raw["camera"]]
    else:
        cameras_raw = None
    cameras = [CameraConfig(**c) for c in cameras_raw] if cameras_raw else [CameraConfig()]

    recognition = RecognitionConfig(**raw.get("recognition", {}))
    paths = PathsConfig(**raw.get("paths", {})).resolve(path.parent)
    app = AppConfig(**raw.get("app", {}))

    config = Config(cameras=cameras, recognition=recognition, paths=paths, app=app)
    config.paths.ensure_dirs()
    return config
