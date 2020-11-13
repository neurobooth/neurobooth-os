import eel
import sqlite3 as sql
import json
import os

eel.init('www', ['.js', '.html', '.jpg'])
con = sql.connect('users.db')
c = con.cursor()

def create_db():
    

    c.execute(''' CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT
    )''')

@eel.expose
def register(username,password):
    
    c.execute("SELECT * FROM users WHERE username=:user",{"user":username})
    check = c.fetchall()
    
    if len(check) == 0:
        c.execute("INSERT INTO users(username,password) VALUES (:username,:password)",{"username":username,"password":password})
        con.commit()

        return 1
    else:
        return 0

@eel.expose
def login(username,password):
    c.execute("SELECT * FROM users WHERE username=:user",{"user":username})
    check = c.fetchall()

    
    if len(check) == 1 and check[0][2] == password:
        return 1
    else:
        return 0

@eel.expose
def get_data_mt(file_name, data):
    with open(os.path.join('data', file_name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data[1:-1], f, ensure_ascii=False, indent=4)

@eel.expose
def get_data(results, score, outcomes):
    print(results, score, outcomes)


if __name__ == "__main__":
    create_db()  
    eel.start('register.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})
   