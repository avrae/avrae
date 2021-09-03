import json
import logging

import aioboto3
import aiohttp
import cachetools
from boto3.dynamodb.conditions import Key

from cogsmisc.stats import Stats
from ddb import auth, campaign, entitlements
from ddb.errors import AuthException, WaterdeepException
from utils.config import DDB_AUTH_SERVICE_URL as AUTH_BASE_URL, \
    DDB_WATERDEEP_URL as WATERDEEP_BASE, \
    DYNAMO_ENTITY_TABLE, DYNAMO_REGION, DYNAMO_USER_TABLE

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

    async def get_ddb_user(self, ctx, user_id):
        return None

    async def get_active_campaigns(self, ctx, user):
        return []

    async def close(self):
        pass


class BeyondClient(BeyondClientBase):
    """
    Client to interface with DDB's Auth Service and Entitlements tables in DynamoDB.
    Asyncio-compatible.

    Most methods are private since local dev environments cannot connect to the DDB stack, and
    public methods should return the most conservative permissions (i.e. user owns nothing in db)
    possible without making external connections in this scenario.
    """

    def __init__(self, loop):
        self.http = None
        self.dynamo = None
        self.ddb_user_table = None
        self.ddb_entity_table = None
        loop.run_until_complete(self._initialize())

    async def _initialize(self):
        """Initialize our async resources: aiohttp, aioboto3"""
        self.http = aiohttp.ClientSession()
        self.dynamo = await aioboto3.resource('dynamodb', region_name=DYNAMO_REGION).__aenter__()
        self.ddb_user_table = await self.dynamo.Table(DYNAMO_USER_TABLE)
        self.ddb_entity_table = await self.dynamo.Table(DYNAMO_ENTITY_TABLE)
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

    async def get_ddb_user(self, ctx, user_id):
        """
        Gets a Discord user's DDB user, communicating with the Auth Service if necessary.
        Returns None if the user has no DDB link.

        :type ctx: discord.ext.commands.Context
        :type user_id: int
        :rtype: auth.BeyondUser or None
        """
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
        await ctx.bot.rdb.jsetex(user_cache_key, user.to_dict(), ttl)
        await Stats.count_ddb_link(ctx, user_id, user)

        # update the ddb -> discord user mapping
        await ctx.bot.mdb.ddb_account_map.delete_one({"ddb_id": user.user_id})
        await ctx.bot.mdb.ddb_account_map.update_one(
            {"discord_id": user_id},
            {"$set": {"ddb_id": user.user_id}},
            upsert=True
        )

        return user

    async def get_active_campaigns(self, ctx, user):
        """
        Gets a list of campaigns the given user is in.

        GET /api/campaign/stt/active-campaigns

        :type ctx: discord.ext.commands.Context
        :param user: The DDB user.
        :type user: auth.BeyondUser
        :rtype: list[campaign.ActiveCampaign]
        """
        try:
            async with self.http.get(f"{WATERDEEP_BASE}/api/campaign/stt/active-campaigns",
                                     headers={"Authorization": f"Bearer {user.token}"}) as resp:
                if not 199 < resp.status < 300:
                    log.warning(f"Bad Waterdeep response: {resp.status}\n{await resp.text()}")
                    raise WaterdeepException(f"D&D Beyond returned an error: {resp.status} {resp.reason}")
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    log.warning(f"Bad Waterdeep response (deserialize): {resp.status}\n{await resp.text()}")
                    raise WaterdeepException("Could not deserialize D&D Beyond response.")
        except aiohttp.ServerTimeoutError:
            raise WaterdeepException("Timed out connecting to D&D Beyond.")
        if not data.get('status') == 'success':
            log.warning(f"Bad Waterdeep response (data): {resp.status}\n{data}")
            raise WaterdeepException(f"D&D Beyond returned an error: {data}")
        return [campaign.ActiveCampaign.from_json(j) for j in data['data']]

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
        await ctx.bot.rdb.jsetex(user_entitlement_cache_key,
                                 user_e10s.to_dict(),
                                 USER_ENTITLEMENT_TTL)
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
        await ctx.bot.rdb.jsetex(entity_entitlement_cache_key,
                                 [e.to_dict() for e in entity_e10s],
                                 ENTITY_ENTITLEMENT_TTL)
        return entity_e10s

    # ---- low-level auth ----
    async def _fetch_token(self, claim: str):
        """
        Requests a short-term token from the DDB Auth Service given a Discord user claim in JWT form.

        :param str claim: The JWT representing the Discord user.
        :returns: A tuple representing the short-term token for the user and its TTL, or (None, None).
        :rtype: tuple[str or None,int or None]
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
        return data['token'], data.get('ttl')

    async def _fetch_user_entitlements(self, ddb_id: int):
        """
        Queries the entitlement tables to determine a DDB user's entitlements.

        :param int ddb_id: The DDB user ID.
        :rtype: entitlements.UserEntitlements
        """
        user_r = await self.ddb_user_table.get_item(Key={"ID": ddb_id})  # ints are automatically converted to N-type
        if 'Item' not in user_r:
            return entitlements.UserEntitlements([], [])
        result = user_r['Item']
        log.debug(f"fetched user entitlements for DDB user {ddb_id}: {result}")
        return entitlements.UserEntitlements.from_dict(json.loads(result['JSON']))

    async def _fetch_entities(self, etype: str):
        """
        Queries the entitlement tables to get all entity entitlements of a certain type.

        :param str etype: The type of entity to get.
        :return: A list of all entity entitlements for all entities of that type.
        :rtype: list[entitlements.EntityEntitlements]
        """
        log.debug(f"fetching entity entitlements for etype {etype}")
        return [entitlements.EntityEntitlements.from_dict(e)
                async for e in self.query(self.ddb_entity_table, KeyConditionExpression=Key('EntityType').eq(etype))]

    # ---- helpers ----
    @staticmethod
    async def query(table, **kwargs):
        """An async generator that automatically handles query pagination."""
        sentinel = lek = object()
        while lek is not None:
            if lek is sentinel:
                response = await table.query(**kwargs)
            else:
                response = await table.query(ExclusiveStartKey=lek, **kwargs)

            lek = response.get('LastEvaluatedKey')
            for obj in response['Items']:
                yield json.loads(obj['JSON'])

    async def close(self):
        await self.http.close()
        await self.dynamo.__aexit__(None, None, None)
