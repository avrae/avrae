import discord

import ddb.dice
from cogs5e.utils import gamelogutils
from utils import constants
from utils.dice import VerboseMDStringifier
from utils.functions import a_or_an, verbose_stat
from .callback import GameLogCallbackHandler, callback


class DiceHandler(GameLogCallbackHandler):
    @callback('dice/roll/pending')
    async def dice_roll_begin(self, gctx):
        """
        Sends a typing indicator to the linked channel to indicate that something is about to happen.
        """
        await gctx.trigger_typing()

    @callback('dice/roll/fulfilled')
    async def dice_roll(self, gctx):
        """
        Sends a message with the result of the roll, similar to `!r`.
        """
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

    # ==== helpers ====
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
                comment_getter = lambda _: comment  # noqa: E731

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
