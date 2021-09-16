import ddb
from cogs5e.utils import gameutils
from ddb.gamelog.context import GameLogEventContext
from .callback import GameLogCallbackHandler, callback


class CharacterHandler(GameLogCallbackHandler):
    @callback('character-sheet/character-update/fulfilled')
    async def character_update_fulfilled(
            self,
            gctx: GameLogEventContext,
            data: ddb.character.scds_types.SCDSMessageBrokerData):
        character_id = data.character_id
        ddb_user = await self.bot.ddb.get_ddb_user(gctx, gctx.discord_user_id)
        resp = await self.bot.ddb.scds.get_characters(ddb_user, [character_id])
        if not resp.found_characters:
            return
        scds_char = resp.found_characters[0]
        char = await gctx.get_character()

        char.hp = scds_char.hit_point_info.current
        char._max_hp = scds_char.hit_point_info.maximum
        char.temp_hp = scds_char.hit_point_info.temp
        await char.commit(gctx, do_live_integrations=False)
        await gameutils.send_hp_result(gctx, char)
