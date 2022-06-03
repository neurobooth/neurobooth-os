# -*- coding: utf-8 -*-
"""
Created on Wed Apr 13 15:52:09 2022

@author: STM
"""

from pylsl import local_clock
import pylink
import time
from psychopy.core import wait, CountdownTimer

time_period = .0005
n_reps = 10000

print(f"    sleep period: {time_period}, n_reps: {n_reps}")
tstart = local_clock()

for _ in range(n_reps):
    
    
    t1 = local_clock()
    t2 = local_clock()
    while t2-t1 < time_period:
        t2 =local_clock()
    
print("pypls local_clock ", local_clock()-tstart)



tstart = local_clock()

for _ in range(n_reps):
        
    t1 = time.time()
    t2 = time.time()
    while t2-t1 < time_period:
        t2 = time.time()

print("time.time", local_clock()-tstart)


    
tstart = local_clock()

for _ in range(n_reps):
    time.sleep(time_period)

print("time.sleep", local_clock()-tstart)
    



tstart = local_clock()
for _ in range(n_reps):    
    # CountdownTimer().add( 0.0001)
    wait(time_period)

print("core.wait ", local_clock()-tstart)


tstart = local_clock()
for _ in range(n_reps):    
    # CountdownTimer().add( 0.0001)
    wait(time_period, hogCPUperiod=time_period)

print("core.wait hogCPUperiod ", local_clock()-tstart)



# from psychopy import core
 
# myclock = core.Clock()
# tstart = myclock.getTime()

# for _ in range(10000):
    
    
#     t1 = myclock.getTime()
#     t2 = myclock.getTime()
#     while t2-t1 < 0.0001:
#         t2 =myclock.getTime()
    
# print(myclock.getTime() - tstart)




# tstart = local_clock()

# for _ in range(10000):
    
#     pylink.msecDelay(1)


    
# print(local_clock()-tstart)








