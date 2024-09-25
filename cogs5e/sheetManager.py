"""
Created on Jan 19, 2017

@author: andrew
"""

import asyncio
import logging
import re
import time
import traceback
from typing import List

import automation_common.validation
import disnake
import pydantic
import yaml
from disnake.ext import commands
from disnake.ext.commands.cooldowns import BucketType

import ui
from aliasing import helpers
from cogs5e.models import embeds
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import ExternalImportError, NoCharacter
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.sheets.beyond import BeyondSheetParser, DDB_URL_RE, DDB_PDF_URL_RE
from cogs5e.sheets.dicecloud import DICECLOUD_URL_RE, DicecloudParser
from cogs5e.sheets.dicecloudv2 import DICECLOUDV2_URL_RE, DicecloudV2Parser
from cogs5e.sheets.gsheet import GoogleSheet, extract_gsheet_id_from_url
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from ddb.gamelog import CampaignLink
from ddb.gamelog.errors import NoCampaignLink
from utils import img
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.enums import ActivationType
from utils.functions import confirm, get_positivity, list_get, search_and_select, try_delete, camel_to_title, chunk_text
from utils.settings.character import CHARACTER_SETTINGS, CSetting

log = logging.getLogger(__name__)
DELETE_AFTER_SECONDS = 20


