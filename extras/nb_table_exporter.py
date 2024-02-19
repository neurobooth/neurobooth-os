import math

from neurobooth_terra import Table
import yaml
from neurobooth_os.iout.metadator import get_database_connection
import os.path

"""
    Utility code for exporting database tables to yaml files 
    to support migration of configuration data out of the database
"""

#   TODO(larry): Remove this module after all nb_ tables have been exported

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

    filename = os.path.join(write_path, "stimuli", identifier + ".yml")
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


# NOTE: Exports from production neurobooth. Don't write anything to the DB!!
def export_all_stimulus_records():
    connection = get_database_connection("neurobooth", False)
    task_ids = get_task_ids_for_collection("test_mvp_030", connection)
    for task_id in task_ids:
        result = get_task_param(task_id, connection)
        export_stimulus(result[0], connection)

def export_all_instruction_records():
    connection = get_database_connection("neurobooth", False)
    task_ids = get_task_ids_for_collection("test_mvp_030", connection)

    def get_instruction_id(t_id, connection):
        table_task = Table("nb_task", conn=connection)
        task_df = table_task.query(where=f"task_id = '{t_id}'")
        (instr,) = task_df["instruction_id"]
        return instr

    for task_id in task_ids:
        instruction_id = get_instruction_id(task_id, connection)
        export_instructions(instruction_id, connection)


def export_all_task_records():
    conn = get_database_connection("neurobooth", False)
    path = os.path.join(write_path, 'tasks')

    task_ids = get_task_ids_for_collection("test_mvp_030", conn)
    for t_id in task_ids:
        table_task = Table("nb_task", conn=conn)
        task_df = table_task.query(where=f"task_id = '{t_id}'")
        (feature_of_interest,) = task_df["feature_of_interest"]
        (device_ids,) = task_df["device_id_array"]
        (sensor_ids,) = task_df["sensor_id_array"]
        (stimulus_id,) = task_df["stimulus_id"]
        (instr_id,) = task_df["instruction_id"]

        task_dict = {}
        task_dict['task_id'] = t_id
        task_dict['feature_of_interest'] = feature_of_interest
        task_dict['stimulus_id'] = stimulus_id
        task_dict['instruction_id'] = instr_id
        task_dict['device_id_array'] = device_ids
        task_dict["sensor_id_array"] = sensor_ids
        task_dict['arg_parser'] = 'iout.stim_param_reader.py::RawTaskParams'

        filename = os.path.join(path, t_id + ".yml")
        with open(filename, 'w') as f:
            yaml.dump(task_dict, f, sort_keys=False)


def export_all_device_records():
    conn = get_database_connection("neurobooth", False)
    path = os.path.join(write_path, 'devices')

    task_ids = get_task_ids_for_collection("test_mvp_030", conn)
    for t_id in task_ids:
        table_task = Table("nb_task", conn=conn)
        task_df = table_task.query(where=f"task_id = '{t_id}'")
        (device_ids,) = task_df["device_id_array"]

        table_device = Table("nb_device", conn=conn)
        for device_id in device_ids:
            device_df = table_device.query(where=f"device_id = '{device_id}'")
            (device_sn,) = device_df["device_sn"]
            (device_name,) = device_df["device_name"]
            (device_location,) = device_df["device_location"]
            (wearable,) = device_df["wearable_bool"]
            (device_make,) = device_df["device_make"]
            (device_model,) = device_df["device_model"]
            (device_firmware,) = device_df["device_firmware"]
            (sensor_id_array,) = device_df["sensor_id_array"]

            dev_dict = {}
            dev_dict['device_id'] = device_id
            dev_dict['device_sn'] = device_sn
            dev_dict['device_name'] = device_name
            dev_dict['device_location'] = device_location
            dev_dict['wearable_bool'] = wearable
            dev_dict["device_make"] = device_make
            dev_dict["device_model"] = device_model
            dev_dict["device_firmware"] = device_firmware
            dev_dict["sensor_ids"] = sensor_id_array
            dev_dict['arg_parser'] = 'iout.stim_param_reader.py::DeviceArgs'

            filename = os.path.join(path, device_id + ".yml")
            with open(filename, 'w') as f:
                yaml.dump(dev_dict, f, sort_keys=False)


