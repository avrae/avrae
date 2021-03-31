import logging
from collections import namedtuple

import aiohttp

from ddb.errors import CharacterServiceException
from utils.config import DDB_CHARACTER_SERVICE_URL as CHARACTER_SERVICE_BASE

log = logging.getLogger(__name__)
log.setLevel(10)


class CharacterServiceClient:
    def __init__(self, http):
        self.http = http

    async def request(self, ddb_user, method, route, **kwargs):
        """Performs a request on behalf of a DDB user."""
        try:
            async with self.http.request(method, f"{CHARACTER_SERVICE_BASE}{route}",
                                         headers={"Authorization": f"Bearer {ddb_user.token}"},
                                         **kwargs) as resp:
                log.debug(f"{method} {CHARACTER_SERVICE_BASE}{route} returned {resp.status}")
                if not 199 < resp.status < 300:
                    raise CharacterServiceException(f"Character Service returned {resp.status}: {await resp.text()}")
                try:
                    data = await resp.json()
                    log.debug(data)
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    raise CharacterServiceException(
                        f"Could not deserialize Character Service response: {await resp.text()}")
        except aiohttp.ServerTimeoutError:
            raise CharacterServiceException("Timed out connecting to Character Service")
        if not data['success']:
            raise CharacterServiceException(f"Character Service returned an error: {data['message']}")
        return CharacterServiceResponse(data['id'], data['message'], data['data'])

    async def set_damage_taken(self, ddb_user, removed_hit_points: int, temporary_hit_points: int, character_id: int):
        data = {
            "removedHitPoints": removed_hit_points,
            "temporaryHitPoints": temporary_hit_points,
            "characterId": character_id
        }
        return await self.request(ddb_user, 'PUT', '/life/hp/damage-taken', json=data)


CharacterServiceResponse = namedtuple('CharacterServiceResponse', 'id message data')
