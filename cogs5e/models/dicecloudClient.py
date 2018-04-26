import asyncio
import logging
import os
import random
import sys
import time

from MeteorClient import MeteorClient

import credentials
from cogs5e.models.errors import LoginFailure, InsertFailure, MeteorClientException

TESTING = (os.environ.get("TESTING", False) or 'test' in sys.argv)
UNAME = 'avrae' if not TESTING else 'zhu.alt'
PWD = credentials.dicecloud_pass.encode() if not TESTING else credentials.test_dicecloud_pass.encode()

log = logging.getLogger(__name__)


class Parent:
    def __init__(self, _id, collection, group=None):
        self.id = _id
        self.collection = collection
        self.group = group

    @classmethod
    def character(cls, charId):
        return cls(charId, 'Characters')

    @classmethod
    def race(cls, charId):
        return cls(charId, 'Characters', 'racial')

    @classmethod
    def class_(cls, classId):
        return cls(classId, 'Classes')

    @classmethod
    def feature(cls, featId):
        return cls(featId, 'Features')

    @classmethod
    def background(cls, charId):
        return cls(charId, 'Characters', 'background')

    def to_dict(self):
        d = {'id': self.id, 'collection': self.collection}
        if self.group is not None:
            d['group'] = self.group
        return d


class DicecloudClient(MeteorClient):
    instance = None
    user_id = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logged_in = False

    @classmethod
    def getInstance(cls):
        if cls.instance is None:
            try:
                cls.instance = cls('ws://dicecloud.com/websocket', debug=TESTING)
                cls.instance.initialize()
            except:
                return None
        return cls.instance

    def initialize(self):
        self.connect()
        loops = 0
        while not self.connected and loops < 100:
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

        self.login(UNAME, PWD, callback=on_login)
        while not self.logged_in:
            time.sleep(0.1)
        log.info(f"Logged in as {self.user_id}")

    async def _get_list_id(self, character, list_name=None):
        """
        :param character: (Character) the character to get the spell list ID of.
        :param list_name: (str) The name of the spell list to look for. Returns default if not passed.
        :return: (str) The default list id.
        """
        if character.get_cached_spell_list_id():
            return character.get_cached_spell_list_id()
        list_id = None

        def on_add(collection, _id, fields):
            nonlocal list_id
            if collection == 'spellLists' and fields['charId'] == character.id[10:] and not fields.get('removed'):
                if list_name:
                    if fields.get('name').lower() == list_name.lower():
                        list_id = _id
                else:
                    list_id = _id

        self.on('added', on_add)
        self.subscribe('singleCharacter', [character.id[10:]])
        self.unsubscribe('singleCharacter')
        for _ in range(20):  # wait 2 sec for spelllist data
            if not list_id:
                await asyncio.sleep(0.1)
            else:
                break
        character.update_cached_spell_list_id(list_id)
        return list_id

    async def sync_add_spell(self, character, spell):
        """Adds a spell to the dicecloud list."""
        assert character.live
        list_id = await self._get_list_id(character)
        log.info(list_id)
        if not list_id:  # still
            raise InsertFailure("No spell lists on origin sheet. Run `!update` if this seems incorrect.")

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

    async def sync_add_mass_spells(self, character, spells, spell_list=None):
        """
        :param character: (Character) The character to add spells for.
        :param spells: (list) The list of spells to add
        :param spell_list: (str) The spell list name to search for in Dicecloud.
        """
        assert character.live
        list_id = await self._get_list_id(character, spell_list)
        log.info(list_id)
        if not list_id:  # still
            raise InsertFailure("No spell lists on origin sheet. Run `!update` if this seems incorrect.")

        def insert_callback(error, data):
            if error:
                log.warning(str(error))
            else:
                log.debug(data)

        for spell in spells:
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

    @staticmethod
    def _generate_id():
        valid_characters = "23456789ABCDEFGHJKLMNPQRSTWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(random.choice(valid_characters) for _ in range(17))

    def create_character(self, name: str = "New Character", gender: str = None, race: str = None,
                         backstory: str = None):
        data = {'name': name, 'owner': self.user_id}
        if gender is not None:
            data['gender'] = gender
        if race is not None:
            data['race'] = race
        if backstory is not None:
            data['backstory'] = backstory

        data['settings'] = {'viewPermission': 'public'}  # sharing is caring!
        data['_id'] = self._generate_id()
        self.insert('characters', data)
        return data['_id']

    def delete_character(self, charId: str):
        self.remove('characters', {'_id': charId})

    async def share_character(self, charId: str, username: str):
        userId = None

        def get_id_cb(err, data):
            nonlocal userId
            if err:
                raise MeteorClientException("Invalid user.")
            userId = data

        self.call("getUserId", [username], get_id_cb)
        for _ in range(100):  # wait 10 sec for user data
            if not userId:
                await asyncio.sleep(0.1)
            else:
                break

        if userId:
            def share_callback(error, data):
                if error:
                    log.warning(error)
                    raise MeteorClientException("Could not share character.")
                else:
                    log.debug(data)

            self.update('characters', {'_id': charId}, {
                '$addToSet': {'writers': userId},
                '$pull': {'readers': userId},
            }, share_callback)
            return True
        else:
            raise MeteorClientException("Invalid user.")

    def insert_feature(self, charId: str, name: str = "New Feature", description: str = None, uses: str = None,
                       used: int = 0, reset: str = 'manual', enabled: bool = True, alwaysEnabled: bool = True):
        if not reset in ('shortRest', 'longRest', 'manual'):
            raise ValueError("Reset must be shortRest, longRest, or manual")
        data = {'charId': charId, 'used': used, 'reset': reset, 'enabled': enabled, 'alwaysEnabled': alwaysEnabled}
        if name is not None:
            data['name'] = name
        if description is not None:
            data['description'] = description
        if uses is not None:
            data['uses'] = uses

        data['_id'] = self._generate_id()
        self.insert('features', data)
        return data['_id']

    def insert_proficiency(self, charId: str, parent: Parent, name: str = None, value: float = 1, type_: str = 'skill',
                           enabled: bool = True):
        if not value in (0, 0.5, 1, 2):
            raise ValueError("Value must be 0, 0.5, 1, or 2")
        if not type_ in ("skill", "save", "weapon", "armor", "tool", "language"):
            raise ValueError("Invalid proficiency type")
        data = {'charId': charId, 'parent': parent.to_dict(), 'value': value, 'type': type_, 'enabled': enabled}
        if name is not None:
            data['name'] = name

        data['_id'] = self._generate_id()
        self.insert('proficiencies', data)
        return data['_id']

    def insert_effect(self, charId: str, parent: Parent, operation: str, value: float = None,
                      calculation: str = None, stat: str = None, enabled: bool = True, name: str = None):
        if not operation in (
                "base", "proficiency", "add", "mul", "min", "max", "advantage", "disadvantage", "passiveAdd", "fail",
                "conditional"):
            raise ValueError("Invalid operation")
        data = {'charId': charId, 'parent': parent.to_dict(), 'operation': operation}
        if name is not None:
            data['name'] = name
        if value is not None:
            data['value'] = value
        if calculation is not None:
            data['calculation'] = calculation
        if stat is not None:
            data['stat'] = stat
        if enabled is not None:
            data['enabled'] = enabled

        data['_id'] = self._generate_id()
        self.insert('effects', data)
        return data['_id']

    def insert_class(self, charId: str, level: int, name: str = "New Level"):
        data = {'charId': charId, 'level': level}
        if name is not None:
            data['name'] = name

        data['_id'] = self._generate_id()
        self.insert('classes', data)
        return data['_id']

    def insert_spell_list(self, charId: str, name: str = "New Spell List", description: str = None, saveDC: str = None,
                          attackBonus: str = None, maxPrepared: str = None):
        data = {'charId': charId}
        if name is not None:
            data['name'] = name
        if description is not None:
            data['description'] = description
        if saveDC is not None:
            data['saveDC'] = saveDC
        if attackBonus is not None:
            data['attackBonus'] = attackBonus
        if maxPrepared is not None:
            data['maxPrepared'] = maxPrepared

        data['_id'] = self._generate_id()
        self.insert('classes', data)
        return data['_id']

    def insert_item(self, charId: str, parent: Parent, name: str = "New Item", plural: str = None,
                    description: str = None, quantity: int = 1, weight: float = 0, value: float = 0,
                    enabled: bool = False, requiresAttunement: bool = False, showIncrement: bool = False):
        data = {'charId': charId, 'parent': parent.to_dict()}
        if name is not None:
            data['name'] = name
        if plural is not None:
            data['plural'] = plural
        if description is not None:
            data['description'] = description
        if quantity is not None:
            data['quantity'] = quantity
        if weight is not None:
            data['weight'] = weight
        if value is not None:
            data['value'] = value
        if enabled is not None:
            data['enabled'] = enabled
        if requiresAttunement is not None:
            data['requiresAttunement'] = requiresAttunement
        if showIncrement is not None:
            data['settings'] = {'showIncrement': showIncrement}

        data['_id'] = self._generate_id()
        self.insert('items', data)
        return data['_id']


dicecloud_client = DicecloudClient.getInstance()
