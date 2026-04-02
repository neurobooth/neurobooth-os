"""Tests for ManagedConnection wrapper."""

from unittest.mock import MagicMock, patch
import pytest

from neurobooth_os.iout.db_connection import ManagedConnection


@pytest.fixture
def mock_conn():
    conn = MagicMock()
    conn.closed = False
    return conn


@pytest.fixture
def mock_tunnel():
    return MagicMock()


class TestDelegation:
    def test_getattr_delegates_to_connection(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        mc.cursor()
        mock_conn.cursor.assert_called_once()

    def test_setattr_delegates_unknown_attrs(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        mc.autocommit = True
        assert mock_conn.autocommit is True

    def test_setattr_keeps_own_attrs(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        # _closed is an own attr -- should not delegate
        assert mc._closed is False


class TestClose:
    def test_closes_connection(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        mc.close()
        mock_conn.close.assert_called_once()

    def test_stops_tunnel(self, mock_conn, mock_tunnel):
        mc = ManagedConnection(mock_conn, mock_tunnel)
        mc.close()
        mock_tunnel.stop.assert_called_once()

    def test_no_tunnel_is_fine(self, mock_conn):
        mc = ManagedConnection(mock_conn, tunnel=None)
        mc.close()
        mock_conn.close.assert_called_once()

    def test_idempotent(self, mock_conn, mock_tunnel):
        mc = ManagedConnection(mock_conn, mock_tunnel)
        mc.close()
        mc.close()
        mock_conn.close.assert_called_once()
        mock_tunnel.stop.assert_called_once()

    def test_closed_property(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        assert mc.closed is False
        mc.close()
        assert mc.closed is True

    def test_close_handles_already_closed_connection(self, mock_conn):
        mock_conn.closed = True
        mc = ManagedConnection(mock_conn)
        mc.close()  # Should not raise
        mock_conn.close.assert_not_called()


class TestContextManager:
    def test_enter_returns_self(self, mock_conn):
        mc = ManagedConnection(mock_conn)
        assert mc.__enter__() is mc

    def test_exit_commits_and_closes(self, mock_conn, mock_tunnel):
        mc = ManagedConnection(mock_conn, mock_tunnel)
        mc.__enter__()
        mc.__exit__(None, None, None)
        mock_conn.__exit__.assert_called_once_with(None, None, None)
        mock_conn.close.assert_called_once()
        mock_tunnel.stop.assert_called_once()

    def test_exit_with_exception(self, mock_conn, mock_tunnel):
        mc = ManagedConnection(mock_conn, mock_tunnel)
        mc.__enter__()
        exc = ValueError("test")
        mc.__exit__(type(exc), exc, None)
        mock_conn.__exit__.assert_called_once_with(type(exc), exc, None)
        mock_conn.close.assert_called_once()
        mock_tunnel.stop.assert_called_once()

    def test_exit_cleans_up_even_if_conn_exit_fails(self, mock_conn, mock_tunnel):
        mock_conn.__exit__.side_effect = RuntimeError("boom")
        mc = ManagedConnection(mock_conn, mock_tunnel)
        mc.__enter__()
        mc.__exit__(None, None, None)
        # Tunnel should still be stopped despite connection __exit__ failure
        mock_tunnel.stop.assert_called_once()

    def test_with_statement(self, mock_conn, mock_tunnel):
        mc = ManagedConnection(mock_conn, mock_tunnel)
        with mc as c:
            assert c is mc
            c.cursor()
        mock_conn.cursor.assert_called_once()
        mock_conn.close.assert_called_once()
        mock_tunnel.stop.assert_called_once()
