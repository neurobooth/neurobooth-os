# -*- coding: utf-8 -*-
"""
Created on Wed Apr 27 15:46:36 2022

@author: STM
"""

from pylsl import local_clock
# import pylink
import time
from psychopy.core import wait, CountdownTimer

time_period = .01
n_reps = 100

print(f"    sleep period: {time_period}, n_reps: {n_reps}")

t_intervals = dict()
t_intervals['pylsl'] = list()
tstart = local_clock()
for _ in range(n_reps):

    t1 = local_clock()
    t2 = local_clock()
    while t2-t1 < time_period:
        t2 = local_clock()
    t_intervals['pylsl'].append(t2 - t1)

print("pypls local_clock ", local_clock() - tstart)

time.sleep(1.)

t_intervals['time.time'] = list()
tstart = local_clock()
for _ in range(n_reps):

    t1 = time.time()
    t2 = time.time()
    while t2-t1 < time_period:
        t2 = time.time()
    t_intervals['time.time'].append(t2 - t1)

print("time.time", local_clock()-tstart)

time.sleep(1.)

t_intervals['time.sleep'] = list()
tstart = local_clock()
for _ in range(n_reps):
    t1 = local_clock()
    time.sleep(time_period)
    t2 = local_clock()
    t_intervals['time.sleep'].append(t2 - t1)

print("time.sleep", local_clock()-tstart)

time.sleep(1.)

t_intervals['wait'] = list()
tstart = local_clock()
for _ in range(n_reps):
    t1 = local_clock()
    # CountdownTimer().add( 0.0001)
    wait(time_period, hogCPUperiod=0)
    t2 = local_clock()
    t_intervals['wait'].append(t2 - t1)

print("core.wait ", local_clock()-tstart)

time.sleep(1.)  # make sure no interaction with previous timing measurements

t_intervals['wait_hogcpuperiod'] = list()
tstart = local_clock()
for _ in range(n_reps):
    t1 = local_clock()
    # CountdownTimer().add( 0.0001)
    wait(time_period, hogCPUperiod=time_period)
    t2 = local_clock()
    t_intervals['wait_hogcpuperiod'].append(t2 - t1)

print("core.wait hogCPUperiod ", local_clock()-tstart)

time.sleep(1.)

print('')
import numpy as np
for wait_type in t_intervals:
    err = np.abs(np.array(t_intervals[wait_type]) - time_period)
    avg_error = np.mean(err)
    std_error = np.std(err)
    print(f'error for {wait_type}: {avg_error:.8f} +/- {std_error:.8f}')