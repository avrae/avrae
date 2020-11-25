import re

from discord.ext import commands

from ddb.gamelog import CampaignLink
from ddb.gamelog.errors import NoCampaignLink
from utils import checks
from utils.functions import confirm, search_and_select


class GameLog(commands.Cog):
    """
    Link your D&D Beyond campaign to a Discord channel to see players' rolls in real time!
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='campaign', invoke_without_command=True)
    @commands.guild_only()
    @checks.feature_flag('command.campaign.enabled', use_ddb_user=True)
    async def campaign(self, ctx, campaign_link):
        """
        Links a D&D Beyond campaign to this channel, displaying rolls made on players' character sheets in real time.

        You must be the DM of the campaign to link it to a channel.
        """
        link_match = re.match(r'(?:https?://)?(?:www\.)?dndbeyond\.com/campaigns/(\d+)(?:$|/)', campaign_link)
        if link_match is None:
            return await ctx.send("This is not a D&D Beyond campaign link.")
        campaign_id = link_match.group(1)

        # is there already an existing link?
        try:
            existing_link = await CampaignLink.from_id(self.bot.mdb, campaign_id)
        except NoCampaignLink:
            existing_link = None

        if existing_link is not None and existing_link.channel_id == ctx.channel.id:
            return await ctx.send("This campaign is already linked to this channel.")
        elif existing_link is not None:
            result = await confirm(
                ctx, "This campaign is already linked to another channel. Link it to this one instead?")
            if not result:
                return await ctx.send("Ok, canceling.")
            await existing_link.delete(ctx.bot.mdb)

        # do link (and dm check)
        result = await self.bot.glclient.create_campaign_link(ctx, campaign_id)
        await ctx.send(f"Linked {result.campaign_name} to this channel! Your players' rolls from D&D Beyond will show "
                       f"up here, and checks, saves, and attacks made by characters in your campaign here will "
                       f"appear in D&D Beyond!")

    @campaign.command(name='list')
    @commands.guild_only()
    @checks.feature_flag('command.campaign.enabled', use_ddb_user=True)
    async def campaign_list(self, ctx):
        """Lists all campaigns connected to this channel."""
        existing_links = await CampaignLink.get_channel_links(ctx)
        if not existing_links:
            return await ctx.send(f"This channel is not linked to any D&D Beyond campaigns. "
                                  f"Use `{ctx.prefix}campaign https://www.dndbeyond.com/campaigns/...` to have "
                                  f"your and your players' rolls show up here in real time!")
        await ctx.send(f"This channel is linked to {len(existing_links)} "
                       f"{'campaign' if len(existing_links) == 1 else 'campaigns'}:\n"
                       f"{', '.join(cl.campaign_name for cl in existing_links)}")

    @campaign.command(name='remove')
    @commands.guild_only()
    @checks.feature_flag('command.campaign.enabled', use_ddb_user=True)
    async def campaign_remove(self, ctx, name):
        """
        Unlinks a campaign from this channel.

        You must be the DM of the campaign or have Manage Server permissions to remove it from a channel.
        """
        existing_links = await CampaignLink.get_channel_links(ctx)
        if not existing_links:
            return await ctx.send(f"This channel is not linked to any D&D Beyond campaigns. "
                                  f"Use `{ctx.prefix}campaign https://www.dndbeyond.com/campaigns/...` to have "
                                  f"your and your players' rolls show up here in real time!")
        the_link = await search_and_select(ctx, existing_links, name, key=lambda cl: cl.campaign_name)

        # check: is the invoker the linker or do they have manage server?
        if not (the_link.campaign_connector == ctx.author.id
                or ctx.author.guild_permissions.manage_guild):
            return await ctx.send("You do not have permission to unlink this campaign. "
                                  "You must be the DM of the campaign or have Manage Server permissions to remove it "
                                  "from a channel.")

        # remove campaign link
        await the_link.delete(ctx.bot.mdb)
        await ctx.send(f"Okay, removed the link from {the_link.campaign_name}. Its rolls will no longer show up here.")

    @campaign.command(name='add-debug')
    @commands.guild_only()
    async def campaign_add_debug(self, ctx):
        # https://stg.dndbeyond.com/game-log-test/897929
        # https://stg.dndbeyond.com/campaigns/897929
        campaign_id = "897929"
        campaign_name = "DDB Test Campaign"

        # is there already an existing link?
        try:
            existing_link = await CampaignLink.from_id(self.bot.mdb, campaign_id)
        except NoCampaignLink:
            existing_link = None

        if existing_link is not None and existing_link.channel_id == ctx.channel.id:
            return await ctx.send("This campaign is already linked to this channel.")
        elif existing_link is not None:
            result = await confirm(
                ctx, "This campaign is already linked to another channel. Link it to this one instead?")
            if not result:
                return await ctx.send("Ok, canceling.")
            await existing_link.delete()

        link = CampaignLink(campaign_id, campaign_name, ctx.channel.id, ctx.guild.id, ctx.author.id)
        await self.bot.mdb.gamelog_campaigns.insert_one(link.to_dict())

        await ctx.send(f"Linked {campaign_name} to this channel! Your players' rolls from D&D Beyond will show "
                       f"up here, and checks, saves, and attacks made by characters in your campaign here will "
                       f"appear in D&D Beyond!")

        # ===== game log handlers (move to own cog?) =====


def setup(bot):
    bot.add_cog(GameLog(bot))