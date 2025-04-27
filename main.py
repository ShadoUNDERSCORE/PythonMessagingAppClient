import asyncio
import aioconsole
import requests
from websockets.asyncio.client import connect, ClientConnection
import hashlib
import urllib.parse
import json
from datetime import datetime
import sqlite3


SERVER_URL = "localhost:8000"
HTTP_URL = f"http://{SERVER_URL}"
WEBSOCKET_URL = f"ws://{SERVER_URL}"

db_con = sqlite3.connect("local.db")
db_cur = db_con.cursor()
# TODO: Create a Table for Each Contact
# TODO: Delete the Oldest Message After 300 Messages are Stored In a Table
# TODO: Create a Contact System


def create_account() -> str | bool:
    print("\nCREATE ACCOUNT\n")
    new_username = input("Enter A Username: ")
    new_password = input("Enter A Password: ")
    response = requests.post(f"{HTTP_URL}/create_account",
                             json={"username": new_username, "password": new_password})
    return login(new_username, new_password)


def login(username: str | None = None, password: str | None = None) -> str | bool:
    print("\nLOGIN\n")
    if not username and not password:
        username = input("Enter Username: ")
        password = input("Enter Password: ")
    response = requests.post(f"{HTTP_URL}/login",
                             json={"username": username, "password": password})
    print(response.json())
    if response.status_code == 200:
        return username
    elif response.status_code == 404:
        # TODO: Let User Try Again or Create Account
        return False
    else:
        return False


async def send_messages(websocket: ClientConnection, username: str):
    # Accept User Input and Send Messages
    while True:
        recipient = await aioconsole.ainput("To: ")
        chat_id = hashlib.sha256("-".join(sorted([username, recipient])).encode()).hexdigest()
        message = await aioconsole.ainput("> ")
        message_dict = {
            "sent_by": username,
            "sent_to": recipient,
            "chat_id": chat_id,
            "message": message,
            "timestamp": datetime.now()
        }
        await websocket.send(json.dumps(message_dict))
        # TODO: Add Message to local db


async def receive_messages(websocket: ClientConnection):
    async for new_message in websocket:
        new_message_dict = json.loads(new_message)
        # TODO: Add Message to local db


async def ws_connection(username: str):
    async with connect(f"{WEBSOCKET_URL}/socket?username={urllib.parse.quote(username)}") as websocket:
        # Receive Missed Messages
        # Store Sent and Received Messages in SQLite DB
        await asyncio.gather(receive_messages(websocket), send_messages(websocket, username))


def main():
    # Create Account or Login
    command = input("Create Account (1) or Login (2): ")
    if command not in ["1", "2"]:
        print("Not a Valid Input")
    if command == "1":
        username = create_account()
    else:
        username = login()
    if username:
        asyncio.run(ws_connection(username))
    else:
        print("Login Failed")


if __name__ == "__main__":
    main()
