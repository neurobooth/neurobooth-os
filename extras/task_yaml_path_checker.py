from typing import Dict

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.stim_param_reader import StudyArgs, CollectionArgs, RawTaskParams, InstructionArgs, \
    StimulusArgs, DeviceArgs, SensorArgs


class PathError(Exception):
    pass


def check_paths_from_study(study_name: str):
    print("Note: Checking against yaml files in location specified in the NB_CONFIG environment variable.")
    studies: Dict[str, StudyArgs] = meta.read_studies()
    if study_name not in studies:
        raise PathError(f"No yaml file was found for study '{study_name}' ")
    else:
        study = studies[study_name]
        collections: Dict[str, CollectionArgs] = meta.read_collections()
        collection_ids = study.collection_ids
        for collection_id in collection_ids:
            if collection_id not in collections:
                raise PathError(
                    f"Collection '{collection_id}' referenced by study '{study}' was not found in yaml files")
            else:  # check the collection
                task_ids = collections[collection_id].task_ids
                tasks: Dict[str, RawTaskParams] = meta.read_tasks()
                for task_id in task_ids:
                    if task_id not in tasks:
                        raise PathError(f"Task '{task_id}' referenced by collection '{collection_id}' "
                                        f"was not found in yaml files")
                    else:  # check the task
                        task = tasks[task_id]
                        instructions: Dict[str, InstructionArgs] = meta.read_instructions()
                        instruction_id = task.instruction_id
                        if instruction_id and not instruction_id in instructions:
                            raise PathError(f"Instruction '{instruction_id}' referenced by task '{task_id}' "
                                            f"was not found in the yaml files. "
                                            f"Task '{task_id}' is referenced by collection '{collection_id}'.")
                        stimuli: Dict[str, StimulusArgs] = meta.read_stimuli()
                        stim_id = task.stimulus_id
                        if stim_id not in stimuli:
                            raise PathError(f"Stimulus '{stim_id}' referenced by task '{task_id}' "
                                            f"was not found in the yaml files. "
                                            f"Task '{task_id}' is referenced by collection '{collection_id}'.")
                        device_ids = task.device_id_array
                        devices: Dict[str, DeviceArgs] = meta.read_devices()
                        for dev_id in device_ids:
                            if dev_id not in devices:
                                raise PathError(
                                    f"Device '{dev_id}' referenced by task '{task_id}' "
                                    f"was not found in the yaml files. Task '{task_id}' is referenced by collection"
                                    f" '{collection_id}'.")
                            device: DeviceArgs = devices[dev_id]
                            sensor_ids = device.sensor_ids
                            sensors: Dict[str, SensorArgs] = meta.read_sensors()
                            for sensor_id in sensor_ids:
                                if sensor_id not in sensors:
                                    raise PathError(f"Sensor '{sensor_id}' referenced by device '{dev_id}' "
                                                    f"was not found in the yaml files. "
                                                    f"Device '{dev_id}' is referenced by task '{task_id}', "
                                                    f"and '{task_id}' is referenced by collection '{collection_id}'.")

    print(f"All elements referenced from study '{study_name}' have a yaml file"
          f" and all yaml files were successfully parsed.")


def check_all_paths():
    studies: Dict[str, StudyArgs] = meta.read_studies()
    for study in studies:
        check_paths_from_study(study)


# check_paths_from_study("study1")
check_all_paths()
