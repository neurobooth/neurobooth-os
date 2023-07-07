
"""
====================
Run a task using parameters from the database
====================
Use :func:`~neurobooth_os.iout.metadator.get_conn` to get a connection to the database.
"""
# Author: Adonay Nunes <adonay.s.nunes@gmail.com>
#
# License: BSD-3-Clause

# %%
import os.path as op
import time

import neurobooth_os
import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg
from neurobooth_os.tasks.task_importer import get_task_funcs
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
# %%
# Define parameters
subj_id = "test"
collection_id = "mvp_030" 
use_instruction_videos = True  # False if instruction videos not available

# %%
# Prepare for task presentation
conn = meta.get_conn(remote=False, database='neurobooth')
win = utl.make_win(full_screen=False)

task_func_dict = get_task_funcs(collection_id, conn)
task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)

task_karg ={"win": win,
            "path": cfg.neurobooth_config['data_out'],
            "subj_id": subj_id,            
            }

# %%
# The eye tracker requires SReyelink's pylink
from neurobooth_os.iout.eyelink_tracker import EyeTracker
streams = {}
streams['Eyelink'] = EyeTracker(win=win, ip=None)
streams['Eyelink'].calibrated = True

# %%
# Select task
print(list(task_func_dict))
tasks = list(task_func_dict)

# Delete calibration task as there is no eyetracker
if 'calibration_task_1' in tasks:
 del tasks[tasks.index('calibration_task_1')]


# %%
# Preload media 
t0 = time.time()
for task in tasks:
    # Get task and params
    tsk_fun = task_func_dict[task]['obj']
    if not use_instruction_videos:
        task_func_dict[task]['kwargs']['instruction_file'] = op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4')
    this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}

    # Run task
    task_func_dict[task]['obj'] = tsk_fun(**this_task_kwargs)

print(f"Media loading took {time.time() - t0} for {len(tasks)} tasks")
# %%
# Loop over each task and present it
win = welcome_screen(win=win)
for task in tasks:
    this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}
    task_func_dict[task]['obj'].run(**this_task_kwargs)

finish_screen(win)
task_func_dict[task]['obj'].win.close()