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
SyncHPResult = namedtuple('SyncHPResult', 'changed old_hp old_max old_temp delta')
SyncDeathSavesResult = namedtuple('SyncDeathSavesResult', 'changed old_successes old_fails')


# ==== handler ====
class CharacterHandler(GameLogCallbackHandler):
    @callback('character-sheet/character-update/fulfilled')
    @feature_flag('cog.gamelog.character-update-fulfilled.enabled')
    async def character_update_fulfilled(
            self,
            gctx: GameLogEventContext,
            data: ddb.character.scds_types.SCDSMessageBrokerData):
        char = await gctx.get_character()
        if char is None:
            raise IgnoreEvent("Character is not imported")

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
            hp_info: scds_types.SimplifiedHitPointInfo) -> SyncHPResult:
        old_hp = char.hp
        old_max = char.max_hp
        old_temp = char.temp_hp

        char.hp = hp_info.current
        char.max_hp = hp_info.maximum
        char.temp_hp = hp_info.temp

        return SyncHPResult(
            changed=any((old_hp != hp_info.current, old_max != hp_info.maximum, old_temp != hp_info.temp)),
            old_hp=old_hp, old_max=old_max, old_temp=old_temp,
            delta=hp_info.current - old_hp
        )

    @staticmethod
    def sync_death_saves(
            char: Character,
            death_save_info: scds_types.SimplifiedDeathSaveInfo) -> SyncDeathSavesResult:
        old_successes = char.death_saves.successes
        old_fails = char.death_saves.fails

        # it is possible in ddb to have a death save state at nonzerho HP, but in Avrae it resets this, so
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
            death_save_result: SyncDeathSavesResult):
        embed = embeds.EmbedWithCharacter(char)

        # --- hp ---
        if hp_result.changed:
            deltaend = f" ({hp_result.delta:+})" if hp_result.delta else ""
            embed.add_field(name="Hit Points", value=f"{char.hp_str()}{deltaend}")

        # --- death saves ---
        if death_save_result.changed:
            embed.add_field(name="Death Saves", value=str(char.death_saves))

        embed.set_footer(text=f"Updated in {gctx.campaign.campaign_name}", icon_url=constants.DDB_LOGO_ICON)
        await gctx.send(embed=embed)
