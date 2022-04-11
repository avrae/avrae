import disnake

from cogs5e.models.automation import Target
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
            await try_update_interaction_message_components(inter, None)
            return

        # find the combatant
        combatant = combat.combatant_by_id(combatant_id)
        if combatant is None:
            # if the combatant was removed, we can remove the buttons
            await inter.send("This combatant is no longer in the referenced combat.", ephemeral=True)
            await try_update_interaction_message_components(inter, None)
            return

        # find the effect
        effect = combatant.effect_by_id(effect_id)
        if effect is None:
            # we can't remove all the buttons if the effect got yeeted, but we can update them
            await inter.send("This effect is no longer active on the referenced combatant.", ephemeral=True)
            await try_update_interaction_message_components(inter, utils.combatant_interaction_components(combatant))
            return

        # find the ButtonInteraction
        button_interaction = next((i for i in effect.buttons if i.id == button_id), None)
        if button_interaction is None:
            # this should be impossible, but if it happens, we'll update the components anyway
            await inter.send("This effect no longer provides this button interaction.", ephemeral=True)
            await try_update_interaction_message_components(inter, utils.combatant_interaction_components(combatant))
            return

        # we need to set up the autoctx to target the combatant this effect is on before running, so we use the before
        # hook to run a phony Target effect
        def set_up_caster_target(autoctx):
            Target(target="self", effects=[]).run_target(autoctx, target=combatant, target_index=0)

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
            before=set_up_caster_target,
        )
        await inter.response.edit_message(components=utils.combatant_interaction_components(combatant))
        await inter.channel.send(embed=embed)
        if (gamelog := self.bot.get_cog("GameLog")) and combatant.type == CombatantType.PLAYER and result is not None:
            await gamelog.send_automation(inter, combatant.character, button_interaction.label, result)


async def try_update_interaction_message_components(inter: disnake.MessageInteraction, components):
    try:
        await inter.message.edit(components=components)
    except disnake.HTTPException:
        pass
