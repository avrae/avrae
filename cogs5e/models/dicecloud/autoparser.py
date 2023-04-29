import collections
import logging
import re

from cogs5e.models.automation import Automation
from cogs5e.models.dicecloud.errors import AutoParserException
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import chunk_text

# because I like attributes
Effects = collections.namedtuple("Effects", ["damage", "saves", "save_damage"])

# various regex for annotated strings
NO_DICE_COUNT = re.compile(r"(?=\s|^)d(?=[\d{])")
THE_DICE_D = re.compile(r"(?=^|\b)([\d}]+)d([\d{]+)(?=$|\b)")
IF_TRUE_FALSE = re.compile(r"([^?(]*)\?([^:]*):([^)]*)")
MAGIC_ANNOSTR_REGEX = re.compile(
    r"(\s*)(\(?\s*?(?:(?<!\w)\d+(?!\d*d\d+(?=\s|$|\b)).*?)?(?:(?:[a-ce-zA-Z_]|d(?!\d+(?=\s|$|\b)))\w*).*?\)?)(?=$|\s*[+\-*/]?[+\-*/(\d\s]*(?:\d*d\d+))"
)
SPECIAL_FUNCS = (
    (re.compile(r"\btrunc\b"), "int"),
    (re.compile(r"sign\(([^\)]*)\)"), r"((\1) and round((\1)/abs(\1)))"),
)

log = logging.getLogger(__name__)