def export_all_sensor_records():
    conn = get_database_connection("neurobooth", False)
    path = os.path.join(write_path, 'sensors')

    table_sens = Table("nb_sensor", conn=conn)
    sens_df = table_sens.query()
    sens_df.reset_index()
    for index, row in sens_df.iterrows():
        sensor_id = index
        temporal_res = row["temporal_res"]
        spatial_res_x = row["spatial_res_x"]
        spatial_res_y = row["spatial_res_y"]
        file_type = row["file_type"]
        additional_parameters = row["additional_parameters"]

        sens_dict = {}
        sens_dict["sensor_id"] = sensor_id
        if not math.isnan(temporal_res):
            sens_dict["temporal_res"] = temporal_res
        if not math.isnan(spatial_res_x):
            sens_dict["spatial_res_x"] = spatial_res_x
        if not math.isnan(spatial_res_y):
            sens_dict["spatial_res_y"] = spatial_res_y
        sens_dict["file_type"] = file_type
        sens_dict['arg_parser'] = 'iout.stim_param_reader.py::SensorArgs'

        if additional_parameters is not None:
            for key in additional_parameters:
                sens_dict[key] = additional_parameters[key]

        print(sens_dict)
        filename = os.path.join(path, sensor_id + ".yml")
        with open(filename, 'w') as f:
            yaml.dump(sens_dict, f, sort_keys=False)
            
            
def export_all_connection_records():
    conn = get_database_connection("neurobooth", False)
    path = os.path.join(write_path, 'collections')

    table_collection = Table("nb_collection", conn=conn)
    collection_df = table_collection.query()
    collection_df.reset_index()
    for index, row in collection_df.iterrows():
        collection_id = index
        is_active = row["is_active"]
        task_array = row["task_array"]

        collection_dict = {}
        collection_dict["collection_id"] = collection_id
        collection_dict["is_active"] = is_active
        collection_dict["task_ids"] = task_array
        collection_dict['arg_parser'] = 'iout.stim_param_reader.py::CollectionArgs'

        print(collection_dict)
        filename = os.path.join(path, collection_id + ".yml")
        with open(filename, 'w') as f:
            yaml.dump(collection_dict, f, sort_keys=False)


def export_all_study_records():
    conn = get_database_connection("neurobooth", False)
    path = os.path.join(write_path, 'studies')

    table_study = Table("nb_study", conn=conn)
    study_df = table_study.query()
    study_df.reset_index()
    for index, row in study_df.iterrows():
        study_id = index
        irb_protocol_number = row["IRB_protocol_number"]
        study_title = row["study_title"]
        protocol_version = row["protocol_version_array"]
        consent_version = row["consent_version_array"]
        collection_ids = row["collection_ids"]
        consent_dates = row["consent_dates"]
        protocol_dates = row["protocol_dates"]

        study_dict = {}
        study_dict["study_id"] = study_id
        study_dict["study_title"] = study_title
        study_dict["collection_ids"] = collection_ids

        study_dict["irb_protocol_number"] = irb_protocol_number

        if not math.isnan(protocol_version):
            study_dict["protocol_version"] = protocol_version
        else:
            study_dict["protocol_version"] = None

        study_dict["consent_version"] = consent_version
        study_dict["consent_dates"] = consent_dates
        study_dict["protocol_dates"] = protocol_dates
        
        study_dict['arg_parser'] = 'iout.stim_param_reader.py::StudyArgs'

        print(study_dict)
        filename = os.path.join(path, study_id + ".yml")
        with open(filename, 'w') as f:
            yaml.dump(study_dict, f, sort_keys=False)


def get_task_ids_for_collection(collection_id, conn):
    """

    Parameters
    ----------
    collection_id: str
        Unique identifier for collection: (The primary key of nb_collection table)
    conn : object
        Database connection

    Returns
    -------
        List[str] of task_ids for all tasks in the collection
    """
    table_collection = Table("nb_collection", conn=conn)
    collection_df = table_collection.query(where=f"collection_id = '{collection_id}'")
    (tasks_ids,) = collection_df["task_array"]
    return tasks_ids


def get_task_param(task_id, conn: connection):
    """

    Parameters
    ----------
    task_id : str
        The unique identifier for a task
    conn : object
        database connection

    Returns
    -------
        tuple of task parameters
    """
    # task_data, stimulus, instruction
    table_task = Table("nb_task", conn=conn)
    task_df = table_task.query(where=f"task_id = '{task_id}'")
    (device_ids,) = task_df["device_id_array"]
    (sensor_ids,) = task_df["sensor_id_array"]
    (stimulus_id,) = task_df["stimulus_id"]
    (instr_id,) = task_df["instruction_id"]

    instr_kwargs: Optional[InstructionArgs] = None

    if instr_id is not None:
        instr_kwargs = _get_instruction_kwargs_from_file(instr_id)
    return (
        stimulus_id,
        device_ids,
        sensor_ids,
        instr_kwargs,
    )  # XXX: name similarly in calling function


# export_all_task_records()
# export_all_stimulus_records()
# export_all_instruction_records()
# export_all_device_records()
# export_all_connection_records()
export_all_study_records()
# export_all_sensor_records()
