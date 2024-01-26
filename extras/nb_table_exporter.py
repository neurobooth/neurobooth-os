from typing import Set

from neurobooth_terra import Table
import yaml
from neurobooth_os.iout.metadator import get_conn, get_task_ids_for_collection, get_task_param, \
    get_device_kwargs_by_task, _get_device_kwargs
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


def export_device(device_id, conn):
    print()
    print(device_id)

    table = Table("nb_device", conn=conn)

    df = table.query(where=f"device_id = '{device_id}'")
    (device_sn,) = df["device_sn"]
    (wearable_bool,) = df["wearable_bool"]
    (device_location,) = df["device_location"]
    (device_name,) = df["device_name"]
    (device_make,) = df["device_make"]
    (device_model,) = df["device_model"]
    (device_firmware,) = df["device_firmware"]
    (sensor_id_array,) = df["sensor_id_array"]

    if device_name == 'EYELIN Portable Duo':
        device_name = 'EYELINK Portable Duo'

    dev_dict = {}
    dev_dict['device_id'] = device_id
    dev_dict['device_sn'] = device_sn
    dev_dict['wearable_bool'] = wearable_bool
    dev_dict["device_location"] = device_location
    dev_dict['arg_parser'] = None
    dev_dict['device_name'] = device_name
    dev_dict['device_make'] = device_make
    dev_dict['device_model'] = device_model
    dev_dict['device_firmware'] = device_firmware
    dev_dict['sensor_id_array'] = sensor_id_array

    filename = os.path.join(write_path, 'devices', device_id + ".yml")
    with open(filename, 'w') as file:
        yaml.dump(dev_dict, file, sort_keys=False)

    print(yaml.dump(dev_dict, sort_keys=False))

    return sensor_id_array

def export_sensor(sensor_id, conn):
    print()
    if sensor_id == 'sens_Eyelink_sens_1':
        sensor_id = 'Eyelink_sens_1'

    print(sensor_id)

    table = Table("nb_sensor", conn=conn)

    df = table.query(where=f"sensor_id = '{sensor_id}'")
    (temporal_res,) = df["temporal_res"]
    (spatial_res_x,) = df["spatial_res_x"]
    (spatial_res_y,) = df["spatial_res_y"]
    (file_type,) = df["file_type"]
    (laterality,) = df["laterality"]
    (additional_parameters,) = df["additional_parameters"]

    sensor_dict = {}
    sensor_dict['sensor_id'] = sensor_id
    sensor_dict['temporal_res'] = temporal_res
    sensor_dict['spatial_res_x'] = spatial_res_x
    sensor_dict["spatial_res_y"] = spatial_res_y
    sensor_dict['file_type'] = file_type
    sensor_dict['laterality'] = laterality
    if temporal_res is not None:
        sensor_dict["temporal_res"] = float(temporal_res)
    else:
        sensor_dict["temporal_res"] = None

    if spatial_res_x is not None:
        sensor_dict["spatial_res_x"] = float(spatial_res_x)
    else:
        sensor_dict["spatial_res_x"] = None

    if spatial_res_y is not None:
        sensor_dict["spatial_res_y"] = float(spatial_res_y)
    else:
        sensor_dict["spatial_res_y"] = None

    if additional_parameters is not None:
        for key in additional_parameters:
            sensor_dict[key] = additional_parameters[key]

    filename = os.path.join(write_path, 'sensors', sensor_id + ".yml")
    with open(filename, 'w') as file:
        yaml.dump(sensor_dict, file, sort_keys=False)

    print(yaml.dump(sensor_dict, sort_keys=False))


def export_all_device_records():
    connection = get_conn("neurobooth", False)
    task_ids = get_task_ids_for_collection("test_mvp_030", connection)
    sensor_set: Set = set()

    def get_devices(t_id, conn):
        _, dev_ids, _, _ = get_task_param(t_id, conn)
        for dev_id in dev_ids:
            sensor_ids = export_device(dev_id, conn)
            for sid in sensor_ids:
                sensor_set.add(sid)

    def get_sensors(sensor_ids):
        for sid in sensor_ids:
            export_sensor(sid, connection)

    for t_id in task_ids:
        get_devices(t_id, connection)

    print()
    print("processing sensors")
    print(sensor_set)
    get_sensors(sensor_set)


# export_all_stimulus_records()
# export_all_instruction_records()
export_all_device_records()
