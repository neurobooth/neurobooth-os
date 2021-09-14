import io
import sys
import socket

from neurobooth_os.netcomm.client import socket_message


def _get_fprint(node_name):
    """Return function to capture prints for sending to ctr"""
    old_stdout = sys.stdout
    sys.stdout = mystdout = io.StringIO()

    def send_stdout():
        try:
            msg = mystdout.getvalue()
            if msg == "":
                return
            socket_message(f"{node_name}: {msg} ", "control")
            mystdout.truncate(0)
            mystdout.seek(0)
        except Exception as e:
            print(e)

    def fprint(str_print):
        print(str_print)
        send_stdout()

    return fprint, old_stdout


def get_client_messages(s1, fprint, old_stdout, port=12347, host='localhost'):
    """Create server and get messages from client.

    Parameters
    ----------
    s1 : instance of socket.Socket
        The socket object
    port : int
        The port
    host : str
        The host

    Returns
    -------
    data : str
        Yields the data.
    """

    s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s1.bind((host, port))
    print("socket binded to port", port)

    # put the socket into listening mode
    s1.listen(5)
    print("socket is listening")

    # Signal event to change init_serv button to green
    fprint ("UPDATOR:-init_servs-")

    streams = {}
    # a forever loop until client wants to exit
    while True:

        # establish connection with client
        try:
            c, addr = s1.accept()
            data = c.recv(1024)
        except:
            continue

        if not data:
            sys.stdout = old_stdout
            print("Connection fault, closing Stim server")
            break

        data = data.decode("utf-8")
        yield data
