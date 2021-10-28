import abc
import logging

import aiohttp

from .auth import BeyondUser
from .errors import ClientResponseError, ClientTimeoutError, ClientValueError


class BaseClient(abc.ABC):
    SERVICE_BASE: str = ...
    logger: logging.Logger = ...

    def __init__(self, http: aiohttp.ClientSession):
        self.http = http

    async def request(self, ddb_user: BeyondUser, method: str, route: str, **kwargs):
        """Performs a request on behalf of a DDB user."""
        try:
            async with self.http.request(method,
                                         f"{self.SERVICE_BASE}{route}",
                                         headers={"Authorization": f"Bearer {ddb_user.token}"},
                                         **kwargs) as resp:
                self.logger.debug(f"{method} {self.SERVICE_BASE}{route} returned {resp.status}")
                if not 199 < resp.status < 300:
                    data = await resp.text()
                    self.logger.warning(
                        f"{method} {self.SERVICE_BASE}{route} returned {resp.status} {resp.reason}\n{data}")
                    raise ClientResponseError(f"D&D Beyond returned an error: {resp.status}: {resp.reason}")
                try:
                    data = await resp.json()
                    self.logger.debug(data)
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    data = await resp.text()
                    self.logger.warning(
                        f"{method} {self.SERVICE_BASE}{route} response could not be deserialized:\n{data}")
                    raise ClientValueError(f"Could not deserialize D&D Beyond response: {data}")
        except aiohttp.ServerTimeoutError:
            self.logger.warning(f"Request timeout: {method} {self.SERVICE_BASE}{route}")
            raise ClientTimeoutError("Timed out connecting to D&D Beyond. Please try again in a few minutes.")
        return data

    async def get(self, ddb_user: BeyondUser, route: str, **kwargs):
        return await self.request(ddb_user, 'GET', route, **kwargs)

    async def post(self, ddb_user: BeyondUser, route: str, **kwargs):
        return await self.request(ddb_user, 'POST', route, **kwargs)

    async def put(self, ddb_user: BeyondUser, route: str, **kwargs):
        return await self.request(ddb_user, 'PUT', route, **kwargs)

    async def delete(self, ddb_user: BeyondUser, route: str, **kwargs):
        return await self.request(ddb_user, 'DELETE', route, **kwargs)
