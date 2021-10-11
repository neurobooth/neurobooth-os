

from neurobooth_os.iout import metadator as meta



def test_tech_obs_addition():

    conn = meta.get_conn(remote=True,database="mock_neurobooth")
    subj_id = "Test"
    tech_obs_id = meta._make_new_tech_obs_row(conn, subj_id)

    vals_dict = meta._new_tech_log_dict()
    vals_dict['subject_id'] = subj_id
    vals_dict['study_id'] = "mock_study"
    vals_dict['tech_obs_id'] = "mock_obs_1"
    vals_dict['staff_id'] = "mocker"    
    vals_dict['event_array'] = "event:datestamp"
    vals_dict['collection_id'] = "mock_collection"
    vals_dict['site_id'] = "mock_site"

    meta._fill_tech_obs_row(tech_obs_id, vals_dict, conn)
    


