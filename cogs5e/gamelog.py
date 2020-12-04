import logging
import re

import discord
from discord.ext import commands

import ddb.dice
from ddb.gamelog import CampaignLink
from ddb.gamelog.errors import NoCampaignLink
from utils import checks
from utils.constants import DDB_LOGO_EMOJI
from utils.dice import VerboseMDStringifier
from utils.functions import confirm, search_and_select

log = logging.getLogger(__name__)


class GameLog(commands.Cog):
    """
    Link your D&D Beyond campaign to a Discord channel to see players' rolls in real time!
    """

    # setup/teardown
    def __init__(self, bot):
        self.bot = bot

        self._gl_callbacks = {
            'dice_roll_begin': self.dice_roll_begin,
            'dice/roll/begin': self.dice_roll,
            'dice_roll': self.dice_roll,
            'dice/roll/fulfilled': self.dice_roll
        }
        for event_type, callback in self._gl_callbacks.items():
            self.bot.glclient.register_callback(event_type, callback)

    def cog_unload(self):
        # deregister all glclient listeners
        for event_type in self._gl_callbacks:
            self.bot.glclient.deregister_callback(event_type)

    # ==== commands ====
    @commands.group(name='campaign', invoke_without_command=True)
    @commands.guild_only()
    @checks.feature_flag('command.campaign.enabled', use_ddb_user=True)
    async def campaign(self, ctx, campaign_link):
        """
        Links a D&D Beyond campaign to this channel, displaying rolls made on players' character sheets in real time.

        You must be the DM of the campaign to link it to a channel.

        Not seeing a player's rolls? Link their D&D Beyond and Discord accounts [here](https://www.dndbeyond.com/account), and check with the `!ddb` command!
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
        await ctx.trigger_typing()
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

    # https://stg.dndbeyond.com/game-log-test/897929
    # https://stg.dndbeyond.com/campaigns/897929

    # ==== game log handlers ====
    # ---- dice ----
    @staticmethod
    async def dice_roll_begin(gctx):
        """
        Sends a typing indicator to the linked channel to indicate that something is about to happen.
        """
        await gctx.channel.trigger_typing()

    async def dice_roll(self, gctx):
        """
        Sends a message with the result of the roll, similar to `!r`.
        """
        roll_request = ddb.dice.RollRequest.from_dict(gctx.event.data)
        if not roll_request.rolls:  # do nothing if there are no rolls actually made
            return
        first_roll = roll_request.rolls[0]

        roll_callbacks = {  # takes in (gctx, roll_request)
            ddb.dice.RollType.CHECK: self.dice_roll_check,
            ddb.dice.RollType.SAVE: self.dice_roll_save,
            ddb.dice.RollType.TO_HIT: self.dice_roll_to_hit,
            ddb.dice.RollType.DAMAGE: self.dice_roll_damage,
            ddb.dice.RollType.SPELL: self.dice_roll_spell,
            ddb.dice.RollType.HEAL: self.dice_roll_heal
        }

        # noinspection PyArgumentList
        await roll_callbacks.get(first_roll.roll_type, self.dice_roll_roll)(gctx, roll_request)

    @staticmethod
    async def dice_roll_roll(gctx, roll_request):
        """Generic roll: Display the roll in a format similar to ``!r``."""
        results = '\n\n'.join(str(rr.to_d20(stringifier=VerboseMDStringifier())) for rr in roll_request.rolls)

        out = f"<@{gctx.discord_user_id}> **rolled from** {DDB_LOGO_EMOJI}:\n{results}"
        # the user knows they rolled - don't need to ping them in discord
        await gctx.channel.send(out, allowed_mentions=discord.AllowedMentions.none())

    async def dice_roll_check(self, gctx, roll_request):
        """Check: Display like ``!c``. Requires character - if not imported falls back to default roll."""
        # check for loaded character

        # only listen to the first roll
        if len(roll_request.rolls) > 1:
            log.warning(f"Got {len(roll_request.rolls)} rolls for check (event {gctx.event.id!r}), discarding rolls 2+")
        roll = roll_request.rolls[0]

    async def dice_roll_save(self, gctx, roll_request):
        """Save: Display like ``!s``."""
        pass

    async def dice_roll_to_hit(self, gctx, roll_request):
        """To Hit rolls from attacks/spells."""
        pass

    async def dice_roll_damage(self, gctx, roll_request):
        """Damage rolls from attacks/spells."""
        pass

    async def dice_roll_spell(self, gctx, roll_request):
        """Unknown when this is used. Set roll comment and pass to default roll handler."""
        pass

    async def dice_roll_heal(self, gctx, roll_request):
        """Healing and temp HP. how to handle best?"""
        pass


def setup(bot):
    bot.add_cog(GameLog(bot))
