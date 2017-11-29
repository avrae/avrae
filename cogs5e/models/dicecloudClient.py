import asyncio
import logging
import time

from MeteorClient import MeteorClient

import credentials
from cogs5e.models.errors import LoginFailure, InsertFailure

UNAME = 'avrae'
PWD = credentials.dicecloud_pass.encode()

log = logging.getLogger(__name__)


class DicecloudClient(MeteorClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logged_in = False
        self.user_id = None

    def initialize(self):
        self.connect()
        while not self.connected:
            time.sleep(0.1)
        log.info("Connected")

        def on_login(error, data):
            if data:
                self.user_id = data.get('id')
                self.logged_in = True
            else:
                raise LoginFailure()

        self.login(UNAME, PWD, callback=on_login)
        while not self.logged_in:
            time.sleep(0.1)
        log.info(f"Logged in as {self.user_id}")

    async def _get_list_id(self, character):
        """
        :param character: (dict) the character to get the spell list ID of.
        :return: (str) The default list id.
        """
        list_id = None

        def on_add(collection, _id, fields):
            nonlocal list_id
            if collection == 'spellLists' and fields['charId'] == character.id[10:] and not fields.get('removed'):
                list_id = _id

        self.on('added', on_add)
        self.subscribe('singleCharacter', [character.id[10:]])
        self.unsubscribe('singleCharacter')
        for _ in range(20):  # wait 2 sec for spelllist data
            if not list_id:
                await asyncio.sleep(0.1)
            else:
                break
        return list_id

    async def sync_add_spell(self, character, spell):
        """Adds a spell to the dicecloud list."""
        assert character.live
        list_id = await self._get_list_id(character)
        log.info(list_id)
        if not list_id:  # still
            raise InsertFailure("No spell lists on origin sheet.")

        def insert_callback(error, data):
            if error:
                log.warning(str(error))
            else:
                log.debug(data)

        spellData = {
            'name': spell['name'],
            'description': spell['description'],
            'castingTime': spell['castingTime'],
            'range': spell['range'],
            'duration': spell['duration'],
            'components': {
                'verbal': spell['components.verbal'],
                'somatic': spell['components.somatic'],
                'concentration': spell['components.concentration'],
                'material': spell['components.material']
            },
            'ritual': spell['ritual'],
            'level': spell['level'],
            'school': spell['school'],
            'charId': character.id[10:],
            'parent': {
                'id': list_id,
                'collection': "SpellLists",
            },
            'prepared': "prepared",
        }
        self.insert('spells', spellData, insert_callback)

    async def sync_add_mass_spells(self, character, spells):
        """
        :param character: (Character) The character to add spells for.
        :param spells: (list) The list of spells to add
        """
        assert character.live
        list_id = await self._get_list_id(character)
        log.info(list_id)
        if not list_id:  # still
            raise InsertFailure("No spell lists on origin sheet.")
        for spell in spells:
            def insert_callback(error, data):
                if error:
                    log.warning(str(error))
                else:
                    log.debug(data)

            spellData = {
                'name': spell['name'],
                'description': spell['description'],
                'castingTime': spell['castingTime'],
                'range': spell['range'],
                'duration': spell['duration'],
                'components': {
                    'verbal': spell['components.verbal'],
                    'somatic': spell['components.somatic'],
                    'concentration': spell['components.concentration'],
                    'material': spell['components.material']
                },
                'ritual': spell['ritual'],
                'level': spell['level'],
                'school': spell['school'],
                'charId': character.id[10:],
                'parent': {
                    'id': list_id,
                    'collection': "SpellLists",
                },
                'prepared': "prepared",
            }
            self.insert('spells', spellData, insert_callback)


dicecloud_client = DicecloudClient('ws://dicecloud.com/websocket', debug=False)  # turn debug off later
dicecloud_client.initialize()
