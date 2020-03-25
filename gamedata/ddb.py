import time

import aioboto3
import aiohttp
import jwt
from boto3.dynamodb.conditions import Key

# todo set these in config
# jwt
AUDIENCE = 'avrae.io'
ISSUER = 'dndbeyond.com'
SECRET = 'my-secret'
EXPIRY_SECONDS = 5 * 60

# auth service
AUTH_URL = 'https://postb.in/1585160084275-2945728471968'

# dynamo
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY
DYNAMO_REGION = 'us-east-1'
DYNAMO_USER_TABLE = 'users-foobartest'
DYNAMO_ENTITY_TABLE = 'licenses-foobartest'


class BeyondClient:
    """
    Client to interface with DDB's Auth Service and Entitlements tables in DynamoDB.
    Asyncio-compatible.

    Most methods are private since local dev environments cannot connect to the DDB stack, and
    public methods should return the most liberal permissions (i.e. user owns everything in db) possible without making
    external connections in this scenario.
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
        :rtype: set[str]
        """
        user_r = await self.ddb_user_table.get_item(Key={"ID": ddb_id})  # ints are automatically converted to N-type
        if 'Item' not in user_r:
            return set()

        user_entitlements = UserEntitlements.from_dict(user_r['Item'])
        return user_entitlements.licenses

    async def _fetch_entities(self, etype: str):
        """
        Queries the entitlement tables to get all entities of a certain type.

        :param str etype: The type of entity to get.
        :return: A list of all entity entitlements for all entities of that type.
        :rtype: list[EntityEntitlements]
        """
        return [EntityEntitlements.from_dict(e)
                async for e in self.query(self.ddb_entity_table, KeyConditionExpression=Key('EntityType').eq(etype))]

    # helpers
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


class AuthException(Exception):
    """Something happened during auth that shouldn't have"""
    pass
