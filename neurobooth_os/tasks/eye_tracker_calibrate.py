# -*- coding: utf-8 -*-
"""
A task that is run to calibrate the eyetracker
"""
import logging
import os.path as op

from neurobooth_os.tasks import Task_Eyetracker
from neurobooth_os.iout.metadator import get_database_connection
from neurobooth_os import config

logger = logging.getLogger(__name__)


class Calibrate(Task_Eyetracker):
    def __init__(self, **kwargs):

        super().__init__(**kwargs)

    def present_stimulus(self, **kwargs):
        fname = kwargs["fname"]
        run_fname = kwargs["run_fname"]
        log_task_id = kwargs.get("log_task_id")

        edf_basename = op.split(fname)[-1]

        # Register the .edf in log_sensor_file immediately so the file is
        # tracked even if the session is cancelled before post-processing.
        if log_task_id is not None:
            self._register_edf(log_task_id, run_fname, edf_basename)

        self.fname = fname
        self.fname_temp = "name8chr.edf"
        self.eye_tracker.tk.openDataFile(self.fname_temp)

        self.eye_tracker.calibrate()

        # record for an instant so loadable in data viewer
        self.eye_tracker.tk.startRecording(1, 1, 1, 1)
        self.eye_tracker.tk.stopRecording()
        self.eye_tracker.tk.closeDataFile()
        # Download file
        self.eye_tracker.tk.receiveDataFile(self.fname_temp, self.fname)

    def _register_edf(self, log_task_id: str, run_fname: str, edf_basename: str) -> None:
        """Write a log_sensor_file row for the calibration .edf at creation time.

        run_fname has the form ``{session_name}_{tsk_start_time}_{task_id}``,
        so ``run_fname.split('_', 2)[:2]`` gives us the session folder. Failures
        are logged but not raised — the XDF split's INSERT fallback handles it.
        """
        try:
            from neurobooth_terra import Table
            from neurobooth_os.iout.split_xdf import LOG_SENSOR_COLUMNS
            device_id = getattr(self.eye_tracker, 'device_id', None)
            sensor_ids = getattr(self.eye_tracker, 'sensor_ids', None) or []
            if not device_id or not sensor_ids:
                logger.error(
                    "Cannot register EyeTracker .edf: missing device_id/sensor_ids")
                return
            # run_fname = "{subj_date}_{time}_{task_id}" — session folder is
            # the first two underscore-separated tokens ({subj}_{date}).
            parts = run_fname.split('_', 2)
            session_folder = '_'.join(parts[:2]) if len(parts) >= 2 else run_fname
            pg_array = '{' + f'{session_folder}/{edf_basename}' + '}'
            conn = get_database_connection()
            try:
                table = Table("log_sensor_file", conn=conn)
                for sensor_id in sensor_ids:
                    table.insert_rows(
                        [(log_task_id, None, None, None, None,
                          device_id, sensor_id, pg_array)],
                        cols=LOG_SENSOR_COLUMNS,
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error(
                f"Early log_sensor_file write failed for calibration "
                f"(log_task_id={log_task_id}): {e}")


if __name__ == "__main__":
    from neurobooth_os.iout.eyelink_tracker import EyeTracker
    from neurobooth_os.tasks import utils

    win = utils.make_win(False)
    eye_tracker = EyeTracker(win=win, ip="192.168.100.15")
    config.load_config()
    server_config = config.neurobooth_config.current_server()
    file_name = f"{server_config.local_data_dir}calibration.edf"
    cal = Calibrate(eye_tracker=eye_tracker, win=win, fname=file_name)
    cal.run()
    cal.win.close()
