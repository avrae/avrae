import abc
import asyncio
import re
from contextlib import suppress
from typing import List, Optional, TYPE_CHECKING, TypeVar

import d20
import disnake

from utils.constants import STAT_ABBREVIATIONS
from utils.enums import CritDamageType
from utils.functions import natural_join
from utils.settings.guild import InlineRollingType, LegacyPreference, RandcharRule, ServerSettings
from .menu import MenuBase

_AvraeT = TypeVar("_AvraeT", bound=disnake.Client)
if TYPE_CHECKING:
    from dbot import Avrae

    _AvraeT = Avrae

TOO_MANY_ROLES_SENTINEL = "__special:too_many_roles"


class ServerSettingsMenuBase(MenuBase, abc.ABC):
    __menu_copy_attrs__ = ("bot", "settings", "guild")
    bot: _AvraeT
    settings: ServerSettings
    guild: disnake.Guild

    async def commit_settings(self):
        """Commits any changed guild settings to the db."""
        await self.settings.commit(self.bot.mdb)

    async def get_inline_rolling_desc(self) -> str:
        flag_enabled = await self.bot.ldclient.variation_for_discord_user(
            "cog.dice.inline_rolling.enabled", user=self.owner, default=False
        )
        if not flag_enabled:
            return "Inline rolling is currently **globally disabled** for all users. Check back soon!"

        if self.settings.inline_enabled == InlineRollingType.DISABLED:
            return "Inline rolling is currently **disabled**."
        elif self.settings.inline_enabled == InlineRollingType.REACTION:
            return (
                "Inline rolling is currently set to **react**. I'll look for messages containing `[[dice]]` "
                "and react with :game_die: - click the reaction to roll!"
            )
        return "Inline rolling is currently **enabled**. I'll roll any `[[dice]]` I find in messages!"


