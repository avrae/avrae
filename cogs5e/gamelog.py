import logging
import re

import d20
import discord
from discord.ext import commands

import ddb.dice
from cogs5e.models import embeds
from cogs5e.models.automation.results import AttackResult, DamageResult, RollResult, SaveResult, TempHPResult
from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter
from cogs5e.utils import gamelogutils
from ddb.dice import RollContext, RollKind, RollRequest, RollRequestRoll, RollType
from ddb.gamelog import CampaignLink
from ddb.gamelog.errors import LinkNotAllowed, NoCampaignLink
from ddb.gamelog.event import GameLogEvent
from utils import checks, constants
from utils.dice import VerboseMDStringifier
from utils.functions import a_or_an, confirm, search_and_select, verbose_stat

log = logging.getLogger(__name__)


class GameLog(commands.Cog):
    """
    Link your D&D Beyond campaign to a Discord channel to see players' rolls in real time!
    """

    # setup/teardown
    def __init__(self, bot):
        self.bot = bot

        self._gl_callbacks = {
            'dice/roll/begin': self.dice_roll,
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
    async def campaign(self, ctx, campaign_link=None):
        """
        Links a D&D Beyond campaign to this channel, displaying rolls made on players' character sheets in real time.

        You must be the DM of the campaign to link it to a channel.

        Not seeing a player's rolls? Link their D&D Beyond and Discord accounts [here](https://www.dndbeyond.com/account), and check with the `!ddb` command!
        """
        if campaign_link is None:
            return await self.campaign_list(ctx)

        link_match = re.match(r'(?:https?://)?(?:www\.)?dndbeyond\.com/campaigns/(\d+)(?:$|/)', campaign_link)
        invite_link_match = re.match(r'(?:https?://)?ddb\.ac/campaigns/join/(\d+)\d{10}(?:$|/)', campaign_link)
        if link_match is None and invite_link_match is None:
            return await ctx.send("This is not a D&D Beyond campaign link.")
        campaign_id = (link_match or invite_link_match).group(1)

        # is there already an existing link?
        try:
            existing_link = await CampaignLink.from_id(self.bot.mdb, campaign_id)
        except NoCampaignLink:
            existing_link = None

        if existing_link is not None and existing_link.channel_id == ctx.channel.id:
            return await ctx.send("This campaign is already linked to this channel.")
        elif existing_link is not None:
            result = await confirm(
                ctx, "This campaign is already linked to another channel. Link it to this one instead?  (Reply with yes/no)")
            if not result:
                return await ctx.send("Ok, canceling.")

        # do link (and dm check)
        await ctx.trigger_typing()
        try:
            result = await self.bot.glclient.create_campaign_link(ctx, campaign_id, overwrite=True)
        except LinkNotAllowed:
            # the invite link match will only work 77% of the time because the hash can start w/ 0 - try using the
            # main link instead
            if invite_link_match:
                await ctx.send("You are not allowed to link this campaign. "
                               "Try using the campaign URL (in your browser bar) rather than the invite link!")
                return
            raise

        embed = embeds.EmbedWithAuthor(ctx)
        embed.title = f"Linked {result.campaign_name}!"
        embed.description = (f"Linked {result.campaign_name} to this channel! Your players' rolls from D&D Beyond "
                             f"will show up here, and checks, saves, and attacks made by characters in your campaign "
                             f"here will appear in D&D Beyond!")
        embed.add_field(name="Not Seeing Rolls?",
                        value=f"Not seeing one or more of your players' rolls? Make sure their [D&D Beyond "
                              f"and Discord accounts are linked](https://www.dndbeyond.com/account) and their "
                              f"[characters are imported](https://avrae.readthedocs.io/en/stable/cheatsheets/get_started.html#step-2-add-a-character)! "
                              f"You can check your players' link status with `{ctx.prefix}ddb`.")
        await ctx.send(embed=embed)

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
        embed = embeds.EmbedWithAuthor(ctx)
        embed.title = "D&D Beyond Campaign Links"
        embed.description = (f"This channel is linked to {len(existing_links)} "
                             f"{'campaign' if len(existing_links) == 1 else 'campaigns'}:\n"
                             f"{', '.join(cl.campaign_name for cl in existing_links)}")
        embed.add_field(name="Not Seeing Rolls?",
                        value=f"Not seeing one or more of your players' rolls? Make sure their [D&D Beyond "
                              f"and Discord accounts are linked](https://www.dndbeyond.com/account) and their "
                              f"[characters are imported](https://avrae.readthedocs.io/en/stable/cheatsheets/get_started.html#step-2-add-a-character)! "
                              f"You can check your players' link status with `{ctx.prefix}ddb`.")
        await ctx.send(embed=embed)

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

    # ==== game log handlers ====
    # ---- dice ----
    @staticmethod
    async def dice_roll_begin(gctx):
        """
        Sends a typing indicator to the linked channel to indicate that something is about to happen.
        """
        await gctx.trigger_typing()

    async def dice_roll(self, gctx):
        """
        Sends a message with the result of the roll, similar to `!r`.
        """
        await gctx.trigger_typing()

        roll_request = ddb.dice.RollRequest.from_dict(gctx.event.data)
        if not roll_request.rolls:  # do nothing if there are no rolls actually made
            return
        elif len(roll_request.rolls) > 1:  # if there are multiple rolls in the same event, just use the default handler
            await self.dice_roll_roll(gctx, roll_request,
                                      comment_getter=gamelogutils.default_comment_getter(roll_request))
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
    async def dice_roll_roll(gctx, roll_request, comment=None, comment_getter=None):
        """
        Generic roll: Display the roll in a format similar to ``!r``.

        :type gctx: ddb.gamelog.context.GameLogEventContext
        :type roll_request: ddb.dice.RollRequest
        :param comment: If comment_getter is not supplied, the comment used for all rolls.
        :type comment: str or None
        :param comment_getter: A function that takes a RollRequestRoll and returns a string, or None.
        :type comment_getter: Callable[[ddb.dice.RollRequestRoll], str]
        """
        if comment_getter is None:
            if comment is None:
                comment_getter = gamelogutils.default_comment_getter(roll_request)
            else:
                comment_getter = lambda _: comment

        results = []
        for rr in roll_request.rolls:
            results.append(str(rr.to_d20(stringifier=VerboseMDStringifier(), comment=comment_getter(rr))))

        if sum(len(r) for r in results) > 1950:  # some len removed for other stuff
            final_results = '\n'.join(f"**{comment_getter(rr)}**: {rr.result.total}" for rr in roll_request.rolls)
        else:
            final_results = '\n'.join(results)

        out = f"<@!{gctx.discord_user_id}> **rolled from** {constants.DDB_LOGO_EMOJI}:\n{final_results}"
        # the user knows they rolled - don't need to ping them in discord
        await gctx.send(out, allowed_mentions=discord.AllowedMentions.none())

    async def _dice_roll_embed_common(self, gctx, roll_request, title_fmt: str, **fmt_kwargs):
        """
        Common method to display a character embed based on some check/save result.

        Note: {name} will be formatted with the character's name in title_fmt.
        """
        # check for valid caster
        caster = await gctx.get_statblock()
        if caster is None:
            await self.dice_roll_roll(gctx, roll_request,
                                      comment_getter=gamelogutils.default_comment_getter(roll_request))
            return

        # only listen to the first roll
        the_roll = roll_request.rolls[0]

        # send embed
        embed = gamelogutils.embed_for_caster(caster)
        embed.title = title_fmt.format(name=caster.get_title_name(), **fmt_kwargs)
        embed.description = str(the_roll.to_d20())
        embed.set_footer(text=f"Rolled in {gctx.campaign.campaign_name}", icon_url=constants.DDB_LOGO_ICON)
        await gctx.send(embed=embed)

    async def dice_roll_check(self, gctx, roll_request):
        """Check: Display like ``!c``. Requires character - if not imported falls back to default roll."""
        check_name = roll_request.action
        if check_name in constants.STAT_ABBREVIATIONS:
            check_name = verbose_stat(check_name)
        await self._dice_roll_embed_common(gctx, roll_request, "{name} makes {check} check!",
                                           check=a_or_an(check_name.title()))

    async def dice_roll_save(self, gctx, roll_request):
        """Save: Display like ``!s``."""
        save_name = roll_request.action
        if save_name in constants.STAT_ABBREVIATIONS:
            save_name = verbose_stat(save_name)
        await self._dice_roll_embed_common(gctx, roll_request, "{name} makes {save} Save!",
                                           save=a_or_an(save_name.title()))

    async def dice_roll_heal(self, gctx, roll_request):
        """Healing and temp HP. Displays like a check/save/attack"""
        await self._dice_roll_embed_common(gctx, roll_request, "{name} heals with {heal}!",
                                           heal=roll_request.action)

    async def dice_roll_spell(self, gctx, roll_request):
        """Unknown when this is used. Set roll comment and pass to default roll handler."""
        await self.dice_roll_roll(gctx, roll_request, comment=f"{roll_request.action}: Spell")

    async def dice_roll_to_hit(self, gctx, roll_request):
        """To Hit rolls from attacks/spells."""

        # check for loaded character
        if (caster := await gctx.get_statblock()) is None:
            await self.dice_roll_roll(gctx, roll_request, comment=f"{roll_request.action}: To Hit")
            return

        # setup
        attack_roll = roll_request.rolls[0]
        action = await gamelogutils.action_from_roll_request(gctx, caster, roll_request)
        automation = None if action is None else action.automation
        pend_damage = True

        # generate the embed based on whether we found avrae annotated data
        if action is not None:
            embed = gamelogutils.embed_for_action(gctx, action, caster, attack_roll)
            # create a PendingAttack if the action has a damage,
            if not gamelogutils.automation_has_damage(automation):
                pend_damage = False
        else:
            # or if the action is unknown (we assume basic to hit/damage then)
            embed = gamelogutils.embed_for_basic_attack(gctx, roll_request.action, caster, attack_roll)

        message = await gctx.send(embed=embed)
        if pend_damage:
            await gamelogutils.PendingAttack.create(gctx, roll_request, gctx.event, message.id)

    async def dice_roll_damage(self, gctx, roll_request):
        """Damage rolls from attacks/spells."""
        # check for loaded character
        if (caster := await gctx.get_statblock()) is None:
            await self.dice_roll_roll(gctx, roll_request, comment=f"{roll_request.action}: Damage")
            return

        # only listen for first roll
        damage_roll = roll_request.rolls[0]
        attack_roll = None

        # find the relevant PendingAttack, if available
        pending = await gamelogutils.PendingAttack.for_damage(gctx, roll_request)
        if pending is not None:
            # update the PendingAttack with its damage
            attack_roll = pending.roll_request.rolls[0]
            # and remove it from the pending
            await pending.delete(gctx)

        # generate embed based on action
        action = await gamelogutils.action_from_roll_request(gctx, caster, roll_request)
        if action is not None:
            embed = gamelogutils.embed_for_action(gctx, action, caster, attack_roll, damage_roll)
        else:
            embed = gamelogutils.embed_for_basic_attack(gctx, roll_request.action, caster,
                                                        attack_roll, damage_roll)

        # either update the old message or post a new one
        if pending is not None:
            partial = discord.PartialMessage(channel=await gctx.destination_channel(), id=pending.message_id)
            try:
                await partial.edit(embed=embed)
            except discord.NotFound:  # original message was deleted
                await gctx.send(embed=embed)
        else:
            await gctx.send(embed=embed)

    # ==== game log send methods ====
    # to access, get the cog from the handler function that is making the checks and call these
    async def _send_preflight(self, ctx, character):
        """
        Call before any dice event processing. Returns a tuple (campaign_id, ddb_user), the latter will be None
        if the preflight checks fail.
        """
        # their character must be in a campaign
        if (campaign_id := character.ddb_campaign_id) is None:
            return None, None
        # and the character's campaign must be linked to this channel
        try:
            campaign_link = await CampaignLink.from_id(ctx.bot.mdb, campaign_id)
        except NoCampaignLink:
            return None, None
        if campaign_link.channel_id != ctx.channel.id:
            return None, None
        # and the user must have their ddb acct connected
        ddb_user = await self.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        if ddb_user is None:
            return campaign_id, None
        # and they must be allowed to use game log send by feature flag
        flag = await self.bot.ldclient.variation('cog.gamelog.roll_send.enabled', ddb_user.to_ld_dict(), False)
        if not flag:
            return campaign_id, None
        return campaign_id, ddb_user

    async def _send_roll_request(self, campaign_id, ddb_user, character, roll_request):
        """Sends a roll result to DDB."""
        event = GameLogEvent.dice_roll_fulfilled(
            game_id=campaign_id, user_id=ddb_user.user_id, roll_request=roll_request,
            entity_id=character.upstream_id
        )
        await self.bot.glclient.post_message(ddb_user, event)

    async def send_roll(self, ctx, result):
        """
        Send the result of a basic roll the user made, with no knowledge of character or context

        :type ctx: discord.ext.commands.Context
        :type result: d20.RollResult
        """
        # while roll doesn't require character, sendback to ddb does
        try:
            character = await Character.from_ctx(ctx)
        except NoCharacter:
            return
        campaign_id, ddb_user = await self._send_preflight(ctx, character)
        if ddb_user is None:
            return

        rrr = RollRequestRoll.from_d20(result, roll_type=RollType.ROLL, roll_kind=RollKind.guess_from_d20(result))
        comment = result.comment or 'Custom'
        roll_request = RollRequest.new([rrr], RollContext.from_character(character), comment)
        await self._send_roll_request(campaign_id, ddb_user, character, roll_request)

    async def send_check(self, ctx, character, skill, rolls):
        """
        :type ctx: discord.ext.commands.Context
        :type character: cogs5e.models.character.Character
        :type skill: str
        :type rolls: list of d20.RollResult
        """
        campaign_id, ddb_user = await self._send_preflight(ctx, character)
        if ddb_user is None:
            return

        roll_request_rolls = [
            RollRequestRoll.from_d20(r, roll_type=RollType.CHECK, roll_kind=RollKind.guess_from_d20(r))
            for r in rolls
        ]
        roll_request = RollRequest.new(roll_request_rolls, RollContext.from_character(character), skill)
        await self._send_roll_request(campaign_id, ddb_user, character, roll_request)

    async def send_save(self, ctx, character, ability, rolls):
        """
        :type ctx: discord.ext.commands.Context
        :type character: cogs5e.models.character.Character
        :type ability: str
        :type rolls: list of d20.RollResult
        """
        campaign_id, ddb_user = await self._send_preflight(ctx, character)
        if ddb_user is None:
            return

        roll_request_rolls = [
            RollRequestRoll.from_d20(r, roll_type=RollType.SAVE, roll_kind=RollKind.guess_from_d20(r))
            for r in rolls
        ]
        roll_request = RollRequest.new(roll_request_rolls, RollContext.from_character(character), ability)
        await self._send_roll_request(campaign_id, ddb_user, character, roll_request)

    async def send_automation(self, ctx, character, ability_name, automation_result):
        """
        Attacks, casting, etc (any result from the automation engine)

        :type ctx: discord.ext.commands.Context
        :type character: cogs5e.models.character.Character
        :type ability_name: str
        :type automation_result: cogs5e.models.automation.AutomationResult
        """
        campaign_id, ddb_user = await self._send_preflight(ctx, character)
        if ddb_user is None:
            return

        roll_request_rolls = []

        # dfs over the automation result tree, looking for results w/ dice that we care about
        def dfs(node):
            if isinstance(node, AttackResult):
                if node.to_hit_roll is not None:
                    roll_request_rolls.append(RollRequestRoll.from_d20(
                        node.to_hit_roll, roll_type=RollType.TO_HIT,
                        roll_kind=RollKind.from_d20_adv(node.adv)
                    ))
            elif isinstance(node, SaveResult):
                if node.save_roll is not None:
                    roll_request_rolls.append(RollRequestRoll.from_d20(
                        node.save_roll, roll_type=RollType.SAVE,
                        roll_kind=RollKind.from_d20_adv(node.adv)
                    ))
            elif isinstance(node, DamageResult):
                roll_request_rolls.append(RollRequestRoll.from_d20(
                    node.damage_roll, roll_type=RollType.DAMAGE,
                    roll_kind=RollKind.CRITICAL_HIT if node.in_crit else RollKind.NONE
                ))
            elif isinstance(node, TempHPResult):
                roll_request_rolls.append(RollRequestRoll.from_d20(node.amount_roll, roll_type=RollType.HEAL))
            elif isinstance(node, RollResult):
                if not node.hidden:
                    roll_request_rolls.append(RollRequestRoll.from_d20(
                        node.roll,
                        roll_type=RollType.SPELL if automation_result.is_spell else RollType.ROLL
                    ))
            for child in node.get_children():
                dfs(child)

        dfs(automation_result)
        if not roll_request_rolls:
            return
        roll_request = RollRequest.new(roll_request_rolls, RollContext.from_character(character), ability_name)
        await self._send_roll_request(campaign_id, ddb_user, character, roll_request)


def setup(bot):
    bot.add_cog(GameLog(bot))
