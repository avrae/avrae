"""
File containing models related to campaigns on DDB.
"""

import datetime


class ActiveCampaign:
    """
    https://www.dndbeyond.com/api/campaign/active-campaigns
    """

    def __init__(
        self, _id: str, name: str, dm_username: str, date_created: datetime.date, player_count: int, dm_id: str
    ):
        self.id = _id
        self.name = name
        self.dm_username = dm_username
        self.date_created = date_created
        self.player_count = player_count
        self.dm_id = dm_id

    @classmethod
    def from_json(cls, j):
        date_created = datetime.datetime.strptime(j["dateCreated"], "%m/%d/%Y").date()
        return cls(
            _id=str(j["id"]),
            name=j["name"],
            dm_username=j["dmUsername"],
            date_created=date_created,
            player_count=j["playerCount"],
            dm_id=str(j["dmId"]),
        )
