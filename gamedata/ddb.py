import json
import logging
import time

import aioboto3
import aiohttp
import jwt
from boto3.dynamodb.conditions import Key

from cogsmisc.stats import Stats
# auth service
from utils.config import DDB_AUTH_AUDIENCE as AUDIENCE, DDB_AUTH_EXPIRY_SECONDS as EXPIRY_SECONDS, \
    DDB_AUTH_ISSUER as ISSUER, DDB_AUTH_SECRET as MY_SECRET, DDB_AUTH_SERVICE_URL as AUTH_BASE_URL, \
    DDB_WATERDEEP_SECRET as WATERDEEP_SECRET
# dynamo
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY
from utils.config import DYNAMO_ENTITY_TABLE, DYNAMO_REGION, DYNAMO_USER_TABLE

AUTH_DISCORD = f"{AUTH_BASE_URL}/v1/discord-token"

# cache
USER_ENTITLEMENT_TTL = 1 * 60
ENTITY_ENTITLEMENT_TTL = 15 * 60

log = logging.getLogger(__name__)


class BeyondClientBase:  # for development - assumes no entitlements
    async def get_accessible_entities(self, ctx, user_id, entity_type):
        return None

    async def get_ddb_user(self, ctx, user_id):
        return None

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
        self.dynamo = aioboto3.resource('dynamodb', region_name=DYNAMO_REGION)
        self.ddb_user_table = self.dynamo.Table(DYNAMO_USER_TABLE)
        self.ddb_entity_table = self.dynamo.Table(DYNAMO_ENTITY_TABLE)
        log.info("DDB client initialized")

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
        :rtype: BeyondUser or None
        """
        log.debug(f"Getting DDB user for Discord ID {user_id}")
        user_cache_key = f"beyond.user.{user_id}"
        unlinked_sentinel = {"unlinked": True}

        cached_user = await ctx.bot.rdb.jget(user_cache_key)
        if cached_user == unlinked_sentinel:
            return None
        elif cached_user is not None:
            return BeyondUser.from_dict(cached_user)

        user_claim = self._jwt_for_user(user_id)
        token, ttl = await self._fetch_token(user_claim)

        # cache unlinked if user is unlinked
        if token is None:
            await ctx.bot.rdb.jsetex(user_cache_key, unlinked_sentinel, USER_ENTITLEMENT_TTL)
            return None

        user = self._parse_jwt(token)
        await ctx.bot.rdb.jsetex(user_cache_key, user.to_dict(), ttl)
        await Stats.count_ddb_link(ctx, user_id, user)
        return user

    async def _get_user_entitlements(self, ctx, user_id):
        """
        Gets a user's entitlements in the current context, from cache or by communicating with DDB.

        Returns None if the user has no DDB connection.

        :type ctx: discord.ext.commands.Context
        :param user_id: The Discord user ID.
        :type user_id: int
        :rtype: UserEntitlements
        """
        user_entitlement_cache_key = f"entitlements.user.{user_id}"
        cached_user_entitlements = await ctx.bot.rdb.jget(user_entitlement_cache_key)
        if cached_user_entitlements is not None:
            return UserEntitlements.from_dict(cached_user_entitlements)

        user = await self.get_ddb_user(ctx, user_id)

        if user is None:
            return None

        # feature flag: is this user allowed to use entitlements?
        enabled_ff = await ctx.bot.ldclient.variation("entitlements-enabled", user.to_ld_dict(), False)
        if not enabled_ff:
            log.debug(f"hit false entitlements flag - skipping user entitlements")
            return None

        user_e10s = await self._fetch_user_entitlements(int(user.user_id))
        # cache entitlements
        await ctx.bot.rdb.jsetex(user_entitlement_cache_key,
                                 user_e10s.to_dict(),
                                 USER_ENTITLEMENT_TTL)
        return user_e10s

    async def _get_entity_entitlements(self, ctx, entity_type):
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
            "external_user_id": str(user_id),
            "iat": now,
            "exp": now + EXPIRY_SECONDS,
            "aud": AUDIENCE,
            "iss": ISSUER
        }

        return jwt.encode(jwt_body, MY_SECRET, algorithm='HS256').decode()  # return as a str, not bytes

    @staticmethod
    def _parse_jwt(token: str):
        """
        Parses a JWT from the Auth Service into a DDB User.

        :param str token: The JWT returned by the Auth Service.
        :return: The DDB user represented by the JWT.
        :rtype: BeyondUser
        """
        payload = jwt.decode(token, WATERDEEP_SECRET, algorithms=['HS256'],
                             issuer=ISSUER, audience=[AUDIENCE, ISSUER], verify=True)
        return BeyondUser(
            token,
            payload['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier'],
            payload['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name'],
            payload.get('http://schemas.microsoft.com/ws/2008/06/identity/claims/role', []),
            payload.get('http://schemas.dndbeyond.com/ws/2019/08/identity/claims/subscriber'),
            payload.get('http://schemas.dndbeyond.com/ws/2019/08/identity/claims/subscriptiontier')
        )

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
                    raise AuthException(f"Auth Service returned {resp.status}: {await resp.text()}")
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError, TypeError):
                    raise AuthException(f"Could not deserialize Auth Service response: {await resp.text()}")
        except aiohttp.ServerTimeoutError:
            raise AuthException("Timed out connecting to Auth Service")
        return data['token'], data.get('ttl')

    async def _fetch_user_entitlements(self, ddb_id: int):
        """
        Queries the entitlement tables to determine a DDB user's entitlements.

        :param int ddb_id: The DDB user ID.
        :rtype: UserEntitlements
        """
        user_r = await self.ddb_user_table.get_item(Key={"ID": ddb_id})  # ints are automatically converted to N-type
        if 'Item' not in user_r:
            return UserEntitlements([], [])
        result = user_r['Item']
        log.debug(f"fetched user entitlements for DDB user {ddb_id}: {result}")
        return UserEntitlements.from_dict(json.loads(result['JSON']))

    async def _fetch_entities(self, etype: str):
        """
        Queries the entitlement tables to get all entity entitlements of a certain type.

        :param str etype: The type of entity to get.
        :return: A list of all entity entitlements for all entities of that type.
        :rtype: list[EntityEntitlements]
        """
        log.debug(f"fetching entity entitlements for etype {etype}")
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
                yield json.loads(obj['JSON'])

    async def close(self):
        await self.http.close()


class BeyondUser:
    def __init__(self, token, user_id, username, roles, subscriber=None, subscription_tier=None):
        self.token = token
        self.user_id = user_id
        self.username = username
        self.roles = roles
        self.subscriber = subscriber
        self.subscription_tier = subscription_tier

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {
            "token": self.token,
            "user_id": self.user_id,
            "username": self.username,
            "roles": self.roles,
            "subscriber": self.subscriber,
            "subscription_tier": self.subscription_tier
        }

    def to_ld_dict(self):
        """Returns a dict representing the DDB user in LaunchDarkly."""
        return {
            "key": self.user_id,
            "name": self.username,
            "custom": {
                "Roles": self.roles,
                "Subscription": self.subscriber,
                "SubscriptionTier": self.subscription_tier
            }
        }

    @property
    def is_insider(self):
        return 'Insider' in self.roles

    @property
    def is_staff(self):
        return 'D&D Beyond Staff' in self.roles

    @property
    def is_subscriber(self):
        """Used to count staff and insiders as subscribers."""
        return self.subscriber or self.is_insider or self.is_staff


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
        return cls(d['campaignID'], d['licenseIDs'])

    def to_dict(self):
        return {
            "campaignID": self.campaign_id,
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
        return cls(d['entityType'], d['entityID'], d['isFree'], d['licenseIDs'])

    def to_dict(self):
        return {
            "entityType": self.entity_type,
            "entityID": self.entity_id,
            "isFree": self.is_free,
            "licenseIDs": list(self.license_ids)
        }


class AuthException(Exception):
    """Something happened during auth that shouldn't have"""
    pass