class SheetManager(commands.Cog):
    """
    Commands to load a character sheet into Avrae, and supporting commands to modify the character, as well as basic macros.
    """  # noqa: E501

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def new_arg_stuff(args, ctx, character, base_args=None):
        args = await helpers.parse_snippets(args, ctx, character=character, base_args=base_args)
        args = argparse(args)
        return args

    @commands.group(
        aliases=["a", "attack"],
        invoke_without_command=True,
        help=f"""
        Performs an action (attack or ability) for the current active character.
        __**Valid Arguments**__
        {VALID_AUTOMATION_ARGS}
        """,
    )
    async def action(self, ctx, atk_name=None, *, args: str = ""):
        if atk_name is None:
            return await self.action_list(ctx)

        char: Character = await ctx.get_character()
        args = await self.new_arg_stuff(args, ctx, char, base_args=[atk_name])
        hide = args.last("h", type_=bool)
        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)

        caster, targets, combat = await targetutils.maybe_combat(ctx, char, args)
        # we select from caster attacks b/c a combat effect could add some
        attack_or_action = await actionutils.select_action(ctx, atk_name, attacks=caster.attacks, actions=char.actions)

        if isinstance(attack_or_action, Attack):
            result = await actionutils.run_attack(ctx, embed, args, caster, attack_or_action, targets, combat)
        else:
            result = await actionutils.run_action(ctx, embed, args, caster, attack_or_action, targets, combat)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if (gamelog := self.bot.get_cog("GameLog")) and result is not None:
            await gamelog.send_automation(ctx, char, attack_or_action.name, result)

    @action.command(name="list")
    async def action_list(self, ctx, *args):
        """
        Lists the active character's actions.
        __Valid Arguments__
        -v - Verbose: Displays each action's character sheet description rather than the effect summary.
        attack - Only displays the available attacks.
        action - Only displays the available actions.
        bonus - Only displays the available bonus actions.
        reaction - Only displays the available reactions.
        legendary - Only displays the available legendary actions.
        mythic - Only displays the available mythic actions.
        lair - Only displays the available lair actions.
        other - Only displays the available actions that have another activation time.
        """
        char: Character = await ctx.get_character()
        caster = await targetutils.maybe_combat_caster(ctx, char)
        embed = embeds.EmbedWithCharacter(char, name=False)
        embed.title = f"{char.name}'s Actions"

        await actionutils.send_action_list(
            ctx, caster=caster, attacks=caster.attacks, actions=char.actions, embed=embed, args=args
        )

    # ---- attack management commands ----
    @action.command(name="add", aliases=["create"])
    async def attack_add(self, ctx, name, *, args=""):
        """
        Adds an attack to the active character.
        __Valid Arguments__
        -d <damage> - How much damage the attack should do.
        -b <to-hit> - The to-hit bonus of the attack.
        -desc <description> - A description of the attack.
        -verb <verb> - The verb to use for this attack. (e.g. "Padellis <verb> a dagger!")
        proper - This attack's name is a proper noun.
        -criton <#> - This attack crits on a number other than a natural 20.
        -phrase <text> - Some flavor text to add to each attack with this attack.
        -thumb <image url> - The attack's image.
        -c <extra crit damage> - How much extra damage (beyond doubling dice) this attack does on a crit.
        -activation <value> - The activation type of the action (e.g. action, bonus, etc).```
        | Action Type  | Value |
        +==============+=======+
        | Action       | 1     |
        | No Action    | 2     |
        | Bonus Action | 3     |
        | Reaction     | 4     |
        | Minute       | 6     |
        | Hour         | 7     |
        | Special      | 8     |
        | Legendary    | 9     |
        | Mythic       | 10    |
        | Lair         | 11    |```
        """
        character: Character = await ctx.get_character()
        parsed = argparse(args)

        activation = parsed.last("activation", type_=int)
        if activation is not None:
            activation = ActivationType(activation)

        attack = Attack.new(
            name,
            bonus_calc=parsed.join("b", "+"),
            damage_calc=parsed.join("d", "+"),
            details=parsed.join("desc", "\n"),
            verb=parsed.last("verb"),
            proper=parsed.last("proper", False, bool),
            criton=parsed.last("criton", type_=int),
            phrase=parsed.join("phrase", "\n"),
            thumb=parsed.last("thumb"),
            extra_crit_damage=parsed.last("c"),
            activation_type=activation,
        )

        conflict = next((a for a in character.overrides.attacks if a.name.lower() == attack.name.lower()), None)
        if conflict:
            if await confirm(ctx, "This will overwrite an attack with the same name. Continue? (Reply with yes/no)"):
                character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, aborting.")
        character.overrides.attacks.append(attack)
        await character.commit(ctx)

        out = f"Created attack {attack.name}!"
        if conflict:
            out += " Removed a duplicate attack."
        await ctx.send(out)

    @action.command(name="import")
    async def attack_import(self, ctx, *, data: str):
        """
        Imports an attack from JSON or YAML exported from the Avrae Dashboard.
        """
        # strip any code blocks
        if data.startswith(("```\n", "```json\n", "```yaml\n", "```yml\n", "```py\n")) and data.endswith("```"):
            data = "\n".join(data.split("\n")[1:]).rstrip("`\n")

        character: Character = await ctx.get_character()

        try:
            attack_json = yaml.safe_load(data)
        except yaml.YAMLError:
            return await ctx.send("This is not a valid attack: invalid data.")

        if not isinstance(attack_json, list):
            attack_json = [attack_json]

        # to validate, we normalize using pydantic and then pass it to AttackList
        try:
            normalized_obj = pydantic.parse_obj_as(
                List[automation_common.validation.models.AttackModel], attack_json, type_name="AttackList"
            )
        except pydantic.ValidationError as e:
            err_fmt = automation_common.validation.utils.format_validation_error(e)
            return await ctx.send(f"This is not a valid attack: ```py\n{err_fmt}\n```")

        attacks = AttackList.from_dict([atk.dict() for atk in normalized_obj])

        conflicts = [a for a in character.overrides.attacks if a.name.lower() in [new.name.lower() for new in attacks]]
        if conflicts:
            if await confirm(
                ctx,
                f"This will overwrite {len(conflicts)} attacks with the same name "
                f"({', '.join(c.name for c in conflicts)}). Continue? (Reply with yes/no)",
            ):
                for conflict in conflicts:
                    character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, cancelling.")

        character.overrides.attacks.extend(attacks)
        await character.commit(ctx)

        out = f"Imported {len(attacks)} attacks:\n{attacks.build_str(character)}"
        await ctx.send(out)

    @action.command(name="delete", aliases=["remove"])
    async def attack_delete(self, ctx, name):
        """
        Deletes an attack override.
        """
        character: Character = await ctx.get_character()
        attack = await search_and_select(ctx, character.overrides.attacks, name, lambda a: a.name)
        if not (await confirm(ctx, f"Are you sure you want to delete {attack.name}? (Reply with yes/no)")):
            return await ctx.send("Okay, cancelling delete.")
        character.overrides.attacks.remove(attack)
        await character.commit(ctx)
        await ctx.send(f"Okay, deleted attack {attack.name}.")

    @commands.group(
        aliases=["s"],
        invoke_without_command=True,
        help=f"""
        Rolls a save for your current active character.
        {VALID_SAVE_ARGS}
        """,
    )
    async def save(self, ctx, skill, *, args=""):
        char: Character = await ctx.get_character()

        args = await self.new_arg_stuff(args, ctx, char, base_args=[skill])

        hide = args.last("h", type_=bool)

        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)

        checkutils.update_csetting_args(char, args)
        caster = await targetutils.maybe_combat_caster(ctx, char)

        result = checkutils.run_save(skill, caster, args, embed)

        # send
        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if gamelog := self.bot.get_cog("GameLog"):
            await gamelog.send_save(ctx, char, result.skill_name, result.rolls)

    @save.command(name="death", help="Equivalent to `!game deathsave`")
    async def save_death(self, ctx, *, args=""):
        base_cmd = "game deathsave"
        if args and (sub_cmd := args.split()[0].lower()) in ("fail", "success", "reset"):
            base_cmd += f" {sub_cmd}"
        ds_cmd = self.bot.get_command(base_cmd)
        if ds_cmd is None:
            return await ctx.send("Error: GameTrack cog not loaded.")

        if base_cmd == "game deathsave":
            return await ctx.invoke(ds_cmd, args=args)
        else:
            return await ctx.invoke(ds_cmd)

    @commands.command(
        aliases=["c"],
        help=f"""
        Rolls a check for your current active character.
        {VALID_CHECK_ARGS}
        """,
    )
    async def check(self, ctx, check, *, args=""):
        char: Character = await ctx.get_character()
        skill_key = await search_and_select(ctx, SKILL_NAMES, check, camel_to_title)
        args = await self.new_arg_stuff(args, ctx, char, base_args=[check])

        hide = args.last("h", type_=bool)

        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)
        skill = char.skills[skill_key]

        checkutils.update_csetting_args(char, args, skill)
        caster = await targetutils.maybe_combat_caster(ctx, char)

        result = checkutils.run_check(skill_key, caster, args, embed)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if gamelog := self.bot.get_cog("GameLog"):
            await gamelog.send_check(ctx, char, result.skill_name, result.rolls)

    @commands.group(invoke_without_command=True)
    async def desc(self, ctx):
        """Prints or edits a description of your currently active character."""
        char: Character = await ctx.get_character()

        desc = char.description
        if not desc:
            desc = "No description available."

        if len(desc) > 2048:
            desc = desc[:2044] + "..."
        elif len(desc) < 2:
            desc = "No description available."

        embed = embeds.EmbedWithCharacter(char, name=False)
        embed.title = char.name
        embed.description = desc

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @desc.command(name="update", aliases=["edit"])
    async def edit_desc(self, ctx, *, desc):
        """Updates the character description."""
        char: Character = await ctx.get_character()
        char.overrides.desc = desc
        await char.commit(ctx)
        await ctx.send("Description updated!")

    @desc.command(name="remove", aliases=["delete"])
    async def remove_desc(self, ctx):
        """Removes the character description, returning to the default."""
        char: Character = await ctx.get_character()
        char.overrides.desc = None
        await char.commit(ctx)
        await ctx.send("Description override removed!")

    @commands.group(invoke_without_command=True)
    async def portrait(self, ctx):
        """Shows or edits the image of your currently active character."""
        char: Character = await ctx.get_character()

        if not char.image:
            return await ctx.send("No image available.")

        embed = disnake.Embed()
        embed.title = char.name
        embed.colour = char.get_color()
        embed.set_image(url=char.image)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @portrait.command(name="update", aliases=["edit"])
    async def edit_portrait(self, ctx, *, url):
        """Updates the character portrait."""
        char: Character = await ctx.get_character()
        char.overrides.image = url
        await char.commit(ctx)
        await ctx.send("Portrait updated!")

    @portrait.command(name="remove", aliases=["delete"])
    async def remove_portrait(self, ctx):
        """Removes the character portrait, returning to the default."""
        char: Character = await ctx.get_character()
        char.overrides.image = None
        await char.commit(ctx)
        await ctx.send("Portrait override removed!")

    @commands.command(hidden=True)  # hidden, as just called by token command
    async def playertoken(self, ctx, *, args=""):
        """
        Generates and sends a token for use on VTTs.
        __Valid Arguments__
        -border <gold|plain|none> - Chooses the token border.
        """

        char: Character = await ctx.get_character()
        if not char.image:
            return await ctx.send("This character has no image.")

        token_args = argparse(args)
        ddb_user = await self.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        is_subscriber = ddb_user and ddb_user.is_subscriber

        try:
            processed = await img.generate_token(char.image, is_subscriber, token_args)
        except Exception as e:
            return await ctx.send(f"Error generating token: {e}")

        file = disnake.File(processed, filename="image.png")
        embed = embeds.EmbedWithCharacter(char, image=False)
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
        processed.close()

    @commands.command()
    async def sheet(self, ctx):
        """Prints the embed sheet of your currently active character."""
        char: Character = await ctx.get_character()

        await ctx.send(embed=char.get_sheet_embed())
        await try_delete(ctx.message)

    @commands.group(aliases=["char"], invoke_without_command=True)
    async def character(self, ctx, *, name: str = None):
        """View or change your current active character.
        Displays the current active character and any assigned channel, server or global character.

        __Optional Arguments__
        `name` - The name of the character you want to use. Example: `!character Froedrick Frankenstien`
        """
        if name is None:
            embed = await self._active_character_embed(ctx)
            await ctx.send(embed=embed)
            return

        char = await self.get_character_by_name(ctx, name)
        result = await char.set_active(ctx)
        await try_delete(ctx.message)
        embed = await self._active_character_embed(
            ctx,
            result.message,
        )
        await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)

    async def get_character_by_name(self, ctx, name):
        user_characters = await self.bot.mdb.characters.find({"owner": str(ctx.author.id)}).to_list(None)
        if not user_characters:
            return await ctx.send("You have no characters.")

        selected_char = await search_and_select(
            ctx, user_characters, name, lambda e: e["name"], selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)"
        )

        return Character.deserialize_character_from_dict(str(ctx.author.id), selected_char)

    @character.group(name="server", invoke_without_command=True)
    @commands.guild_only()
    async def character_server(self, ctx, *, name: str = None):
        """
        Sets the passed in character name as the server character.

        All commands in the server that use your active character will instead use the server character, even if the active character is changed elsewhere.

        __Required Arguments__
        `name` - The name of the character you want to set as your server character.
            e.g. `!character server "Character Name"`
        """  # noqa: E501
        new_character_to_set = None
        server_character = None

        if name is None:
            await ctx.send(
                "Please pass in the name of a character to switch to for the server command. e.g. `!char server"
                " Merlin`",
                delete_after=DELETE_AFTER_SECONDS,
            )
            return
        else:
            new_character_to_set = await self.get_character_by_name(ctx, name)

        try:
            server_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=True, use_channel=False
            )
        except:
            pass

        msg = ""
        if (
            server_character is not None
            and new_character_to_set.upstream == server_character.upstream
            and server_character.is_active_server(ctx)
        ):
            message = (
                f"'{server_character.name}' is already the server character. "
                f"Use the `!char server reset` command if you want to no longer "
                f"use a server character here."
            )
            embed = await self._active_character_embed(ctx, message)
            await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
            return

        set_result = await new_character_to_set.set_server_active(ctx, server_character)
        embed = await self._active_character_embed(ctx, set_result.message)
        await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
        await try_delete(ctx.message)

    @character_server.command(name="reset", aliases=["unset"])
    @commands.guild_only()
    async def character_server_reset(self, ctx):
        """
        This will reset the current server character and leave you with no currently set server character.
        """  # noqa: E501
        server_character: Character = await Character.from_ctx(ctx, use_global=False, use_guild=True, use_channel=False)
        await server_character.unset_server_active(ctx)
        msg = f"Reset previous server character '{server_character.name}'"
        embed = await self._active_character_embed(ctx, msg)
        await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
        return

    @character.group(name="channel", invoke_without_command=True)
    @commands.guild_only()
    async def character_channel(self, ctx, *, name: str = None):
        """
        Sets the passed in character name as the channel character.

        All commands in the channel that use your active character will instead use the new channel character, even if the active character is changed elsewhere.

        __Required Arguments__
        `name` - The name of the character you want to set as your channel character.
            e.g. `!character channel "Character Name"`
        """  # noqa: E501

        channel_character = None
        new_character_to_set = None
        if name is None:
            await ctx.send(
                "Please pass in the name of a character to switch to for the channel command. e.g. `!char channel"
                " Merlin`",
                delete_after=DELETE_AFTER_SECONDS,
            )
            return
        else:
            new_character_to_set = await self.get_character_by_name(ctx, name)

        try:
            channel_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=False, use_channel=True
            )
        except NoCharacter:
            pass

        msg = ""
        if (
            channel_character is not None
            and new_character_to_set is not None
            and new_character_to_set.upstream == channel_character.upstream
            and channel_character.is_active_channel(ctx)
        ):
            message = (
                f"'{channel_character.name}' is already the channel character. "
                f"Use the `!char channel reset` command if you want to no "
                f"longer use a channel character here."
            )
            embed = await self._active_character_embed(ctx, message)
            await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
            return

        set_result = await new_character_to_set.set_channel_active(ctx, channel_character)
        embed = await self._active_character_embed(ctx, set_result.message)
        await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
        await try_delete(ctx.message)

    @character_channel.command(name="reset", aliases=["unset"])
    @commands.guild_only()
    async def character_channel_reset(self, ctx):
        """
        This will reset the current channel character and leave you with no currently set channel character.
        """  # noqa: E501
        channel_character: Character = await Character.from_ctx(
            ctx, use_global=False, use_guild=False, use_channel=True
        )
        await channel_character.unset_channel_active(ctx)
        msg = f"Reset previous channel character '{channel_character.name}'"
        embed = await self._active_character_embed(ctx, msg)
        await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
        return

    @character.command(name="resetall")
    @commands.guild_only()
    async def reset_all(self, ctx):
        """
        This will unset any channel and server-specific characters that have been set and force the current global character to be used everywhere on this server.
        """  # noqa: E501

        list_of_unset_characters = []
        # get all channels in server
        for channel in ctx.guild.channels:
            channel_id = channel.id
            try:
                channel_character: Character = await Character.from_bot_and_channel_id(ctx, ctx.author.id, channel_id)
                unset_result = await channel_character.unset_active_channel_helper(ctx, channel_id)
                if unset_result.did_unset_active_location:
                    list_of_unset_characters.append(f"{channel_character.name} for channel '{channel.name}'")
            except NoCharacter:
                continue

        server_character = None
        try:
            server_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=True, use_channel=False
            )
        except NoCharacter:
            pass
        if server_character:
            unset_server_result = await server_character.unset_server_active(ctx)
            if unset_server_result.did_unset_active_location:
                list_of_unset_characters.append(f"{server_character.name} for server '{ctx.guild.name}'")
        if len(list_of_unset_characters) > 0:
            full_list_message = "\n".join(list_of_unset_characters)
            embed = await self._active_character_embed(
                ctx, f"Unset the following character mappings:\n\n{full_list_message}"
            )
            await ctx.send(embed=embed, delete_after=DELETE_AFTER_SECONDS)
        else:
            await ctx.send("No characters were set on any channels or servers")
        await try_delete(ctx.message)

    @character.command(name="list")
    async def character_list(self, ctx):
        """
        Lists the characters owned by the user.

        This command retrieves all the characters owned by the user from the database, and sends an embed containing
        the names of these characters. If the user has an active character, it is highlighted in the embed.

        Args:
            ctx (Context): The context in which the command was called.

        Returns:
            None
        """
        user_characters = await self.bot.mdb.characters.find(
            {"owner": str(ctx.author.id)}, ["name", "upstream"]
        ).to_list(None)
        if not user_characters:
            return await ctx.send("You have no characters.")
        user_characters = {c["upstream"]: c["name"] for c in user_characters}

        try:
            char = await Character.from_ctx(ctx, use_global=True, use_guild=True, use_channel=True)
            char_out = f"**Active Character**: {char.name}\n\n"
            user_characters.pop(char.upstream)
        except NoCharacter:
            char_out = ""

        character_names = sorted(user_characters.values())
        character_chunks = chunk_text(
            ", ".join(character_names),
            max_chunk_size=4096 - len(char_out),
            chunk_on=(", ",),
        )
        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour
        embed_queue[-1].title = "Your characters"
        embed_queue[-1].description = char_out + character_chunks[0]

        for chunk in character_chunks[1:]:
            embed_queue.append(disnake.Embed(colour=color, description=chunk))

        for embed in embed_queue:
            await ctx.send(embed=embed)

    @character.command(name="delete")
    async def character_delete(self, ctx, *, name):
        """
        Deletes a character.

        This command deletes a character from the user's character list. The user is asked to confirm the deletion before
        the character is deleted. If the user has no characters, a message is sent to the user and the command ends.

        Args:
            ctx (Context): The context in which the command was called.
            name (str): The name of the character to delete.

        Returns:
            None
        """
        user_characters = await self.bot.mdb.characters.find(
            {"owner": str(ctx.author.id)}, ["name", "upstream"]
        ).to_list(None)
        if not user_characters:
            return await ctx.send("You have no characters.")

        selected_char = await search_and_select(
            ctx, user_characters, name, lambda e: e["name"], selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)"
        )

        if await confirm(ctx, f"Are you sure you want to delete {selected_char['name']}? (Reply with yes/no)"):
            await Character.delete(ctx, str(ctx.author.id), selected_char["upstream"])
            return await ctx.send(f"{selected_char['name']} has been deleted.")
        else:
            return await ctx.send("Ok, cancelling.")

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def update(self, ctx, *, args=""):
        """
        Updates the current character sheet, preserving all settings.
        __Valid Arguments__
        `-v` - Shows character sheet after update is complete.
        `-nocc` - Do not automatically create or update custom counters for class resources and features.
        `-noprep` - Import all known spells as prepared.
        """
        old_character: Character = await ctx.get_character()
        url = old_character.upstream
        args = argparse(args)

        prefixes = "dicecloud-", "google-", "beyond-", "dicecloudv2-"
        _id = url[:]
        for p in prefixes:
            if url.startswith(p):
                _id = url[len(p) :]
                break
        sheet_type = old_character.sheet_type
        if sheet_type == "dicecloud":
            parser = DicecloudParser(_id)
            loading = await ctx.send("Updating character data from Dicecloud...")
        elif sheet_type == "dicecloudv2":
            parser = DicecloudV2Parser(_id)
            loading = await ctx.send("Updating character data from Dicecloud V2...")
        elif sheet_type == "google":
            parser = GoogleSheet(_id)
            loading = await ctx.send("Updating character data from Google...")
        elif sheet_type == "beyond":
            parser = BeyondSheetParser(_id)
            loading = await ctx.send("Updating character data from Beyond...")
        else:
            return await ctx.send(f"Error: Unknown sheet type {sheet_type}.")

        try:
            character = await parser.load_character(ctx, args)
        except ExternalImportError as eep:
            return await loading.edit(content=f"Error loading character: {eep}")
        except Exception as eep:
            log.warning(f"Error importing character {old_character.upstream}")
            log.warning(traceback.format_exc())
            return await loading.edit(content=f"Error loading character: {eep}")

        character.update(old_character)

        # keeps an old check if the old character was active on the current server
        was_server_active = old_character.is_active_server(ctx)
        was_channel_active = old_character.is_active_channel(ctx)

        await character.commit(ctx)

        # overwrites the old_character's server active state
        # since character._active_guilds is old_character._active_guilds here
        if old_character.is_active_global():
            await character.set_active(ctx)
        if was_server_active:
            await character.set_server_active(ctx, old_character)
        if was_channel_active:
            await character.set_channel_active(ctx, old_character)

        await loading.edit(content=f"Updated and saved data for {character.name}!")
        if args.last("v"):
            await ctx.send(embed=character.get_sheet_embed())
        if sheet_type == "beyond":
            await send_ddb_ctas(ctx, character)

    @commands.command()
    async def transferchar(self, ctx, user: disnake.Member):
        """Gives a copy of the active character to another user."""
        character: Character = await ctx.get_character()
        overwrite = ""

        conflict = await self.bot.mdb.characters.find_one({"owner": str(user.id), "upstream": character.upstream})
        if conflict:
            overwrite = "**WARNING**: This will overwrite an existing character."

        await ctx.send(
            f"{user.mention}, accept a copy of {character.name}? (Type yes/no)\n{overwrite}",
            allowed_mentions=disnake.AllowedMentions(users=[ctx.author]),
        )
        try:
            m = await self.bot.wait_for(
                "message",
                timeout=300,
                check=lambda msg: (
                    msg.author == user and msg.channel == ctx.channel and get_positivity(msg.content) is not None
                ),
            )
        except asyncio.TimeoutError:
            m = None

        if m is None or not get_positivity(m.content):
            return await ctx.send("Transfer not confirmed, aborting.")

        character.owner = str(user.id)
        await character.commit(ctx)
        await ctx.send(f"Copied {character.name} to {user.display_name}'s storage.")

    @commands.command()
    async def csettings(self, ctx, *args):
        """
        Opens the Character Settings menu.

        In this menu, you can change your character's cosmetic and gameplay settings, such as their embed color,
        crit range, extra crit dice, and more.
        """
        char = await ctx.get_character()

        if not args:
            settings_ui = ui.CharacterSettingsUI.new(ctx.bot, owner=ctx.author, character=char)
            await settings_ui.send_to(ctx)
            return

        # old deprecated CLI behaviour
        out = []
        skip = False
        for i, arg in enumerate(args):
            if skip:
                continue
            if arg in CHARACTER_SETTINGS:
                skip = True
                out.append(CHARACTER_SETTINGS[arg].run(ctx, char, list_get(i + 1, None, args)))

        if not out:
            return await ctx.send(
                f"No valid settings found. Try `{ctx.prefix}csettings` with no arguments to use an interactive menu!"
            )

        await char.options.commit(ctx.bot.mdb, char)
        await ctx.send("\n".join(out))

    async def _confirm_overwrite(self, ctx, _id):
        """Prompts the user if command would overwrite another character.
        Returns True to overwrite, False or None otherwise."""
        conflict = await self.bot.mdb.characters.find_one({"owner": str(ctx.author.id), "upstream": _id})
        if conflict:
            return await confirm(
                ctx,
                "Warning: This will overwrite a character with the same ID. Do you wish to continue "
                "(Reply with yes/no)?\n"
                f"If you only wanted to update your character, run `{ctx.prefix}update` instead.",
            )
        return True

    @commands.command(name="import")
    @commands.max_concurrency(1, BucketType.user)
    async def import_sheet(self, ctx, url: str, version: str = None, *, args=""):
        """
        Loads a character sheet from one of the accepted sites:
            [D&D Beyond](https://www.dndbeyond.com/)
            [Dicecloud v1](https://v1.dicecloud.com/)
            [Dicecloud v2](https://dicecloud.com/)
            [GSheet v2.1](https://gsheet2.avrae.io) (auto)
            [GSheet v1.4](https://gsheet.avrae.io) (manual)

        __Valid Arguments__
        `-nocc` - Do not automatically create custom counters for class resources and features.
        `-noprep` - Import all known spells as prepared.

        __Valid Versions__
        `2014` - 2014 D&D 5e Ruleset.
        `2024` - 2024 D&D 5e Ruleset.

        __Sheet-specific Notes__
        D&D Beyond:
            Private sheets can be imported if you have linked your DDB and Discord accounts.  Otherwise, the sheet needs to be publicly shared.

        Dicecloud v1:
            Share your character with `avrae` on Dicecloud v1 to import private sheets, and give edit permissions for live updates.

        Dicecloud v2:
            Share your character with `avrae` on Dicecloud v2 to import private sheets. Tag actions, spells, and features with `avrae:no_import` if you don't want them to be imported, and actions with `avrae:parse_only` if you don't want them to be loaded from Beyond.

        Gsheet:
            The sheet must be shared with directly with Avrae or be publicly viewable to anyone with the link.
            Avrae's google account is `avrae-320@avrae-bot.iam.gserviceaccount.com`.


        """  # noqa: E501
        if version is None:
            serverSettings = await ctx.get_server_settings()
            version = serverSettings.version
        url = await self._check_url(ctx, url)  # check for < >
        # Sheets in order: DDB, Dicecloud, Gsheet
        if beyond_match := DDB_URL_RE.match(url):
            loading = await ctx.send("Loading character data from Beyond...")
            prefix = "beyond"
            url = beyond_match.group(1)
            parser = BeyondSheetParser(url)
        elif beyond_pdf_match := DDB_PDF_URL_RE.match(url):
            await ctx.send(
                "Warning: This URL is for a PDF, and not for the actual character sheet. "
                "Next time, please use the sharing link instead."
            )
            loading = await ctx.send("Loading character data from Beyond...")
            prefix = "beyond"
            url = beyond_pdf_match.group(1)
            parser = BeyondSheetParser(url)
        elif dicecloud_match := DICECLOUD_URL_RE.match(url):
            loading = await ctx.send("Loading character data from Dicecloud...")
            url = dicecloud_match.group(1)
            prefix = "dicecloud"
            parser = DicecloudParser(url)
        elif dicecloudv2_match := DICECLOUDV2_URL_RE.match(url):
            loading = await ctx.send("Loading character data from Dicecloud V2...")
            url = dicecloudv2_match.group(1)
            prefix = "dicecloudv2"
            parser = DicecloudV2Parser(url)
        else:
            try:
                url = extract_gsheet_id_from_url(url)
            except ExternalImportError:
                if re.match(r"https?://(?:www\.)?bestiarybuilder.com/bestiary-viewer/([0-9a-f]+)", url) or re.match(
                    r"https?://(?:www\.)?critterdb.com(?::443|:80)?.*#/(published)?bestiary/view/([0-9a-f]+)", url
                ):
                    return await ctx.send("Bestiaries must be imported with the `!bestiary import` command instead.")
                return await ctx.send("Sheet type did not match accepted formats.")
            loading = await ctx.send("Loading character data from Google...")
            prefix = "google"
            parser = GoogleSheet(url)

        override = await self._confirm_overwrite(ctx, f"{prefix}-{url}")
        if not override:
            return await ctx.send("Character overwrite unconfirmed. Aborting.")

        # Load the parsed sheet
        character = await self._load_sheet(ctx, parser, args, loading, version)
        if character and beyond_match:
            await send_ddb_ctas(ctx, character)

    @commands.command(hidden=True, aliases=["gsheet", "dicecloud"])
    @commands.max_concurrency(1, BucketType.user)
    async def beyond(self, ctx, url: str, *, args=""):
        """
        This is an old command and has been replaced. Use `!import` instead!
        """
        await self.import_sheet(ctx, url, args=args)

    @staticmethod
    async def _load_sheet(ctx, parser, args, loading, version):
        try:
            character = await parser.load_character(ctx, argparse(args))
        except ExternalImportError as eep:
            await loading.edit(content=f"Error loading character: {eep}")
            return
        except Exception as eep:
            log.warning(f"Error importing character {parser.url}")
            log.warning(traceback.format_exc())
            await loading.edit(content=f"Error loading character: {eep}")
            return

        await loading.edit(content=f"Loaded and saved data for {character.name}!")

        # Update charsetting based on the version argument
        character.options.version = version

        await character.commit(ctx)
        await character.set_active(ctx)
        await ctx.send(embed=character.get_sheet_embed())
        return character

    @staticmethod
    async def _check_url(ctx, url):
        if url.startswith("<") and url.endswith(">"):
            url = url.strip("<>")
            await ctx.send(
                "Hey! Looks like you surrounded that URL with '<' and '>'. I removed them, but remember not to "
                "include those for other arguments!"
                f"\nUse `{ctx.prefix}help` for more details."
            )
        return url

    @staticmethod
    async def _active_character_embed(ctx, message=""):
        """Creates an embed to be displayed when the active character is checked"""
        global_character = None
        server_character = None
        channel_character = None

        try:
            global_character: Character = await Character.from_ctx(
                ctx, use_global=True, use_guild=False, use_channel=False
            )
        except NoCharacter:
            pass
        try:
            server_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=True, use_channel=False
            )
        except NoCharacter:
            pass
        try:
            channel_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=False, use_channel=True
            )
        except NoCharacter:
            pass

        active_character: Character = await ctx.get_character()
        embed = embeds.EmbedWithCharacter(active_character)

        desc = (
            f"Your current active character is {active_character.name}. "
            "All of your checks, saves and actions will use this character's stats."
        )
        if (link := active_character.get_sheet_url()) is not None:
            desc = f"{desc}\n[Go to Character Sheet]({link})"
        if message != "":
            embed.add_field(name="Changes", value=message, inline=True)
        embed.description = desc
        characterInfoMessages = []

        if global_character is not None:
            characterInfoMessages.append(f"Global Character: {global_character.name}")
        if server_character is not None:
            characterInfoMessages.append(f"Server Character: {server_character.name}")
        if channel_character is not None:
            characterInfoMessages.append(f"Channel Character: {channel_character.name}")

        # global and server active differ
        embed.set_footer(text="\n".join(characterInfoMessages))
        return embed


