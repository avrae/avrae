from ddb.gamelog import errors


class CampaignLink:
    def __init__(
        self,
        campaign_id: str,
        campaign_name: str,
        channel_id: int,
        guild_id: int,
        campaign_connector: int,
        **_
    ):
        self.campaign_id = campaign_id
        self.campaign_name = campaign_name
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.campaign_connector = campaign_connector

    # ==== constructors ====
    @classmethod
    async def from_id(cls, mdb, the_id):
        campaign_dict = await mdb.gamelog_campaigns.find_one({"campaign_id": the_id})
        if campaign_dict is None:
            raise errors.NoCampaignLink()
        return cls.from_dict(campaign_dict)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "campaign_connector": self.campaign_connector,
        }

    @classmethod
    async def get_channel_links(cls, ctx):
        """Returns an list of CampaignLinks in the current channel."""
        return [
            cls.from_dict(link)
            async for link in ctx.bot.mdb.gamelog_campaigns.find(
                {"channel_id": ctx.channel.id}
            )
        ]

    async def delete(self, mdb):
        await mdb.gamelog_campaigns.delete_one(
            {"campaign_id": self.campaign_id, "channel_id": self.channel_id}
        )
