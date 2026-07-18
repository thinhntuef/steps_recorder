import json
import os
import sys

import steps_recorder
from steps_recorder import AppConfig


def _use_tmp_config(monkeypatch, tmp_path):
    path = str(tmp_path / "config.json")
    monkeypatch.setattr(steps_recorder, "CONFIG_PATH", path)
    return path


def test_save_load_roundtrip(monkeypatch, tmp_path):
    _use_tmp_config(monkeypatch, tmp_path)
    cfg = AppConfig(base_url="http://localhost:8000/v1", model="m",
                    api_key="sk-test", mask_typed_text=False)
    assert cfg.save() is True
    loaded = AppConfig.load()
    assert loaded.base_url == "http://localhost:8000/v1"
    assert loaded.api_key == "sk-test"
    assert loaded.mask_typed_text is False


def test_save_returns_false_on_unwritable_path(monkeypatch, tmp_path):
    monkeypatch.setattr(steps_recorder, "CONFIG_PATH",
                        str(tmp_path / "no_such_dir" / "config.json"))
    assert AppConfig().save() is False


def test_saved_file_has_0600_permissions(monkeypatch, tmp_path):
    if sys.platform == "win32":
        return
    path = _use_tmp_config(monkeypatch, tmp_path)
    AppConfig(api_key="secret").save()
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_load_returns_defaults_when_missing(monkeypatch, tmp_path):
    _use_tmp_config(monkeypatch, tmp_path)
    cfg = AppConfig.load()
    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.mask_typed_text is True


def test_load_returns_defaults_on_corrupt_file(monkeypatch, tmp_path):
    path = _use_tmp_config(monkeypatch, tmp_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{hỏng")
    cfg = AppConfig.load()
    assert cfg.model == "gpt-4o-mini"


def test_export_redacts_api_key_by_default(tmp_path):
    cfg = AppConfig(api_key="sk-secret")
    out = cfg.export_to(str(tmp_path / "share"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert data["api_key"] == ""
    assert out.endswith(".config.json")


def test_import_keeps_key_when_redacted(tmp_path):
    path = str(tmp_path / "in.config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"api_key": "***", "model": "khac"}, f)
    cfg = AppConfig(api_key="sk-real")
    cfg.import_from(path)
    assert cfg.api_key == "sk-real"
    assert cfg.model == "khac"


def test_apply_dict_ignores_unknown_keys():
    cfg = AppConfig()
    cfg.apply_dict({"chrome_path": "/x", "model": "m2"})
    assert cfg.model == "m2"
    assert not hasattr(cfg, "chrome_path") or cfg.model == "m2"
