"""Mock-device substitution registry and resolution helpers.

Mocks register themselves at import time via :func:`register_mock`, mapping a
real ``DeviceArgs`` subclass to a mock counterpart. ``DeviceManager`` consults
:func:`active_mock_targets` and :func:`apply_mock_substitution` during
``create_streams`` to swap real device args for mock ones before
``device_class()`` resolution runs.

The active set comes from two sources, in priority order:

1. ``NB_MOCK_DEVICES`` environment variable — comma-separated device-class
   names (``Mbient,IPhone,EyeTracker``) or the special value ``all``.
2. ``NeuroboothConfig.mock_devices`` field — same shape, persisted in
   ``neurobooth_os_config.yaml``.

The env var wins when both are set so a developer can always force-disable
or force-enable mocks for a single run without editing config files.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Set, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from neurobooth_os.iout.stim_param_reader import DeviceArgs


# real DeviceArgs subclass -> mock DeviceArgs subclass
MOCK_REGISTRY: Dict[Type["DeviceArgs"], Type["DeviceArgs"]] = {}

# Sentinel that means "every registered mock target is active".
_ALL = "all"

ENV_VAR = "NB_MOCK_DEVICES"


def register_mock(real_cls: Type["DeviceArgs"],
                  mock_cls: Type["DeviceArgs"]) -> None:
    """Register a mock DeviceArgs subclass as a substitute for a real one.

    Called at module-import time from each mock module. ``mock_cls`` must
    be a subclass of ``real_cls`` so all of ``real_cls``'s field validation
    still applies; this is enforced at registration time.
    """
    if not issubclass(mock_cls, real_cls):
        raise TypeError(
            f"{mock_cls.__name__} must be a subclass of {real_cls.__name__} "
            "to register as its mock"
        )
    MOCK_REGISTRY[real_cls] = mock_cls


def _parse_target_list(raw: Optional[str]) -> Set[str]:
    """Parse ``"Mbient,IPhone"`` or ``"all"`` into a normalised set."""
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def active_mock_targets() -> Set[str]:
    """Return the set of mock-target names active for this run.

    Sources, in priority order: ``NB_MOCK_DEVICES`` env var, then
    ``NeuroboothConfig.mock_devices``. The result contains *device-class
    names* (e.g. ``"Mbient"``, ``"IPhone"``, ``"EyeTracker"``) — not
    device IDs — and may contain the literal ``"all"`` sentinel.

    Returns an empty set when neither source is set or the config has not
    been loaded.
    """
    env_raw = os.environ.get(ENV_VAR)
    if env_raw is not None:
        return _parse_target_list(env_raw)

    # Fallback to the config field. Config may not be loaded yet (e.g. unit
    # tests that import this module before calling load_config); treat that
    # as "no config-driven targets".
    try:
        from neurobooth_os import config as cfg
        targets = getattr(cfg.neurobooth_config, "mock_devices", None)
    except Exception:
        return set()
    if not targets:
        return set()
    return {t.strip() for t in targets if t and t.strip()}


def _is_target_active(real_cls: Type["DeviceArgs"], active: Set[str]) -> bool:
    """Whether the mock for ``real_cls`` should be substituted in this run."""
    if not active:
        return False
    if _ALL in active:
        return True
    # Match against the resolved Device class name. We use the Device class
    # (not the DeviceArgs class name) so a user writes
    # NB_MOCK_DEVICES=Mbient rather than NB_MOCK_DEVICES=MbientDeviceArgs.
    try:
        device_cls_name = real_cls.device_class().__name__
    except (NotImplementedError, ImportError, Exception):
        return False
    return device_cls_name in active


def apply_mock_substitution(device_args: "DeviceArgs",
                            active: Optional[Set[str]] = None) -> "DeviceArgs":
    """Return a mock-substituted ``DeviceArgs`` instance, or the original.

    Field values from ``device_args`` are preserved on the substituted
    instance via Pydantic ``model_construct`` — no re-validation runs, so
    fields like ``ENV_devices`` that the original loader populated stay
    intact.
    """
    if active is None:
        active = active_mock_targets()
    if not active:
        return device_args

    real_cls = type(device_args)
    if real_cls not in MOCK_REGISTRY:
        return device_args
    if not _is_target_active(real_cls, active):
        return device_args

    mock_cls = MOCK_REGISTRY[real_cls]
    # Reuse the validated field values from the real instance. model_construct
    # skips re-validation, which is what we want — the YAML already validated
    # them once.
    return mock_cls.model_construct(**device_args.model_dump())
