import random

import discord

import ddb.dice
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.sheet.attack import Attack
from ddb.gamelog.context import GameLogEventContext
from ddb.gamelog.event import GameLogEvent
from gamedata import Monster
from gamedata.compendium import compendium
from gamedata.lookuputils import available
from utils import constants
from utils.functions import a_or_an


# ==== event helpers ====
async def action_from_roll_request(gctx, caster, roll_request):
    """
    Gets an action (spell or attack) from a character based on the roll request. None if it cannot be found.

    Prioritizes attack first, then spell if not found.

    :type gctx: ddb.gamelog.context.GameLogEventContext
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type roll_request: ddb.dice.RollRequest
    :rtype: Attack or gamedata.spell.Spell
    """
    action_name = roll_request.action

    attack = next((a for a in caster.attacks if a.name == action_name), None)
    if attack is not None:
        return attack

    available_spells = await available(gctx, compendium.spells, "spell", gctx.discord_user_id)
    # noinspection PyUnresolvedReferences
    # this is a Spell
    spell = next((s for s in available_spells if s.name == action_name), None)
    # todo do better filtering by context id if available

    if spell is not None:
        return spell
    return None


# ---- display helpers ----
def default_comment_getter(roll_request):
    """
    Given a RollRequest, return a function mapping RollRequestRolls to comments (strs).

    :type roll_request: ddb.dice.RollRequest
    :rtype: typing.Callable[[ddb.dice.RollRequestRoll], typing.Optional[str]]
    """
    if roll_request.action != "custom":
        if roll_request.context and roll_request.context.name:
            return lambda rr: f"{roll_request.context.name}: {roll_request.action}: {rr.roll_type.value.title()}"
        return lambda rr: f"{roll_request.action}: {rr.roll_type.value.title()}"
    else:
        return lambda _: None


def embed_for_caster(caster):
    if isinstance(caster, Character):
        return EmbedWithCharacter(character=caster, name=False)
    embed = discord.Embed()
    embed.colour = random.randint(0, 0xFFFFFF)
    if isinstance(caster, Monster):
        embed.set_thumbnail(url=caster.get_image_url())
    return embed


def embed_for_action(gctx, action, caster, to_hit_roll=None, damage_roll=None):
    """
    Creates an embed for a character performing some action (attack or spell).

    Handles inserting the correct fields for to-hit and damage based on the action's automation and whether the rolls
    are present.

    :type gctx: GameLogEventContext
    :type action: Attack or gamedata.spell.Spell
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type to_hit_roll: ddb.dice.tree.RollRequestRoll
    :type damage_roll: ddb.dice.tree.RollRequestRoll
    """
    embed = embed_for_caster(caster)
    automation = action.automation
    waiting_for_damage = False

    # set title
    if isinstance(action, Attack):
        attack_name = a_or_an(action.name) if not action.proper else action.name
        verb = action.verb or "attacks with"
        embed.title = f"{caster.get_title_name()} {verb} {attack_name}!"
    else:  # spell
        embed.title = f"{caster.get_title_name()} casts {action.name}!"

    # add to hit (and damage, either if it is provided or the action expects damage and it is not provided)
    meta_rolls = []
    if to_hit_roll is not None:
        meta_rolls.append(f"**To Hit**: {str(to_hit_roll.to_d20())}")
    if damage_roll is not None:
        if damage_roll.roll_kind == ddb.dice.RollKind.CRITICAL_HIT:
            meta_rolls.append(f"**Damage (CRIT!)**: {str(damage_roll.to_d20())}")
        else:
            meta_rolls.append(f"**Damage**: {str(damage_roll.to_d20())}")
    elif automation_has_damage(automation):
        meta_rolls.append("**Damage**: Waiting for roll...")
        waiting_for_damage = True

    # add dcs, texts
    if automation:
        for effect in automation_dfg(automation, enter_filter=action_enter_filter):
            # break if we see a damage and are waiting on a damage roll
            if effect.type == "damage" and waiting_for_damage:
                break

            # note: while certain fields here are AnnotatedStrings, it should never be annotated directly from the sheet
            # and GameLog events cannot trigger custom attacks, so this should be fine

            # save: add the DC
            if effect.type == "save":
                meta_rolls.append(f"**DC**: {effect.dc}\n{effect.stat[:3].upper()} Save")
            # text: add the text as a field
            elif effect.type == "text":
                text = effect.text
                if len(text) > 1020:
                    text = f"{text[:1020]}..."
                embed.add_field(name="Effect", value=text, inline=False)

    embed.insert_field_at(0, name="Meta", value="\n".join(meta_rolls), inline=False)

    # set footer
    embed.set_footer(text=f"Rolled in {gctx.campaign.campaign_name}", icon_url=constants.DDB_LOGO_ICON)
    return embed