class DCV2AutoParser:
    def __init__(self, parser):
        self.parser = parser
        self.auto = []
        self.stack = [self.auto]
        self.old_stacks = []
        self.saves = []
        self.attacks = []
        self.target = {}
        self.resources = []
        self.meta = {"target_count": 0, "random_count": 0}
        self.text = []

    def get_automation(self, prop):
        self.parse(prop, initial=True)

        # the insert the action description as the first text
        desc = prop.get("summary", {}).get("value") or prop.get("description", {}).get("value")
        if desc is not None:
            self.text.insert(0, desc)

        for text in self.text:
            for chunk in chunk_text(text):
                self.auto.append({
                    "type": "text",
                    "text": chunk
                })

        return Automation.from_data(self.auto)

    def parse(self, prop, *, initial=False):
        # most types have unique effects under an action
        try:
            match prop["type"]:
                case "action" | "spell":
                    self.parse_action(prop, initial)
                case "savingThrow":
                    self.parse_save(prop)
                case "damage":
                    self.parse_damage(prop)
                case "buff":
                    pass  # maybe someday we can convert these into ieffects
                case "toggle":
                    # since all properties under actions are inactive, we have to check the toggles
                    if prop["condition"]["value"]:
                        self.parse_children(prop["children"])
                case "branch":
                    self.parse_brance(prop)
                case "note":
                    # we only use the summary here, since it's all DC would display
                    desc = prop.get("summary", {}).get("value")
                    if desc is not None:
                        self.text.append(desc)
                    self.parse_children(prop["children"])
                # rolls, pretty straight forward
                case "roll":
                    self.parse_roll(prop)
                # everything else does nothing and just runs its children
                case _:
                    self.parse_children(prop["children"])
        except Exception as e:
            if isinstance(e, AutoParserException):
                raise e
            raise AutoParserException(prop, "Auto Parser encounter an error parsing a property") from e

    def add_resource(self, name, amt=1):
        self.auto.insert(0, {
            "type": "counter",
            "counter": name,
            "amount": str(amt)
        })

    def set_target(self, target_self):
        target = {
            "type": "target",
            "target": "self" if target_self else "all",
            "effects": []
        }
        if (
            (not target_self and self.target in self.stack)
            or
            (target_self and self.self_target in self.stack)
        ):
            variable_name = "DCV2_TARGET" + self.meta["target_count"]
            self.meta["target_count"] += 1
            variable = {
                "type": "variable",
                "name": variable_name,
                "value": "True"
            }

            self.stack[-1].append(variable)

            self.old_stacks.append(self.stack)
            self.stack = []

            branch = {
                "type": "condition",
                "condition": f"{variable_name}",
                "onTrue": [],
                "onFalse": [],
                "errorBehaviour": "false"
            }
            self.auto.append(branch)
            branch["onTrue"].append(target)
        elif self.target in self.stack or self.self_target in self.stack:
            return
        else:
            self.stack[-1].append(target)

        if target_self:
            self.self_target = target
        else:
            self.target = target

        self.stack.append(target["effects"])

    def pop_stack(self):
        self.stack.pop()
        if not self.stack:
            self.stack = self.old_stacks.pop()

    def parse_children(self, children):
        for child_id in children:
            child_prop = self.parser._by_id[child_id]
            self.parse(child_prop, initial=False)

    def parse_action(self, prop, initial):
        # get names for custom counters
        if prop.get("uses", None):
            sl_name = prop.get("spellListName")
            self.add_resource(f"{sl_name}: {prop['name']}" if sl_name else prop["name"], 1)
        if attrs := prop["resources"]["attributesConsumed"]:
            for attr in attrs:
                if "statName" in attr:
                    self.add_resources(attr["statName"], attr["quantity"]["value"])
                else:
                    raise AutoParserException(prop, "Resource is not tied to a specfic attribute.")

        self.set_target(prop["target"] == "self")

        # get attack bonus
        if atk_roll := prop.get("attackRoll"):
            attack = {
                "type": "attack",
                "hit": [],
                "miss": [],
                "attackBonus": str(atk_roll["value"])
            }

            self.stack[-1].append(attack)
            self.attacks.append(attack)

        self.parse_children(prop["children"])

        if atk_roll:
            self.attacks.pop()

        self.pop_stack()

    def parse_save(self, prop):
        self.set_target(prop.get("target") == "self")

        stat = prop["stat"][:3].lower()
        if stat not in STAT_ABBREVIATIONS:
            raise AutoParserException(prop, "Save did not have a valid stat type")

        save = {
            "type": "save",
            "stat": stat,
            "fail": [],
            "success": [],
            "dc": prop["dc"]["value"]
        }

        self.saves.append(save)
        self.stack[-1].append(save)
        self.parse_children(prop["children"])

    def parse_damage(self, prop):
        # all the checks for what exactly we're doing here
        magical = "magical" in prop["tags"]
        healing = prop["damageType"] == "healing"
        self.set_target(prop["target"] == "self")

        effects = [
            str(effect["amount"]["value"]).strip()
            for effect in prop["amount"].get("effects", [])
            if effect["amount"]["value"] is not None
        ]

        damage_dice = str(prop["amount"]["value"]) + "".join(
            effect if effect[0] in "+-" else f"+{effect}" for effect in effects
        )
        damage_dice = f"{'-1*(' if healing else ''}{damage_dice}{')' if healing else ''}"
        # handle all the annotated string stuff, as well as a few funcs
        damage_dice = self.convert_to_annostr(damage_dice) + f" [{'magical ' if magical else ''}{prop['damageType']}]"

        damage = {
            "type": "damage",
            "damage": damage_dice,
        }

        self.stack[-1].append(damage)
        log.debug(f"Parsing damage: {damage}")
        self.parse_children(prop["children"])

    def parse_branch(self, prop):
        parse_children = True
        match prop["branchType"]:
            case "if":
                condition = prop["condition"]["value"]

                branch = {
                    "type": "condition",
                    "condition": condition,
                    "onTrue": [],
                    "onFalse": [],
                    "errorBehaviour": "false"
                }

                self.stack[-1].append(branch)
                self.stack.append(branch["onTrue"])

            case "hit" | "miss" as hit:
                attack = self.attacks[-1][hit]
                self.stack.append(attack)
            case "successfulSave":
                save = self.saves[-1]["success"]
                self.stack.append(save)
            case "failedSave":
                save = self.saves[-1]["fail"]
                self.stack.append(save)
            case "random" | "index" as listing:
                parse_children = False
                if listing == "random":
                    child_count = len(prop["children"])
                    index = "DCV2_Random" + self.meta["random_count"]
                    variable = {
                        "type": "variable",
                        "name": index,
                        "value": f"random(1, {child_count + 1})"
                    }
                    self.meta["random_count"] += 1

                    self.stack[-1].append(variable)
                else:
                    index = prop["condition"]["value"]
                for i, child_id in enumerate(prop["children"]):
                    condition = f"({index}) == {i + 1}"
                    branch = {
                        "type": "condition",
                        "condition": condition,
                        "onTrue": [],
                        "onFalse": [],
                        "errorBehaviour": "false"
                    }
                    self.stack[-1].append(branch)
                    self.stack.append(branch["onTrue"])
                    self.parse_children([child_id])
                    self.pop_stack()
            case "eachTarget":
                self.text.append("Each Target Branch is not supported, and will not work correctly")
        if parse_children:
            self.parse_children(prop["children"])

    def parse_roll(self, prop):
        if name := prop.get("variableName"):
            roll = {
                "type": "roll",
                "dice": self.convert_to_annostr(prop["roll"]["value"]),
                "name": name,
            }
            if d_name := prop.get("name"):
                roll["displayName"] = d_name

            self.stack[-1].append(roll)
        self.parse_children(prop["children"])

    @staticmethod
    def convert_to_annostr(string: str):
        string = re.sub(IF_TRUE_FALSE, r"(\2) if (\1) else (\3)", string, re.IGNORECASE)
        string = re.sub(MAGIC_ANNOSTR_REGEX, r"\1{\2}", string)
        string = re.sub(NO_DICE_COUNT, "1d", string, re.IGNORECASE)
        string = re.sub(THE_DICE_D, r"\1d\2", string, re.IGNORECASE)
        for patt, rep in SPECIAL_FUNCS:
            string = re.sub(patt, rep, string)
        return string
