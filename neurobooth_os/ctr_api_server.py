import datetime
import os
import os.path as op
import time
from dataclasses import dataclass, field
from datetime import datetime
from queue import PriorityQueue
from typing import Dict, List, Union
import http.client
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.templating import Jinja2Templates

from neurobooth_os import config
from neurobooth_os.log_manager import make_db_logger
from neurobooth_os.iout import marker_stream
import neurobooth_os.iout.metadator as meta
import neurobooth_os.main_control_rec as ctr_rec

from neurobooth_os.netcomm import node_info, get_messages_to_ctr
from neurobooth_os.msg.request import PrepareRequest


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    item: str = field(compare=False)


api_title = "Neurobooth CTR API"
api_description = """
The Neurobooth CTR API operates the control (CTR) process in Neurobooth, which, in turn, provides control over the 
entire Neurobooth system. Using this API, 
the developer can start and stop STM and ACQ processes, as well as control at the task level the delivery of task 
stimuli and acquisition of task measurements. In normal operations, this API will be used by the Neurobooth operator UI
(aka, the GUI). 
"""

tags_metadata = [
    {
        "name": "session setup",
        "description": "Operations for creating a Neurobooth session.",
    },
    {
        "name": "session operation",
        "description": "Operations that manage the session, including delivery of task stimuli to subjects, "
                       "and acquisition of measurement data.",
    },
    {
        "name": "server operations",
        "description": "Operations to manage the operations of servers in a Neurobooth system.",
    },
    {
        "name": "monitoring",
        "description": "Operations enabling Neurobooth users to monitor the state of a session.",
    },
]

app = FastAPI(
    title=api_title,
    description=api_description,
    summary="API for controlling the operation of the Neurobooth CTR (control) function.",
    version="0.0.1",
    tags_metadata=tags_metadata,
)

