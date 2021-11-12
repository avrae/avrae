import abc
import asyncio
from typing import TYPE_CHECKING, TypeVar

import disnake
import pydantic
import pydantic.color

from cogs5e.models import embeds
from cogs5e.models.character import Character
from utils.settings import CharacterSettings
from .menu import MenuBase

_AvraeT = TypeVar('_AvraeT', bound=disnake.Client)
if TYPE_CHECKING:
    from dbot import Avrae

    _AvraeT = Avrae


class CharacterSettingsMenuBase(MenuBase, abc.ABC):
    __menu_copy_attrs__ = ('bot', 'settings', 'character')
    bot: _AvraeT
    settings: CharacterSettings
    character: Character  # the character object here may be detached; its settings are kept in sync though

    async def commit_settings(self):
        """
        Commits any changed character settings to the db and the cached character object (if applicable - ours may be
        detached if the interaction has lasted a while).
        This is significantly more efficient than using Character.commit().
        """
        self.character.options = self.settings
        await self.settings.commit(self.bot.mdb, self.character)


class CharacterSettingsUI(CharacterSettingsMenuBase):
    @classmethod
    def new(cls, bot: _AvraeT, owner: disnake.User, character: Character):
        inst = cls(owner=owner)
        inst.bot = bot
        inst.settings = character.options
        inst.character = character
        return inst

    @disnake.ui.button(label='Cosmetic Settings', style=disnake.ButtonStyle.primary)
    async def cosmetic_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_CosmeticSettingsUI, interaction)

    @disnake.ui.button(label='Gameplay Settings', style=disnake.ButtonStyle.primary)
    async def gameplay_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_GameplaySettingsUI, interaction)

    @disnake.ui.button(label='Exit', style=disnake.ButtonStyle.danger)
    async def exit(self, *_):
        await self.on_timeout()  # todo redirect back to global settings

    async def get_content(self):
        embed = embeds.EmbedWithCharacter(
            self.character,
            title=f"Character Settings for {self.character.name}"
        )
        embed.add_field(
            name="Cosmetic Settings",
            value=f"**Embed Color**: {color_setting_desc(self.settings.color)}\n"
                  f"**Show Character Image**: {self.settings.embed_image}",
            inline=False
        )
        embed.add_field(
            name="Gameplay Settings",
            value=f"**Crit Range**: {crit_range_desc(self.settings.crit_on)}\n"
                  f"**Extra Crit Dice**: {self.settings.extra_crit_dice}\n"
                  f"**Reroll**: {self.settings.reroll}\n"
                  f"**Ignore Crits**: {self.settings.ignore_crit}\n"
                  f"**Reliable Talent**: {self.settings.talent}\n"
                  f"**Reset All Spell Slots on Short Rest**: {self.settings.srslots}",
            inline=False
        )
        return {"embed": embed}


