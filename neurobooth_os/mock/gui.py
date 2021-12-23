"""Mock GUI"""

# Authors: Mainak Jas <mjas@mgh.harvard.edu>

import time


class MockGUIElement(dict):
    """Mock GUI element."""
    def get_indexes(self):
        return 0

    def Update(self, button_color):
        pass

    def update(self, *args, **kwargs):
        pass

class MockWindow(dict):
    def __init__(self, mapping):
        super(MockWindow, self).__init__(mapping)
        self.events = dict()

    def read(self, timeout):
        time.sleep(timeout)
        try:
            return self.events.popitem()
        except:
            return (None, None)

    def write_event_value(self, key, val):
        self.events[key] = val

    def close(self):
        pass
