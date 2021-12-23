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
    def __init__(self, gui_element_names):
        mapping = {name: MockGUIElement() for name in gui_element_names}
        super(MockWindow, self).__init__(mapping)
        self.events = list()

    def read(self, timeout):
        time.sleep(timeout)
        if len(self.events) > 0:
            return self.events.pop(0)
        return (None, None)

    def write_event_value(self, key, val):
        self.events.append((key, val))

    def close(self):
        pass
