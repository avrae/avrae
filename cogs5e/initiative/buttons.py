import asyncio
from typing import Iterable, TYPE_CHECKING

import disnake

import gamedata
from cogs5e.utils import actionutils
from utils.argparser import ParsedArguments
from . import Combat, CombatNotFound, CombatantType, utils
from .utils import InteractionMessageType

if TYPE_CHECKING:
    from . import Combatant


class ButtonHandler:
    def __init__(self, bot):
        self.bot = bot

    async def handle(
        self,
        inter: disnake.MessageInteraction,
        combatant_id: str,
        effect_id: str,
        button_id: str,
        message_type: InteractionMessageType,
    ):
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
            # if the combatant was removed, we can remove buttons with the same combatant ID
            # but the message might have combatants in the same group
            await inter.send("This combatant is no longer in the referenced combat.", ephemeral=True)
            await remove_triggering_message_components_for_combatant(inter, combatant_id)
            return

        # check ownership
        author_id = inter.author.id
        if not (author_id == combatant.controller_id or author_id == combat.dm_id):
            await inter.send(
                (
                    "You do not have permission to control this combatant. Only the combatant owner and combat DM may"
                    " use this button."
                ),
                ephemeral=True,
            )
            return

        # find the effect
        effect = combatant.effect_by_id(effect_id)
        if effect is None:
            # we can't remove all the buttons if the effect got yeeted, but we can update them
            await inter.send("This effect is no longer active on the referenced combatant.", ephemeral=True)
            await update_triggering_message(inter, combat, combatant, message_type)
            return

        # find the ButtonInteraction
        button_interaction = next((i for i in effect.buttons if i.id == button_id), None)
        if button_interaction is None:
            # this should be impossible, but if it happens, we'll update the components anyway
            await inter.send("This effect no longer provides this button interaction.", ephemeral=True)
            await update_triggering_message(inter, combat, combatant, message_type)
            return

        # in some rate-limited cases we can fail the 3-second response time so we have to defer each interaction
        await inter.response.defer()

        # anyway, we're good to run the automation!
        if button_interaction.verb is not None:
            verb = button_interaction.verb
        else:
            verb = f"uses {button_interaction.label}"

        if button_interaction.granting_spell_id is not None:
            spell = gamedata.compendium.lookup_entity(gamedata.Spell.entity_type, button_interaction.granting_spell_id)
        else:
            spell = None

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
            allow_caster_ieffects=False,  # do not allow things like damage-boosting effects to affect dot ticks
            ab_override=button_interaction.override_default_attack_bonus,
            dc_override=button_interaction.override_default_dc,
            spell_override=button_interaction.override_default_casting_mod,
            spell=spell,
            spell_level_override=button_interaction.granting_spell_cast_level,
            from_button=True,
            original_choice=button_interaction.original_choice,
        )

        # and send the result
        await asyncio.gather(
            update_triggering_message(inter, combat, combatant, message_type),
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


async def remove_triggering_message_components_for_combatant(inter: disnake.MessageInteraction, combatant_id: str):
    """
    Update the triggering message of the interaction, removing any components with the combatant's custom id prefix.
    """
    # ieb:<combatant_id>:<effect_id>:<button_id>
    combatant_prefix = f"ieb:{combatant_id}:"
    components = [
        disnake.ui.Button.from_component(button)
        for button in _walk_components_extract_buttons(inter.message.components)
        if not button.custom_id.startswith(combatant_prefix)
    ]
    try:
        await inter.message.edit(components=components)
    except disnake.HTTPException:
        pass


def _walk_components_extract_buttons(components: list[disnake.Component]) -> Iterable[disnake.Button]:
    """Given a list of message components, yields all the buttons, recursively entering into ActionRows."""
    for component in components:
        if isinstance(component, disnake.Button):
            yield component
        elif isinstance(component, disnake.ActionRow):
            yield from _walk_components_extract_buttons(component.children)


async def update_triggering_message(
    inter: disnake.MessageInteraction, combat: "Combat", combatant: "Combatant", message_type: InteractionMessageType
):
    """Update the triggering message of the interaction to reflect the combatant's current state."""
    # get the new state of the combatant
    if message_type == InteractionMessageType.TURN_MESSAGE:
        await inter.edit_original_message(
            content=utils.get_turn_str_content(combat, combatant=combatant, promote_to_group=True),
            # todo: can we remove the below if DisnakeDev/disnake#573 gets fixed?
            allowed_mentions=combat.get_turn_str_mentions_for(combatant),
            components=utils.combatant_interaction_components(
                combatant, message_type=message_type, promote_to_group=True
            ),
        )
    elif message_type == InteractionMessageType.STATUS_INDIVIDUAL:
        await inter.edit_original_message(
            content=utils.get_combatant_status_content(
                combatant=combatant, author=inter.author, promote_to_group=False
            ),
            components=utils.combatant_interaction_components(
                combatant, message_type=message_type, promote_to_group=False
            ),
        )
    else:  # message_type == InteractionMessageType.STATUS_GROUP
        await inter.edit_original_message(
            content=utils.get_combatant_status_content(combatant=combatant, author=inter.author, promote_to_group=True),
            components=utils.combatant_interaction_components(
                combatant, message_type=message_type, promote_to_group=True
            ),
        )
