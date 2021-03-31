from cogs5e.models.sheet.integrations import LiveIntegration


class DDBSheetSync(LiveIntegration):
    def _preflight(self):
        if self._ctx is None:
            raise ValueError("Attempted to call DDB sheet sync method with no valid context")

    async def _do_sync_hp(self):
        self._preflight()
        ddb_user = await self._ctx.bot.ddb.get_ddb_user(self._ctx)
        if ddb_user is None:
            return
        await self._ctx.bot.ddb.character.set_damage_taken(
            ddb_user=ddb_user,
            removed_hit_points=min(max(0, self.character.max_hp - self.character.hp), self.character.max_hp),
            temporary_hit_points=max(self.character.temp_hp, 0),
            character_id=int(self.character.upstream_id)
        )

    async def _do_sync_slots(self):
        pass

    async def _do_sync_consumable(self, consumable):
        pass

    async def _do_sync_death_saves(self):
        pass
