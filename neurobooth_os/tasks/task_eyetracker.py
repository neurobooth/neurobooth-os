# -*- coding: utf-8 -*-
"""
Created on Thu Oct 14 11:03:01 2021

Author: Sheraz Khan <sheraz@khansheraz.com>

License: BSD-3-Clause
"""

from neurobooth_os.tasks import Task


class TaskEyetracker(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


if __name__ == "__main__":
    tet = TaskEyetracker()
    tet.run()
