from neurobooth_terra import Table
import yaml
from neurobooth_os.iout.metadator import get_conn, get_task_ids_for_collection, get_task_param
import os.path

"""
    Utility code for exporting database tables to yaml files 
    to support migration of configuration data out of the database
"""
write_path = 'C:\\Users\\lw412\\Documents\\GitHub\\neurobooth\\neurobooth-os\\examples\\configs'


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


def export_instructions(identifier, conn):
    if identifier is not None:
        print()
        print(f"instruction_id = {identifier}")
        path = os.path.join(write_path, 'instructions')
        table = Table("nb_instruction", conn=conn)

        df = table.query(where=f"instruction_id = '{identifier}'")
        if not df.empty:
            (text,) = df["instruction_text"]
            (file,) = df["instruction_file"]
            (file_type,) = df["instruction_filetype"]

            instr_dict = {}
            instr_dict['instruction_id'] = identifier
            instr_dict['instruction_text'] = text
            instr_dict['instruction_filetype'] = file_type
            instr_dict['instruction_file'] = file
            print(instr_dict)
            filename = os.path.join(path, identifier + ".yml")
            with open(filename, 'w') as f:
                yaml.dump(instr_dict, f, sort_keys=False)

            print(f"{identifier} has SOME instructions")
        else:
            print(f"{identifier} has no instructions")


# NOTE: Exports from production neurobooth. Don't write anything to the DB!!
def export_all_stimulus_records():
    connection = get_conn("neurobooth", False)
    task_ids = get_task_ids_for_collection("test_mvp_030", connection)
    for task_id in task_ids:
        result = get_task_param(task_id, connection)
        export_stimulus(result[0], connection)


# def get_param(task_id, conn):
#     # task_data, stimulus, instruction
#     table_task = Table("nb_task", conn=conn)
#     task_df = table_task.query(where=f"task_id = '{task_id}'")
#     # (device_ids,) = task_df["device_id_array"]
#     # (sensor_ids,) = task_df["sensor_id_array"]
#     # (stimulus_id,) = task_df["stimulus_id"]
#     (instr_id,) = task_df["instruction_id"]
#     instr_kwargs = _get_instruction_kwargs(instr_id, conn)
#     return (
#         stimulus_id,
#         device_ids,
#         sensor_ids,
#         instr_kwargs,
#     )  # XXX: name similarly in calling function


def export_all_instruction_records():
    connection = get_conn("neurobooth", False)
    task_ids = get_task_ids_for_collection("test_mvp_030", connection)

    def get_instruction_id(t_id, connection):
        table_task = Table("nb_task", conn=connection)
        task_df = table_task.query(where=f"task_id = '{task_id}'")
        (instr,) = task_df["instruction_id"]
        return instr

    for task_id in task_ids:
        instruction_id = get_instruction_id(task_id, connection)
        export_instructions(instruction_id, connection)


# export_all_stimulus_records()
export_all_instruction_records()