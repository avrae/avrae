import json


class GameLogEvent:
    """
    A "Message" as defined by
    https://github.com/DnDBeyond/ddb-game-log/blob/main/packages/message-broker-lib/src/types.ts#L28
    """

    def __init__(self, **kwargs):
        # useful attrs
        self.game_id = kwargs['gameId']
        self.user_id = kwargs['userId']
        self.event_type = kwargs['eventType']
        self.source = kwargs['source']
        self.data = kwargs['data']  # todo parse this based on event type

        # other stuff
        self.id = kwargs['id']
        self.entity_id = kwargs['entityId']
        self.entity_type = kwargs['entityType']
        self.date_time = kwargs['dateTime']  # to be parsed into a datetime obj
        self.persist = kwargs['persist']
        self.message_scope = kwargs['messageScope']
        self.message_target = kwargs['messageTarget']
        self.connection_id = kwargs.get('connectionId')

    @classmethod
    def from_gamelog_message(cls, event: str):  # todo event-type based deser
        data = json.loads(event)
        return cls(**data)
