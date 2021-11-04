import logging
from typing import List

from ddb.baseclient import BaseClient
from ddb.utils import ApiBaseModel
from utils.config import DDB_SCDS_SERVICE_URL
from .scds_types import SimplifiedCharacterData

log = logging.getLogger(__name__)


class CharacterStorageServiceClient(BaseClient):
    SERVICE_BASE = DDB_SCDS_SERVICE_URL
    logger = log

    async def get_characters(self, ddb_user, character_ids):
        """
        Gets simplified character data from the SCDS.

        :type ddb_user: ddb.auth.BeyondUser
        :type character_ids: list[int]
        :rtype: SimplifiedCharacterDataResponse
        """
        data = {
            "characterIds": character_ids
        }
        resp = await self.post(ddb_user, '/characters', json=data)
        return SimplifiedCharacterDataResponse.parse_obj(resp)


class SimplifiedCharacterDataResponse(ApiBaseModel):
    found_characters: List[SimplifiedCharacterData]
    queued_ids: List[int]
    not_found_ids: List[int]
