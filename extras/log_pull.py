import os
from stat import S_ISDIR, S_ISREG
import paramiko


def main(
    sftp_url='neurodoor.nmr.mgh.harvard.edu',
    sftp_user = 'lw412',
    sftp_pass = 'frontyard4',
    remote_dir = '/autofs/nas/neurobooth/data',
    local_dir = 'C:/neurobooth/remote-logs'
):

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
            # TODO: Make this configurable so we can get data in 2024+
            # if str(entry.filename).__contains__('_2023_'):  # logging was added in May 2023
            # print(entry.filename + " is a folder from 2023")
            folders.append(entry.filename)


    scp = ssh.open_sftp()

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
