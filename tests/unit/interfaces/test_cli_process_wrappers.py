from __future__ import annotations

import subprocess

from src.interfaces import cli


def test_run_command__returns_subprocess_exit_code(monkeypatch) -> None:
    class _Result:
        returncode = 7

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    assert cli._run_command(["python3", "-V"]) == 7


def test_run_command__converts_keyboard_interrupt_to_shell_exit_code(monkeypatch) -> None:
    def _raise_keyboard_interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", _raise_keyboard_interrupt)

    assert cli._run_command(["python3", "-V"]) == 130
