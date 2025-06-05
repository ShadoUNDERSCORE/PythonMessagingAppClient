import asyncio
import aioconsole
import requests
from websockets.asyncio.client import connect, ClientConnection
import hashlib
import urllib.parse
import json
from datetime import datetime
import sqlite3
import re
import os
import sys


SERVER_URL = "localhost:8000"
HTTP_URL = f"http://{SERVER_URL}"
WEBSOCKET_URL = f"ws://{SERVER_URL}"

recipient = None

db_con = sqlite3.connect(f"local{input("db: ")}.db")
db_cur = db_con.cursor()
# TODO: Delete the Oldest Message After 1,000 Messages are Stored In the Table
# TODO: See if I can make input and messages more separated eg:
# Dave> Message of words
# Jeff> Another message
# > Message to be sent


def sanitize_input(name: str) -> str:
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
        raise ValueError("Invalid table name")
    return name


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')
    sys.stdout.flush()


def create_account() -> str | bool:
    clear()
    print("\nCREATE ACCOUNT\n")
    new_username = sanitize_input(input("Enter A Username: "))
    new_password = input("Enter A Password: ")
    response = requests.post(f"{HTTP_URL}/create_account",
                             json={"username": new_username, "password": new_password})
    # Create a Contacts Table for this User
    db_cur.execute(f"""CREATE TABLE IF NOT EXISTS {new_username}(
                           id INTEGER PRIMARY KEY,
                           sent_by TEXT,
                           sent_to TEXT,
                           chat_id TEXT,
                           message TEXT,
                           timestamp TEXT
                           )""")
    db_con.commit()
    return login(new_username, new_password)


def login(username: str | None = None, password: str | None = None) -> str | bool:
    clear()
    print("\nLOGIN\n")
    if not username and not password:
        username = sanitize_input(input("Enter Username: "))
        password = input("Enter Password: ")
    response = requests.post(f"{HTTP_URL}/login",
                             json={"username": username, "password": password})
    if response.status_code == 200:
        return username
    elif response.status_code == 404:
        return login()
    else:
        return False


def add_contact(contact_of: str):
    clear()
    new_contact = input("New Contact's Username: ")
    db_cur.execute("""CREATE TABLE IF NOT EXISTS contacts(
                        id INTEGER PRIMARY KEY,
                        contact_of TEXT,
                        contact_name TEXT
                        )""")
    db_cur.execute(f"INSERT INTO contacts(contact_of, contact_name) VALUES(?,?)",
                   (contact_of, new_contact))
    db_con.commit()
    return new_contact


def select_contact(contact_of: str):
    clear()
    print("\nSELECT CONTACT\n")
    print("Type a Contact's Username\nor\nSimply Press Enter to Add a New One:\n")
    contact_of = sanitize_input(contact_of)
    if not db_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'").fetchall():
        return add_contact(contact_of)
    res = db_cur.execute(f"SELECT contact_name FROM contacts WHERE contact_of=?", (contact_of,))
    contacts = [c[0] for c in res.fetchall()]
    for c in contacts:
        print(f"- {c}")
    selection = input("> ")
    if selection == "":
        return add_contact(contact_of)
    elif selection in contacts:
        return selection
    else:
        raise ValueError("Not a Valid Contact")


async def send_messages(websocket: ClientConnection, username: str):
    # Accept User Input and Send Messages
    while True:
        chat_id = hashlib.sha256("-".join(sorted([username, recipient])).encode()).hexdigest()
        message = await aioconsole.ainput("> ")
        message_dict = {
            "sent_by": username,
            "sent_to": recipient,
            "chat_id": chat_id,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(message_dict))
        db_cur.execute(f"""INSERT INTO {sanitize_input(username)}
                        (sent_by, sent_to, chat_id, message, timestamp) 
                        VALUES (?,?,?,?,?)""",
                       (
                            username,
                            message_dict.get("sent_to"),
                            message_dict.get("chat_id"),
                            message_dict.get("message"),
                            message_dict.get("timestamp")
                       ))
        db_con.commit()


async def receive_messages(websocket: ClientConnection):
    async for new_message in websocket:
        new_message_dict = json.loads(new_message)
        print(f"{new_message_dict.get('message')}\n> ", end="")
        db_cur.execute(f"""INSERT INTO {sanitize_input(new_message_dict.get('sent_to'))}
                        (sent_by, sent_to, chat_id, message, timestamp)  
                        VALUES (?,?,?,?,?)""",
                       (
                           new_message_dict.get('sent_by'),
                           new_message_dict.get("sent_to"),
                           new_message_dict.get("chat_id"),
                           new_message_dict.get("message"),
                           new_message_dict.get("timestamp")
                       ))
        db_con.commit()


async def ws_connection(username: str):
    username = sanitize_input(username)
    async with connect(f"{WEBSOCKET_URL}/socket?username={urllib.parse.quote(username)}") as websocket:
        # Receive Missed Messages
        # Store Sent and Received Messages in SQLite DB
        await asyncio.gather(receive_messages(websocket), send_messages(websocket, username))


def main():
    clear()
    global recipient
    # Create Account or Login
    command = input("Create Account (1) or Login (2): ")
    if command not in ["1", "2"]:
        print("Not a Valid Input")
    if command == "1":
        username = create_account()
    else:
        username = login()
    if username:
        recipient = select_contact(username)
        asyncio.run(ws_connection(username))
    else:
        print("Login Failed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\033[31mKeyboard Interrupt\033[0m")
        exit()

