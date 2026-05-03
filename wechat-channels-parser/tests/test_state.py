from __future__ import annotations

import os
from pathlib import Path

import pytest

# Required env BEFORE importing app modules.
os.environ.setdefault("WECHAT_CORP_ID", "ww_test")
os.environ.setdefault("WECHAT_MSGAUDIT_SECRET", "secret_test")
os.environ.setdefault("RSA_PRIVATE_KEY_PATH", "/tmp/fake_key.pem")

from app import state as state_mod  # noqa: E402


@pytest.fixture
def temp_state_file(tmp_path, monkeypatch):
    """Point state._path() at an isolated tmp file per test."""
    fake = tmp_path / "state.json"
    monkeypatch.setattr(state_mod, "_path", lambda: fake)
    return fake


def test_load_returns_empty_state_when_file_missing(temp_state_file: Path) -> None:
    s = state_mod.load()
    assert s.msgaudit_seq == 0
    assert s.processed_msgids == []


async def test_save_then_load_round_trip(temp_state_file: Path) -> None:
    s = state_mod.State(msgaudit_seq=42, processed_msgids=["m1", "m2"])
    await state_mod.save(s)

    loaded = state_mod.load()
    assert loaded.msgaudit_seq == 42
    assert loaded.processed_msgids == ["m1", "m2"]
    assert loaded.last_updated  # non-empty timestamp


async def test_save_is_atomic_no_partial_files_left_behind(temp_state_file: Path) -> None:
    await state_mod.save(state_mod.State(msgaudit_seq=7))
    leftover = list(temp_state_file.parent.glob("*.tmp"))
    assert leftover == []


def test_mark_processed_dedupes() -> None:
    s = state_mod.State()
    s.mark_processed("a")
    s.mark_processed("a")
    s.mark_processed("b")
    assert s.processed_msgids == ["a", "b"]


def test_mark_processed_rolls_over_window(monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "MAX_PROCESSED", 5)
    s = state_mod.State()
    for i in range(10):
        s.mark_processed(f"m{i}")
    assert s.processed_msgids == ["m5", "m6", "m7", "m8", "m9"]


def test_load_corrupted_file_falls_back_to_empty(temp_state_file: Path) -> None:
    temp_state_file.write_text("not-json", encoding="utf-8")
    s = state_mod.load()
    assert s.msgaudit_seq == 0
