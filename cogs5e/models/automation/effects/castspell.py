import aliasing.api.combat
import gamedata
import gamedata.lookuputils
from cogs5e.models.errors import RequiresLicense, InvalidArgument
from utils.functions import smart_trim
from . import Effect
from .ieffect import IEffectMetaVar
from ..results import CastSpellResult


class CastSpell(Effect):
    def __init__(
        self,
        id: int,
        level: int = None,
        dc: str = None,
        attackBonus: str = None,
        castingMod: str = None,
        parent: str = None,
        **kwargs,
    ):
        super().__init__("spell", **kwargs)
        self.id = id
        self.level = level
        self.dc = dc
        self.attack_bonus = attackBonus
        self.casting_mod = castingMod
        self.parent = parent

    def to_dict(self):
        out = super().to_dict()
        out.update({
            "id": self.id,
            "level": self.level,
            "dc": self.dc,
            "attackBonus": self.attack_bonus,
            "castingMod": self.casting_mod,
            "parent": self.parent,
        })
        return out

    async def preflight(self, autoctx):
        """Checks that the user has entitlement access to the referenced entity, if applicable."""
        await super().preflight(autoctx)
        if self.spell is None:
            return
        type_e10s = await autoctx.ctx.bot.ddb.get_accessible_entities(
            ctx=autoctx.ctx, user_id=autoctx.ctx.author.id, entity_type=gamedata.Spell.entity_type
        )
        if not gamedata.lookuputils.can_access(self.spell, type_e10s):
            raise RequiresLicense(self.spell, type_e10s is not None)

    def run(self, autoctx):
        super().run(autoctx)
        spell = self.spell
        if spell is None:
            autoctx.meta_queue(f"**Error**: Spell {self.id} not found.")
            return CastSpellResult(success=False)
        cast_level = self.level if self.level is not None else spell.level
        if not spell.level <= cast_level <= 9:
            autoctx.meta_queue(f"**Error**: Unable to cast {spell.name} at level {cast_level} (invalid level).")
            return CastSpellResult(success=False, spell_id=self.id)

        if autoctx.is_spell:
            autoctx.meta_queue(f"**Error**: Unable to cast another spell inside a spell.")
            return CastSpellResult(success=False, spell_id=self.id)

        dc_override = ab_override = spell_override = None
        if spell.automation and spell.automation.effects:
            # save old autoctx values
            old_ab_override = autoctx.ab_override
            old_dc_override = autoctx.dc_override
            old_spell_override = autoctx.evaluator.builtins.get("spell")
            old_level_override = autoctx.spell_level_override
            autoctx.metavars["spell_level"] = (
                old_spell_level := autoctx.spell_level_override if autoctx.spell_level_override else cast_level
            )

            # parenting
            explicit_parent = None
            if self.parent is not None and (parent_ref := autoctx.metavars.get(self.parent, None)) is not None:
                if not isinstance(parent_ref, (IEffectMetaVar, aliasing.api.combat.SimpleEffect)):
                    raise InvalidArgument(
                        f"Could not set IEffect parent: The variable `{self.parent}` is not an IEffectMetaVar "
                        f"(got `{type(parent_ref).__name__}`)."
                    )
                # noinspection PyProtectedMember
                explicit_parent = parent_ref._effect

            autoctx.conc_effect = explicit_parent

            # run the spell using the given values
            if self.attack_bonus is not None:
                ab_override = autoctx.ab_override = autoctx.parse_intexpression(self.attack_bonus)
            if self.dc is not None:
                dc_override = autoctx.dc_override = autoctx.parse_intexpression(self.dc)
            if self.casting_mod is not None:
                spell_override = autoctx.evaluator.builtins["spell"] = autoctx.parse_intexpression(self.casting_mod)
            if self.level is not None:
                autoctx.spell_level_override = self.level
                autoctx.metavars["spell_level"] = autoctx.spell_level_override
            autoctx.spell = spell

            results = self.run_children(spell.automation.effects, autoctx)

            # and restore them
            autoctx.ab_override = old_ab_override
            autoctx.dc_override = old_dc_override
            autoctx.evaluator.builtins["spell"] = old_spell_override
            autoctx.spell_level_override = old_level_override
            autoctx.spell = None
            autoctx.metavars["spell_level"] = old_spell_level

            # display higher level info
            if cast_level != spell.level and spell.higherlevels:
                autoctx.effect_queue(f"**At Higher Levels**: {smart_trim(spell.higherlevels)}")
        else:
            # copied from Spell.cast
            results = []
            autoctx.queue(smart_trim(spell.description))
            autoctx.push_embed_field(title=spell.name)

            # display higher level info
            if cast_level != spell.level and spell.higherlevels:
                autoctx.queue(smart_trim(spell.higherlevels))
                autoctx.push_embed_field(title="At Higher Levels")

        return CastSpellResult(
            success=True,
            spell_id=self.id,
            level_override=self.level,
            dc_override=dc_override,
            attack_bonus_override=ab_override,
            casting_mod_override=spell_override,
            children=results,
        )

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        level = ""
        spell_name = "an unknown spell"
        if self.spell is not None:
            spell_name = self.spell.name
            if self.level is not None and self.level != self.spell.level:
                level = f" at level {self.level}"
        return f"casts {spell_name}{level}"

    @property
    def spell(self):
        return gamedata.compendium.lookup_entity(gamedata.Spell.type_id, self.id)

    @property
    def children(self):
        if self.spell is not None and self.spell.automation and self.spell.automation.effects:
            return self.meta + self.spell.automation.effects
        return self.meta
