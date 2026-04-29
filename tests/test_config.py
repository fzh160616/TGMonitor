import json
import pytest
from tg_monitor import config as cfg


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr("tg_monitor.config.CONFIG_PATH", p)
    monkeypatch.setattr("tg_monitor.paths.DATA_DIR", tmp_path)
    monkeypatch.setattr("tg_monitor.paths.LOG_DIR", tmp_path)
    return p


def test_load_defaults_when_missing(config_path):
    c = cfg.load()
    assert c.api_id == 0
    assert c.keywords == []
    assert c.backfill_minutes == 5
    assert c.notification_sound is True
    assert c.launch_at_login is True


def test_load_reads_json(config_path):
    config_path.write_text(
        json.dumps({"api_id": 42, "api_hash": "abc", "keywords": ["foo"]}),
        encoding="utf-8",
    )
    c = cfg.load()
    assert c.api_id == 42
    assert c.api_hash == "abc"
    assert c.keywords == ["foo"]


def test_save_roundtrip(config_path):
    c = cfg.Config(api_id=1, api_hash="x", keywords=["k1", "k2"])
    cfg.save(c)
    c2 = cfg.load()
    assert c2.api_id == 1
    assert c2.keywords == ["k1", "k2"]


def test_load_ignores_unknown_fields(config_path):
    config_path.write_text(
        json.dumps({"api_id": 1, "api_hash": "x", "unknown_future_field": True}),
        encoding="utf-8",
    )
    c = cfg.load()  # should not raise
    assert c.api_id == 1


def test_save_writes_valid_json(config_path):
    cfg.save(cfg.Config())
    data = json.loads(config_path.read_text())
    assert "api_id" in data
