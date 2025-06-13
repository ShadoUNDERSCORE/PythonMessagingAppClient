import asyncio
import aioconsole
import requests
import hashlib
import urllib.parse
import json
from datetime import datetime
import sqlite3
import re
import os
import sys

from websockets.asyncio.client import connect, ClientConnection
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, Label
from textual.scroll_view import ScrollableContainer

SERVER_URL = "localhost:8000"
HTTP_URL = f"http://{SERVER_URL}"
WEBSOCKET_URL = f"ws://{SERVER_URL}"

glb_recipient = ""
glb_username = ""
session_messages = asyncio.Queue()
shutdown_event = asyncio.Event()
message_db_updated_event = asyncio.Event()

db_con = sqlite3.connect(f"local{input("db: ")}.db")
db_cur = db_con.cursor()


# TODO: Delete the Oldest Message After 1,000 Messages are Stored In the Table


def _log(message):
    with open("log.log", "a") as f:
        f.write(f"> {message}\n")


def get_most_recent_message():
    chat_id = hashlib.sha256("-".join(sorted([glb_username, glb_recipient])).encode()).hexdigest()
    res = db_cur.execute(f'SELECT * FROM "{glb_username}" WHERE chat_id=?', (chat_id,))
    messages = [(f"|{datetime.strptime(m[5], "%Y-%m-%dT%H:%M:%S.%f").strftime("%Y-%m-%d %H:%M")}|"
                 f"\n{m[1]}> {m[4]}") for m in res.fetchall()]
    return messages[-1]


class LoginUI(App):
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    def compose(self) -> ComposeResult:
        yield Label("Username")
        yield Input(id="uname_field")
        yield Label("Password")
        yield Input(id="passwd_field")
        yield Label("Contact's Username")
        yield Input(id="recipient_field")

    @on(Input.Submitted, "#uname_field")
    def uname_entered(self, event: Input.Submitted):
        global glb_username
        glb_username = sanitize_input(event.value)
        self.screen.focus_next()

    @on(Input.Submitted, "#passwd_field")
    def passwd_entered(self, event: Input.Submitted):
        password = event.value
        if not login(password):
            exit("NOT A VALID USERNAME PASSWORD COMBO")
        self.screen.focus_next()

    @on(Input.Submitted, "#recipient_field")
    def recipient_entered(self, event: Input.Submitted):
        global glb_recipient
        glb_recipient = event.value
        self.exit()

    def action_quit(self) -> None:
        exit()


class MessagesWidget(ScrollableContainer):

    def compose(self) -> ComposeResult:
        chat_id = hashlib.sha256("-".join(sorted([glb_username, glb_recipient])).encode()).hexdigest()
        res = db_cur.execute(f'SELECT * FROM "{glb_username}" WHERE chat_id=?', (chat_id,))
        simplified_messages = [(m[1], m[4], m[5]) for m in res.fetchall()]
        for author, message, date in simplified_messages:
            yield Label(f"|{datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f").strftime("%Y-%m-%d %H:%M")}|"
                        f"\n{author}> {message}")


class ChatUI(App):
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    def compose(self) -> ComposeResult:
        yield Label(glb_recipient)
        yield MessagesWidget()
        yield Input(id="new_msg_field")

    def _on_key(self, event: events.Key) -> None:
        message_widget = self.query_one(MessagesWidget)
        input_widget = self.query_one("#new_msg_field", Input)
        if not message_widget.is_vertical_scroll_end:
            message_widget.scroll_end(immediate=True, speed=0)
            input_widget.focus()

    @on(Input.Submitted, "#new_msg_field")
    async def new_message_entered(self, event: Input.Submitted):
        await session_messages.put(event.value)
        input_widget = self.query_one("#new_msg_field", Input)
        input_widget.value = ""
        message_widget = self.query_one(MessagesWidget)
        await message_db_updated_event.wait()
        await message_widget.mount(Label(get_most_recent_message()))
        message_widget.scroll_end(immediate=True, speed=0)
        message_db_updated_event.clear()

    def action_quit(self) -> None:
        self.exit()
        shutdown_event.set()


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
    requests.post(f"{HTTP_URL}/create_account", json={"username": new_username, "password": new_password})
    db_cur.execute(f"""CREATE TABLE IF NOT EXISTS {new_username}(
                           id INTEGER PRIMARY KEY,
                           sent_by TEXT,
                           sent_to TEXT,
                           chat_id TEXT,
                           message TEXT,
                           timestamp TEXT
                           )""")
    db_con.commit()

    global glb_username
    glb_username = new_username
    return login(new_password)


