"""Tests for machine-role detection in :mod:`neurobooth_os.config`.

Role detection used to read ``USERPROFILE``, which does not exist off Windows,
so these tests cover both the Windows path and the POSIX fallback regardless of
the platform the suite is running on.
"""

import pytest

from neurobooth_os import config


@pytest.fixture(autouse=True)
def clear_identity_env(monkeypatch):
    """Start every test from a known-empty environment."""
    for var in (config.NODE_ENV_VAR, "USERPROFILE", "USER", "LOGNAME"):
        monkeypatch.delenv(var, raising=False)


class TestGetServerName:
    @pytest.mark.parametrize(
        "identifier,expected",
        [
            (r"C:\Users\STM", "presentation"),
            (r"C:\Users\PARTICIPANT", "presentation"),
            (r"C:\Users\ACQ", "acquisition"),
            (r"C:\Users\CTR", "control"),
            (r"C:\Users\COORDINATOR", "control"),
            ("acq booth-3", "acquisition"),
            ("stm", "presentation"),
        ],
    )
    def test_recognised_abbreviations(self, identifier, expected):
        assert config.get_server_name(identifier) == expected

    @pytest.mark.parametrize("identifier", [None, "", "somebody laptop-7"])
    def test_absent_or_unrecognised_returns_none(self, identifier):
        """A missing identifier must return None, not raise.

        ``None.upper()`` is what this used to do on any machine without
        ``USERPROFILE``, which is every Mac and every Linux box.
        """
        assert config.get_server_name(identifier) is None


class TestLocalIdentity:
    def test_prefers_userprofile_when_present(self, monkeypatch):
        monkeypatch.setenv("USERPROFILE", r"C:\Users\ACQ")
        monkeypatch.setenv("USER", "someone-else")
        assert config.local_identity() == r"C:\Users\ACQ"

    def test_falls_back_to_user_and_hostname(self, monkeypatch):
        monkeypatch.setenv("USER", "acq")
        identity = config.local_identity()
        assert "acq" in identity
        assert identity.strip(), "identity must not be empty"

    def test_uses_logname_when_user_absent(self, monkeypatch):
        monkeypatch.setenv("LOGNAME", "ctr")
        assert "ctr" in config.local_identity()

    def test_never_returns_none(self):
        """With no environment at all, the hostname still yields a string."""
        assert isinstance(config.local_identity(), str)


class TestNodeEnvVar:
    @pytest.mark.parametrize(
        "value", ["presentation", "control", "acquisition", "acquisition_0", "acquisition_2"]
    )
    def test_canonical_names_pass_through(self, monkeypatch, value):
        monkeypatch.setenv(config.NODE_ENV_VAR, value)
        assert config.get_server_name_from_env() == value

    def test_abbreviation_is_resolved(self, monkeypatch):
        monkeypatch.setenv(config.NODE_ENV_VAR, "STM")
        assert config.get_server_name_from_env() == "presentation"

    def test_wins_over_userprofile(self, monkeypatch):
        monkeypatch.setenv("USERPROFILE", r"C:\Users\ACQ")
        monkeypatch.setenv(config.NODE_ENV_VAR, "control")
        assert config.get_server_name_from_env() == "control"

    def test_unrecognised_value_raises(self, monkeypatch):
        """An explicit wrong answer should fail loudly; an absent one should not."""
        monkeypatch.setenv(config.NODE_ENV_VAR, "banana")
        with pytest.raises(config.ConfigException) as excinfo:
            config.get_server_name_from_env()
        assert "banana" in str(excinfo.value)

    def test_unset_falls_back_to_local_identity(self, monkeypatch):
        monkeypatch.setenv("USER", "acq")
        assert config.get_server_name_from_env() == "acquisition"

    def test_unset_and_unrecognisable_returns_none(self, monkeypatch):
        monkeypatch.setenv("USER", "nobody")
        monkeypatch.setattr(config.socket, "gethostname", lambda: "some-laptop")
        assert config.get_server_name_from_env() is None
