import pytest

from anpr_app.config import CameraConfig, load_config


def test_load_config_from_example(tmp_path):
    config_text = """
cameras:
  - name: "دوربین ۱"
    source: 0
    role: toggle
recognition:
  min_char_confidence: 0.5
paths:
  database: data/anpr.db
  templates_dir: data/templates
  snapshots_dir: data/snapshots
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(config_path)

    assert len(config.cameras) == 1
    assert config.cameras[0].role == "toggle"
    assert config.recognition.min_char_confidence == 0.5
    assert config.paths.database == str((tmp_path / "data" / "anpr.db").resolve())
    assert (tmp_path / "data" / "templates").exists()


def test_missing_config_file_uses_defaults(tmp_path):
    config = load_config(tmp_path / "does-not-exist.yaml")
    assert len(config.cameras) == 1
    assert config.cameras[0].source == 0


def test_invalid_camera_role_raises():
    with pytest.raises(ValueError):
        CameraConfig(role="sideways")
