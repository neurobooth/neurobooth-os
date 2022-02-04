"""Mock GUI"""

# Authors: Mainak Jas <mjas@mgh.harvard.edu>

import time


class _MockGUIElement(dict):
    """Mock GUI element."""
    def get_indexes(self):
        return 0

    def Update(self, button_color):
        pass

    def update(self, *args, **kwargs):
        pass

class MockWindow(dict):
    def __init__(self, gui_element_names):
        """MockWindow

        Parameters
        ----------
        gui_element_names : list of str
            The GUI elements being faked.

        Attributes
        ----------
        events : list of tuple
            The events queue containing (event, value) pairs.
        """
        mapping = {name: _MockGUIElement() for name in gui_element_names}
        super(MockWindow, self).__init__(mapping)
        self.events = list()

    def read(self, timeout):
        """Read and delete an event from the queue.

        Parameters
        ----------
        timeout : float
            Time to sleep before retrieving the events
            (lazy approach compared to implementing a real timeout)
        """
        time.sleep(timeout)
        if len(self.events) > 0:
            return self.events.pop(0)
        return (None, None)

    def write_event_value(self, key, val):
        """Write the events to the queue.

        Parameters
        ----------
        key : str
            The event name
        val : str
            The event values
        """
        self.events.append((key, val))

    def close(self):
        pass
