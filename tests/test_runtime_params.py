import json
from pathlib import Path

from backend import runtime_params


def test_load_runtime_params_reloads_when_file_mtime_changes(tmp_path: Path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        json.dumps(
            {
                "KRW-TEST": {
                    "name": "테스트",
                    "enabled": True,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    runtime_params._table = None
    runtime_params._table_mtime_ns = None

    first = runtime_params.load_runtime_params(force=True)
    assert first["KRW-TEST"]["reason"] == "init"

    path.write_text(
        json.dumps(
            {
                "KRW-TEST": {
                    "name": "테스트",
                    "enabled": True,
                    "reason": "updated",
                    "realistic_return_pct": 1.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                }
            }
        ),
        encoding="utf-8",
    )

    second = runtime_params.load_runtime_params()
    assert second["KRW-TEST"]["reason"] == "updated"


def test_manual_override_disables_symbol(tmp_path: Path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        json.dumps(
            {
                "KRW-TEST": {
                    "name": "테스트",
                    "enabled": True,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    runtime_params._table = None
    runtime_params._table_mtime_ns = None

    runtime_params.set_symbol_manual_override("KRW-TEST", "disabled", actor="test")
    meta = runtime_params.runtime_selection_meta()

    assert meta["KRW-TEST"]["base_enabled"] is False
    assert meta["KRW-TEST"]["manual_override"] == "disabled"


def test_manual_override_enabled_forces_symbol_on(tmp_path: Path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        json.dumps(
            {
                "KRW-TEST": {
                    "name": "테스트",
                    "enabled": False,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    runtime_params._table = None
    runtime_params._table_mtime_ns = None

    runtime_params.set_symbol_manual_override("TEST", "enabled", actor="test")
    active = runtime_params.get_base_active_buy_symbols()

    assert active == {"KRW-TEST": "테스트"}
