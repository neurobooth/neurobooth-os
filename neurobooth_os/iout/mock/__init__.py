"""Hardware mocks for laptop/CI testing without real devices.

Each mock module imports its corresponding real device module's top half
(class definitions only — hardware imports are guarded in the real
modules), subclasses the real ``Device``, and overrides hardware-touching
hooks. The matching mock ``DeviceArgs`` subclass lives in
``stim_param_reader.py`` and registers via
:func:`neurobooth_os.iout.mock_substitution.register_mock` at import time.

The package is intentionally separate from ``iout/mock_device.py``, which
contains base-class testing scaffolding (``MockStreamDevice`` /
``MockRecordingDevice``) for ``Device`` itself, not hardware mocks.
"""
