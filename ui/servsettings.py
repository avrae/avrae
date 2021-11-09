import abc
from typing import TYPE_CHECKING, TypeVar

import disnake

from utils.aldclient import discord_user_to_dict
from utils.settings.guild import InlineRollingType, ServerSettings
from .menu import MenuBase

_AvraeT = TypeVar('_AvraeT', bound=disnake.Client)
if TYPE_CHECKING:
    from dbot import Avrae

    _AvraeT = Avrae


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

    @disnake.ui.button(label='Exit', style=disnake.ButtonStyle.danger)
    async def exit(self, *_):
        await self.on_timeout()  # todo redirect back to global settings

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings for {self.guild.name}",
            colour=disnake.Colour.blurple()
        )
        embed.add_field(
            name="Lookup Settings",
            value=f"**DM Role**: Dungeon Master, DM, Game Master, or GM\n"  # {self.settings.lookup_dm_role}"
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
        return {"embed": embed}


class _LookupSettingsUI(ServerSettingsMenuBase):
    # @disnake.ui.button(label='Edit DM Role', style=disnake.ButtonStyle.primary)
    # async def edit_dm_role(self, button: disnake.ui.Button, interaction: disnake.Interaction):
    #     self.settings.lookup_dm_role += 1  # todo follow-up
    #     await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Monsters Require DM', style=disnake.ButtonStyle.primary)
    async def toggle_dm_required(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_dm_required = not self.settings.lookup_dm_required
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Direct Message DMs', style=disnake.ButtonStyle.primary)
    async def toggle_pm_dm(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_dm = not self.settings.lookup_pm_dm
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Toggle Direct Message Results', style=disnake.ButtonStyle.primary)
    async def toggle_pm_result(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_result = not self.settings.lookup_pm_result
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=1)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Lookup Settings",
            colour=disnake.Colour.blurple(),
            description="These settings affect how lookup results are displayed on this server."
        )
        # embed.add_field(
        #     name="DM Role",
        #     value=f"**{self.settings.lookup_dm_role}**\n"
        #           f"*If `Monsters Require DM` is enabled, any user with this role will be considered a DM.*",
        #     inline=False
        # )
        embed.add_field(
            name="DM Roles",
            value=f"**Dungeon Master, DM, Game Master, or GM**\n"
                  f"*If `Monsters Require DM` is enabled, any user with a role named one of these will be considered "
                  f"a DM. In the future, you will be able to select a server DM role.*",
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
    async def disable(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.DISABLED
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='React', style=disnake.ButtonStyle.primary)
    async def react(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.REACTION
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Enable', style=disnake.ButtonStyle.primary)
    async def enable(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.ENABLED
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label='Back', style=disnake.ButtonStyle.grey, row=1)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Inline Rolling Settings",
            colour=disnake.Colour.blurple(),
            description=await self.get_inline_rolling_desc()
        )
        return {"embed": embed}
