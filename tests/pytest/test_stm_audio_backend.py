"""STM's audio backend preference must name a backend the installed PsychoPy knows.

PsychoPy 2025 and later match backend names case-sensitively. STM set
``prefs.hardware["audioLib"] = ["PTB"]``, which older PsychoPy accepted and
the current one rejects -- but only when a task plays its first countdown tone,
so the server started, prepared devices and presented instructions before the
task loop died with ModuleNotFoundError.
"""
from psychopy.preferences import prefs
from psychopy.sound import Sound

import neurobooth_os.server_stm  # noqa: F401 -- sets prefs.hardware["audioLib"] on import


def test_stm_audio_backend_resolves_to_psychtoolbox() -> None:
    backend_module = Sound.resolveBackend()

    assert backend_module.__name__ == "psychopy.sound.backend_ptb", prefs.hardware["audioLib"]