class ServerSettingsUI(ServerSettingsMenuBase):
    @classmethod
    def new(cls, bot: _AvraeT, owner: disnake.User, settings: ServerSettings, guild: disnake.Guild):
        inst = cls(owner=owner)
        inst.bot = bot
        inst.settings = settings
        inst.guild = guild
        return inst

    @disnake.ui.button(label="Lookup Settings", style=disnake.ButtonStyle.primary)
    async def lookup_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_LookupSettingsUI, interaction)

    @disnake.ui.button(label="Inline Rolling Settings", style=disnake.ButtonStyle.primary)
    async def inline_rolling_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_InlineRollingSettingsUI, interaction)

    @disnake.ui.button(label="Custom Stat Roll Settings", style=disnake.ButtonStyle.primary)
    async def rollstats_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_RollStatsSettingsUI, interaction)

    @disnake.ui.button(label="Miscellaneous Settings", style=disnake.ButtonStyle.primary)
    async def miscellaneous_settings(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(_MiscellaneousSettingsUI, interaction)

    @disnake.ui.button(label="Exit", style=disnake.ButtonStyle.danger)
    async def exit(self, *_):
        await self.on_timeout()

    async def get_content(self):
        embed = disnake.Embed(title=f"Server Settings for {self.guild.name}", colour=disnake.Colour.blurple())
        if self.settings.dm_roles:
            dm_roles = natural_join([f"<@&{role_id}>" for role_id in self.settings.dm_roles], "or")
        else:
            dm_roles = "Dungeon Master, DM, Game Master, or GM"
        embed.add_field(
            name="__Lookup Settings__",
            value=(
                f"**DM Roles**: {dm_roles}\n"
                f"**Monsters Require DM**: {self.settings.lookup_dm_required}\n"
                f"**Direct Message DM**: {self.settings.lookup_pm_dm}\n"
                f"**Direct Message Results**: {self.settings.lookup_pm_result}\n"
                f"**Prefer Legacy Content**: {legacy_preference_desc(self.settings.legacy_preference)}\n"
                f"**5e Rules Version**: {self.settings.version}"
            ),
            inline=False,
        )
        embed.add_field(name="Inline Rolling Settings", value=await self.get_inline_rolling_desc(), inline=False)

        embed.add_field(
            name="__Custom Stat Roll Settings__",
            value=(
                f"**Dice**: {self.settings.randchar_dice}\n"
                f"**Number of Sets**: {self.settings.randchar_sets}\n"
                f"**Assign Stats**: {self.settings.randchar_straight}\n"
                f"**Stat Names:** {stat_names_desc(self.settings.randchar_stat_names)}\n"
                f"**Minimum Total**: {self.settings.randchar_min}\n"
                f"**Maximum Total**: {self.settings.randchar_max}\n"
                f"**Over/Under Rules**: {get_over_under_desc(self.settings.randchar_rules)}"
            ),
            inline=False,
        )

        nlp_enabled_description = ""
        nlp_feature_flag = await self.bot.ldclient.variation_for_discord_user(
            "cog.initiative.upenn_nlp.enabled", user=self.owner, default=False
        )
        if nlp_feature_flag:
            nlp_enabled_description = f"\n**Contribute Message Data to NLP Training**: {self.settings.upenn_nlp_opt_in}"
        embed.add_field(
            name="__Miscellaneous Settings__",
            value=(
                f"**Show DDB Campaign Message**: {self.settings.show_campaign_cta}\n"
                f"**Critical Damage Type**: {crit_type_desc(self.settings.crit_type)}"
                f"{nlp_enabled_description}"
            ),
            inline=False,
        )

        return {"embed": embed}


_LEGACY_PREFERENCE_SELECT_OPTIONS = [
    disnake.SelectOption(label="No", value=str(LegacyPreference.LATEST.value)),
    disnake.SelectOption(label="Yes", value=str(LegacyPreference.LEGACY.value)),
    disnake.SelectOption(label="Always Ask", value=str(LegacyPreference.ASK.value)),
]


class _LookupSettingsUI(ServerSettingsMenuBase):
    select_dm_roles: disnake.ui.Select  # make the type checker happy

    # ==== ui ====
    @disnake.ui.select(placeholder="Select DM Roles", min_values=0)
    async def select_dm_roles(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        if len(select.values) == 1 and select.values[0] == TOO_MANY_ROLES_SENTINEL:
            role_ids = await self._text_select_dm_roles(interaction)
        else:
            role_ids = list(map(int, select.values))
        self.settings.dm_roles = role_ids or None
        self._refresh_dm_role_select()
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Toggle Monsters Require DM", style=disnake.ButtonStyle.primary, row=1)
    async def toggle_dm_required(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_dm_required = not self.settings.lookup_dm_required
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Toggle Direct Message DMs", style=disnake.ButtonStyle.primary, row=1)
    async def toggle_pm_dm(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_dm = not self.settings.lookup_pm_dm
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Toggle Direct Message Results", style=disnake.ButtonStyle.primary, row=1)
    async def toggle_pm_result(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.lookup_pm_result = not self.settings.lookup_pm_result
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.select(placeholder="Select Legacy Preference", options=_LEGACY_PREFERENCE_SELECT_OPTIONS, row=2)
    async def legacy_preference_select(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        self.settings.legacy_preference = int(select.values[0])
        await self.commit_settings()
        await self.refresh_content(interaction)

    # Switch between 2014 and 2024 version from guild.py Server Settings
    @disnake.ui.button(label="Switch Version", style=disnake.ButtonStyle.primary)
    async def switch_version(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        if self.settings.version == "2024":
            self.settings.version = "2014"
        else:
            self.settings.version = "2024"
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    # ==== handlers ====
    async def _text_select_dm_roles(self, interaction: disnake.Interaction) -> Optional[List[int]]:
        self.select_dm_roles.disabled = True
        await self.refresh_content(interaction)
        await interaction.send(
            (
                "Choose the DM roles by sending a message to this channel. You can mention the roles, or use a "
                "comma-separated list of role names or IDs. Type `reset` to reset the role list to the default."
            ),
            ephemeral=True,
        )

        try:
            input_msg: disnake.Message = await self.bot.wait_for(
                "message",
                timeout=60,
                check=lambda msg: msg.author == interaction.author and msg.channel.id == interaction.channel_id,
            )
            with suppress(disnake.HTTPException):
                await input_msg.delete()

            if input_msg.content == "reset":
                await interaction.send("The DM roles have been updated.", ephemeral=True)
                return None

            role_ids = {r.id for r in input_msg.role_mentions}
            for stmt in input_msg.content.split(","):
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
                label="Whoa, this server has a lot of roles! Click here to select them.", value=TOO_MANY_ROLES_SENTINEL
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
            description="These settings affect how lookup results are displayed on this server.",
        )
        if not self.settings.dm_roles:
            embed.add_field(
                name="DM Roles",
                value=(
                    f"**Dungeon Master, DM, Game Master, or GM**\n"
                    f"*Any user with a role named one of these will be considered a DM. This lets them look up a "
                    f"monster's full stat block if `Monsters Require DM` is enabled, skip other players' turns in "
                    f"initiative, and more.*"
                ),
                inline=False,
            )
        else:
            dm_roles = natural_join([f"<@&{role_id}>" for role_id in self.settings.dm_roles], "or")
            embed.add_field(
                name="DM Roles",
                value=(
                    f"**{dm_roles}**\n"
                    "*Any user with at least one of these roles will be considered a DM. This lets them look up a "
                    "monster's full stat block if `Monsters Require DM` is enabled, skip turns in initiative, and "
                    "more.*"
                ),
                inline=False,
            )
        embed.add_field(
            name="Monsters Require DM",
            value=(
                f"**{self.settings.lookup_dm_required}**\n"
                "*If this is enabled, monster lookups will display hidden stats for any user without "
                "a role named DM, GM, Dungeon Master, Game Master, or the DM role configured above.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Direct Message DMs",
            value=(
                f"**{self.settings.lookup_pm_dm}**\n"
                "*If this is enabled, the result of monster lookups will be direct messaged to the user who looked "
                "it up, rather than being printed to the channel, if the user is a DM.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Direct Message Results",
            value=(
                f"**{self.settings.lookup_pm_result}**\n"
                "*If this is enabled, the result of all lookups will be direct messaged to the user who looked "
                "it up, rather than being printed to the channel.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Prefer Legacy Content",
            value=(
                f"**{legacy_preference_desc(self.settings.legacy_preference)}**\n"
                "*If the only two options found in a content search are a legacy and non-legacy version of the same "
                "thing, whether to prefer the latest version, the legacy version, or always ask the user to select "
                "between the two.*"
            ),
        )
        embed.add_field(
            name="D&D 5e Version",
            value=(
                f"**{self.settings.version}**\n" "*Toggle the version of D&D 5e rules you want to use in this server.*"
            ),
            inline=False,
        )
        return {"embed": embed}


class _InlineRollingSettingsUI(ServerSettingsMenuBase):
    @disnake.ui.button(label="Disable", style=disnake.ButtonStyle.primary)
    async def disable(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.DISABLED
        button.disabled = True
        self.react.disabled = False
        self.enable.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="React", style=disnake.ButtonStyle.primary)
    async def react(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.REACTION
        button.disabled = True
        self.disable.disabled = False
        self.enable.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Enable", style=disnake.ButtonStyle.primary)
    async def enable(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.inline_enabled = InlineRollingType.ENABLED
        button.disabled = True
        self.disable.disabled = False
        self.react.disabled = False
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.grey, row=1)
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
            description=await self.get_inline_rolling_desc(),
        )
        return {"embed": embed}


_CRIT_TYPE_OPTIONS = [
    disnake.SelectOption(label="Add Max Dice Value", value=str(CritDamageType.MAX_ADD.value)),
    disnake.SelectOption(label="Double Dice Number (Default)", value=str(CritDamageType.NORMAL.value)),
    disnake.SelectOption(label="Double Dice Total", value=str(CritDamageType.DOUBLE_DICE.value)),
    disnake.SelectOption(label="Double Total", value=str(CritDamageType.DOUBLE_ALL.value)),
]


class _MiscellaneousSettingsUI(ServerSettingsMenuBase):
    # ==== ui ====
    @disnake.ui.button(label="Toggle DDB Campaign Message", style=disnake.ButtonStyle.primary, row=1)
    async def toggle_campaign_cta(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.show_campaign_cta = not self.settings.show_campaign_cta
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.select(placeholder="Crit Damage Type", options=_CRIT_TYPE_OPTIONS)
    async def crit_type_select(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        value = select.values[0]
        self.settings.crit_type = int(value)
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Toggle NLP Opt In", style=disnake.ButtonStyle.primary, row=1)
    async def toggle_upenn_nlp_opt_in(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.upenn_nlp_opt_in = not self.settings.upenn_nlp_opt_in
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    # ==== content ====
    async def _before_send(self):
        if TYPE_CHECKING:
            self.toggle_upenn_nlp_opt_in: disnake.ui.Button

        # nlp feature flag
        flag_enabled = await self.bot.ldclient.variation_for_discord_user(
            "cog.initiative.upenn_nlp.enabled", user=self.owner, default=False
        )
        if not flag_enabled:
            self.remove_item(self.toggle_upenn_nlp_opt_in)

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Miscellaneous Settings",
            colour=disnake.Colour.blurple(),
        )
        embed.add_field(
            name="Show DDB Campaign Message",
            value=(
                f"**{self.settings.show_campaign_cta}**\n"
                "*If this is enabled, you will receive occasional reminders to link your D&D Beyond campaign when "
                "you import a character in an unlinked campaign.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Crit Damage Type",
            value=(
                f"**{crit_type_desc(self.settings.crit_type)}**\n"
                "_This affects how critical damage is treated on the server._\n"
                " ● Add Max Dice Value\n"
                "> _This type adds the maximum value of each die to the total._\n> `2d8 + 4` -> `2d8 + 16 + 4`\n"
                " ● Double Dice Amount (Default)\n"
                "> _This type doubles the amount of dice rolled._\n> `2d8 + 4` -> `4d8 + 4`\n"
                " ● Double Dice Total\n"
                "> _This type doubles the total value of the dice rolled._\n> `2d8 + 4` -> `(2d8) * 2 + 4`\n"
                " ● Double Total\n"
                "> _This type doubles the total, including modifiers._\n> `2d8 + 4` -> `(2d8 + 4) * 2`"
            ),
            inline=False,
        )

        nlp_feature_flag = await self.bot.ldclient.variation_for_discord_user(
            "cog.initiative.upenn_nlp.enabled", user=self.owner, default=False
        )
        if nlp_feature_flag:
            embed.add_field(
                name="Contribute Message Data to Natural Language AI Training",
                value=(
                    f"**{self.settings.upenn_nlp_opt_in}**\n*If this is enabled, the contents of messages, displayed"
                    " nicknames, character names, and snapshots of a character's sheet will be recorded in channels"
                    " **with an active combat.***\n*This data will be used in a project to make advances in"
                    " interactive fiction and text generation using artificial intelligence at the University of"
                    " Pennsylvania.*\n*Read more about the project"
                    " [here](https://www.cis.upenn.edu/~ccb/language-to-avrae.html), and our data handling and Privacy"
                    " Policy [here](https://company.wizards.com/en/legal/wizards-coasts-privacy-policy).*"
                ),
                inline=False,
            )

        return {"embed": embed}


class _RollStatsSettingsUI(ServerSettingsMenuBase):
    # ==== ui ====
    @disnake.ui.button(label="Set Dice", style=disnake.ButtonStyle.primary)
    async def select_dice(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_dice = await self.prompt_message(
                interaction,
                (
                    "Choose a new dice string to roll by sending a message in this channel. If you wish to "
                    "use the default dice (4d6kh3), respond with 'default'."
                ),
            )
            if randchar_dice is None:
                await interaction.send(f"No valid dice found. Press `{button.label}` to try again.", ephemeral=True)
                return
            if randchar_dice.lower() == "default":
                randchar_dice = "4d6kh3"
            try:
                d20.parse(randchar_dice)
            except d20.errors.RollSyntaxError:
                await interaction.send(f"Invalid dice string. Press `{button.label}` to try again.", ephemeral=True)
                return

            self.settings.randchar_dice = randchar_dice
            await self.commit_settings()
            await interaction.send("Your dice have been updated.", ephemeral=True)

    @disnake.ui.button(label="Set Number of Sets", style=disnake.ButtonStyle.primary)
    async def select_sets(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_sets = await self.prompt_message(
                interaction, "Choose a new number of sets to roll by sending a message in this channel."
            )
            if randchar_sets is None:
                await interaction.send(
                    f"No valid number of sets found. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            if not (randchar_sets.isdigit() and 1 <= int(randchar_sets) <= 25):
                await interaction.send(
                    f"Number of sets not between 1 and 25. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            self.settings.randchar_sets = int(randchar_sets)
            await self.commit_settings()
            await interaction.send("Your number of sets have been updated.", ephemeral=True)

    @disnake.ui.button(label="Set Number of Stats", style=disnake.ButtonStyle.primary)
    async def select_stats(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_stats = await self.prompt_message(
                interaction, "Choose a new number of stats to roll by sending a message in this channel."
            )
            if randchar_stats is None:
                await interaction.send(
                    f"No valid number of stats found. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            if not (randchar_stats.isdigit() and 1 <= int(randchar_stats) <= 10):
                await interaction.send(
                    f"Number of stats not between 1 and 10. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            self.settings.randchar_num = int(randchar_stats)
            if self.settings.randchar_num != len(self.settings.randchar_stat_names) and self.settings.randchar_straight:
                self.settings.randchar_straight = False
                await interaction.send(
                    "Disabled `Assign Stats` due to the number of stat names not matching the number of stats.",
                    ephemeral=True,
                )
            await self.commit_settings()
            await interaction.send("Your number of stats have been updated.", ephemeral=True)

    @disnake.ui.button(label="Toggle Assign Stats", style=disnake.ButtonStyle.primary)
    async def toggle_straight(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        self.settings.randchar_straight = not self.settings.randchar_straight
        if self.settings.randchar_straight:
            async with self.disable_component(interaction, button):
                randchar_stat_names = await self.prompt_message(
                    interaction,
                    (
                        "Choose the stat names to automatically assign the rolled stats to, separated by commas.\nIf"
                        " you wish to use the default stats, respond with 'default'. This will only work if your number"
                        " of stats is 6."
                    ),
                )
                if randchar_stat_names is None:
                    await interaction.send(
                        f"No valid stat names found. Press `{button.label}` to try again.", ephemeral=True
                    )
                    self.settings.randchar_straight = False
                    await self.commit_settings()
                    await self.refresh_content(interaction)
                    return
                if randchar_stat_names.lower() == "default":
                    stat_names = [stat.upper() for stat in STAT_ABBREVIATIONS]
                else:
                    stat_names = randchar_stat_names.replace(", ", ",").split(",")
                if len(stat_names) != self.settings.randchar_num:
                    await interaction.send(
                        (
                            f"Number of stat names does not match the number of stats. Press `{button.label}` to try"
                            " again."
                        ),
                        ephemeral=True,
                    )
                    self.settings.randchar_straight = False
                    await self.commit_settings()
                    await self.refresh_content(interaction)
                    return
                self.settings.randchar_stat_names = stat_names
                await self.commit_settings()
                await interaction.send("Your stat names have been updated.", ephemeral=True)
        else:
            await self.commit_settings()
            await self.refresh_content(interaction)

    @disnake.ui.button(label="Set Minimum", style=disnake.ButtonStyle.primary, row=1)
    async def select_minimum(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_min = await self.prompt_message(
                interaction,
                (
                    "Choose a new minimum roll total by sending a message in this channel. "
                    "To reset it, respond with 'reset'."
                ),
            )
            if randchar_min is None:
                await interaction.send(f"No valid minimum found. Press `{button.label}` to try again.", ephemeral=True)
                return
            if randchar_min.lower() == "reset":
                self.settings.randchar_min = None
            elif not randchar_min.isdigit():
                await interaction.send(f"No valid minimum found. Press `{button.label}` to try again.", ephemeral=True)
                return
            else:
                self.settings.randchar_min = int(randchar_min)
            await self.commit_settings()
            await interaction.send("Your minimum score has been updated.", ephemeral=True)

    @disnake.ui.button(label="Set Maximum", style=disnake.ButtonStyle.primary, row=1)
    async def select_maximum(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_max = await self.prompt_message(
                interaction,
                (
                    "Choose a new maximum roll total by sending a message in this channel. "
                    "To reset it, respond with 'reset'."
                ),
            )
            if randchar_max is None:
                await interaction.send(f"No valid maximum found. Press `{button.label}` to try again.", ephemeral=True)
                return
            if randchar_max.lower() == "reset":
                self.settings.randchar_max = None
            elif not randchar_max.isdigit():
                await interaction.send(f"No valid maximum found. Press `{button.label}` to try again.", ephemeral=True)
                return
            else:
                self.settings.randchar_max = int(randchar_max)
            await self.commit_settings()
            await interaction.send("Your maximum score has been updated.", ephemeral=True)

    @disnake.ui.button(label="Add Over/Under Rule", style=disnake.ButtonStyle.primary, row=1)
    async def add_rule(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        async with self.disable_component(interaction, button):
            randchar_rule = await self.prompt_message(
                interaction,
                (
                    'Add a new score rule by sending a message in this channel.\nPlease use the format "number>score"'
                    ' or "number<score", for example "1>15" for at least one over 15, or "2<10" for at least two'
                    " under 10."
                ),
            )
            if randchar_rule is None:
                await interaction.send(
                    f"No valid over/under found. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            rule_match = re.fullmatch(r"(\d+)(>|<)(\d+)", randchar_rule)
            if rule_match is None:
                await interaction.send(
                    f"No valid over/under rule found. Press `{button.label}` to try again.", ephemeral=True
                )
                return
            match rule_match.groups():
                case [amount, "<", value]:
                    new_rule = RandcharRule(type="lt", amount=amount, value=value)
                case [amount, ">", value]:
                    new_rule = RandcharRule(type="gt", amount=amount, value=value)
            self.settings.randchar_rules.append(new_rule)
            self._refresh_remove_rule_select()
            await self.commit_settings()
            await interaction.send("Your required over/under rules has been updated.", ephemeral=True)
        # Disable button if we have >= 25 rules, so we don't overfill the select
        if len(self.settings.randchar_rules) >= 25:
            button.disabled = True
            await self.refresh_content(interaction)

    @disnake.ui.select(placeholder="Remove Rule", min_values=0, max_values=1, row=3)
    async def remove_rule(self, select: disnake.ui.Select, interaction: disnake.Interaction):
        removed_rule = int(select.values[0])
        self.settings.randchar_rules.pop(removed_rule)
        self._refresh_remove_rule_select()
        await self.commit_settings()
        await self.refresh_content(interaction)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.grey, row=4)
    async def back(self, _: disnake.ui.Button, interaction: disnake.Interaction):
        await self.defer_to(ServerSettingsUI, interaction)

    # ==== content ====
    def _refresh_remove_rule_select(self):
        """Update the options in the Remove Rule select to reflect the currently available values."""
        self.remove_rule.options.clear()
        if not self.settings.randchar_rules:
            self.remove_rule.add_option(label="Empty")
            self.remove_rule.disabled = True
            return
        self.remove_rule.disabled = False
        if len(self.settings.randchar_rules) < 25:
            self.add_rule.disabled = False
        else:
            self.add_rule.disabled = True
        for i, rule in enumerate(self.settings.randchar_rules):
            self.remove_rule.add_option(
                label=f"{rule.amount} {'over' if rule.type == 'gt' else 'under'} {rule.value}", value=str(i)
            )

    async def _before_send(self):
        self._refresh_remove_rule_select()

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Server Settings ({self.guild.name}) / Custom Stat Roll Settings",
            colour=disnake.Colour.blurple(),
        )
        embed.add_field(
            name="Dice Rolled",
            value=(
                f"**{self.settings.randchar_dice}**\n"
                "*This is the dice string that will be rolled six times for "
                "each stat set.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Number of Sets",
            value=(
                f"**{self.settings.randchar_sets}**\n"
                "*This is how many sets of stat rolls it will return, "
                "allowing your players to choose between them.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Number of Stats",
            value=(
                f"**{self.settings.randchar_num}**\n"
                "*This is how many stat rolls it will return per set, "
                "allowing your players to choose between them.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Assign Stats Directly",
            value=(
                f"**{self.settings.randchar_straight}**\n"
                f"**Stat Names:** {stat_names_desc(self.settings.randchar_stat_names)}\n"
                "*If this is enabled, stats will automatically be assigned to stats in the order "
                "they are rolled.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Minimum Total Score Required",
            value=(
                f"**{self.settings.randchar_min}**\n"
                "*This is the minimum combined score required. Standard array is 72 total.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Maximum Total Score Required",
            value=(
                f"**{self.settings.randchar_max}**\n"
                "*This is the maximum combined score required. Standard array is 72 total.*"
            ),
            inline=False,
        )
        embed.add_field(
            name="Over/Under Rules",
            value=(
                f"**{get_over_under_desc(self.settings.randchar_rules)}**\n"
                "*This is a list of how many of the stats you require to be over/under a certain value, "
                "such as having at least one stat over 17, or two stats under 10.*"
            ),
            inline=False,
        )

        return {"embed": embed}


def get_over_under_desc(rules) -> str:
    if not rules:
        return "None"
    out = []
    for rule in rules:
        out.append(f"{rule.amount} {'over' if rule.type == 'gt' else 'under'} {rule.value}")
    return f"At least {', '.join(out)}"


def stat_names_desc(stat_names: list) -> str:
    return ", ".join(stat_names or [stat.upper() for stat in STAT_ABBREVIATIONS])


def crit_type_desc(mode: CritDamageType) -> str:
    match mode:
        case CritDamageType.NORMAL:
            return "Double Dice Amount (Default)"
        case CritDamageType.MAX_ADD:
            return "Add Max Dice Value"
        case CritDamageType.DOUBLE_ALL:
            return "Double Total"
    # CritDamageType.DOUBLE_DICE
    return "Double Dice Total"


def legacy_preference_desc(leg_pref: LegacyPreference) -> str:
    match leg_pref:
        case LegacyPreference.LATEST:
            return "No"
        case LegacyPreference.LEGACY:
            return "Yes"
    # LegacyPreference.ASK
    return "Always Ask"
