import eel
from collections import OrderedDict



session_information = {"subject_id":"", "condition":"", "gender":"", "age":"", 
                       "rc_initials":"", "tasks":OrderedDict({"sync_test":True,
                        "dst":True, "mt":"mouse_tracking.html", "ft":True })}

tasks_html_pages = {"sync_test":"synch_task.html", 
                    "dst":"DSC_simplified_oneProbe_2020.html", 
                    "mt":"mouse_tracking.html",
                    "ft":"task_motor_assess/motortask_instructions.html"}

selected_tasks = []                       
      
def find_checked_tasks(tasks):
    global selected_tasks
    for key, selected in tasks.items():
        if selected:
            selected_tasks.append(key)
            
    
@eel.expose
def get_session_info(sub_id, condition, gender, age, rc_initials, check_st, check_dst, check_mt, check_ft):
    global session_information
    print(type(check_st))
    session_information["subject_id"] = sub_id
    session_information["condition"] = condition
    session_information["gender"] = gender
    session_information["age"] = age
    session_information["rc_initials"] = rc_initials
    session_information["tasks"]["sync_test"] = check_st
    session_information["tasks"]["dst"] = check_dst
    session_information["tasks"]["mt"] = check_mt
    session_information["tasks"]["ft"] = check_ft
    find_checked_tasks(session_information["tasks"])
    print(session_information)


    for key, selected in session_information["tasks"].items():
        
        if selected:
            if key == "sync_test":
                eel.go_to_link(tasks_html_pages[key])
                break
                
            elif key == "dst":
                eel.go_to_link(tasks_html_pages[key])
                break
            
            elif key == "mt":
                eel.go_to_link(tasks_html_pages[key])
                break

            elif key == "ft":
                eel.go_to_link(tasks_html_pages[key])
                break
                
@eel.expose
def send_session_info():
    return session_information

@eel.expose
def next_task(current_task):
    index = selected_tasks.index(current_task)
    if not current_task==selected_tasks[-1]:
        return tasks_html_pages[selected_tasks[index+1]]
    else:
        return 'index.html'
        

eel.init('www', ['.js', '.html', '.jpg'])


eel.start('index.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})






   