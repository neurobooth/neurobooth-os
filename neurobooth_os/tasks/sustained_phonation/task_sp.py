# -*- coding: utf-8 -*-
"""
Created on Thu Oct 14 11:03:01 2021

Author: Sheraz Khan <sheraz@khansheraz.com>

License: BSD-3-Clause
"""

from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task


class SustainedPhonation(Task):
    def __init__(self, *args):
        super().__init__(*args)


if __name__ == "__main__":
    sts = SustainedPhonation()
    utils.run_task(sts, prompt=True)