from neurobooth_os.netcomm import (
    start_server,
    kill_pid_txt,
)


def _get_nodes(nodes):
    if isinstance(nodes, str):
        nodes = nodes
    return nodes


def start_servers(nodes=("acquisition", "presentation")):
    """Start servers

    Parameters
    ----------
    nodes : tuple, optional
        The nodes at which to start server, by default ("acquisition", "presentation")
    """
    kill_pid_txt()
    nodes = _get_nodes(nodes)
    for node in nodes:
        start_server(node)
