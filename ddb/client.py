import asyncio
import json
import logging

import aiohttp
import cachetools
from aiobotocore.session import get_session

from cogsmisc.stats import Stats
from ddb import auth, character, entitlements, waterdeep
from ddb.errors import AuthException
from ddb.utils import update_user_map
from utils.config import DDB_AUTH_SERVICE_URL as AUTH_BASE_URL, DYNAMO_ENTITLEMENTS_TABLE, DYNAMO_REGION

# dynamo
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY

AUTH_DISCORD = f"{AUTH_BASE_URL}/v1/discord-token"

# cache
# in addition to caching in redis, we have a LRU cache for 64 entity types and the 128 most recent users
USER_ENTITLEMENT_TTL = 1 * 60
ENTITY_ENTITLEMENT_TTL = 15 * 60
USER_ENTITLEMENT_CACHE = cachetools.TTLCache(128, USER_ENTITLEMENT_TTL)
ENTITY_ENTITLEMENT_CACHE = cachetools.TTLCache(64, ENTITY_ENTITLEMENT_TTL)
USER_ENTITLEMENTS_NONE_SENTINEL = object()

log = logging.getLogger(__name__)


class BeyondClientBase:  # for development - assumes no entitlements
    async def get_accessible_entities(self, ctx, user_id, entity_type):
        return None

    async def get_ddb_user(self, ctx, user_id=None):
        return None

    async def close(self):
        pass


