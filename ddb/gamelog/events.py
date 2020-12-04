import datetime
import json


class GameLogEvent:
    """
    A "Message" as defined by
    https://github.com/DnDBeyond/ddb-game-log/blob/main/packages/message-broker-lib/src/types.ts#L28
    """

    def __init__(self, **kwargs):
        # useful attrs
        self.game_id = kwargs['gameId']  # type: str
        self.user_id = kwargs['userId']  # type: str
        self.event_type = kwargs['eventType']  # type: str
        self.source = kwargs['source']  # type: str
        self.data = kwargs['data']
        self.entity_id = kwargs['entityId']  # type: str
        self.entity_type = kwargs['entityType']  # type: str

        # other stuff
        self.id = kwargs['id']  # type: str
        self.date_time = kwargs['dateTime']  # type: str
        self.persist = kwargs['persist']  # type: bool
        self.message_scope = kwargs['messageScope']  # type: str
        self.message_target = kwargs['messageTarget']  # type: str
        self.connection_id = kwargs.get('connectionId')

    @classmethod
    def from_gamelog_message(cls, event: str):
        data = json.loads(event)
        return cls(**data)

    @property
    def timestamp(self):
        return datetime.datetime.fromtimestamp(float(self.date_time))

