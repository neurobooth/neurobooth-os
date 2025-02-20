from typing import List

from neurobooth_os.netcomm import (
    start_server,
    kill_pid_txt,
)


def start_servers(nodes: List[str]):
    """Start servers

    Parameters
    ----------
    nodes : list
        The nodes at which to start server
    """
    kill_pid_txt()
    for node in nodes:
        start_server(node)
