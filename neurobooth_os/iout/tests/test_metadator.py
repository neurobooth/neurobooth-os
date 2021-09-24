
from datetime import datetime 
from collections import OrderedDict
from neurobooth_os.iout import metadator as meta



def test_tech_obs_addition():

    conn = meta.get_conn(remote=True,database="mock_neurobooth")
    subj_id = "Test"
    tech_obs_id = meta.make_new_tech_obs_row(conn, subj_id)

    conn = meta.get_conn(remote=True,database="mock_neurobooth")
    vals_dict = OrderedDict()
    vals_dict['subject_id'] = subj_id
    vals_dict['study_id'] = "test_study"
    vals_dict['tech_obs_id'] = "mock_obs"
    vals_dict['staff_id'] = "mocker"
    vals_dict['application_id'] = "test"
    vals_dict['event_array'] = "event:str"
    vals_dict['collection_id'] = "mock_collection"
    datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vals_dict['date_times'] = "{" + datetime_str + "}"
    vals_dict['site_id'] = "mock"

    vals = list(vals_dict.values())
    meta.fill_tech_obs_row(tech_obs_id, tuple(vals), conn)


