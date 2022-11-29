import collections
import logging
import re

from cogs5e.models.automation import Automation
from utils.constants import STAT_ABBREVIATIONS

Effects = collections.namedtuple("Effects", ["damage", "saves", "save_damage"])
NO_DICE_COUNT = re.compile(r"(?<!\d)d")

log = logging.getLogger(__name__)


class DCV2AutoParser:
    def __init__(self, parser):
        self.parser = parser
        self.self_effects = Effects([], [], [])
        self.target_effects = Effects([], [], [])
        self.resources = []
        self.meta = {}

    def get_automation(self, prop):
        self.parse(prop)

        auto = []
        for resource, amt in self.resources:
            auto.append({"type": "counter", "counter": resource, "amount": str(amt)})

        if (damages := self.target_effects.damage) or self.target_effects.saves or self.meta.get("bonus") is not None:
            stack = []
            auto.append({"type": "target", "target": "all", "effects": stack.append([]) or stack[-1]})
            if bonus := self.meta.get("bonus"):
                stack[-1].append(
                    {"type": "attack", "hit": stack.append([]) or stack[-1], "miss": [], "attackBonus": str(bonus)}
                )
            for damage in damages:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

            # do save stuff
            for save in self.target_effects.saves:
                if (stat := save["stat"][:3].lower()) in STAT_ABBREVIATIONS:
                    stack[-1].append(
                        {"type": "save", "stat": stat, "fail": stack.append([]) or stack[-1], "success": []}
                    )
            for damage in self.target_effects.save_damage:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

        if (
            (damages := self.self_effects.damage)
            or self.self_effects.saves
            or (self.meta.get("self") and self.meta.get("bonus") is not None)
        ):
            stack = []
            auto.append({"type": "target", "target": "self", "effects": stack.append([]) or stack[-1]})
            if self.meta.get("self") and (bonus := self.meta.get("bonus")):
                stack[-1].append(
                    {"type": "attack", "hit": stack.append([]) or stack[-1], "miss": [], "attackBonus": str(bonus)}
                )
            for damage in damages:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

            # do save stuff
            for save in self.self_effects.saves:
                if (stat := save["stat"][:3].lower()) in STAT_ABBREVIATIONS:
                    stack[-1].append(
                        {"type": "save", "stat": stat, "fail": stack.append([]) and stack[-1], "success": []}
                    )
            for damage in self.self_effects.save_damage:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

        log.debug(
            f"Damage for {prop['name']}: {self.target_effects.damage}, {self.target_effects.save_damage},"
            f" {self.self_effects.damage}, {self.self_effects.save_damage}"
        )
        log.debug(f"Automation for {prop['name']}: {auto}")

        return Automation.from_data(auto)

    def parse(self, prop, *, initial=True, save=False):
        match prop["type"]:
            case "action" | "spell":
                if initial:
                    # check if target is self
                    self.meta["self"] = prop["target"] == "self"

                    # get attack bonus
                    if atk_roll := prop.get("attackRoll"):
                        self.meta["bonus"] = atk_roll["value"]

                    # get names for custom counters
                    if prop.get("uses", None):
                        sl_name = prop.get("spellListName")
                        self.resources.append((f"{sl_name}: {prop['name']}" if sl_name else prop["name"], 1))
                    if attrs := prop["resources"]["attributesConsumed"]:
                        for attr in attrs:
                            self.resources.append((attr["statName"], attr["quantity"]["value"]))

                    self.parse_children(prop["children"], save=save)

            case "savingThrow":
                if self.meta.get("self") or prop.get("target") == "self":
                    self.self_effects.saves.append(
                        {
                            "id": prop["_id"],
                            "dc": prop.get("dc", {}).get("value", 10),
                            "stat": prop["stat"],
                        }
                    )
                else:
                    self.target_effects.saves.append(
                        {
                            "id": prop["_id"],
                            "dc": prop.get("dc", {}).get("value", 10),
                            "stat": prop["stat"],
                        }
                    )
                self.parse_children(prop["children"], save=True)
            case "damage":
                magical = "magical" in prop["tags"]
                healing = prop["damageType"] == "healing"
                effects = [str(effect["amount"]["value"]).strip() for effect in prop["amount"].get("effects", [])]
                damage_dice = str(prop["amount"]["value"]) + "".join(
                    effect if effect[0] in "+-" else f"+{effect}" for effect in effects
                )
                damage = re.sub(
                    NO_DICE_COUNT,
                    "1d",
                    f"{'-1*(' if healing else ''}{damage_dice}{')' if healing else ''}".lower(),
                )
                effects = (
                    self.self_effects if self.meta.get("self") or prop.get("target") == "self" else self.target_effects
                )
                damage = {
                    "id": prop["_id"],
                    "damage": damage,
                    "type": prop["damageType"],
                }
                log.debug(f"Parsing damage: {damage}")
                if save:
                    effects.save_damage.append(damage)
                else:
                    effects.damage.append(damage)
                self.parse_children(prop["children"], save=save)
            case "buff":
                pass
            case "toggle":
                if prop["condition"]["value"]:
                    self.parse_children(prop["children"], save=save)
            case _:
                self.parse_children(prop["children"], save=save)

    def parse_children(self, children, *, save=False):
        for child_id in children:
            child_prop = self.parser._by_id[child_id]
            self.parse(child_prop, initial=False, save=save)
