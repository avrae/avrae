import asyncio

import disnake

from cogs5e.utils import actionutils
from utils.argparser import ParsedArguments
from . import Combat, CombatNotFound, CombatantType, utils


class ButtonHandler:
    def __init__(self, bot):
        self.bot = bot

    async def handle(self, inter: disnake.MessageInteraction, combatant_id: str, effect_id: str, button_id: str):
        # load the combat
        try:
            # oh boy, here we go with ctx duck-typing
            combat = await Combat.from_id(channel_id=str(inter.channel_id), ctx=inter)
        except CombatNotFound:
            # if the combat has ended, we can remove the buttons
            await inter.send("This channel is no longer in combat.", ephemeral=True)
            await remove_triggering_message_components(inter)
            return

        # find the combatant
        combatant = combat.combatant_by_id(combatant_id)
        if combatant is None:
            # if the combatant was removed, we can remove the buttons
            await inter.send("This combatant is no longer in the referenced combat.", ephemeral=True)
            await remove_triggering_message_components(inter)
            return

        # check ownership
        author_id = inter.author.id
        if not (author_id == combatant.controller_id or author_id == combat.dm_id):
            await inter.send(
                "You do not have permission to control this combatant. Only the combatant owner and combat DM may use "
                "this button.",
                ephemeral=True,
            )
            return

        # find the effect
        effect = combatant.effect_by_id(effect_id)
        if effect is None:
            # we can't remove all the buttons if the effect got yeeted, but we can update them
            await inter.send("This effect is no longer active on the referenced combatant.", ephemeral=True)
            await update_triggering_message(inter, combat, combatant)
            return

        # find the ButtonInteraction
        button_interaction = next((i for i in effect.buttons if i.id == button_id), None)
        if button_interaction is None:
            # this should be impossible, but if it happens, we'll update the components anyway
            await inter.send("This effect no longer provides this button interaction.", ephemeral=True)
            await update_triggering_message(inter, combat, combatant)
            return

        # in some rate-limited cases we can fail the 3-second response time so we have to defer each interaction
        await inter.response.defer()

        # anyway, we're good to run the automation!
        if button_interaction.verb is not None:
            verb = button_interaction.verb
        else:
            verb = f"uses {button_interaction.label}"

        embed = disnake.Embed(color=combatant.get_color())
        embed.title = f"{combatant.get_title_name()} {verb}!"
        result = await actionutils.run_automation(
            ctx=inter,
            embed=embed,
            args=ParsedArguments.empty_args(),
            caster=combatant,
            automation=button_interaction.automation,
            targets=[],
            combat=combat,
            ieffect=effect,
        )

        # and send the result
        await asyncio.gather(
            update_triggering_message(inter, combat, combatant),
            inter.channel.send(embed=embed),
        )
        if (gamelog := self.bot.get_cog("GameLog")) and combatant.type == CombatantType.PLAYER and result is not None:
            await gamelog.send_automation(inter, combatant.character, button_interaction.label, result)


async def remove_triggering_message_components(inter: disnake.MessageInteraction):
    """Update the triggering message of the interaction, removing all components."""
    try:
        await inter.message.edit(components=None)
    except disnake.HTTPException:
        pass


async def update_triggering_message(inter: disnake.MessageInteraction, combat, combatant):
    """Update the triggering message of the interaction to reflect the combatant's current state."""
    # get the new state of the combatant
    # (HACK: it's probably an on-turn message if it mentions someone, otherwise it's probably an !i status message)
    if inter.message.mentions:
        await inter.edit_original_message(
            content=combat.get_turn_str(),
            allowed_mentions=combat.get_turn_str_mentions(),
            components=utils.combatant_interaction_components(combatant),
        )
    else:
        await inter.edit_original_message(
            content=utils.get_combatant_status_content(combatant=combatant, author=inter.author),
            components=utils.combatant_interaction_components(combatant),
        )
