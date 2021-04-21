from cogs5e.models.sheet.integrations import LiveIntegration


class DDBSheetSync(LiveIntegration):
    async def _preflight(self):
        """Checks that the context is set and returns the DDB user."""
        if self._ctx is None:
            raise ValueError("Attempted to call DDB sheet sync method with no valid context")
        return await self._ctx.bot.ddb.get_ddb_user(self._ctx)

    async def _do_sync_hp(self):
        if (ddb_user := await self._preflight()) is None:
            return
        await self._ctx.bot.ddb.character.set_damage_taken(
            ddb_user=ddb_user,
            removed_hit_points=clamp(0, self.character.max_hp - self.character.hp, self.character.max_hp),
            temporary_hit_points=max(self.character.temp_hp, 0),
            character_id=int(self.character.upstream_id)
        )

    async def _do_sync_slots(self):
        if (ddb_user := await self._preflight()) is None:
            return
        sb = self.character.spellbook
        if any(sb.max_slots.values()):
            real_slots = []  # 9-length list of slot levels 1-9
            for l in range(1, 10):
                slots_of_level_used = sb.get_max_slots(l) - sb.get_slots(l)
                if l == sb.pact_slot_level:
                    slots_of_level_used -= sb.max_pact_slots - sb.num_pact_slots  # remove # of used pact slots
                real_slots.append(slots_of_level_used)
            await self._ctx.bot.ddb.character.set_spell_slots(
                ddb_user,
                *real_slots,
                character_id=int(self.character.upstream_id)
            )
        if sb.max_pact_slots is not None:
            pact_slots = [0] * 5
            pact_slots[sb.pact_slot_level - 1] = sb.max_pact_slots - sb.num_pact_slots
            await self._ctx.bot.ddb.character.set_pact_magic(
                ddb_user,
                *pact_slots,
                character_id=int(self.character.upstream_id)
            )

    async def _do_sync_consumable(self, consumable):
        if (ddb_user := await self._preflight()) is None:
            return
        if not consumable.live_id:
            return
        if consumable.max is None:
            return
        try:
            limited_use_id, type_id = consumable.live_id.split('-')
        except (ValueError, TypeError):
            return
        await self._ctx.bot.ddb.character.set_limited_use(
            ddb_user=ddb_user,
            id=int(limited_use_id),
            entity_type_id=int(type_id),
            uses=clamp(0, consumable.get_max() - consumable.value, consumable.get_max()),
            character_id=int(self.character.upstream_id)
        )

    async def _do_sync_death_saves(self):
        if (ddb_user := await self._preflight()) is None:
            return
        death_saves = self.character.death_saves
        await self._ctx.bot.ddb.character.set_death_saves(
            ddb_user=ddb_user,
            success_count=clamp(0, death_saves.successes, 3),
            fail_count=clamp(0, death_saves.fails, 3),
            character_id=int(self.character.upstream_id)
        )


# helpers
def clamp(minimum, value, maximum):
    return min(max(minimum, value), maximum)
