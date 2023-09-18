"""Retrieve log files to local folder for analysis.

All log files are retrieved, as determined by the string '.log' in the file name
Files are retrieved using SFTP.
Further filtering of log types, date ranges, etc. should be performed on the local log copies as needed.

"""
import os
from stat import S_ISDIR, S_ISREG
import paramiko
import argparse


DESCRIPTION = "Securely retrieve log flies from a remove drive for analysis."

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)

    group = parser.add_argument_group(title='Device Discovery')
    group.add_argument(
        '--url',
        default='neurodoor.nmr.mgh.harvard.edu',
        type=str,
        help='The address of the remote server holding the log files.'
    )
    group.add_argument(
        '--user',
        default=None,
        required=True,
        type=str,
        help='The sftp user performing the transfer.'
    )
    group.add_argument(
        '--pwd',
        default=None,
        required=True,
        type=str,
        help='The sftp password for the user performing the transfer.'
    )
    group.add_argument(
        '--remote-dir',
        default=None,
        required=True,
        type=str,
        help='The absolute path to the folder from which the logs will be retrieved.'
    )

    group = parser.add_argument_group(title='Reset Arguments')
    group.add_argument(
        '--local-dir',
        default=None,
        required=True,
        type=str,
        help='The absolute path to the folder where the logs are to be stored.'
    )

    args = parser.parse_args()

    return args


def main():

    args = parse_arguments()
    sftp_url = args.url
    sftp_user = args.user
    sftp_pass = args.pwd
    remote_dir = args.remote_dir
    local_dir = args.local_dir

    if not os.path.exists(local_dir):
        os.mkdir(local_dir)

    ssh = paramiko.SSHClient()
    # automatically add keys without requiring human intervention
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(sftp_url, username=sftp_user, password=sftp_pass)

    # Collect the names of the remote folders that may contain logs
    folders = []

    sftp = ssh.open_sftp()

    for entry in sftp.listdir_attr(remote_dir):
        mode = entry.st_mode
        if S_ISDIR(mode):
            folders.append(entry.filename)

    scp =  ssh.open_sftp()

    for folder in folders:
        remote_session_dir = remote_dir + "/" + folder
        local_session_dir = local_dir + "/" + folder
        for entry in sftp.listdir_attr(remote_session_dir):
            mode = entry.st_mode
            if S_ISREG(mode):
                if entry.filename.endswith(".log"):
                    if not os.path.exists(local_session_dir):
                        os.mkdir(local_session_dir)
                    remote_log_file = remote_session_dir + "/" + entry.filename
                    local_log_file = local_session_dir + "/" + entry.filename
                    print(f"Copying log file: {entry.filename}.")
                    scp.get(remote_log_file, local_log_file)

    scp.close()
    ssh.close()


if __name__ == "__main__":
    main()
