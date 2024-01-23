import io
import sys
import socket

from neurobooth_os.netcomm import socket_message


def get_fprint(current_node, target_node="control"):
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


class NewStdout:
    def __init__(self, current_node, target_node="control", terminal_print=False):
        """Class that substitutes stdout pipe, sends message to socket and can print to terminal.

        Parameters
        ----------
        current_node : str
            Name of the current node, will be added in the message: {current_node}:::{msg}
        target_node : str, optional
            name of the node to whick send socket message, by default 'control'
        terminal_print : bool, optional
            if True the message will be printed in the terminal, by default False
        """

        self.terminal = sys.stdout
        self.current_node = current_node
        self.target_node = target_node
        self.terminal_print = terminal_print

    def write(self, message):
        "write message to terminal and socket."
        # Print in the terminal
        if self.terminal_print:
            self.terminal.write(message)

        # send to socket if message not empty
        if message not in ["\n", ""]:
            try:
                socket_message(
                    f"{self.current_node}:::{message}", node_name=self.target_node
                )
            except:
                try:
                    socket_message(
                        f"{self.current_node}:::{message}", node_name=self.target_node
                    )
                except:
                    self.terminal.write(
                        f"\n***MESSAGE*** ###{message}### not sent to {self.target_node}\n"
                    )

    def flush(self):
        # For compatibility, just pass
        pass


def get_client_messages(s1: socket, port: int, host: str):
    """Create socket server and get messages from clients.

    Parameters
    ----------
    s1 : instance of socket.Socket
        The socket object
    port : int
        The port
    host : str
        The socket address, '' for local host

    Returns
    -------
    data : str
        Yields the data.
    conn : callable
        Socket connector for sending back data.
    """

    s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s1.bind((host, port))
    print("socket bound to port", port)

    # put the socket into listening mode
    s1.listen(5)
    print("socket is listening")

    # Signal event to change init_serv button to green
    print("UPDATOR:-init_servs-")

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
            break

        data = data.decode("utf-8")
        yield data, conn


def get_messages_to_ctr(
    callback=None, host="", port=12347, *callback_args
):
    """Creates socket server and run callback with socket data string.

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
            # print("Connection fault on ctr server")
            continue

        data = data.decode("utf-8")
        print(data)
        if callback is not None:
            callback(data, *callback_args)

        if data == "close":
            break
    s.close()


def get_data_with_timeout(s1: socket, timeout: float = 0.1):
    """Change socket timeout, get data, and remove timeout.

    Parameters
    ----------
    s1 : socket.socket instance
    timeout: float
        Time to wait for message
    """
    s1.settimeout(timeout)

    try:
        conn, _ = s1.accept()
        data = conn.recv(1024)
        data = data.decode("utf-8")
    except socket.timeout:
        data = None

    s1.settimeout(None)
    return data