def embed_for_basic_attack(gctx, action_name, caster, to_hit_roll=None, damage_roll=None):
    """
    Creates an embed for a character making an attack where the Avrae action is unknown.

    Handles inserting the correct fields for to-hit and damage.

    :type gctx: GameLogEventContext
    :type action_name: str
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type to_hit_roll: ddb.dice.tree.RollRequestRoll
    :type damage_roll: ddb.dice.tree.RollRequestRoll
    """
    embed = embed_for_caster(caster)

    # set title
    embed.title = f"{caster.get_title_name()} attacks with {action_name}!"

    # add to hit (and damage, either if it is provided or the action expects damage and it is not provided)
    meta_rolls = []
    if to_hit_roll is not None:
        meta_rolls.append(f"**To Hit**: {str(to_hit_roll.to_d20())}")

    if damage_roll is not None:
        if damage_roll.roll_kind == ddb.dice.RollKind.CRITICAL_HIT:
            meta_rolls.append(f"**Damage (CRIT!)**: {str(damage_roll.to_d20())}")
        else:
            meta_rolls.append(f"**Damage**: {str(damage_roll.to_d20())}")
    else:
        meta_rolls.append("**Damage**: Waiting for roll...")

    embed.add_field(name="Meta", value="\n".join(meta_rolls), inline=False)

    # set footer
    embed.set_footer(text=f"Rolled in {gctx.campaign.campaign_name}", icon_url=constants.DDB_LOGO_ICON)
    return embed


# ---- automation tree helpers ----
def automation_dfg(automation, enter_filter=None):
    """
    Depth-first generator on automation.

    :type automation: cogs5e.models.automation.Automation
    :param enter_filter: A callable that takes an automation effect and returns the children to iterate over.
    """
    if enter_filter is None:
        enter_filter = lambda e: e.children

    def iterator(effects):
        for effect in effects:
            yield effect
            yield from iterator(enter_filter(effect))

    yield from iterator(automation.effects)


def automation_has_damage(automation):
    """Returns whether a given automation does damage."""
    if automation is None:
        return False

    for effect in automation_dfg(automation):
        if effect.type == "damage":
            return True
    return False


def action_enter_filter(effect):
    """Only enter an effect if it is top level or an attack."""
    if effect.type == "attack":
        return effect.children
    return []


# ---- attack state helper ----
class PendingAttack:
    """A cached attack that is waiting on a damage roll."""

    TTL = 60 * 2  # 2m

    def __init__(self, key: str, to_hit_event: GameLogEvent, message_id: int):
        self.key = key
        self.to_hit_event = to_hit_event
        self.message_id = message_id

    # ser/deser
    @classmethod
    def from_dict(cls, key, d):
        to_hit_event = GameLogEvent.from_dict(d["to_hit_event"])
        return cls(key, to_hit_event, d["message_id"])

    def to_dict(self):
        return {"to_hit_event": self.to_hit_event.to_dict(), "message_id": self.message_id}

    @classmethod
    async def create(
        cls, gctx: GameLogEventContext, roll_request: ddb.dice.RollRequest, to_hit_event: GameLogEvent, message_id: int
    ):
        """Creates and caches a new PendingAttack instance."""
        cache_key = await cls.cache_key_from_ctx(gctx, roll_request)
        inst = cls(cache_key, to_hit_event, message_id)
        await gctx.bot.rdb.jsetex(key=cache_key, data=inst.to_dict(), exp=cls.TTL)
        return inst

    @classmethod
    async def for_damage(cls, gctx: GameLogEventContext, roll_request: ddb.dice.RollRequest):
        """Gets the relevant PendingAttack instance from cache for a given damage RollRequest in context, or None."""
        cache_key = await cls.cache_key_from_ctx(gctx, roll_request)
        data = await gctx.bot.rdb.jget(cache_key)
        if data is None:
            return None
        return cls.from_dict(cache_key, data)

    # helpers
    @property
    def roll_request(self):
        return ddb.dice.RollRequest.from_dict(self.to_hit_event.data)

    async def delete(self, gctx):
        await gctx.bot.rdb.delete(self.key)

    @staticmethod
    async def cache_key_from_ctx(gctx: GameLogEventContext, roll_request: ddb.dice.RollRequest):
        action_name = roll_request.action  # todo maybe this can be the context instead
        return f"gamelog.pendingattack.{gctx.discord_user_id}.{gctx.event.entity_type}.{gctx.event.entity_id}.{action_name}"
