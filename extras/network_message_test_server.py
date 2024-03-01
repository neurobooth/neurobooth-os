import numpy as np
from threading import Lock, Thread, Event
import argparse
import signal
from typing import Optional

from neurobooth_os.netcomm import get_messages_to_ctr
import neurobooth_os.config as cfg

lock = Lock()
sigint_event = Event()
recv_array: Optional[np.ndarray] = None


def main() -> None:
    cfg.load_config()
    args = parse_arguments()

    global recv_array
    recv_array = np.zeros(args.N, dtype=bool)

    port = cfg.neurobooth_config.current_server().port
    listen_thread = Thread(
        target=get_messages_to_ctr,
        args=(
            listener_callback,
            '',
            port,
            [],
        ),
        daemon=True,
    )
    listen_thread.start()
    print(f'Listening for messages on port {port}.')

    signal.signal(signal.SIGINT, sigint_callback)
    sigint_event.wait()
    listen_thread.join(timeout=5)

    print(f'Received {recv_array.sum()}/{len(recv_array)} messages.')


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run a server to listen for the test client.')
    parser.add_argument(
        '-N',
        type=int,
        default=100,
        help='The number of messages expected from the client.',
    )
    return parser.parse_args()


def listener_callback(data: str, *args) -> None:
    if data == 'close':
        print('Close received!')
        sigint_event.set()

    data = int(data)
    with lock:
        recv_array[data] = True


def sigint_callback(*args) -> None:
    sigint_event.set()


if __name__ == '__main__':
    main()
