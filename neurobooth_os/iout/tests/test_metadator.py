import unittest

from neurobooth_os.iout import metadator as meta


class TestMetadator(unittest.TestCase):

    def test_read_sensors(self):
        sens_dict = meta.read_sensors()
        print(sens_dict)

    def test_read_devices(self):
        sens_dict = meta.read_devices()
        print(sens_dict)

    def test_read_instructions(self):
        sens_dict = meta.read_instructions()
        print(sens_dict)

    def test_read_stimuli(self):
        sens_dict = meta.read_stimuli()
        print(sens_dict)

    def test_read_tasks(self):
        a_dict = meta.read_tasks()
        print(a_dict)

    def test_read_all_task_params(self):
        a_dict = meta._read_all_task_params()
        print(a_dict["tasks"])
        print(a_dict["stimuli"])
        print(a_dict["instructions"])
        print(a_dict["devices"])
        print(a_dict["sensors"])

    def test_build_tasks_for_collection(self):
        collection_id = 'mvp_030'
        conn = meta.get_conn('neurobooth', False)
        task_dict = meta.build_tasks_for_collection(collection_id, conn)
        print(task_dict)

    def test_garbage(self):
        info = {
            "sensors": {
                "s1": 1}
        }
        (k,) = info["sensors"].keys()
        print(k)

    def test_get_device_kwargs_by_task(self):
        collection_id = 'testing'
        conn = meta.get_conn('mock_neurobooth_1', False)
        args = meta.get_device_kwargs_by_task(collection_id, conn)
        #print(args)

        kwarg_alldevs = {}
        for dc in args.values():
           kwarg_alldevs.update(dc)
        #print("Value size: " + str(len(kwarg_alldevs.keys())))
        #print("Values: " + str(kwarg_alldevs))

        task_dict = meta.build_tasks_for_collection(collection_id, conn)
        kwargs = {}
        for val in task_dict.values():
            list_of_devs_in_task = val.device_args
            for dev_args in list_of_devs_in_task:
                kwargs[dev_args.device_id] = (dict(dev_args))
        #print("New values size: " + str(len(kwargs.keys())))
        #print(kwargs)
        print()

        for k in kwarg_alldevs.keys():
            val1 = kwarg_alldevs[k]
            print(val1)
            val2 = kwargs[k]
            print(val2)
            print()
            for k2 in val1.keys():
                print()
                val1_2 = val1[k2]
                print(val1_2)
                val2_2 = val2[k2]
                assert(val1_2 is not None)
                assert(val2_2 is not None)
                print(val2_2)
                print()


def test_task_addition(database):
    conn = meta.get_conn(database)
    subj_id = "Test"
    task_id = meta.make_new_task_row(conn, subj_id)

    vals_dict = meta._new_tech_log_dict()
    vals_dict["subject_id"] = subj_id
    vals_dict["study_id"] = "mock_study"
    vals_dict["task_id"] = "mock_obs_1"
    vals_dict["staff_id"] = "mocker"
    vals_dict["event_array"] = "event:datestamp"
    vals_dict["collection_id"] = "mock_collection"
    vals_dict["site_id"] = "mock_site"

    meta.fill_task_row(task_id, vals_dict, conn)
