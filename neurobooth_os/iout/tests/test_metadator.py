from neurobooth_os.iout import metadator as meta


def test_task_addition():

    conn = meta.get_database_connection()
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
