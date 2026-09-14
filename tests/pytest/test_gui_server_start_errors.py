"""Tests for the operator-facing message built when a server launch fails.

Starting ACQ/STM shells out to SCHTASKS, which returns "Access is denied" for an
operator without administrator rights. That used to escape ``start_servers()``
as an uncaught ``CalledProcessError``, reach ``main()``, and take the whole GUI
down with ``os._exit(1)`` -- losing the session because one scheduled task could
not be registered. The message built here is what the operator sees instead.
"""
from __future__ import annotations

import subprocess

from neurobooth_os.gui import server_start_failure_message


def _error(stderr: str = "", returncode: int = 1, cmd=None) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        returncode=returncode,
        cmd=cmd if cmd is not None else ["SCHTASKS", "/Create", "/TN", "acquisition0"],
        output="",
        stderr=stderr,
    )


def test_names_the_command_and_the_reason():
    message = server_start_failure_message(_error(stderr="ERROR: Access is denied."))
    assert "SCHTASKS" in message
    assert "Access is denied" in message


def test_access_denied_tells_the_operator_to_elevate():
    """The fix for this failure is not discoverable from the raw stderr."""
    message = server_start_failure_message(_error(stderr="ERROR: Access is denied."))
    assert "administrator" in message.lower()


def test_elevation_hint_is_matched_case_insensitively():
    message = server_start_failure_message(_error(stderr="error: ACCESS IS DENIED."))
    assert "administrator" in message.lower()


def test_unrelated_failure_gets_no_elevation_hint():
    """Suggesting elevation for an unrelated fault would send them down a
    blind alley."""
    message = server_start_failure_message(
        _error(stderr="ERROR: The system cannot find the file specified."))
    assert "administrator" not in message.lower()
    assert "cannot find the file" in message


def test_empty_stderr_falls_back_to_the_exit_status():
    message = server_start_failure_message(_error(stderr="", returncode=3))
    assert "exit status 3" in message


def test_none_stderr_is_not_a_crash():
    """subprocess leaves stderr None when the command was not captured."""
    error = _error()
    error.stderr = None
    assert "exit status 1" in server_start_failure_message(error)


def test_string_command_is_reported():
    message = server_start_failure_message(_error(stderr="nope", cmd="SCHTASKS /Create"))
    assert "SCHTASKS /Create" in message
