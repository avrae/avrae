from collections import namedtuple

import ddb
from cogs5e.models import embeds
from cogs5e.models.character import Character
from ddb.character import scds_types
from ddb.gamelog import GameLogEventContext
from ddb.gamelog.errors import IgnoreEvent
from utils import constants
from .callback import GameLogCallbackHandler, callback
from .utils import feature_flag

# ==== types ====
SyncHPResult = namedtuple('SyncHPResult', 'changed old_hp old_max old_temp delta message')
SyncDeathSavesResult = namedtuple('SyncDeathSavesResult', 'changed old_successes old_fails')


# ==== handler ====
class CharacterHandler(GameLogCallbackHandler):
    @callback('character-sheet/character-update/fulfilled')
    @feature_flag('cog.gamelog.character-update-fulfilled.enabled')
    async def character_update_fulfilled(
        self,
        gctx: GameLogEventContext,
        data: ddb.character.scds_types.SCDSMessageBrokerData
    ):
        char = await gctx.get_character()
        if char is None:
            raise IgnoreEvent("Character is not imported")
        if not char.options.sync_inbound:
            return

        character_id = data.character_id
        ddb_user = await self.bot.ddb.get_ddb_user(gctx, gctx.discord_user_id)
        resp = await self.bot.ddb.scds.get_characters(ddb_user, [character_id])
        if not resp.found_characters:
            return
        scds_char = resp.found_characters[0]

        hp_result = self.sync_hp(char, scds_char.hit_point_info)
        death_save_result = self.sync_death_saves(char, scds_char.death_save_info)

        if any((hp_result.changed, death_save_result.changed)):
            await self.send_sync_result(gctx, char, hp_result, death_save_result)
            await char.commit(gctx, do_live_integrations=False)

    # ==== sync handlers ====
    @staticmethod
    def sync_hp(
        char: Character,
        hp_info: scds_types.SimplifiedHitPointInfo
    ) -> SyncHPResult:
        old_hp = new_hp = char.hp
        old_max = new_max = char.max_hp
        old_temp = char.temp_hp

        # if the character's current hp is greater than its canonical max (i.e. not considering combats) and ddb says
        # the character is at full, skip hp sync - the character's hp may have been updated in some combat somewhere
        # which may or may not be the combat in the sync channel (which is the *combat* local here)
        # (demorgans: char.hp > char.max_hp and hp_info.current == hp_info.maximum)
        if char.hp <= char.max_hp or hp_info.current != hp_info.maximum:
            # otherwise, we can sync it up
            char.hp = new_hp = hp_info.current
            char.max_hp = new_max = hp_info.maximum
        char.temp_hp = hp_info.temp

        # build display message
        delta = new_hp - old_hp
        deltaend = f" ({delta:+})" if delta else ""
        message = f"{char.hp_str()}{deltaend}"

        return SyncHPResult(
            changed=any((old_hp != new_hp, old_max != new_max, old_temp != hp_info.temp)),
            old_hp=old_hp, old_max=old_max, old_temp=old_temp,
            delta=delta, message=message
        )

    @staticmethod
    def sync_death_saves(
        char: Character,
        death_save_info: scds_types.SimplifiedDeathSaveInfo
    ) -> SyncDeathSavesResult:
        old_successes = char.death_saves.successes
        old_fails = char.death_saves.fails

        # it is possible in ddb to have a death save state at nonzero HP, but in Avrae it resets this, so
        # any update will show the death saves since on_hp resets them when syncing hp
        if char.hp <= 0:
            char.death_saves.successes = death_save_info.success_count
            char.death_saves.fails = death_save_info.fail_count

        return SyncDeathSavesResult(
            changed=old_successes != char.death_saves.successes or old_fails != char.death_saves.fails,
            old_successes=old_successes, old_fails=old_fails
        )

    # ==== display helpers ====
    async def send_sync_result(
        self,
        gctx: GameLogEventContext,
        char: Character,
        hp_result: SyncHPResult,
        death_save_result: SyncDeathSavesResult
    ):
        embed = embeds.EmbedWithCharacter(char)

        # --- hp ---
        if hp_result.changed:
            embed.add_field(name="Hit Points", value=hp_result.message)

        # --- death saves ---
        if death_save_result.changed:
            embed.add_field(name="Death Saves", value=str(char.death_saves))

        embed.set_footer(text=f"Updated in {gctx.campaign.campaign_name}", icon_url=constants.DDB_LOGO_ICON)
        await gctx.send(embed=embed)
