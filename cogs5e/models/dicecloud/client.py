import logging
import os
import sys
import time
import urllib.parse

from MeteorClient import MeteorClient

import credentials
from .errors import InsertFailure, LoginFailure
from .http import DicecloudHTTP

TESTING = (os.environ.get("TESTING", False) or 'test' in sys.argv)
UNAME = 'avrae' if not TESTING else credentials.test_dicecloud_user
PWD = credentials.dicecloud_pass.encode() if not TESTING else credentials.test_dicecloud_pass.encode()
API_KEY = credentials.dicecloud_token if not TESTING else credentials.test_dicecloud_token
API_BASE = "https://dicecloud.com"
SOCKET_BASE = "wss://dicecloud.com/websocket"

log = logging.getLogger(__name__)


class DicecloudClient:
    instance = None
    user_id = None

    def __init__(self, debug=False):
        self.meteor_client = MeteorClient(SOCKET_BASE, debug=debug)
        self.http = DicecloudHTTP(API_BASE, API_KEY, debug=debug)
        self.logged_in = False

    @classmethod
    def getInstance(cls):
        if cls.instance is None:
            try:
                cls.instance = cls(debug=TESTING)
                cls.instance.initialize()
            except:
                return None
        return cls.instance

    def initialize(self):
        log.info(f"Initializing Dicecloud Meteor client (debug={TESTING})")
        self.meteor_client.connect()
        loops = 0
        while (not self.meteor_client.connected) and loops < 100:
            time.sleep(0.1)
            loops += 1
        log.info(f"Connected to Dicecloud in {loops/10} seconds")

        def on_login(error, data):
            if data:
                type(self).user_id = data.get('id')
                self.logged_in = True
            else:
                log.warning(error)
                raise LoginFailure()

        self.meteor_client.login(UNAME, PWD, callback=on_login)
        loops = 0
        while not self.logged_in and loops < 100:
            time.sleep(0.1)
            loops += 1
        log.info(f"Logged in as {self.user_id}")

    async def _get_list_id(self, character, list_name=None):
        """
        :param character: (Character) the character to get the spell list ID of.
        :param list_name: (str) The name of the spell list to look for. Returns default if not passed.
        :return: (str) The default list id.
        """
        if character.get_cached_spell_list_id():
            return character.get_cached_spell_list_id()
        char_id = character.id[10:]

        char = await self.get_character(char_id)
        if list_name:
            list_id = next((l for l in char.get('spellLists', []) if l['name'].lower() == list_name.lower()), None)
        else:
            list_id = next((l for l in char.get('spellLists', [])), None)
        character.update_cached_spell_list_id(list_id)
        return list_id

    async def get_character(self, charId):
        return await self.http.get(f'/character/{charId}/json')

    async def add_spell(self, character, spell):
        """Adds a spell to the dicecloud list."""
        return await self.add_spells(character, [spell])

    async def add_spells(self, character, spells, spell_list=None):
        """
        :param character: (Character) The character to add spells for.
        :param spells: (list) The list of spells to add
        :param spell_list: (str) The spell list name to search for in Dicecloud.
        """
        assert character.live
        list_id = await self._get_list_id(character, spell_list)
        if not list_id:  # still
            raise InsertFailure("No matching spell lists on origin sheet. Run `!update` if this seems incorrect.")
        return await self.http.post(f'/api/character/{character.id[10:]}/spellList/{list_id}',
                                    [s.to_dicecloud() for s in spells])

    async def create_character(self, name: str = "New Character", gender: str = None, race: str = None,
                               backstory: str = None):
        data = {'name': name, 'writers': [self.user_id]}
        if gender is not None:
            data['gender'] = gender
        if race is not None:
            data['race'] = race
        if backstory is not None:
            data['backstory'] = backstory

        data['settings'] = {'viewPermission': 'public'}  # sharing is caring!
        response = await self.http.post('/api/character', data)
        return response['id']

    async def delete_character(self, charId: str):
        await self.http.delete(f'/api/character/{charId}')

    async def get_user_id(self, username: str):
        username = urllib.parse.quote_plus(username)
        userId = await self.http.get(f'/api/user?username={username}')
        return userId['id']

    async def transfer_ownership(self, charId: str, userId: str):
        await self.http.put(f'/api/character/{charId}/owner', {'id': userId})

    async def insert_feature(self, charId, feature):
        return (await self.insert_features(charId, [feature]))[0]

    async def insert_features(self, charId: str, features: list):
        response = await self.http.post(f'/api/character/{charId}/feature', [f.to_dict() for f in features])
        return response

    async def insert_proficiency(self, charId, prof):
        return (await self.insert_proficiencies(charId, [prof]))[0]

    async def insert_proficiencies(self, charId: str, profs: list):
        response = await self.http.post(f'/api/character/{charId}/prof', [p.to_dict() for p in profs])
        return response

    async def insert_effect(self, charId, effect):
        return (await self.insert_effects(charId, [effect]))[0]

    async def insert_effects(self, charId: str, effects: list):
        response = await self.http.post(f'/api/character/{charId}/effect', [e.to_dict() for e in effects])
        return response

    async def insert_class(self, charId, klass):
        return (await self.insert_classes(charId, [klass]))[0]

    async def insert_classes(self, charId: str, classes: list):
        response = await self.http.post(f'/api/character/{charId}/class', [c.to_dict() for c in classes])
        return response


dicecloud_client = DicecloudClient.getInstance()