# TODO: Replace with appropriate URLs
origins = [
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

task_queue = PriorityQueue()

stm_server = '127.0.0.1'
stm_port = 8084
stm_http_conn = http.client.HTTPConnection(host=stm_server, port=stm_port)

acq_server = '127.0.0.1'
acq_port = 8083
acq_http_conn = http.client.HTTPConnection(host=acq_server, port=acq_port)

# TODO: Fix db connection validate config paths arg
db_validate_paths = False
config.load_config(validate_paths=db_validate_paths)
db_name = config.neurobooth_config.database.dbname
conn = meta.get_database_connection(db_name, db_validate_paths)
logger = make_db_logger()
logger.debug("Starting CTR")
log_sess: Dict = meta._new_session_log_dict()
log_task: Dict = meta._new_tech_log_dict()
stream_ids, inlets = {}, {}
plot_elem, inlet_keys = [], []


def _get_ports():
    other_nodes = ("acquisition", "presentation")
    host, port = node_info("control")
    return other_nodes, host, port


nodes, host_ctr, port_ctr = _get_ports()

connection = meta.get_database_connection()


@app.get("/get_studies", tags=['session setup'])
async def get_all_studies():
    """Returns a list of all studies in the database"""
    studies = meta.get_study_ids()
    return f"studies: {studies}"


@app.get("/get_collections/{study_id}", tags=['session setup'])
async def get_collections(study_id: str):
    """Returns the collections associated with the given study_id"""
    log_sess["study_id"] = study_id
    collection_ids = _get_collections(study_id)
    collection_ids.insert(0, "Select a collection")
    id_dict = {study_id: collection_ids}
    return json.dumps(id_dict)


@app.get("/get_tasks/{collection_id}", tags=['session setup'])
async def get_tasks(request: Request, collection_id: str):
    """Returns a list of the tasks associated with the given collection_id"""
    log_sess["collection_id"] = collection_id
    tasks = _get_tasks(collection_id)
    # log_sess["tasks"] = tasks
    # response = {collection_id: tasks}
    # return json.dumps(response)
    return templates.TemplateResponse("task_selection.html", {
        'request': request,
        'tasks': tasks,
    })


# @app.get("/get_subjects/{last_name}/{first_name}", tags=['session setup'])
# async def get_subjects_by_name(last_name: str, first_name: str):
#     """Retrieve a list of subjects with the provided first and last names. The names should be those given to the
#     subject at birth"""
#     subject_df = _find_subject(first_name, last_name)
#     print("Testing")
#     return f"subjects: {subject_df}"
#

@app.get("/get_subject/{subject_id}", tags=['session setup'])
async def get_subject_by_id(subject_id: str):
    """Returns the subject record corresponding to the provided subject ID"""
    log_sess["subject_id"] = subject_id
    subject = meta.get_subject_by_id(conn, subject_id)
    if subject is not None:
        return subject
    else:
        raise HTTPException(status_code=404, detail="Subject not found")


class Session(BaseModel):
    staff_id: str
    subject_id: str
    study_id: str
    collection_id: str
    selected_tasks: List[str]


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    print(f"The client sent invalid data!: {exc}")
    exc_json = json.loads(exc.json())
    response = {"message": [], "data": None}
    for error in exc_json:
        response['message'].append(f"{error['loc']}: {error['msg']}")

    return JSONResponse(response, status_code=422)


@app.post("/save_session", tags=['session setup'])
async def save_session(request: Request, session: Session):
    """Saves the current session"""
    log_sess['staff_id'] = session.staff_id
    log_sess['subject_id'] = session.subject_id
    log_sess['study_id'] = session.study_id
    log_sess['collection_id'] = session.collection_id
    tasks = _get_tasks(session.collection_id)
    log_sess['tasks'] = tasks
    log_sess['selected_tasks'] = session.selected_tasks
    result = _init_session_save()
    return templates.TemplateResponse("page_2.html", {
        'request': request,
        'subject': session.subject_id,
        'staff_id': session.staff_id,
        'tasks': tasks,
    })


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
    logger.error(f"{request}: {exc_str}")
    content = {'status_code': 10422, 'message': exc_str, 'data': None}
    return content


# return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


@app.get("/save_notes", tags=['session operation'])
async def save_rc_notes(note_text: str, note_task: str):
    """Save the current rc notes"""
    result = _save_session_notes(log_sess, note_task, note_text)
    return f"'message': {result}"


@app.get("/start_servers", tags=['server operations'])
async def start_servers():
    """Start Neurobooth presentation and data acquisition servers """
    # TODO: Start the STM and ACQ servers
    _start_servers(nodes)
    dict = {"message": "servers started, I guess"}
    return json.dumps(dict)


@app.get("/connect_devices", tags=['server operations'])
async def connect_data_capture_devices():
    """Connect devices for capturing sound, image, and position data streams"""
    send_prepare_request(log_sess, database_name=db_name)
    # session = _start_lsl_session(window, inlets, folder_session)


@app.get("/terminate_servers", tags=['server operations'])
async def terminate_servers():
    """Shut-down Neurobooth servers after the end of the current task (if any)"""
    # TODO: Queue request for deferred execution
    headers = {'Content-type': 'application/json'}
    stm_http_conn.request('GET', '/shut_down/', "", headers)
    acq_http_conn.request('GET', '/shut_down/', "", headers)
    stm_response = stm_http_conn.getresponse()
    acq_response = acq_http_conn.getresponse()
    print(stm_response.read().decode())
    print(acq_response.read().decode())


class Item(BaseModel):
    name: str
    description: Union[str, None] = None
    price: float
    tax: Union[float, None] = None


@app.post("/items/")
async def create_item(item: Item):
    return item


@app.get("/start_session", tags=['session operation'])
async def start_session():
    """Starts a Neurobooth session, and begin presentation of stimuli to subjects. """
    global task_queue
    await run_round_trip_time_test()
    dict = {"message": "session started, sorta"}
    # using priority queue, execute all tasks

    # build task queue
    priority = 100
    for task in log_sess['tasks']:
        task_queue.put(PrioritizedTask(priority, task))
        priority = priority + 1

    for t in task_queue.queue:
        send_present_request(t.item)
    return json.dumps(dict)


async def run_round_trip_time_test():
    """ Run time test against STM and ACQ
    """
    time_0 = time.time()
    # TODO: send requests
    # Send request to ACQ to STM
    time_1 = time.time()
    elapsed_time = time_1 - time_0
    logger.info(f'Round-trip time: {elapsed_time}')


@app.get("/pause_session", tags=['session operation'])
async def pause_session():
    """Pause an ongoing Neurobooth session at the end of the current task.
    Once paused, the session can be continued or canceled, or a calibration task can be run"""
    pass


@app.get("/continue_session", tags=['session operation'])
async def continue_session_after_pause():
    """Continue a Neurobooth session that has been paused. Tasks presentation will re-start at this time."""
    pass


@app.get("/end_session", tags=['session operation'])
async def end_session_during_pause():
    """Ends the current Neurobooth session after the current task"""
    pass


@app.get("/run_calibration", tags=['session operation'])
async def run_calibration_during_pause():
    """Run calibration of devices while system is paused"""
    pass


@app.get("/iphone_preview", tags=['monitoring'])
async def preview_image_from_iphone():
    """Return an image from the iPhone camera if one is present and functioning properly"""
    pass


@app.get("/plot", tags=['monitoring'])
async def plot_lsl_data_streams():
    """Initiate plotting of LSL data streams"""
    pass


def _get_collections(study_id: str):
    collection_ids = meta.get_collection_ids(study_id)
    return collection_ids


def _get_tasks(collection_id: str):
    task_obs = meta.get_task_ids_for_collection(collection_id)
    return task_obs


def _select_subject(window, subject_df):
    """Select subject from the DOB window"""

    subject = subject_df.iloc[window["dob"].get_indexes()]
    subject_id = subject.name
    first_name = subject["first_name_birth"]
    last_name = subject["last_name_birth"]

    # Update GUI
    window["dob"].update(values=[""])
    window["select_subject"].update(f"Subject ID: {subject_id}")
    return first_name, last_name, subject_id


def _find_subject(first_name, last_name):
    """Find subject from database"""
    subject_df = meta.get_subject_ids(conn, first_name.strip(), last_name.strip())
    # TODO: Convert df to something easier to work with
    return subject_df


def _start_servers(nodes):
    # TODO: implement
    print(f"CTR starting servers on nodes {nodes}")
    # # window["-init_servs-"].Update(button_color=("black", "red"))
    # ctr_rec.start_servers(nodes=nodes)
    # time.sleep(1)
    print(log_sess)
    print("CTR started servers")
    # return event, values
    return None


def _init_session_save():
    if log_sess['staff_id'] == "":
        return "No staff ID"
    else:
        sess_info = _save_session()
        return sess_info


def _process_received_data(serv_data, window):
    """Gets messages from other servers and create PySimpleGui window events."""
    pass


def _save_session():
    """Save session."""
    now: str = datetime.now().strftime("%Y-%m-%d")
    log_task['subject_id'] = log_sess['subject_id']
    log_task["subject_id-date"] = f'{log_sess["subject_id"]}_{log_sess["date"]}'
    log_sess["subject_id-date"] = log_task['subject_id-date']
    log_sess["session_id"] = int(meta._make_session_id(conn, log_sess))
    return log_sess


def send_present_request(task_id):
    print(f"Starting presentation for {task_id}")

    headers = {'Content-type': 'application/json'}

    print("Sending STM present message")
    stm_http_conn.request('GET', f'/present/{task_id}', "", headers)

    stm_response = stm_http_conn.getresponse()
    print(f'STM response: {stm_response.read().decode()}')
    return f"Presented {task_id} Ok?"


def send_prepare_request(log_sess, database_name):

    print("Connecting devices")
    print(json.dumps(log_sess))
    # vidf_mrkr = marker_stream("videofiles")
    vidf_mrkr = None

    req = PrepareRequest(
        database_name=database_name,
        collection_id=log_sess["collection_id"],
        subject_id=log_sess["subject_id"],
        session_id=log_sess["session_id"],
        selected_tasks=log_sess["selected_tasks"],
        date=log_sess["date"]
    )
    collection_id = log_sess["collection_id"]
    subject_id = log_sess["subject_id"]
    session_id = log_sess["session_id"]
    selected_tasks = log_sess["selected_tasks"]

    headers = {'Content-type': 'application/json'}
    # nodes = ctr_rec._get_nodes(nodes)

    print("Sending STM prepare message")

    stm_http_conn.request('POST', '/prepare/', req.model_dump_json(), headers)
    stm_response = stm_http_conn.getresponse()
    print(f'STM response: {stm_response.read().decode()}')

    print("Sending ACQ prepare message")
    acq_http_conn.request('GET', f'/prepare/{collection_id}'
                                 f'?database_name={database_name}'
                                 f'&subject_id={subject_id}'
                                 f'&session_id={session_id}', "", headers)
    acq_response = acq_http_conn.getresponse()
    print(f'ACQ response: {acq_response.read().decode()}')

    return vidf_mrkr

def _save_session_notes(sess_info, notes_task, notes):
    if not notes_task:
        return
    _make_session_folder(sess_info)
    if notes_task == "All tasks":
        for task in sess_info["tasks"]:
            if not any([i in task for i in ["intro", "pause"]]):
                write_task_notes(
                    sess_info["subject_id-date"],
                    sess_info["staff_id"],
                    task,
                    notes,
                )
    else:
        write_task_notes(
            sess_info["subject_id-date"],
            sess_info["staff_id"],
            notes_task,
            notes,
        )
    return '{"message": "notes saved"}'


def _make_session_folder(sess_info):
    session_dir = op.join(config.neurobooth_config.control.local_data_dir, sess_info['subject_id-date'])
    if not op.exists(session_dir):
        os.mkdir(session_dir)


def write_task_notes(subject_id, staff_id, task_name, task_notes):
    """Write task notes.
    Parameters
    ----------
    subject_id : str
        The subject ID
    staff_id : str
        The RC ID
    task_name : str
        The task name.
    task_notes : str
        The task notes.
    """

    fname = op.join(config.neurobooth_config.control.local_data_dir, subject_id, f'{subject_id}-{task_name}-notes.txt')
    task_txt = ""
    if not op.exists(fname):
        task_txt += f"{subject_id}, {staff_id}\n"

    with open(fname, "a") as fp:
        datestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_txt += f"[\t{datestamp}]: {task_notes}\n"
        fp.write(task_txt)