class _CosmeticSettingsUI(CharacterSettingsMenuBase):
    @disnake.ui.button(label='Select Color', style=disnake.ButtonStyle.primary)
    async def select_color(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        button.disabled = True
        await self.refresh_content(interaction)
        await interaction.send(
            "Choose a new color by sending a message in this channel. You can use a hex code or color like `pink`.",
            ephemeral=True
        )

        try:
            input_msg: disnake.Message = await self.bot.wait_for(
                'message', timeout=60,
                check=lambda msg: msg.author == interaction.author and msg.channel == interaction.channel
            )
            color_val = pydantic.color.Color(input_msg.content)
            r, g, b = color_val.as_rgb_tuple(alpha=False)
            self.settings.color = (r << 16) + (g << 8) + b
            await input_msg.delete()
        except (ValueError, asyncio.TimeoutError, pydantic.ValidationError):
            await interaction.send("No valid color found. Press `Select Color` to try again.", ephemeral=True)
        except disnake.HTTPException:
            pass
        finally:
            button.disabled = False
            await self.commit_settings()
            await self.refresh_content(interaction)
            await interaction.send("Your embed color has been updated.", ephemeral=True)

    @disnake.ui.button(label='Reset Color', style=disnake.ButtonStyle.danger)
    async def reset_color(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.color = None
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Show Character Image', style=disnake.ButtonStyle.primary, row=1)
    async def toggle_show_character_image(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.embed_image = not self.settings.embed_image
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=2)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(CharacterSettingsUI, interaction)

    async def get_content(self):
        embed = embeds.EmbedWithCharacter(
            self.character,
            title=f"Character Settings ({self.character.name}) / Cosmetic Settings"
        )
        embed.add_field(
            name="Embed Color",
            value=f"**{color_setting_desc(self.settings.color)}**\n"
                  f"*This color will appear on the left side of your character's check, save, actions, and some "
                  f"other embeds (like this one!).*",
            inline=False
        )
        embed.add_field(
            name="Show Character Image",
            value=f"**{self.settings.embed_image}**\n"
                  f"*If this is disabled, your character's portrait will not appear on the right side of their "
                  f"checks, saves, actions, and some other embeds.*",
            inline=False
        )
        return {"embed": embed}


_CRIT_RANGE_SELECT_OPTIONS = [
    disnake.SelectOption(label="20"),
    *[disnake.SelectOption(label=f"{i}-20", value=str(i)) for i in range(19, 0, -1)],
]
_CRIT_DICE_SELECT_OPTIONS = [disnake.SelectOption(label=str(i)) for i in range(0, 21)]
_REROLL_SELECT_OPTIONS = [
    disnake.SelectOption(label="Disabled", value='null'),
    *[disnake.SelectOption(label=str(i)) for i in range(1, 21)]
]


class _GameplaySettingsUI(CharacterSettingsMenuBase):
    @disnake.ui.select(placeholder='Select New Crit Range', options=_CRIT_RANGE_SELECT_OPTIONS)
    async def crit_range_select(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        self.settings.crit_on = int(select.values[0])
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.select(placeholder='Select Extra Crit Dice', options=_CRIT_DICE_SELECT_OPTIONS, row=1)
    async def crit_dice_select(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        self.settings.extra_crit_dice = int(select.values[0])
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.select(placeholder='Select Reroll', options=_REROLL_SELECT_OPTIONS, row=2)
    async def reroll_select(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        value = select.values[0]
        if value == 'null':
            self.settings.reroll = None
        else:
            self.settings.reroll = int(value)
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Ignore Crits', style=disnake.ButtonStyle.primary, row=3)
    async def toggle_ignore_crits(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.ignore_crit = not self.settings.ignore_crit
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Reliable Talent', style=disnake.ButtonStyle.primary, row=3)
    async def toggle_reliable_talent(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.talent = not self.settings.talent
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Short Rest Slots', style=disnake.ButtonStyle.primary, row=3)
    async def toggle_srslots(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.srslots = not self.settings.srslots
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(CharacterSettingsUI, interaction)

    async def get_content(self):
        embed = embeds.EmbedWithCharacter(
            self.character,
            title=f"Character Settings ({self.character.name}) / Gameplay Settings"
        )
        embed.add_field(
            name="Crit Range",
            value=f"**{crit_range_desc(self.settings.crit_on)}**\n"
                  f"*If an attack roll's natural roll (the value on the d20 before modifiers) lands in this range, "
                  f"the attack will be counted as a crit.*",
            inline=False
        )
        embed.add_field(
            name="Extra Crit Dice",
            value=f"**{self.settings.extra_crit_dice}**\n"
                  f"*How many additional dice to add to a weapon's damage dice on a crit (in addition to doubling the "
                  f"dice).*",
            inline=False
        )
        embed.add_field(
            name="Reroll",
            value=f"**{self.settings.reroll}**\n"
                  f"*If an attack, save, or ability check's natural roll lands on this number, the die will be "
                  f"rerolled up to once.*",
            inline=False
        )
        embed.add_field(
            name="Ignore Crits",
            value=f"**{self.settings.ignore_crit}**\n"
                  f"*If this is enabled, any attack against your character will not have its damage dice doubled on a "
                  f"critical hit.*",
            inline=False
        )
        embed.add_field(
            name="Reliable Talent",
            value=f"**{self.settings.talent}**\n"
                  f"*If this is enabled, any d20 roll on an ability check that lets you add your proficiency bonus "
                  f"will be treated as a 10 if it rolls 9 or lower.*",
            inline=False
        )
        embed.add_field(
            name="Reset All Spell Slots on Short Rest",
            value=f"**{self.settings.srslots}**\n"
                  f"*If this is enabled, all of your spell slots (including non-pact slots) will reset on a short "
                  f"rest. Note that pact slots will reset on a short rest even if this setting is disabled.*",
            inline=False
        )
        return {"embed": embed}


def color_setting_desc(color):
    return f"#{color:06X}" if color is not None else 'Random'


def crit_range_desc(crit_on):
    return '20' if crit_on == 20 else f'{crit_on}-20'
