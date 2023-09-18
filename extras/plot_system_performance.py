import os
import argparse
import numpy as np
import pandas as pd
import json
import re
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
from typing import List


# Log file name patterns
PERFORMANCE_LOG_PATTERN = re.compile(r'(.*)_system_resource_(.*_.*)\.log')
SESSION_LOG_PATTERN = re.compile(r'(.*)_session_(.*_.*)\.log')

# Log entry patterns
PERFORMANCE_LOG_JSON_PATTERN = re.compile(r'\[(.*)] JSON> (.*)')
TASK_START_PATTERNS = {
    'ACQ': re.compile(r'\|INFO\| \[(.*)] .*> MESSAGE RECEIVED: record_start::.*::(.*)'),
    'STM': re.compile(r'\|INFO\| \[(.*)] .*> STARTING TASK: (.*)'),
}
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S,%f'

# Byte Unit Definitions
GiB = 1 << 30
MiB = 1 << 20


def main() -> None:
    args = parse_arguments()
    for server_name in args.server_names:
        print(f'Creating plots for {server_name}')
        figure = plot_system_performance(args.session_dir, server_name)

        if args.interactive:
            plt.show()
            continue

        figure.savefig(os.path.join(args.figure_dir, f'{server_name}_system_resource.svg'))
        figure.savefig(os.path.join(args.figure_dir, f'{server_name}_system_resource.png'))
        plt.close(figure)


def plot_system_performance(session_dir: str, server_name: str) -> plt.Figure:
    assert server_name in ['ACQ', 'STM'], 'Only ACQ and STM logs are supported at the moment.'
    performance_log = parse_performance_logs(session_dir, server_name)
    task_log = parse_session_logs(session_dir, server_name, TASK_START_PATTERNS[server_name])
    return create_performance_figure(performance_log, task_log)


def identify_matching_files(session_dir: str, server_name: str, pattern) -> List[str]:
    """
    Identity a list of files in the session directory matching the given server name and file name pattern.
    :param session_dir: The session directory to search.
    :param server_name: Only keep files from the specified server (e.g., ACQ)
    :param pattern: The regex pattern to match. The first match should be the server name, the second the timestamp.
    :returns: A list of matching files, sorted in ascending order by timestamp.
    """
    log_files, timestamps = [], []
    for f in os.listdir(session_dir):
        matches = re.match(pattern, f)
        if matches is None or matches.group(1) != server_name:
            continue
        ts = datetime.strptime(matches.group(2), '%Y-%m-%d_%Hh-%Mm-%Ss')
        log_files.append(os.path.join(session_dir, f))
        timestamps.append(ts)
    return [f for _, f in sorted(zip(timestamps, log_files))]


def parse_performance_logs(session_dir: str, server_name: str) -> pd.DataFrame:
    """
    Identify and parse all system resource logs in the session directory for a given server.
    :param session_dir: The session directory to search.
    :param server_name: The server of interest (e.g., ACQ)
    :returns: A data frame containing performance metric time-series extracted from all matching logs.
    """
    # Parse through all the "JSON>" lines in each system resource log
    timestamps = []
    json_data = []
    for log_file in identify_matching_files(session_dir, server_name, PERFORMANCE_LOG_PATTERN):
        with open(log_file, 'r') as f:
            line_matches = [re.match(PERFORMANCE_LOG_JSON_PATTERN, line) for line in f.readlines()]
        json_lines = [(m.group(1), m.group(2)) for m in line_matches if m is not None]
        for timestamp, json_str in json_lines:
            timestamp = datetime.strptime(timestamp, LOG_DATE_FORMAT)
            timestamp = timestamp.timestamp()  # Convert to seconds since epoch
            timestamps.append(timestamp)
            json_data.append(json.loads(json_str))

    # Reorganize the extracted data into a DataFrame
    df = pd.DataFrame(json_data)
    df['Timestamps'] = timestamps
    return df


def parse_session_logs(session_dir: str, server_name: str, task_start_pattern) -> pd.DataFrame:
    """
    Identify and parse task start times from all session logs in the session directory for a given server.
    :param session_dir: The session directory to search.
    :param server_name: The server of interest (e.g., ACQ)
    :param task_start_pattern: A regex pattern matching the start of each task.
        The first match should be the timestamp, the second the task name.
    :returns: A data frame containing task names and the time each task began.
    """
    # Parse through lines containing a string signifying task start
    tasks = []
    task_starts = []
    for log_file in identify_matching_files(session_dir, server_name, SESSION_LOG_PATTERN):
        with open(log_file, 'r') as f:
            line_matches = [re.match(task_start_pattern, line) for line in f.readlines()]
        task_start_lines = [(m.group(1), m.group(2)) for m in line_matches if m is not None]
        for timestamp, task_name in task_start_lines:
            timestamp = datetime.strptime(timestamp, LOG_DATE_FORMAT)
            timestamp = timestamp.timestamp()  # Convert to seconds since epoch
            task_starts.append(timestamp)
            tasks.append(task_name)

    # Reorganize the extracted data into a DataFrame
    return pd.DataFrame.from_dict({
        'Task': tasks,
        'StartTime': task_starts,
    })


