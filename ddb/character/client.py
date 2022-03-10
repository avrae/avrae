import logging
from collections import namedtuple

from ddb.baseclient import BaseClient
from ddb.errors import CharacterServiceException
from utils.config import DDB_CHARACTER_SERVICE_URL as CHARACTER_SERVICE_BASE

log = logging.getLogger(__name__)


class CharacterServiceClient(BaseClient):
    SERVICE_BASE = CHARACTER_SERVICE_BASE
    logger = log

    async def request(self, *args, **kwargs):
        data = await super().request(*args, **kwargs)
        if not data["success"]:
            raise CharacterServiceException(
                f"Character Service returned an error: {data['message']}"
            )
        return CharacterServiceResponse(data["id"], data["message"], data["data"])

    # ==== Action ====
    async def set_limited_use(
        self, ddb_user, id: int, entity_type_id: int, uses: int, character_id: int
    ):
        data = {
            "id": id,
            "entityTypeId": entity_type_id,
            "uses": uses,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/action/limited-use", json=data)

    # ==== Life ====
    async def set_damage_taken(
        self,
        ddb_user,
        removed_hit_points: int,
        temporary_hit_points: int,
        character_id: int,
    ):
        data = {
            "removedHitPoints": removed_hit_points,
            "temporaryHitPoints": temporary_hit_points,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/life/hp/damage-taken", json=data)

    async def set_death_saves(
        self, ddb_user, success_count: int, fail_count: int, character_id: int
    ):
        data = {
            "successCount": success_count,
            "failCount": fail_count,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/life/death-saves", json=data)

    # ==== Spell ====
    async def set_pact_magic(
        self,
        ddb_user,
        level1: int,
        level2: int,
        level3: int,
        level4: int,
        level5: int,
        character_id: int,
    ):
        data = {
            "level1": level1,
            "level2": level2,
            "level3": level3,
            "level4": level4,
            "level5": level5,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/spell/pact-magic", json=data)

    async def set_spell_slots(
        self,
        ddb_user,
        level1: int,
        level2: int,
        level3: int,
        level4: int,
        level5: int,
        level6: int,
        level7: int,
        level8: int,
        level9: int,
        character_id: int,
    ):
        data = {
            "level1": level1,
            "level2": level2,
            "level3": level3,
            "level4": level4,
            "level5": level5,
            "level6": level6,
            "level7": level7,
            "level8": level8,
            "level9": level9,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/spell/slots", json=data)

    # ==== Currency ====
    async def set_currency(
        self, ddb_user, pp: int, gp: int, ep: int, sp: int, cp: int, character_id: int
    ):
        data = {
            "cp": cp,
            "sp": sp,
            "ep": ep,
            "gp": gp,
            "pp": pp,
            "characterId": character_id,
        }
        return await self.put(ddb_user, "/inventory/currency", json=data)


CharacterServiceResponse = namedtuple("CharacterServiceResponse", "id message data")
