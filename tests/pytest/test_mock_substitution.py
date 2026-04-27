"""Tests for the mock-device substitution mechanism.

Covers:
- ``register_mock`` registry behaviour and the subclass-of guard.
- ``active_mock_targets`` source priority (env var > config field).
- ``apply_mock_substitution`` returns the original instance when no
  substitution applies, and a mock instance when it does.
- The lazy hardware imports in ``mbient.py`` and ``eyelink_tracker.py``
  do not require the underlying SDKs to be installed at import time.
"""

import builtins
import importlib
import os
import sys
from typing import Type
from unittest.mock import patch

import pytest

from neurobooth_os.iout import mock_substitution as ms
from neurobooth_os.iout.stim_param_reader import DeviceArgs


# ---------------------------------------------------------------------------
# Test-only DeviceArgs subclasses (don't pollute the real registry).
# ---------------------------------------------------------------------------

class _RealForTest(DeviceArgs):
    @classmethod
    def device_class(cls):
        # Returns a stand-in class whose __name__ controls active-target
        # matching. Tests can monkeypatch this.
        return _RealDeviceCls


class _MockForTest(_RealForTest):
    @classmethod
    def device_class(cls):
        return _MockDeviceCls


class _RealDeviceCls:
    pass


class _MockDeviceCls:
    pass


def _make_real(env_devices=None) -> _RealForTest:
    """Build a _RealForTest instance with the minimum fields populated."""
    return _RealForTest(
        ENV_devices=env_devices or {"d1": {}},
        device_id="d1",
        arg_parser="iout.stim_param_reader.py::_RealForTest()",
        sensor_ids=[],
    )


# ---------------------------------------------------------------------------
# Fixtures: keep the global registry clean between tests.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(ms.MOCK_REGISTRY)
    ms.MOCK_REGISTRY.clear()
    yield
    ms.MOCK_REGISTRY.clear()
    ms.MOCK_REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ms.ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# Registry behaviour
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_then_lookup(self):
        ms.register_mock(_RealForTest, _MockForTest)
        assert ms.MOCK_REGISTRY[_RealForTest] is _MockForTest

    def test_subclass_guard_rejects_non_subclass(self):
        class _Unrelated(DeviceArgs):
            pass
        with pytest.raises(TypeError, match="must be a subclass"):
            ms.register_mock(_RealForTest, _Unrelated)


# ---------------------------------------------------------------------------
# active_mock_targets parsing + priority
# ---------------------------------------------------------------------------

class TestActiveMockTargets:
    def test_unset_returns_empty(self):
        assert ms.active_mock_targets() == set()

    def test_env_var_single(self, monkeypatch):
        monkeypatch.setenv(ms.ENV_VAR, "Mbient")
        assert ms.active_mock_targets() == {"Mbient"}

    def test_env_var_multi_with_whitespace(self, monkeypatch):
        monkeypatch.setenv(ms.ENV_VAR, " Mbient , IPhone , EyeTracker ")
        assert ms.active_mock_targets() == {"Mbient", "IPhone", "EyeTracker"}

    def test_env_var_all_sentinel(self, monkeypatch):
        monkeypatch.setenv(ms.ENV_VAR, "all")
        assert ms.active_mock_targets() == {"all"}

    def test_env_var_empty_string_is_empty(self, monkeypatch):
        monkeypatch.setenv(ms.ENV_VAR, "")
        # Empty string means "set but empty"; treat as no targets.
        assert ms.active_mock_targets() == set()

    def test_config_fallback_when_env_unset(self, monkeypatch):
        from neurobooth_os import config as cfg
        # Inject a fake neurobooth_config exposing mock_devices.
        class _Stub:
            mock_devices = ["IPhone"]
        monkeypatch.setattr(cfg, "neurobooth_config", _Stub())
        assert ms.active_mock_targets() == {"IPhone"}

    def test_env_var_wins_over_config(self, monkeypatch):
        from neurobooth_os import config as cfg
        class _Stub:
            mock_devices = ["IPhone"]
        monkeypatch.setattr(cfg, "neurobooth_config", _Stub())
        monkeypatch.setenv(ms.ENV_VAR, "Mbient")
        assert ms.active_mock_targets() == {"Mbient"}

    def test_unloaded_config_returns_empty(self, monkeypatch):
        from neurobooth_os import config as cfg
        # Simulate config not yet loaded — neurobooth_config is None.
        monkeypatch.setattr(cfg, "neurobooth_config", None)
        assert ms.active_mock_targets() == set()


# ---------------------------------------------------------------------------
# apply_mock_substitution
# ---------------------------------------------------------------------------

class TestApplySubstitution:
    def test_no_active_returns_original(self):
        ms.register_mock(_RealForTest, _MockForTest)
        real = _make_real()
        result = ms.apply_mock_substitution(real, active=set())
        assert result is real

    def test_unregistered_class_returns_original(self):
        real = _make_real()
        result = ms.apply_mock_substitution(real, active={"_RealDeviceCls"})
        assert result is real

    def test_registered_and_active_returns_mock(self):
        ms.register_mock(_RealForTest, _MockForTest)
        real = _make_real()
        result = ms.apply_mock_substitution(real, active={"_RealDeviceCls"})
        assert isinstance(result, _MockForTest)
        # Field values preserved via model_construct.
        assert result.device_id == "d1"

    def test_all_sentinel_substitutes(self):
        ms.register_mock(_RealForTest, _MockForTest)
        real = _make_real()
        result = ms.apply_mock_substitution(real, active={"all"})
        assert isinstance(result, _MockForTest)

    def test_active_set_for_other_class_skips_substitution(self):
        ms.register_mock(_RealForTest, _MockForTest)
        real = _make_real()
        result = ms.apply_mock_substitution(
            real, active={"SomeOtherDeviceCls"})
        assert result is real


# ---------------------------------------------------------------------------
# Hardware-less import smoke tests for the lazy imports added in Phase 0a.
# ---------------------------------------------------------------------------

def _import_module_without(*blocked: str) -> object:
    """Re-import target modules with certain top-level imports blocked.

    Returns the freshly-imported module(s).
    """
    blocked_set = set(blocked)
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        for b in blocked_set:
            if name == b or name.startswith(b + "."):
                raise ImportError(f"simulated absence of {name}")
        return orig_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        for k in list(sys.modules):
            if k in blocked_set or k.startswith(tuple(b + "." for b in blocked_set)):
                del sys.modules[k]
        # Drop the cached module so it re-imports under the patched __import__.
        for cached in list(sys.modules):
            if "iout.mbient" in cached or "iout.eyelink_tracker" in cached:
                del sys.modules[cached]
        import neurobooth_os.iout.mbient as mbient_mod
        import neurobooth_os.iout.eyelink_tracker as eyelink_mod
        return mbient_mod, eyelink_mod
    finally:
        builtins.__import__ = orig_import


class TestLazyHardwareImports:
    def test_mbient_imports_without_mbientlab(self):
        mbient_mod, _ = _import_module_without("mbientlab")
        assert mbient_mod._HAS_MBIENTLAB is False
        # The Mbient class must be defined (so MockMbient can subclass it).
        assert mbient_mod.Mbient is not None

    def test_eyelink_imports_without_pylink(self):
        _, eyelink_mod = _import_module_without("pylink")
        assert eyelink_mod._HAS_PYLINK is False
        assert eyelink_mod.EyeTracker is not None