def create_performance_figure(
        performance_log: pd.DataFrame,
        task_log: pd.DataFrame,
        subfigure_width: float = 30,
        subfigure_height: float = 4,
        fontsize: float = 12,
) -> plt.Figure:
    fig, axs = plt.subplots(5, 1, figsize=(subfigure_width, 5*subfigure_height))
    vertical_centers = {}
    ts = performance_log['Timestamps']
    delta_ts = np.diff(ts)

    # Plot CPU
    ax = axs[0]
    colors = plt.cm.get_cmap('tab20').colors
    cpu_cols = [c for c in performance_log.columns if 'CPU' in c]
    for i, col in enumerate(cpu_cols):
        ax.plot(ts, performance_log[col].to_numpy(), c=colors[i % (len(colors))], linewidth=0.5, label=col[:-4])
    ax.legend(ncol=len(cpu_cols)//4, loc='upper left', fontsize=fontsize)
    ax.set_ylabel('CPU Usage (%)', fontsize=fontsize)
    ax.set_yticks(np.linspace(0, 100, 6))
    vertical_centers[0] = 50

    # Plot RAM
    ax = axs[1]
    ram_usage = performance_log['RAM_used'].to_numpy() / GiB
    ram_total = performance_log['RAM_total'].to_numpy().max() / GiB
    ax.plot(ts, ram_usage, linewidth=1)
    ax.set_ylabel('Ram Usage (GiB)', fontsize=fontsize)
    ax.set_yticks(np.linspace(0, ram_total, 6))
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    vertical_centers[1] = ram_total / 2

    # Plot Swap
    ax = axs[2]
    swap_usage = performance_log['SWAP_used'].to_numpy() / GiB
    swap_total = performance_log['SWAP_total'].to_numpy().max() / GiB
    ax.plot(ts, swap_usage, linewidth=1)
    ax.set_ylabel('Swap Usage (GiB)', fontsize=fontsize)
    ax.set_yticks(np.linspace(0, swap_total, 6))
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    vertical_centers[2] = swap_total / 2

    # Plot Disk IO
    ax = axs[3]
    colors = plt.cm.get_cmap('Paired').colors
    disk_cols = [re.match('Disk_(\d+)_name', c) for c in performance_log.columns]
    disk_nos = [int(m.group(1)) for m in disk_cols if m is not None]
    max_ = 0
    for i, disk_no in enumerate(sorted(disk_nos)):
        read_col = f'Disk_{disk_no}_bytes_read'
        write_col = f'Disk_{disk_no}_bytes_written'
        read_per_sec = np.diff(performance_log[read_col].to_numpy() / MiB) / delta_ts
        read_per_sec = np.r_[0, read_per_sec]
        write_per_sec = np.diff(performance_log[write_col].to_numpy() / MiB) / delta_ts
        write_per_sec = np.r_[0, write_per_sec]
        ax.plot(ts, read_per_sec, linewidth=0.75, c=colors[i*2], label=f'Disk {disk_no} Read')
        ax.plot(ts, write_per_sec, linewidth=0.75, c=colors[i*2+1], label=f'Disk {disk_no} Write')
        max_ = max(max_, read_per_sec.max(), write_per_sec.max())
    ax.legend(ncol=2, loc='upper left', fontsize=fontsize)
    ax.set_ylabel('Disk IO (MiB / s)', fontsize=fontsize)
    ax.set_yticks(np.linspace(0, max_, 6))
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    vertical_centers[3] = max_ / 2

    # Plot Network IO
    ax = axs[4]
    colors = plt.cm.get_cmap('Paired').colors
    read_col = 'Network_bytes_received'
    write_col = 'Network_bytes_sent'
    read_per_sec = np.diff(performance_log[read_col].to_numpy() / MiB) / delta_ts
    read_per_sec = np.r_[0, read_per_sec]
    write_per_sec = np.diff(performance_log[write_col].to_numpy() / MiB) / delta_ts
    write_per_sec = np.r_[0, write_per_sec]
    ax.plot(ts, read_per_sec, linewidth=0.75, c=colors[0], label=f'Network Read')
    ax.plot(ts, write_per_sec, linewidth=0.75, c=colors[1], label=f'Network Write')
    max_ = max(read_per_sec.max(), write_per_sec.max())
    ax.legend(ncol=2, loc='upper left', fontsize=fontsize)
    ax.set_ylabel('Network IO (MiB / s)', fontsize=fontsize)
    ax.set_yticks(np.linspace(0, max_, 6))
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    vertical_centers[4] = max_ / 2

    # Set common axes attributes
    for ax in axs:
        ax.set_xlabel('Time (epoch; s)', fontsize=fontsize)
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(fontsize)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(fontsize)

            # Overlay task start on each subfigure
    for i, ax in enumerate(axs):
        for task_name, task_start in zip(task_log['Task'].to_numpy(), task_log['StartTime'].to_numpy()):
            ax.axvline(task_start, color='k', linewidth=1)
            ax.text(
                task_start, vertical_centers[i], task_name,
                rotation=90, verticalalignment='center', fontsize=fontsize
            )

    fig.tight_layout()
    return fig


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Parse and plot system resource logs from a single session.')
    parser.add_argument(
        '--session-dir',
        type=str,
        default='.',
        help='The path to the session directory. Assumes the current directory if not specified.',
    )
    parser.add_argument(
        '--figure-dir',
        type=str,
        default=None,
        help='The path the figure output directory. Assumes the session directory of not specified.',
    )
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Interactively display the figure instead of saving it to a file.',
    )
    parser.add_argument(
        '--acq',
        action='append_const',
        dest='server_names',
        const='ACQ',
        help='Plot data for ACQ.'
    )
    parser.add_argument(
        '--stm',
        action='append_const',
        dest='server_names',
        const='STM',
        help='Plot data for STM.'
    )
    args = parser.parse_args()

    args.session_dir = os.path.abspath(args.session_dir)
    if args.figure_dir is None:
        args.figure_dir = args.session_dir
    else:
        args.figure_dir = os.path.abspath(args.figure_dir)

    if not args.server_names:
        parser.error('No server specified. Try adding --acq or --stm.')

    return args


if __name__ == '__main__':
    main()
