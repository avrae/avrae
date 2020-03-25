import time

import aioboto3
import aiohttp
import jwt
from boto3.dynamodb.conditions import Key

# auth service
from utils.config import DDB_AUTH_AUDIENCE as AUDIENCE, \
    DDB_AUTH_EXPIRY_SECONDS as EXPIRY_SECONDS, \
    DDB_AUTH_ISSUER as ISSUER, \
    DDB_AUTH_SECRET as SECRET, \
    DDB_AUTH_SERVICE_URL as AUTH_URL
# dynamo
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY
from utils.config import DYNAMO_ENTITY_TABLE, DYNAMO_REGION, DYNAMO_USER_TABLE

# cache
USER_ENTITLEMENT_TTL = 1 * 60
ENTITY_ENTITLEMENT_TTL = 15 * 60


class BeyondClientBase:  # todo for development - assumes no entitlements
    async def get_accessible_entities(self, ctx, user_id, entity_type):
        return set()


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
        self.dynamo = await aioboto3.resource('dynamodb', region_name=DYNAMO_REGION)
        self.ddb_user_table = self.dynamo.Table(DYNAMO_USER_TABLE)
        self.ddb_entity_table = self.dynamo.Table(DYNAMO_ENTITY_TABLE)

    async def get_accessible_entities(self, ctx, user_id, entity_type):
        """
        Returns a set of entity IDs that the given user is allowed to access in the given context.

        :type ctx: discord.ext.commands.Context
        :type user_id: int
        :type entity_type: str
        :rtype: set[int]
        """
        user_e10s = await self.get_user_entitlements(ctx, user_id)
        entity_e10s = await self.get_entity_entitlements(ctx, entity_type)

        # calculate visible entities
        accessible = set()
        user_licenses = user_e10s.licenses
        for entity in entity_e10s:
            if entity.is_free or user_licenses & entity.license_ids:
                accessible.add(entity.entity_id)

        return accessible

    async def get_user_entitlements(self, ctx, user_id):
        """
        Gets a user's entitlements in the current context, from cache or by communicating with DDB.

        :type ctx: discord.ext.commands.Context
        :type user_id: int
        :rtype: UserEntitlements
        """
        user_entitlement_cache_key = f"entitlements.user.{user_id}"
        cached_user_entitlements = await ctx.bot.rdb.jget(user_entitlement_cache_key)
        if cached_user_entitlements is not None:
            return UserEntitlements.from_dict(cached_user_entitlements)

        token = await self.get_user_token(ctx, user_id)
        if token is None:
            return UserEntitlements([], [])  # if the user has no DDB account, return an empty entitlements

        ddb_id = 1234  # todo parse out DDB user ID
        user_e10s = await self._fetch_licenses(ddb_id)
        # cache entitlements
        await ctx.bot.rdb.jsetex(user_entitlement_cache_key,
                                 user_e10s.to_dict(),
                                 USER_ENTITLEMENT_TTL)
        return user_e10s

    async def get_entity_entitlements(self, ctx, entity_type):
        """
        Gets the latest entity entitlements, from cache or by communicating with DDB.

        :type ctx: discord.ext.commands.Context
        :type entity_type: str
        :rtype: list[EntityEntitlements]
        """
        entity_entitlement_cache_key = f"entitlements.entity.{entity_type}"
        cached_entity_entitlements = await ctx.bot.rdb.jget(entity_entitlement_cache_key)
        if cached_entity_entitlements is not None:
            return [EntityEntitlements.from_dict(e) for e in cached_entity_entitlements]

        entity_e10s = await self._fetch_entities(entity_type)
        # cache entitlements
        await ctx.bot.rdb.jsetex(entity_entitlement_cache_key,
                                 [e.to_dict() for e in entity_e10s],
                                 ENTITY_ENTITLEMENT_TTL)
        return entity_e10s

    async def get_user_token(self, ctx, user_id):
        """
        Gets a user's short term DDB token from the Auth Service or cache.

        :type ctx: discord.ext.commands.Context
        :type user_id: int
        :rtype: str
        """
        user_token_cache_key = f"entitlements.user.{user_id}.token"
        cached_token = await ctx.bot.rdb.get(user_token_cache_key)
        if cached_token is not None:
            return cached_token
        user_claim = self._jwt_for_user(user_id)
        token, ttl = await self._fetch_token(user_claim)  # todo: double-check that ttl is in seconds
        # cache token for ttl
        if token is not None:
            await ctx.bot.rdb.setex(user_token_cache_key, token, ttl)
        return token

    # ---- low-level auth ----
    @staticmethod
    def _jwt_for_user(user_id: int):
        """
        Gets the HS256-encoded JWT for a Discord user ID.

        :param int user_id: The Discord user ID.
        :returns str: The JWT.
        """
        now = int(time.time())

        jwt_body = {
            "discord_id": str(user_id),
            "iat": now,
            "exp": now + EXPIRY_SECONDS,
            "aud": AUDIENCE,
            "iss": ISSUER
        }

        return jwt.encode(jwt_body, SECRET, algorithm='HS256').decode()  # return as a str, not bytes

    async def _fetch_token(self, claim: str):
        """
        Requests a short-term token from the DDB Auth Service given a Discord user claim in JWT form.

        :param str claim: The JWT representing the Discord user.
        :returns: A tuple representing the short-term token for the user and its TTL, or (None, None).
        :rtype: tuple[str or None,int or None]
        """
        body = {"Token": claim}
        try:
            async with self.http.post(AUTH_URL, json=body) as resp:
                if not 199 < resp.status < 300:
                    raise AuthException(f"Auth Service returned {resp.status}: {await resp.text()}")
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    raise AuthException(f"Could not deserialize Auth Service response: {await resp.text()}")
        except aiohttp.ServerTimeoutError:
            raise AuthException("Timed out connecting to Auth Service")
        return data['token'], data.get('ttl')

    async def _fetch_licenses(self, ddb_id: int):
        """
        Queries the entitlement tables to determine what licenses a DDB user can use.

        :param int ddb_id: The DDB user ID.
        :return: The set of all license IDs the user is allowed to use.
        :rtype: UserEntitlements
        """
        user_r = await self.ddb_user_table.get_item(Key={"ID": ddb_id})  # ints are automatically converted to N-type
        if 'Item' not in user_r:
            return UserEntitlements([], [])
        return UserEntitlements.from_dict(user_r['Item'])

    async def _fetch_entities(self, etype: str):
        """
        Queries the entitlement tables to get all entities of a certain type.

        :param str etype: The type of entity to get.
        :return: A list of all entity entitlements for all entities of that type.
        :rtype: list[EntityEntitlements]
        """
        return [EntityEntitlements.from_dict(e)
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
                yield obj

    async def close(self):
        await self.http.close()


class UserEntitlements:
    __slots__ = ("acquired_license_ids", "shared_licenses")

    def __init__(self, acquired_license_ids, shared_licenses):
        """
        :type acquired_license_ids: list[int]
        :type shared_licenses: list[SharedLicense]
        """
        self.acquired_license_ids = acquired_license_ids
        self.shared_licenses = shared_licenses

    @classmethod
    def from_dict(cls, d):
        return cls(d['acquiredLicenseIDs'], [SharedLicense.from_dict(sl) for sl in d['sharedLicenses']])

    def to_dict(self):
        return {
            "acquiredLicenseIDs": self.acquired_license_ids,
            "sharedLicenses": [sl.to_dict() for sl in self.shared_licenses]
        }

    @property
    def licenses(self):
        """
        The set of all license IDs the user has access to.
        :rtype: set[int]
        """
        return set(self.acquired_license_ids).union(*(sl.license_ids for sl in self.shared_licenses))


class SharedLicense:
    __slots__ = ("campaign_id", "license_ids")

    def __init__(self, campaign_id, license_ids):
        """
        :type campaign_id: int
        :type license_ids: list[int]
        """
        self.campaign_id = campaign_id
        self.license_ids = license_ids

    @classmethod
    def from_dict(cls, d):
        return cls(d['campaignId'], d['licenseIDs'])

    def to_dict(self):
        return {
            "campaignId": self.campaign_id,
            "licenseIDs": self.license_ids
        }


class EntityEntitlements:
    __slots__ = ("entity_type", "entity_id", "is_free", "license_ids")

    def __init__(self, entity_type, entity_id, is_free, license_ids):
        """
        :type entity_type: str
        :type entity_id: int
        :type is_free: bool
        :type license_ids: set[int]
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.is_free = is_free
        self.license_ids = set(license_ids)

    @classmethod
    def from_dict(cls, d):
        return cls(d['entityType'], d['entityId'], d['isFree'], d['licenseIDs'])

    def to_dict(self):
        return {
            "entityType": self.entity_type,
            "entityId": self.entity_id,
            "isFree": self.is_free,
            "licenseIDs": list(self.license_ids)
        }


class AuthException(Exception):
    """Something happened during auth that shouldn't have"""
    pass
