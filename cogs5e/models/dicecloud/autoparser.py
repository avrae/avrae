import collections
import logging
import re

from cogs5e.models.automation import Automation
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import chunk_text

# because I like attributes
Effects = collections.namedtuple("Effects", ["damage", "saves", "save_damage"])

# various regex for annotated strings
NO_DICE_COUNT = re.compile(r"(?=\s|^)d(?=[\d{])")
THE_DICE_D = re.compile(r"(?=^|\b)([\d}]+)d([\d{]+)(?=$|\b)")
IF_TRUE_FALSE = re.compile(r"([^?(]*)\?([^:]*):([^)]*)")
MAGIC_ANNOSTR_REGEX = re.compile(r"(\(?(([a-ce-zA-Z_]|(?<!\w)\d+(?!d\d+)|d(?!\d+))\w*).*?\)?)($|\s*[+\-*/]?\s*\d*d\d+)")
SPECIAL_FUNCS = (
    (re.compile(r"\btrunc\b"), "int"),
    (re.compile(r"sign\(([^\)]*)\)"), r"((\1) and round((\1)/abs(\1)))"),
)

log = logging.getLogger(__name__)


class DCV2AutoParser:
    def __init__(self, parser):
        self.parser = parser
        self.self_effects = Effects([], [], [])
        self.target_effects = Effects([], [], [])
        self.resources = []
        self.meta = {}
        self.text = []
        self.rolls = {}

    def get_automation(self, prop):
        self.parse(prop)

        auto = []  # all the automation is in here

        # the insert the action description as the first text
        desc = prop.get("summary", {}).get("value") or prop.get("description", {}).get("value")
        if desc is not None:
            self.text.insert(0, desc)

        # add counters for each resource found
        for resource, amt in self.resources:
            auto.append({"type": "counter", "counter": resource, "amount": str(amt)})

        # add all the rolls to the automation data
        for name, roll in self.rolls.items():
            auto.append({"type": "roll", "name": name} | roll)

        # check if we actually need an all target, then create and add effects
        if (damages := self.target_effects.damage) or self.target_effects.saves or self.meta.get("bonus") is not None:
            # easiest way I could think of to get a reference back
            stack = []
            auto.append({"type": "target", "target": "all", "effects": stack.append([]) or stack[-1]})

            # add attack and damage nodes
            if bonus := self.meta.get("bonus"):
                stack[-1].append(
                    {"type": "attack", "hit": stack.append([]) or stack[-1], "miss": [], "attackBonus": str(bonus)}
                )
            for damage in damages:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

            # from parsed data, create saves for target
            for save in self.target_effects.saves:
                if (stat := save["stat"][:3].lower()) in STAT_ABBREVIATIONS:
                    stack[-1].append(
                        {
                            "type": "save",
                            "stat": stat,
                            "fail": stack.append([]) or stack[-1],
                            "success": [],
                            "dc": save["dc"],
                        }
                    )
            # tack on all save damage to the saves, not very accurate I suppose
            for damage in self.target_effects.save_damage:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )

        # same as all targets, but this time for the caster
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

            for save in self.self_effects.saves:
                if (stat := save["stat"][:3].lower()) in STAT_ABBREVIATIONS:
                    stack[-1].append(
                        {
                            "type": "save",
                            "stat": stat,
                            "fail": stack.append([]) and stack[-1],
                            "success": [],
                            "dc": save["dc"],
                        }
                    )
            for damage in self.self_effects.save_damage:
                stack[-1].append(
                    {"type": "damage", "damage": f"{damage['damage']}[{damage['type']}]", "overheal": False}
                )
        # add all the text at the end
        for text in self.text:
            auto.extend({"type": "text", "text": chunk} for chunk in chunk_text(text))

        log.debug(
            f"Damage for {prop['name']}: {self.target_effects.damage}, {self.target_effects.save_damage},"
            f" {self.self_effects.damage}, {self.self_effects.save_damage}"
        )
        log.debug(f"Automation for {prop['name']}: {auto}")

        return Automation.from_data(auto)

    def parse(self, prop, *, initial=True, save=False):
        # most types have unique effects under an action
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
                            "stat": prop.get("stat", ""),
                        }
                    )
                else:
                    self.target_effects.saves.append(
                        {
                            "id": prop["_id"],
                            "dc": prop.get("dc", {}).get("value", 10),
                            "stat": prop.get("stat", ""),
                        }
                    )
                self.parse_children(prop["children"], save=True)
            case "damage":
                # all the checks for what exactly we're doing here
                magical = "magical" in prop["tags"]
                healing = prop["damageType"] == "healing"
                effects = [str(effect["amount"]["value"]).strip() for effect in prop["amount"].get("effects", [])]
                damage_dice = str(prop["amount"]["value"]) + "".join(
                    effect if effect[0] in "+-" else f"+{effect}" for effect in effects
                )
                damage_dice = f"{'-1*(' if healing else ''}{damage_dice}{')' if healing else ''}"
                # handle all the annotated string stuff, as well as a few funcs
                damage = self.convert_to_annostr(damage_dice)
                effects = (
                    self.self_effects if self.meta.get("self") or prop.get("target") == "self" else self.target_effects
                )
                damage = {
                    "id": prop["_id"],
                    "damage": damage,
                    "type": ("magical " if magical else "") + prop["damageType"],
                }
                log.debug(f"Parsing damage: {damage}")
                if save:
                    effects.save_damage.append(damage)
                else:
                    effects.damage.append(damage)
                self.parse_children(prop["children"], save=save)
            case "buff":
                pass  # maybe someday we can convert these into ieffects
            case "toggle":
                # since all properties under actions are inactive, we have to check the toggles
                if prop["condition"]["value"]:
                    self.parse_children(prop["children"], save=save)
            case "branch":
                # these branch types specifically are banned
                if prop["branchType"] in ("index", "random"):
                    return
                self.parse_children(prop["children"], save=save)
            case "note":
                # we only use the summary here, since it's all DC would display
                desc = prop.get("summary")
                if desc is not None:
                    self.text.append(desc)
                self.parse_children(prop["children"], save=save)
            # rolls, pretty straight forward
            case "roll":
                if name := prop.get("variableName"):
                    roll = {"dice": prop.get("roll", {}).get("value")}
                    if roll["dice"]:
                        roll["dice"] = self.convert_to_annostr(roll["dice"])
                        if d_name := prop.get("name"):
                            roll["displayName"] = d_name
                        self.rolls[name] = roll
            # everything else does nothing and just runs its children
            case _:
                self.parse_children(prop["children"], save=save)

    def parse_children(self, children, *, save=False):
        for child_id in children:
            child_prop = self.parser._by_id[child_id]
            self.parse(child_prop, initial=False, save=save)

    @staticmethod
    def convert_to_annostr(string: str):
        string = re.sub(IF_TRUE_FALSE, r"(\2) if (\1) else (\3)", string)
        string = re.sub(MAGIC_ANNOSTR_REGEX, r"{\1}\4", string)
        string = re.sub(NO_DICE_COUNT, "1d", string)
        string = re.sub(THE_DICE_D, r"\1d\2", string)
        for patt, rep in SPECIAL_FUNCS:
            string = re.sub(patt, rep, string)
        return string
