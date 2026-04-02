"""Wrapper that ties a psycopg2 connection to its optional SSH tunnel."""

import logging
from typing import Optional

from psycopg2.extensions import connection

logger = logging.getLogger(__name__)

# Attributes that belong to ManagedConnection itself, not the wrapped connection.
_OWN_ATTRS = frozenset({"_conn", "_tunnel", "_closed"})


class ManagedConnection:
    """A psycopg2 connection paired with an optional SSH tunnel.

    Delegates attribute access to the underlying connection so callers
    can use it exactly like a plain ``psycopg2.extensions.connection``.
    On :meth:`close` (or context-manager exit), the connection is closed
    **and** the tunnel is stopped.

    Args:
        conn: A live psycopg2 connection.
        tunnel: An ``SSHTunnelForwarder`` instance, or ``None`` when no
            tunnel is in use.
    """

    def __init__(
        self,
        conn: connection,
        tunnel: Optional[object] = None,
    ) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_tunnel", tunnel)
        object.__setattr__(self, "_closed", False)

    # --- Delegation --------------------------------------------------------

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value) -> None:
        if name in _OWN_ATTRS:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    # --- Context manager ---------------------------------------------------

    def __enter__(self) -> "ManagedConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Let psycopg2 handle transaction commit/rollback first.
        try:
            self._conn.__exit__(exc_type, exc_val, exc_tb)
        except Exception:
            # Connection may already be closed or broken; log and continue
            # so that we still clean up the tunnel.
            logger.debug("Error during connection __exit__", exc_info=True)
        self.close()

    # --- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the connection and stop the SSH tunnel (if any).

        Safe to call multiple times.
        """
        if self._closed:
            return
        self._closed = True

        try:
            if not self._conn.closed:
                self._conn.close()
        except Exception:
            logger.debug("Error closing connection", exc_info=True)

        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception:
                logger.debug("Error stopping SSH tunnel", exc_info=True)

    @property
    def closed(self) -> bool:
        """True after :meth:`close` has been called."""
        return self._closed

    def __del__(self) -> None:
        # Best-effort cleanup for connections that were never explicitly
        # closed (e.g. daemon threads killed on process exit).
        if not self._closed:
            self.close()
