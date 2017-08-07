import json
import time

from DDPClient import DDPClient


def main(url):
    character = {}
    client = DDPClient('ws://dicecloud.com/websocket', auto_reconnect=False)
    client.is_connected = False
    client.connect()
    def connected():
        client.is_connected = True
    client.on('connected', connected)
    while not client.is_connected:
        time.sleep(1)
    client.subscribe('singleCharacter', [url])
    def update_character(collection, _id, fields):
        if character.get(collection) is None:
            character[collection] = []
        fields['id'] = _id
        character.get(collection).append(fields)
    client.on('added', update_character)
    time.sleep(10)
    client.close()
    character['id'] = url
    return character

if __name__ == "__main__":
    url = None
    while not url:
        url = input("Input Dicecloud Sheet ID: ")
    c = main(url)
    print(c)
    def serialize(o):
        return str(o)
    with open('./output/dicecloud-test.json', mode='w') as f:
        json.dump(c, f, skipkeys=True, sort_keys=True, indent=4, default=serialize)