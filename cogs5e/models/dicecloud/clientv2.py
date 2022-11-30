import asyncio
import logging
import time
import urllib.parse

from utils import config
from .errors import InsertFailure, LoginFailure
from .httpv2 import DicecloudV2HTTP

API_BASE = "https://beta.dicecloud.com/api"

log = logging.getLogger(__name__)


class DicecloudV2Client:
    instance = None

    def __init__(self, debug=False):
        self.http = DicecloudV2HTTP(
            API_BASE, config.DICECLOUDV2_USER, config.DICECLOUDV2_PASS, config.DCV2_NO_AUTH, debug=debug
        )

    @classmethod
    def getInstance(cls):
        if cls.instance is None and not config.NO_DICECLOUDV2:
            try:
                cls.instance = cls(debug=config.TESTING)
            except Exception as e:
                log.warning(e)
                return None
        return cls.instance

    async def get_character(self, charId):
        return await self.http.get(f"/creature/{charId}")
