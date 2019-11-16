import asyncio
import json
import logging

import aiohttp

from .errors import Forbidden, HTTPException, NotFound, Timeout

MAX_TRIES = 10
log = logging.getLogger(__name__)


class DicecloudHTTP:
    def __init__(self, api_base, api_key, debug=False):
        self.base = api_base
        self.key = api_key
        self.debug = debug

    async def request(self, method, endpoint, body, headers=None, query=None):
        if headers is None:
            headers = {}
        if query is None:
            query = {}

        if body is not None:
            if isinstance(body, str):
                headers["Content-Type"] = "text/plain"
            else:
                body = json.dumps(body)
                headers["Content-Type"] = "application/json"

        if self.debug:
            print(f"{method} {endpoint}: {body}")
        data = None
        async with aiohttp.ClientSession() as session:
            for _ in range(MAX_TRIES):
                try:
                    async with session.request(method, f"{self.base}{endpoint}", data=body, headers=headers,
                                               params=query) as resp:
                        log.info(f"Dicecloud returned {resp.status} ({endpoint})")
                        if resp.status == 200:
                            data = await resp.json(encoding='utf-8')
                            break
                        elif resp.status == 429:
                            timeout = await resp.json(encoding='utf-8')
                            log.warning(f"Dicecloud ratelimit hit ({endpoint}) - resets in {timeout}ms")
                            await asyncio.sleep(timeout['timeToReset'] / 1000)  # rate-limited, wait and try again
                        elif 400 <= resp.status < 600:
                            if resp.status == 403:
                                raise Forbidden(resp.reason)
                            elif resp.status == 404:
                                raise NotFound(resp.reason)
                            else:
                                raise HTTPException(resp.status, resp.reason)
                        else:
                            log.warning(f"Unknown response from Dicecloud: {resp.status}")
                except aiohttp.ServerDisconnectedError:
                    raise HTTPException(None, "Server disconnected")
        if not data:  # we did 10 loops and always got either 200 or 429 but we have no data, so we must have 429ed
            raise Timeout(f"Dicecloud failed to respond after {MAX_TRIES} tries. Please try again.")

        return data

    async def get(self, endpoint):
        return await self.request("GET", endpoint, None, query={"key": self.key})

    async def post(self, endpoint, body):
        return await self.request("POST", endpoint, body, headers={"Authorization": self.key})

    async def put(self, endpoint, body):
        return await self.request("PUT", endpoint, body, headers={"Authorization": self.key})

    async def delete(self, endpoint):
        return await self.request("DELETE", endpoint, None, headers={"Authorization": self.key})
