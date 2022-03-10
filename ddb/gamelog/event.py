import datetime
import json
import time
import uuid

from ddb.gamelog.constants import AVRAE_EVENT_SOURCE


class GameLogEvent:
    """
    A "Message" as defined by
    https://github.com/DnDBeyond/ddb-game-log/blob/main/packages/message-broker-lib/src/types.ts#L28
    """

    def __init__(self, **kwargs):
        # useful attrs
        self.game_id = kwargs["gameId"]  # type: str
        self.user_id = kwargs["userId"]  # type: str
        self.event_type = kwargs["eventType"]  # type: str
        self.source = kwargs["source"]  # type: str
        self.data = kwargs.get("data")
        self.entity_id = kwargs.get("entityId")  # type: str or None
        self.entity_type = kwargs.get("entityType")  # type: str or None
        self.message_scope = kwargs["messageScope"]  # type: str
        self.message_target = kwargs["messageTarget"]  # type: str

        # other stuff
        self.id = kwargs["id"]  # type: str
        self.date_time = kwargs["dateTime"]  # type: str
        self.persist = kwargs["persist"]  # type: bool
        self.connection_id = kwargs.get("connectionId")

        # raw event for easy serialization
        self._raw = kwargs

    @classmethod
    def from_gamelog_message(cls, event: str):
        data = json.loads(event)
        return cls(**data)

    @classmethod
    def dice_roll_fulfilled(
        cls,
        game_id,
        user_id,
        roll_request,
        entity_id,
        entity_type="character",
        **kwargs
    ):
        return cls(
            gameId=game_id,
            userId=user_id,
            eventType="dice/roll/fulfilled",
            source=AVRAE_EVENT_SOURCE,
            data=roll_request.to_dict(),
            entityId=entity_id,
            entityType=entity_type,
            id=str(uuid.uuid4()),
            dateTime=str(int(time.time())),
            persist=True,
            messageScope="gameId",
            messageTarget=game_id,
            **kwargs
        )

    # ser/deser for event saving
    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return self._raw

    @property
    def timestamp(self):
        return datetime.datetime.fromtimestamp(float(self.date_time))
