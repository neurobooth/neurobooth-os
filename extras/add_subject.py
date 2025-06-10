import FreeSimpleGUI as sg
import yaml
from pydantic import BaseModel
from typing import Dict
import os
from datetime import datetime

from neurobooth_os.config import load_config_by_service_name
from neurobooth_os.config import ConfigException
from neurobooth_os.iout import metadator


class AddSubjectGuiOptions(BaseModel):
    study_options: Dict[str, str]
    gender_options: Dict[str, int]
    country_options: Dict[str, int]


def load_add_subject_options() -> AddSubjectGuiOptions:
    config_file = os.path.join(os.environ.get("NB_CONFIG"), "add_subject_options.yml")
    if not os.path.exists(config_file):
        raise ConfigException(f"Required config file does not exist: {config_file}")

    with open(config_file) as f:
        return AddSubjectGuiOptions(**yaml.load(f, yaml.FullLoader))


def get_next_subject_id(study_code: str, conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT subject_id
            FROM subject
            WHERE subject_id LIKE %s
            ORDER BY subject_id DESC
            LIMIT 1
        """, (f"{study_code}%",))
        result = cur.fetchone()

        if result:
            last_id = result[0]
            last_number = int(last_id[-4:])
            new_number = last_number + 1
        else:
            new_number = 1

        return f"{study_code}{str(new_number).zfill(4)}"


def launch_gui() -> None:
    sg.theme("Dark Grey 9")
    font = ("Arial", 12)

    load_config_by_service_name("CTR")
    conn = metadator.get_database_connection()

    placeholder_dob = "YYYY-MM-DD"

    options = load_add_subject_options()
    study_options = options.study_options
    gender_options = options.gender_options
    country_options = options.country_options

    layout = [
    [sg.Column([[
        sg.Text("Study:", size=(12, 1), font=font),
        sg.Combo(list(study_options.keys()), key="-STUDY-", readonly=True, enable_events=True, size=(30, 1), font=font),
        sg.Text("Subject ID:", size=(12, 1), font=font),
        sg.Input(key="-SUBJECT_ID-", size=(30, 1), disabled=True, readonly=True, font=font,
                 background_color="white", text_color="black")
    ]], pad=(0, 10))],

    [sg.Column([[
        sg.Text("Gender:", size=(12, 1), font=font),
        sg.Combo(list(gender_options.keys()), key="-GENDER-", readonly=True, size=(30, 1), font=font)
    ]], pad=(0, 10))],

    [sg.Column([[
        sg.Text("Date of Birth:", size=(12, 1), font=font),
        sg.Input(key="-DOB-", size=(20, 1), default_text=placeholder_dob, tooltip="Format: YYYY-MM-DD", font=font,
                 background_color="white", text_color="black", enable_events=True),
        sg.CalendarButton("Pick Date", target="-DOB-", format="%Y-%m-%d", size=(10, 1), font=font)
    ]], pad=(0, 10))],

    [sg.Column([[
        sg.Text("First Name:", size=(12, 1), font=font),
        sg.Input(key="-FNAME-", size=(20, 1), font=font, background_color="white", text_color="black"),
        sg.Text("Middle Name:", size=(12, 1), pad=((20, 0), 0), font=font),
        sg.Input(key="-MNAME-", size=(20, 1), font=font, background_color="white", text_color="black"),
        sg.Text("Last Name:", size=(12, 1), pad=((20, 0), 0), font=font),
        sg.Input(key="-LNAME-", size=(20, 1), font=font, background_color="white", text_color="black")
    ]], pad=(0, 10))],

    [sg.Column([[
        sg.Text("Country of Birth:", size=(12, 1), font=font),
        sg.Combo(list(country_options.keys()), key="-COB-", readonly=True, size=(30, 1), font=font),
        sg.Text("Birthplace:", size=(12, 1), pad=((20, 0), 0), font=font),
        sg.Input(key="-BIRTHPLACE-", size=(30, 1), font=font, background_color="white", text_color="black")
    ]], pad=(0, 10))],

    [sg.Column([[
        sg.Push(),
        sg.Button("Submit", size=(10, 1), font=font),
        sg.Push()
    ]], pad=(0, 10))]
    ]


    window = sg.Window("Study Selection", layout, size=(1200, 375), resizable=True, finalize=True)

    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED:
            break

        if event == "-STUDY-":
            study_label = values["-STUDY-"]
            study_code = study_options.get(study_label)
            if study_code:
                subject_id = get_next_subject_id(study_code, conn)
                window["-SUBJECT_ID-"].update(subject_id)
        
        if event == "-DOB-":
            if values["-DOB-"] == placeholder_dob:
                window["-DOB-"].update("")

        if event == "Submit":
            submit_success = submit_event(values, options, conn)
            if submit_success:  # Clear fields after submission
                for key in [
                    "-FNAME-", "-MNAME-", "-LNAME-", "-DOB-", "-GENDER-", "-COB-",
                    "-BIRTHPLACE-","-SUBJECT_ID-", "-STUDY-",
                ]:
                    window[key].update("")
                
                if not values["-DOB-"]:
                    window["-DOB-"].update(placeholder_dob)

    conn.close()
    window.close()


def submit_event(values, options, conn) -> bool:
    required_fields = {
        "Study": values["-STUDY-"],
        "First Name": values["-FNAME-"],
        "Last Name": values["-LNAME-"],
        "Date of Birth": values["-DOB-"]
    }
    missing = [label for label, val in required_fields.items() if not val]
    if missing:
        sg.popup_error(f"The following required fields are missing: {', '.join(missing)}")
        return False

    try:
        datetime.strptime(values["-DOB-"], "%Y-%m-%d")
    except ValueError:
        sg.popup_error("Date must be in YYYY-MM-DD format.")
        return False

    data = {
        "subject_id": values["-SUBJECT_ID-"],
        "first_name_birth": values["-FNAME-"],
        "middle_name_birth": values["-MNAME-"],
        "last_name_birth": values["-LNAME-"],
        "date_of_birth_subject": values["-DOB-"],
        "country_of_birth": options.country_options.get(values["-COB-"], ""),
        "gender_at_birth": options.gender_options.get(values["-GENDER-"], ""),
        "birthplace": values["-BIRTHPLACE-"],
        "redcap_event_name": "manual",
        "guid": "",
        "old_subject_id": ""
    }

    for key in data:
        if data[key] is None:
            data[key] = ""

    try:
        query_str = """
        INSERT INTO subject (
            subject_id, first_name_birth, middle_name_birth, last_name_birth,
            date_of_birth_subject, country_of_birth, gender_at_birth,
            birthplace, redcap_event_name, guid, old_subject_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cur:
            cur.execute(query_str, (
                data["subject_id"],
                data["first_name_birth"],
                data["middle_name_birth"],
                data["last_name_birth"],
                data["date_of_birth_subject"],
                data["country_of_birth"],
                data["gender_at_birth"],
                data["birthplace"],
                data["redcap_event_name"],
                data["guid"],
                data["old_subject_id"]
            ))
            conn.commit()
            sg.popup("Submission successful!")
    except Exception as e:
        sg.popup_error("Database insert failed:", str(e))

    return True


if __name__ == "__main__":
    launch_gui()