async def send_ddb_ctas(ctx, character):
    """Sends relevant CTAs after a DDB character is imported. Only show a CTA 1/24h to not spam people."""
    ddb_user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
    gamelog_flag = await ctx.bot.ldclient.variation_for_ddb_user(
        "cog.gamelog.cta.enabled", ddb_user, False, discord_id=ctx.author.id
    )

    # get server settings for whether to pull up campaign settings
    if ctx.guild is not None:
        guild_settings = await ctx.get_server_settings()
        show_campaign_cta = guild_settings.show_campaign_cta
    else:
        show_campaign_cta = False

    # has the user seen this cta within the last 7d?
    if await ctx.bot.rdb.get(f"cog.sheetmanager.cta.seen.{ctx.author.id}"):
        return

    embed = embeds.EmbedWithCharacter(character)
    embed.title = "Heads up!"
    embed.description = "There's a couple of things you can do to make your experience even better!"
    embed.set_footer(text="You won't see this message again this week.")

    # link ddb user
    if ddb_user is None:
        embed.add_field(
            name="Connect Your D&D Beyond Account",
            value=(
                "Visit your [Account Settings](https://www.dndbeyond.com/account) page in D&D Beyond to link your "
                "D&D Beyond and Discord accounts. This lets you use all your D&D Beyond content in Avrae for free!"
            ),
            inline=False,
        )
    # game log
    if character.ddb_campaign_id and gamelog_flag and show_campaign_cta:
        try:
            await CampaignLink.from_id(ctx.bot.mdb, character.ddb_campaign_id)
        except NoCampaignLink:
            embed.add_field(
                name="Link Your D&D Beyond Campaign",
                value=(
                    "Sync rolls between a Discord channel and your D&D Beyond character sheet by linking your "
                    f"campaign! Use `{ctx.prefix}campaign https://www.dndbeyond.com/campaigns/"
                    f"{character.ddb_campaign_id}` in the Discord channel you want to link it to.\n"
                    f"This message can be disabled in `{ctx.prefix}server_settings`."
                ),
                inline=False,
            )

    if not embed.fields:
        return
    await ctx.send(embed=embed)
    await ctx.bot.rdb.setex(f"cog.sheetmanager.cta.seen.{ctx.author.id}", str(time.time()), 60 * 60 * 24 * 7)


def setup(bot):
    bot.add_cog(SheetManager(bot))