class BeyondClient(BeyondClientBase):
    """
    Client to interface with DDB's services and Entitlements tables in DynamoDB.
    Asyncio-compatible.

    Most methods are private since local dev environments cannot connect to the DDB stack, and
    public methods should return the most conservative permissions (i.e. user owns nothing in db)
    possible without making external connections in this scenario.
    """

    def __init__(self, loop):
        self.http = aiohttp.ClientSession(loop=loop)

        self.character = character.CharacterServiceClient(self.http)
        self.waterdeep = waterdeep.WaterdeepClient(self.http)
        self.scds = character.CharacterStorageServiceClient(self.http)

        self._dynamo = None
        loop.run_until_complete(self._initialize())

    async def _initialize(self):
        """Initialize our async resources: aioboto3"""
        boto_session = get_session()
        self._dynamo = await boto_session.create_client("dynamodb", region_name=DYNAMO_REGION).__aenter__()
        log.info("DDB client initialized")

    # ==== methods ====
    async def get_accessible_entities(self, ctx, user_id, entity_type):
        """
        Returns a set of entity IDs of the given entity type that the given user is allowed to access in the given
        context.

        Returns None if the user has no DDB link.

        :type ctx: discord.ext.commands.Context
        :type user_id: int
        :type entity_type: str
        :rtype: set[int] or None
        """
        log.debug(f"Getting DDB entitlements for Discord ID {user_id}")
        user_e10s = await self._get_user_entitlements(ctx, user_id)
        if user_e10s is None:
            return None

        entity_e10s = await self._get_entity_entitlements(ctx, entity_type)

        # calculate visible entities
        accessible = set()
        user_licenses = user_e10s.licenses
        for entity in entity_e10s:
            if entity.is_free or user_licenses & entity.license_ids:
                accessible.add(entity.entity_id)

        log.debug(f"Discord user {user_id} can see {entity_type}s {accessible}")

        return accessible

    async def get_ddb_user(self, ctx, user_id=None):
        """
        Gets a Discord user's DDB user, communicating with the Auth Service if necessary.
        Returns None if the user has no DDB link.

        :type ctx: discord.ext.commands.Context
        :param int user_id: The Discord user ID to get the DDB user of. If None, defaults to ctx.author.id.
        :rtype: auth.BeyondUser or None
        """
        if user_id is None:
            user_id = ctx.author.id

        log.debug(f"Getting DDB user for Discord ID {user_id}")
        user_cache_key = f"beyond.user.{user_id}"
        unlinked_sentinel = {"unlinked": True}

        cached_user = await ctx.bot.rdb.jget(user_cache_key)
        if cached_user == unlinked_sentinel:
            return None
        elif cached_user is not None:
            return auth.BeyondUser.from_dict(cached_user)

        user_claim = auth.jwt_for_user(user_id)
        token, ttl = await self._fetch_token(user_claim)

        if token is None:
            # cache unlinked if user is unlinked
            await ctx.bot.rdb.jsetex(user_cache_key, unlinked_sentinel, USER_ENTITLEMENT_TTL)
            # remove any ddb -> discord user mapping
            await ctx.bot.mdb.ddb_account_map.delete_one({"discord_id": user_id})
            return None

        user = auth.BeyondUser.from_jwt(token)
        await asyncio.gather(
            # to avoid 403's when using a cached token on the verge of expiring, we expire the token from cache
            # 1 second before its *exp* attribute
            ctx.bot.rdb.jsetex(user_cache_key, user.to_dict(), max(ttl - 1, 1)),
            Stats.count_ddb_link(ctx, user_id, user),
            update_user_map(ctx, ddb_id=user.user_id, discord_id=user_id),
        )
        return user

    # ==== entitlement helpers ====
    async def _get_user_entitlements(self, ctx, user_id):
        """
        Gets a user's entitlements in the current context, from cache or by communicating with DDB.

        Returns None if the user has no DDB connection.

        :type ctx: discord.ext.commands.Context
        :param user_id: The Discord user ID.
        :type user_id: int
        :rtype: ddb.entitlements.UserEntitlements
        """
        # L1: Memory
        l1_user_entitlements = USER_ENTITLEMENT_CACHE.get(user_id)
        if l1_user_entitlements is not None:
            log.debug("found user entitlements in l1 (memory) cache")
            return l1_user_entitlements if l1_user_entitlements is not USER_ENTITLEMENTS_NONE_SENTINEL else None

        # L2: Redis
        user_entitlement_cache_key = f"entitlements.user.{user_id}"
        l2_user_entitlements = await ctx.bot.rdb.jget(user_entitlement_cache_key)
        if l2_user_entitlements is not None:
            log.debug("found user entitlements in l2 (redis) cache")
            return entitlements.UserEntitlements.from_dict(l2_user_entitlements)

        # fetch from ddb
        user = await self.get_ddb_user(ctx, user_id)

        if user is None:
            USER_ENTITLEMENT_CACHE[user_id] = USER_ENTITLEMENTS_NONE_SENTINEL
            return None

        # feature flag: is this user allowed to use entitlements?
        enabled_ff = await ctx.bot.ldclient.variation("entitlements-enabled", user.to_ld_dict(), False)
        if not enabled_ff:
            log.debug(f"hit false entitlements flag - skipping user entitlements")
            return None

        user_e10s = await self._fetch_user_entitlements(int(user.user_id))
        # cache entitlements
        USER_ENTITLEMENT_CACHE[user_id] = user_e10s
        await ctx.bot.rdb.jsetex(user_entitlement_cache_key, user_e10s.to_dict(), USER_ENTITLEMENT_TTL)
        return user_e10s

    async def _get_entity_entitlements(self, ctx, entity_type):
        """
        Gets the latest entity entitlements, from cache or by communicating with DDB.

        :type ctx: discord.ext.commands.Context
        :type entity_type: str
        :rtype: list[ddb.entitlements.EntityEntitlements]
        """
        # L1: Memory
        l1_entity_entitlements = ENTITY_ENTITLEMENT_CACHE.get(entity_type)
        if l1_entity_entitlements is not None:
            log.debug("found entity entitlements in l1 (memory) cache")
            return l1_entity_entitlements

        # L2: Redis
        entity_entitlement_cache_key = f"entitlements.entity.{entity_type}"
        l2_entity_entitlements = await ctx.bot.rdb.jget(entity_entitlement_cache_key)
        if l2_entity_entitlements is not None:
            log.debug("found entity entitlements in l2 (redis) cache")
            return [entitlements.EntityEntitlements.from_dict(e) for e in l2_entity_entitlements]

        # fetch from DDB
        entity_e10s = await self._fetch_entities(entity_type)

        # cache entitlements
        ENTITY_ENTITLEMENT_CACHE[entity_type] = entity_e10s
        await ctx.bot.rdb.jsetex(
            entity_entitlement_cache_key, [e.to_dict() for e in entity_e10s], ENTITY_ENTITLEMENT_TTL
        )
        return entity_e10s

    # ---- low-level auth ----
    async def _fetch_token(self, claim: str):
        """
        Requests a short-term token from the DDB Auth Service given a Discord user claim in JWT form.

        :param str claim: The JWT representing the Discord user.
        :returns: A tuple representing the short-term token for the user and its TTL, or (None, None).
        :rtype: tuple[str, int] or tuple[None, None]
        """
        body = {"Token": claim}
        try:
            async with self.http.post(AUTH_DISCORD, json=body) as resp:
                if not 199 < resp.status < 300:
                    log.warning(f"Auth Service returned {resp.status}: {await resp.text()}")
                    raise AuthException(f"D&D Beyond returned an error: {resp.status} {resp.reason}")
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    log.warning(f"Cannot deserialize Auth Service response: {resp.status}: {await resp.text()}")
                    raise AuthException("Could not deserialize D&D Beyond response.")
        except aiohttp.ServerTimeoutError:
            raise AuthException("Timed out connecting to D&D Beyond. Please try again in a few minutes.")
        return data["token"], data.get("ttl")

    async def _fetch_user_entitlements(self, ddb_id: int):
        """
        Queries the entitlement tables to determine a DDB user's entitlements.

        :param int ddb_id: The DDB user ID.
        :rtype: entitlements.UserEntitlements
        """
        user_r = await self._dynamo.get_item(
            TableName=DYNAMO_ENTITLEMENTS_TABLE,
            Key={"PartitionKey": {"S": f"USER#{ddb_id}"}, "SortKey": {"S": str(ddb_id)}},
        )
        if "Item" not in user_r:
            return entitlements.UserEntitlements([], [])
        result = user_r["Item"]
        log.debug(f"fetched user entitlements for DDB user {ddb_id}: {result}")
        return entitlements.UserEntitlements.from_dict(json.loads(result["JSON"]["S"]))

    async def _fetch_entities(self, etype: str):
        """
        Queries the entitlement tables to get all entity entitlements of a certain type.

        :param str etype: The type of entity to get.
        :return: A list of all entity entitlements for all entities of that type.
        :rtype: list[entitlements.EntityEntitlements]
        """
        log.debug(f"fetching entity entitlements for etype {etype}")
        return [
            entitlements.EntityEntitlements.from_dict(e)
            async for e in self.query(
                TableName=DYNAMO_ENTITLEMENTS_TABLE,
                KeyConditionExpression="PartitionKey = :entityTypeKey",
                ExpressionAttributeValues={":entityTypeKey": {"S": f"ENTITY#{etype}"}},
            )
        ]

    # ---- helpers ----
    async def query(self, **kwargs):
        """An async generator that automatically handles query pagination."""
        sentinel = lek = object()
        while lek is not None:
            if lek is sentinel:
                response = await self._dynamo.query(**kwargs)
            else:
                response = await self._dynamo.query(ExclusiveStartKey=lek, **kwargs)

            lek = response.get("LastEvaluatedKey")
            for obj in response["Items"]:
                try:
                    yield json.loads(obj["JSON"]["S"])
                except json.JSONDecodeError:
                    log.warning(f"Could not decode entitlement object: {obj!r}")

    async def close(self):
        await self.http.close()
        await self._dynamo.__aexit__(None, None, None)