def login(password: str) -> bool:
    response = requests.post(f"{HTTP_URL}/login",
                             json={"username": glb_username, "password": password})
    if response.status_code == 200:
        db_cur.execute(f"""CREATE TABLE IF NOT EXISTS {glb_username}(
                                   id INTEGER PRIMARY KEY,
                                   sent_by TEXT,
                                   sent_to TEXT,
                                   chat_id TEXT,
                                   message TEXT,
                                   timestamp TEXT
                                   )""")
        db_con.commit()
        return True
    elif response.status_code == 404:
        exit("NOT FOUND")
    else:
        return False


def add_contact():
    clear()
    new_contact = input("New Contact's Username: ")
    db_cur.execute("""CREATE TABLE IF NOT EXISTS contacts(
                        id INTEGER PRIMARY KEY,
                        contact_of TEXT,
                        contact_name TEXT
                        )""")
    db_cur.execute(f"INSERT INTO contacts(contact_of, contact_name) VALUES(?,?)",
                   (glb_username, new_contact))
    db_con.commit()
    return new_contact


def select_contact():
    clear()
    print("\nSELECT CONTACT\n")
    print("Type a Contact's Username\nor\nSimply Press Enter to Add a New One:\n")
    if not db_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'").fetchall():
        return add_contact()
    res = db_cur.execute(f"SELECT contact_name FROM contacts WHERE contact_of=?", (glb_username,))
    contacts = [c[0] for c in res.fetchall()]
    for c in contacts:
        print(f"- {c}")
    selection = input("> ")
    if selection == "":
        return add_contact()
    elif selection in contacts:
        return selection
    else:
        raise ValueError("Not a Valid Contact")


async def send_messages(websocket: ClientConnection):
    # Accept User Input and Send Messages
    chat_id = hashlib.sha256("-".join(sorted([glb_username, glb_recipient])).encode()).hexdigest()
    while True:
        try:
            _log("waiting for message to send")
            message = await session_messages.get()
            message_dict = {
                "sent_by": glb_username,
                "sent_to": glb_recipient,
                "chat_id": chat_id,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(message_dict))
            db_cur.execute(f"""INSERT INTO {glb_username}
                            (sent_by, sent_to, chat_id, message, timestamp) 
                            VALUES (?,?,?,?,?)""",
                           (
                               glb_username,
                               message_dict.get("sent_to"),
                               message_dict.get("chat_id"),
                               message_dict.get("message"),
                               message_dict.get("timestamp")
                           ))
            db_con.commit()
            message_db_updated_event.set()
        except asyncio.CancelledError:
            print("Session Cancelled")
            return


async def receive_messages(websocket: ClientConnection, chat_ui_app: ChatUI):
    try:
        async for new_message in websocket:
            new_message_dict = json.loads(new_message)
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
            message_widget = chat_ui_app.query_one(MessagesWidget)
            await message_widget.mount(Label(get_most_recent_message()))
    except asyncio.CancelledError:
        print("Cancelled")
        return


async def start_ws():
    async with connect(f"{WEBSOCKET_URL}/socket?username={urllib.parse.quote(glb_username)}") as ws:
        chat_ui_app = ChatUI()
        ui_task = asyncio.create_task(chat_ui_app.run_async())
        recv_task = asyncio.create_task(receive_messages(ws, chat_ui_app))
        send_task = asyncio.create_task(send_messages(ws))

        await shutdown_event.wait()
        recv_task.cancel()
        send_task.cancel()

        await asyncio.gather(recv_task, send_task)
        await ui_task


if __name__ == "__main__":
    try:
        LoginUI().run()
        asyncio.run(start_ws())
    except KeyboardInterrupt:
        print("\n\033[31mKeyboard Interrupt\033[0m")
        exit()
