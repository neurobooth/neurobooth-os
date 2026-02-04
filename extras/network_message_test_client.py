import argparse
from time import sleep

# from neurobooth_os.netcomm import socket_message
import neurobooth_os.config as cfg


# def main() -> None:
#     cfg.load_config()
#     args = parse_arguments()
#
#     print(f'Sending {args.N} messages...')
#     for i in range(args.N):
#         socket_message(str(i), args.host)
#         sleep(0.02)
#
#     socket_message('close', args.host)
#     print('Done.')


# def parse_arguments() -> argparse.Namespace:
#     parser = argparse.ArgumentParser(description='Send simple messages to the test server.')
#     parser.add_argument(
#         '-N',
#         type=int,
#         default=100,
#         help='The number of messages to send to the server.',
#     )
#     parser.add_argument(
#         '--host',
#         type=str,
#         required=True,
#         help='The machine the test server is running on (e.g., control)'
#     )
#     return parser.parse_args()


# if __name__ == '__main__':
#     main()
