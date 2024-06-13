import unittest
from neurobooth_os.util.task_log_entry import convert_to_array_literal


class TestTaskParamReader(unittest.TestCase):

    def test_convert_array(self):
        mylist = ["a", "b", "c"]
        print(convert_to_array_literal(mylist))
        self.assertEquals('{"a", "b", "c"}', convert_to_array_literal(mylist))

    def test_convert_array_2(self):
        mylist = []
        print(convert_to_array_literal(mylist))
        self.assertEquals("{}", convert_to_array_literal(mylist))

    def test_convert_array_3(self):
        mylist = None
        print(convert_to_array_literal(mylist))
        self.assertEquals("{}", convert_to_array_literal(mylist))

    def test_convert_array_4(self):
        mylist = '{None}'
        print(convert_to_array_literal(mylist))
        self.assertEquals("{None}", convert_to_array_literal(mylist))

    def test_convert_array_5(self):
        mylist = '{f1, f2}'
        print(convert_to_array_literal(mylist))
        self.assertEquals("{f1, f2}", convert_to_array_literal(mylist))
