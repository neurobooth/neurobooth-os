"""Tests for metadator module — import allowlist validation."""

import pytest

from neurobooth_os.iout import metadator as meta


# ---------------------------------------------------------------------------
# Whitelist validation tests for str_fileid_to_eval
# ---------------------------------------------------------------------------

def test_allowed_message_import():
    """msg.messages.py::PrepareRequest() succeeds with message allowlist."""
    from neurobooth_os.msg.messages import PrepareRequest
    result = meta.str_fileid_to_eval(
        "msg.messages.py::PrepareRequest()",
        allowed_modules=meta._ALLOWED_MESSAGE_MODULES,
    )
    assert result is PrepareRequest


def test_disallowed_module_raises():
    """Arbitrary module like os.py::system() is rejected."""
    with pytest.raises(ValueError, match="not in the allowed import list"):
        meta.str_fileid_to_eval(
            "os.py::system()",
            allowed_modules=meta._ALLOWED_MESSAGE_MODULES,
        )


def test_task_prefix_matching():
    """tasks.MOT.task.py::MOT() succeeds with task allowlist (prefix match on 'tasks')."""
    from neurobooth_os.tasks.MOT.task import MOT
    result = meta.str_fileid_to_eval(
        "tasks.MOT.task.py::MOT()",
        allowed_modules=meta._ALLOWED_TASK_MODULES,
    )
    assert result is MOT


def test_cross_category_blocked():
    """Device module is blocked by the message allowlist."""
    with pytest.raises(ValueError, match="not in the allowed import list"):
        meta.str_fileid_to_eval(
            "iout.lsl_streamer.py::start_eyelink_stream()",
            allowed_modules=meta._ALLOWED_MESSAGE_MODULES,
        )


def test_none_allows_all():
    """Omitting allowed_modules disables validation (backward compat)."""
    from neurobooth_os.msg.messages import PrepareRequest
    result = meta.str_fileid_to_eval("msg.messages.py::PrepareRequest()")
    assert result is PrepareRequest


def test_malformed_input_raises():
    """String without '.py::' raises ValueError."""
    with pytest.raises(ValueError, match="Malformed input"):
        meta.str_fileid_to_eval("msg.messages.PrepareRequest()")


def test_prefix_boundary():
    """frozenset({'msg.messages'}) must NOT match 'msg.messages_evil'."""
    with pytest.raises(ValueError, match="not in the allowed import list"):
        meta.str_fileid_to_eval(
            "msg.messages_evil.py::Exploit()",
            allowed_modules=meta._ALLOWED_MESSAGE_MODULES,
        )
