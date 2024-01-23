from neurobooth_terra import Table
import yaml
from neurobooth_os.iout.metadator import get_conn, get_task_ids_for_collection, get_task_param
import os.path

"""
    Utility code for exporting database tables to yaml files 
    to support migration of configuration data out of the database
"""
write_path = 'C:/yaml/'


def export_stimulus(identifier, conn):
    table = Table("nb_stimulus", conn=conn)

    df = table.query(where=f"stimulus_id = '{identifier}'")
    (desc,) = df["stimulus_description"]
    (iterations,) = df["num_iterations"]
    (duration,) = df["duration"]
    (file_type,) = df["stimulus_filetype"]
    (file,) = df["stimulus_file"]
    (params,) = df["parameters"]

    stim_dict = {}
    stim_dict['stimulus_id'] = identifier
    stim_dict['stimulus_description'] = desc
    stim_dict['num_iterations'] = None
    stim_dict["duration"] = None
    stim_dict['arg_parser'] = None
    stim_dict['stimulus_file_type'] = file_type
    stim_dict['stimulus_file'] = file
    if iterations is not None:
        stim_dict["num_iterations"] = int(iterations)
    else:
        stim_dict['num_iterations'] = None

    if duration is not None:
        stim_dict["duration"] = float(duration)
    else:
        stim_dict["duration"] = None

    if params is not None:
        for key in params:
            stim_dict[key] = params[key]

    filename = os.path.join(write_path, identifier + ".yml")
    with open(filename, 'w') as file:
        yaml.dump(stim_dict, file, sort_keys=False)

    print(yaml.dump(stim_dict, sort_keys=False))


# NOTE: Exports from production neurobooth. Don't write anything to the DB!!
connection = get_conn("neurobooth", False)
task_ids = get_task_ids_for_collection("test_mvp_030", connection)
for task_id in task_ids:
    result = get_task_param(task_id, connection)
    export_stimulus(result[0], connection)
