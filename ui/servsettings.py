import abc
import asyncio
from contextlib import suppress
from typing import List, Optional, TYPE_CHECKING, TypeVar

import disnake

from utils.aldclient import discord_user_to_dict
from utils.functions import natural_join
from utils.settings.guild import InlineRollingType, ServerSettings
from .menu import MenuBase

_AvraeT = TypeVar('_AvraeT', bound=disnake.Client)
if TYPE_CHECKING:
    from dbot import Avrae

    _AvraeT = Avrae

TOO_MANY_ROLES_SENTINEL = "__special:too_many_roles"


class ServerSettingsMenuBase(MenuBase, abc.ABC):
    __menu_copy_attrs__ = ('bot', 'settings', 'guild')
    bot: _AvraeT
    settings: ServerSettings
    guild: disnake.Guild

    async def commit_settings(self):
        """Commits any changed guild settings to the db."""
        await self.settings.commit(self.bot.mdb)

    async def get_inline_rolling_desc(self) -> str:
        flag_enabled = await self.bot.ldclient.variation(
            "cog.dice.inline_rolling.enabled",
            user=discord_user_to_dict(self.owner),
            default=False
        )
        if not flag_enabled:
            return "Inline rolling is currently **globally disabled** for all users. Check back soon!"

        if self.settings.inline_enabled == InlineRollingType.DISABLED:
            return "Inline rolling is currently **disabled**."
        elif self.settings.inline_enabled == InlineRollingType.REACTION:
            return ("Inline rolling is currently set to **react**. I'll look for messages containing `[[dice]]` "
                    "and react with :game_die: - click the reaction to roll!")
        return "Inline rolling is currently **enabled**. I'll roll any `[[dice]]` I find in messages!"


class ServerSettingsUI(ServerSettingsMenuBase):
    @classmethod
    def new(cls, bot: _AvraeT, owner: disnake.User, settings: ServerSettings, guild: disnake.Guild):
        inst = cls(owner=owner)
        inst.bot = bot
        inst.settings = settings
        inst.guild = guild
        return inst

    @disnake.ui.button(label='Lookup Settings', style=disnake.ButtonStyle.primary)
    async def lookup_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_LookupSettingsUI, interaction)

    @disnake.ui.button(label='Inline Rolling Settings', style=disnake.ButtonStyle.primary)
    async def inline_rolling_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_InlineRollingSettingsUI, interaction)

    @disnake.ui.button(label='Miscellaneous Settings', style=disnake.ButtonStyle.primary)
    async def miscellaneous_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_MiscellaneousSettingsUI, interaction)

    @disnake.ui.button(label='Exit', style=disnake.ButtonStyle.danger)
    async def exit(self, *_):
        await self.on_timeout()

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings for {self.guild.name}",
            colour=disnake.Colour.blurple()
        )
        if self.settings.dm_roles:
            dm_roles = natural_join([f'<@&{role_id}>' for role_id in self.settings.dm_roles], 'or')
        else:
            dm_roles = "Dungeon Master, DM, Game Master, or GM"
        embed.add_field(
            name="Lookup Settings",
            value=f"**DM Roles**: {dm_roles}\n"
                  f"**Monsters Require DM**: {self.settings.lookup_dm_required}\n"
                  f"**Direct Message DM**: {self.settings.lookup_pm_dm}\n"
                  f"**Direct Message Results**: {self.settings.lookup_pm_result}",
            inline=False
        )
        embed.add_field(
            name="Inline Rolling Settings",
            value=await self.get_inline_rolling_desc(),
            inline=False
        )
        embed.add_field(
            name="Miscellaneous Settings",
            value=f"**Show DDB Campaign Message**: {self.settings.show_campaign_cta}",
            inline=False
        )
        return {"embed": embed}


