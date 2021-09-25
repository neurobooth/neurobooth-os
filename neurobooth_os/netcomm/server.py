import io
import sys
import socket

from neurobooth_os.netcomm.client import socket_message


def get_fprint(current_node, target_node='control'):
    """Return function to capture prints for sending to target_node.

    Stdout is re-routed to target_node via socket connection.

    Parameters
    ----------
    current_node : str
        Name of the node to be displayed, e.g. STM or ACQ
    target_node : str
        PC node name defined in `secrets_info.secrets`

    Returns
    -------
    fprint_flush : callable
        Print function that send message via socket to target_node.
    old_stdout : object
        original Stdout before re-routing.

    """
    old_stdout = sys.stdout
    sys.stdout = mystdout = io.StringIO()

    def fprint_flush(print_msg=None):
        if print_msg:
            print(print_msg)
        # flush any messages in stdout to target_node
        try:
            msg = mystdout.getvalue()
            if msg == "":
                return
            socket_message(f"{current_node}: {msg} ", node_name=target_node)
            mystdout.truncate(0)
            mystdout.seek(0)
        except Exception as e:
            print(e)

    return fprint_flush, old_stdout


def get_client_messages(s1, fprint, old_stdout, port=12347, host='localhost'):
    """Create socket server and get messages from clients.

    Parameters
    ----------
    s1 : instance of socket.Socket
        The socket object
    fprint : callable
        function for printing, e.g. fprint from `get_fprint`
    port : int
        The port
    host : str
        The host. E.g., STM and ACQ

    Returns
    -------
    data : str
        Yields the data.
    conn : callable
        Socket connector for sending back data.
    """

    s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s1.bind((host, port))
    print("socket binded to port", port)

    # put the socket into listening mode
    s1.listen(5)
    print("socket is listening")

    # Signal event to change init_serv button to green
    fprint("UPDATOR:-init_servs-")

    # a forever loop until client wants to exit
    while True:

        # establish connection with client
        try:
            conn, addr = s1.accept()
            data = conn.recv(1024)
        except BaseException:
            continue

        if not data:            
            print("Connection fault, closing Stim server")
            sys.stdout = old_stdout
            s1.close()
            break

        data = data.decode("utf-8")
        yield data, conn


def get_messages_to_ctr(callback=None, host="", port=12347, *callback_args):
    """ Creates socket server and run callback with socket data string.

    Parameters
    ----------
    callback : callable
        Function that processes received socket data, by default None
    host : str, optional
        IP adrress of the socket connexion
    port : int, optional
        Port of the socket, by default 12347
    callback_args : args
        Args to pass into callback function
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    print("Ctr socket binded to port", port)

    s.listen(5)
    print("socket is listening")

    while True:
        try:
            c, addr = s.accept()
            data = c.recv(1024)
        except BaseException:
            print("Connection fault on ctr server")
            continue

        data = data.decode("utf-8")
        # print(data)

        if callback is not None:
            callback(data, *callback_args)

        if data == "close":
            break
    s.close()
