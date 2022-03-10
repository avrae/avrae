import time

import jwt

from utils.config import (
    DDB_AUTH_AUDIENCE as AUDIENCE,
    DDB_AUTH_EXPIRY_SECONDS as EXPIRY_SECONDS,
    DDB_AUTH_ISSUER as ISSUER,
    DDB_AUTH_SECRET as MY_SECRET,
    DDB_WATERDEEP_SECRET as WATERDEEP_SECRET,
)


class BeyondUser:
    def __init__(
        self,
        token: str,
        user_id: str,
        username: str,
        roles: list,
        subscriber=None,
        subscription_tier=None,
    ):
        self.token = token
        self.user_id = user_id
        self.username = username
        self.roles = roles
        self.subscriber = subscriber
        self.subscription_tier = subscription_tier

    @classmethod
    def from_jwt(cls, token):
        """
        Parses a JWT from the Auth Service into a DDB User.

        :param str token: The JWT returned by the Auth Service.
        :return: The DDB user represented by the JWT.
        :rtype: BeyondUser
        """
        payload = jwt.decode(
            token,
            WATERDEEP_SECRET,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=[AUDIENCE, ISSUER],
            verify=True,
        )
        return cls(
            token,
            payload[
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
            ],
            payload["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"],
            payload.get(
                "http://schemas.microsoft.com/ws/2008/06/identity/claims/role", []
            ),
            payload.get(
                "http://schemas.dndbeyond.com/ws/2019/08/identity/claims/subscriber"
            ),
            payload.get(
                "http://schemas.dndbeyond.com/ws/2019/08/identity/claims/subscriptiontier"
            ),
        )

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
            "subscription_tier": self.subscription_tier,
        }

    def to_ld_dict(self):
        """Returns a dict representing the DDB user in LaunchDarkly."""
        return {
            "key": self.user_id,
            "name": self.username,
            "custom": {
                "Roles": self.roles,
                "Subscription": self.subscriber,
                "SubscriptionTier": self.subscription_tier,
            },
        }

    @property
    def is_insider(self):
        return "Insider" in self.roles

    @property
    def is_staff(self):
        return "D&D Beyond Staff" in self.roles

    @property
    def is_subscriber(self):
        """Used to count staff and insiders as subscribers."""
        return self.subscriber or self.is_insider or self.is_staff


# ==== helpers ====
def jwt_for_user(user_id: int):
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
        "iss": ISSUER,
    }

    return jwt.encode(jwt_body, MY_SECRET, algorithm="HS256")