class _LookupSettingsUI(ServerSettingsMenuBase):
    select_dm_roles: disnake.ui.Select  # make the type checker happy

    # ==== ui ====
    @disnake.ui.select(placeholder='Select DM Roles', min_values=0)
    async def select_dm_roles(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        if len(select.values) == 1 and select.values[0] == TOO_MANY_ROLES_SENTINEL:
            role_ids = await self._text_select_dm_roles(interaction)
        else:
            role_ids = list(map(int, select.values))
        self.settings.dm_roles = role_ids or None
        self._refresh_dm_role_select()
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Monsters Require DM', style=disnake.ButtonStyle.primary, row=1)
    async def toggle_dm_required(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_dm_required = not self.settings.lookup_dm_required
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Direct Message DMs', style=disnake.ButtonStyle.primary, row=1)
    async def toggle_pm_dm(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_dm = not self.settings.lookup_pm_dm
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Direct Message Results', style=disnake.ButtonStyle.primary, row=1)
    async def toggle_pm_result(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_result = not self.settings.lookup_pm_result
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    # ==== handlers ====
    async def _text_select_dm_roles(self, interaction: disnake.Interaction) -> Optional[List[int]]:
        self.select_dm_roles.disabled = True
        await self.refresh_content(interaction)
        await interaction.send(
            "Choose the DM roles by sending a message to this channel. You can mention the roles, or use a "
            "comma-separated list of role names or IDs. Type `reset` to reset the role list to the default.",
            ephemeral=True
        )

        try:
            input_msg: disnake.Message = await self.bot.wait_for(
                'message', timeout=60,
                check=lambda msg: msg.author == interaction.author and msg.channel.id == interaction.channel_id
            )
            with suppress(disnake.HTTPException):
                await input_msg.delete()

            if input_msg.content == 'reset':
                await interaction.send("The DM roles have been updated.", ephemeral=True)
                return None

            role_ids = {r.id for r in input_msg.role_mentions}
            for stmt in input_msg.content.split(','):
                clean_stmt = stmt.strip()
                try:  # get role by id
                    role_id = int(clean_stmt)
                    maybe_role = self.guild.get_role(role_id)
                except ValueError:  # get role by name
                    maybe_role = next((r for r in self.guild.roles if r.name.lower() == clean_stmt.lower()), None)
                if maybe_role is not None:
                    role_ids.add(maybe_role.id)

            if role_ids:
                await interaction.send("The DM roles have been updated.", ephemeral=True)
                return list(role_ids)
            await interaction.send("No valid roles found. Use the select menu to try again.", ephemeral=True)
            return self.settings.dm_roles
        except asyncio.TimeoutError:
            await interaction.send("No valid roles found. Use the select menu to try again.", ephemeral=True)
            return self.settings.dm_roles
        finally:
            self.select_dm_roles.disabled = False

    # ==== content ====
    def _refresh_dm_role_select(self):
        """Update the options in the DM Role select to reflect the currently selected values."""
        self.select_dm_roles.options.clear()
        if len(self.guild.roles) > 25:
            self.select_dm_roles.add_option(
                label="Whoa, this server has a lot of roles! Click here to select them.",
                value=TOO_MANY_ROLES_SENTINEL
            )
            return

        for role in reversed(self.guild.roles):  # display highest-first
            selected = self.settings.dm_roles is not None and role.id in self.settings.dm_roles
            self.select_dm_roles.add_option(label=role.name, value=str(role.id), emoji=role.emoji, default=selected)
        self.select_dm_roles.max_values = len(self.select_dm_roles.options)

    async def _before_send(self):
        self._refresh_dm_role_select()

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Lookup Settings",
            colour=disnake.Colour.blurple(),
            description="These settings affect how lookup results are displayed on this server."
        )
        if not self.settings.dm_roles:
            embed.add_field(
                name="DM Roles",
                value=f"**Dungeon Master, DM, Game Master, or GM**\n"
                      f"*Any user with a role named one of these will be considered a DM. This lets them look up a "
                      f"monster's full stat block if `Monsters Require DM` is enabled, skip other players' turns in "
                      f"initiative, and more.*",
                inline=False
            )
        else:
            dm_roles = natural_join([f'<@&{role_id}>' for role_id in self.settings.dm_roles], 'or')
            embed.add_field(
                name="DM Roles",
                value=f"**{dm_roles}**\n"
                      f"*Any user with at least one of these roles will be considered a DM. This lets them look up a "
                      f"monster's full stat block if `Monsters Require DM` is enabled, skip turns in initiative, and "
                      f"more.*",
                inline=False
            )
        embed.add_field(
            name="Monsters Require DM",
            value=f"**{self.settings.lookup_dm_required}**\n"
                  f"*If this is enabled, monster lookups will display hidden stats for any user without "
                  f"a role named DM, GM, Dungeon Master, Game Master, or the DM role configured above.*",
            inline=False
        )
        embed.add_field(
            name="Direct Message DMs",
            value=f"**{self.settings.lookup_pm_dm}**\n"
                  f"*If this is enabled, the result of monster lookups will be direct messaged to the user who looked "
                  f"it up, rather than being printed to the channel, if the user is a DM.*",
            inline=False
        )
        embed.add_field(
            name="Direct Message Results",
            value=f"**{self.settings.lookup_pm_result}**\n"
                  f"*If this is enabled, the result of all lookups will be direct messaged to the user who looked "
                  f"it up, rather than being printed to the channel.*",
            inline=False
        )
        return {"embed": embed}


class _InlineRollingSettingsUI(ServerSettingsMenuBase):
    @disnake.ui.button(label='Disable', style=disnake.ButtonStyle.primary)
    async def disable(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.DISABLED
        button.disabled = True
        self.react.disabled = False
        self.enable.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='React', style=disnake.ButtonStyle.primary)
    async def react(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.REACTION
        button.disabled = True
        self.disable.disabled = False
        self.enable.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Enable', style=disnake.ButtonStyle.primary)
    async def enable(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.ENABLED
        button.disabled = True
        self.disable.disabled = False
        self.react.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=1)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    async def _before_send(self):
        if self.settings.inline_enabled is InlineRollingType.DISABLED:
            self.disable.disabled = True
        elif self.settings.inline_enabled is InlineRollingType.REACTION:
            self.react.disabled = True
        elif self.settings.inline_enabled is InlineRollingType.ENABLED:
            self.enable.disabled = True

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Inline Rolling Settings",
            colour=disnake.Colour.blurple(),
            description=await self.get_inline_rolling_desc()
        )
        return {"embed": embed}

class _MiscellaneousSettingsUI(ServerSettingsMenuBase):
    # ==== ui ====
    @disnake.ui.button(label='Toggle DDB Campaign Message', style=disnake.ButtonStyle.primary, row=1)
    async def toggle_campaign_cta(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.show_campaign_cta = not self.settings.show_campaign_cta
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    # ==== content ====
    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Miscellaneous Settings",
            colour=disnake.Colour.blurple(),
            description="These settings affect less significant parts of Avrae."
        )
        embed.add_field(
            name="Show DDB Campaign Message",
            value=f"**{self.settings.show_campaign_cta}**\n"
                  f"*If this is enabled, every week a reminder about D&D Beyond's Campaign integration "
                  f"will be shown after a character updates.*",
            inline=False
        )
        return {"embed": embed}
