import logging
import re

from cogs5e.models.automation import Automation
from cogs5e.models.dicecloud.errors import AutoParserException
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import chunk_text

# various regex for annotated strings
NO_DICE_COUNT = re.compile(r"(?=\s|^)d(?=[\d{])")
THE_DICE_D = re.compile(r"(?=^|\b)([\d}]+)d([\d{]+)(?=$|\b)")
IF_TRUE_FALSE = re.compile(r"([^?(]*)\?([^:]*):([^)]*)")
MAGIC_ANNOSTR_REGEX = re.compile(
    r"(\s*)(\(?\s*?(?:(?<!\w)\d+(?!\d*d\d+(?=\s|$|\b)).*?)?"
    r"(?:(?:[a-ce-zA-Z_]|d(?!\d+(?=\s|$|\b)))\w*).*?\)?)(?=$|\s*[+\-*/]?[+\-*/(\d\s]*(?:\d*d\d+))"
)
SPECIAL_FUNCS = (
    (re.compile(r"\btrunc\b"), "int"),
    (re.compile(r"sign\(([^\)]*)\)"), r"((\1) and round((\1)/abs(\1)))"),
)

log = logging.getLogger(__name__)


class DCV2AutoParser:
    def __init__(self, parser):
        self.parser = parser

        # where the actual automation is stored
        self.auto = []

        # the stack for where new effects should go, and the correlating effects
        self.stack = [self.auto]
        self.stack_effects = []

        # storage for some effects we need to refer back to
        self.saves = []
        self.attacks = []
        self.ieffects = []
        self.target = {}
        self.targets = []

        self.meta = {"target_count": 0, "random_count": 0}
        self.text = []

    def get_automation(self, prop):
        self.parse(prop, initial=True)

        # the insert the action description as the first text
        desc = prop.get("summary", {}).get("value") or prop.get("description", {}).get("value")
        if desc:
            self.text.insert(0, desc)

        # add all the text as text effects
        for text in self.text:
            for chunk in chunk_text(text):
                # fmt: off
                self.auto.append({
                    "type": "text",
                    "text": chunk,
                })
                # fmt: on

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
                case "toggle":
                    # since all properties under actions are inactive, we have to check the toggles
                    if prop["condition"]["value"]:
                        self.parse_children(prop["children"])
                case "branch":
                    self.parse_branch(prop)
                case "note":
                    # we only use the summary here, since it's all DC would display
                    desc = prop.get("summary", {}).get("value")
                    if desc is not None:
                        self.text.append(desc)
                    self.parse_children(prop["children"])
                case "roll":
                    self.parse_roll(prop)
                case "buff":
                    self.parse_buff(prop)
                # everything else does nothing and just runs its children
                case _:
                    self.parse_children(prop["children"])
        except AutoParserException:
            raise
        except Exception as e:
            log.debug(str(e))
            raise AutoParserException(prop, "Auto Parser encounter an error parsing a property") from e

    def add_resource(self, name, amt=1):
        # initial action resources are only processed once, so we want to do them all at once
        # fmt: off
        self.auto.insert(0, {
            "type": "counter",
            "counter": name,
            "amount": str(amt),
        })
        # fmt: on

    # makes sure that the current target hasn't changed, handling it if it has
    def set_target(self, target):
        target = "self" if target == "self" or self.meta["always_self"] else "all"

        # fmt: off
        target_node = {
            "type": "target",
            "target": target,
            "effects": [],
        }
        # fmt: on

        # handles the swapping of targets, since Avrae does not allow target switching
        if self.target and (self.target["target"] != target) and self.target in self.stack_effects:
            # internal variable to only run this target if we reach this part on the original
            variable_name = f"DCV2_TARGET{self.meta['target_count']}"
            self.meta["target_count"] += 1

            # fmt: off
            variable = {
                "type": "variable",
                "name": variable_name,
                "value": "True",
            }

            # branch that actually handles the check
            branch = {
                "type": "condition",
                "condition": f"{variable_name}",
                "onTrue": [],
                "onFalse": [],
                "errorBehaviour": "false",
            }
            # fmt: on

            self.stack[-1].append(variable)
            self.auto.append(branch)
            branch["onTrue"].append(target_node)
        elif self.target.get("target") == target:
            self.push_effect_stack(self.stack[-1], self.stack_effects[-1])
            return
        else:
            self.auto.append(target_node)

        # swap the current target
        self.target = target_node

        self.push_effect_stack(target_node["effects"], target_node)

    # pops the stack, removing both the node and the effect
    def pop_effect_stack(self):
        self.stack.pop()
        self.stack_effects.pop()

    def push_effect_stack(self, focus, effect):
        self.stack.append(focus)
        self.stack_effects.append(effect)

    # retrieves and parses the children based on the IDs provided by the property
    def parse_children(self, children):
        for child_id in children:
            child_prop = self.parser._by_id[child_id]
            self.parse(child_prop)

    def parse_action(self, prop, initial):
        # resources are only used for the initial action
        if initial:
            self.meta["always_self"] = prop["target"] == "self"
            if prop.get("uses", None):
                sl_name = prop.get("spellListName")
                self.add_resource(f"{sl_name}: {prop['name']}" if sl_name else prop["name"], 1)
            if attrs := prop["resources"]["attributesConsumed"]:
                for attr in attrs:
                    if "statName" in attr:
                        self.add_resource(attr["statName"], attr["quantity"]["value"])
                    else:
                        raise AutoParserException(prop, "Resource is not tied to a specfic attribute.")

        self.set_target(prop["target"])

        # creates the attack effect
        if atk_roll := prop.get("attackRoll"):
            # fmt: off
            attack = {
                "type": "attack",
                "hit": [],
                "miss": [],
                "attackBonus": str(atk_roll["value"]),
            }
            # fmt: on

            # keep a reference to the attack node for branches
            self.attacks.append(attack)
            self.stack[-1].append(attack)

        self.parse_children(prop["children"])

        if atk_roll:
            self.attacks.pop()

        self.pop_effect_stack()

    def parse_save(self, prop):
        self.set_target(prop["target"])

        stat = prop["stat"][:3].lower()
        if stat not in STAT_ABBREVIATIONS:
            raise AutoParserException(prop, "Save did not have a valid stat type")

        # fmt: off
        save = {
            "type": "save",
            "stat": stat,
            "fail": [],
            "success": [],
            "dc": prop["dc"]["value"],
        }
        # fmt: on

        # keep a reference to the save node for branches
        self.saves.append(save)
        self.stack[-1].append(save)
        self.parse_children(prop["children"])

        self.saves.pop()
        self.pop_effect_stack()

    def parse_damage(self, prop):
        # all the checks for what exactly we're doing here
        magical = "magical" in prop["tags"]
        healing = prop["damageType"] == "healing"
        self.set_target(prop["target"])

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

        # fmt: off
        damage = {
            "type": "damage",
            "damage": damage_dice,
        }
        # fmt: on

        self.stack[-1].append(damage)
        log.debug(f"Parsing damage: {damage}")
        self.parse_children(prop["children"])

        self.pop_effect_stack()

    def parse_branch(self, prop):
        # setup variables for whether children should be parsed, and if we should remove an entry from the stack
        parse_children = True
        pop_stack = False
        match prop["branchType"]:
            # if condition is true
            case "if":
                pop_stack = True
                condition = prop["condition"]["value"]

                # fmt: off
                branch = {
                    "type": "condition",
                    "condition": condition,
                    "onTrue": [],
                    "onFalse": [],
                    "errorBehaviour": "false",
                }
                # fmt: on

                self.stack[-1].append(branch)
                self.push_effect_stack(branch["onTrue"], branch)
            # attack hit/miss
            case "hit" | "miss" as hit:
                pop_stack = True
                if self.attacks:
                    attack = self.attacks[-1][hit]
                    self.push_effect_stack(attack, self.attacks[-1])
                else:
                    raise AutoParserException(
                        prop, f"Could not find an attack that is a parent of this on {hit} branch."
                    )
            # save failed/succeeded
            case "successfulSave" | "failedSave" as state:
                state = "success" if state == "successfulSave" else "fail"
                pop_stack = True
                if self.saves:
                    save = self.saves[-1][state]
                    self.push_effect_stack(save, self.saves[-1])
                else:
                    raise AutoParserException(prop, f"Could not find a save that is a parent of this {state} branch.")
            # lots of individual branches need to be generated to handle these
            case "random" | "index" as listing:
                parse_children = False
                if listing == "random":
                    child_count = len(prop["children"])
                    # if the list is random, make a variable that stores a random number
                    index = f"DCV2_RANDOM{self.meta['random_count']}"

                    # fmt: off
                    variable = {
                        "type": "variable",
                        "name": index,
                        "value": f"random(1, {child_count + 1})",
                    }
                    # fmt: on

                    self.meta["random_count"] += 1

                    self.stack[-1].append(variable)
                else:
                    # this should be able to be parsed as an int expression,
                    # though if someone included dice here i'm going to scream
                    index = prop["condition"]["value"]

                # create all the branches to handle each result
                for i, child_id in enumerate(prop["children"]):
                    condition = f"({index}) == {i + 1}"

                    # fmt: off
                    branch = {
                        "type": "condition",
                        "condition": condition,
                        "onTrue": [],
                        "onFalse": [],
                        "errorBehaviour": "false",
                    }
                    # fmt: on

                    self.stack[-1].append(branch)
                    self.push_effect_stack(branch["onTrue"], branch)
                    self.parse_children([child_id])
                    self.pop_effect_stack()
            # would require knowing number of targets ahead of time,
            # since this generally only applies when switching targets
            case "eachTarget":
                self.text.append("Each Target branch is not supported, and will not work correctly")
        if parse_children:
            self.parse_children(prop["children"])
        if pop_stack:
            self.pop_effect_stack()

    # create the roll effect from the property, pretty straightforward
    def parse_roll(self, prop):
        if name := prop.get("variableName"):
            # fmt: off
            roll = {
                "type": "roll",
                "dice": self.convert_to_annostr(str(prop["roll"]["value"])),
                "name": name,
            }
            # fmt: on

            if d_name := prop.get("name"):
                roll["displayName"] = d_name

            self.stack[-1].append(roll)
        self.parse_children(prop["children"])

    def parse_buff(self, prop):
        self.set_target(prop["target"])

        # fmt: off
        ieffect = {
            "type": "ieffect2",
            "name": prop["name"],
            "effects": {},
            "attacks": [],
            "stacking": True,
        }
        # fmt: on

        # TODO: not implemented yet
        # self.ieffects.append(ieffect)
        self.stack[-1].append(ieffect)

        # for child_id in prop["children"]:
        #     child_prop = self.parser._by_id[child_id]
        #     self.parse_buff_child(child_prop)

        # self.ieffects.pop()

    @staticmethod
    def convert_to_annostr(string: str):
        string = re.sub(IF_TRUE_FALSE, r"(\2) if (\1) else (\3)", string, re.IGNORECASE)
        string = re.sub(MAGIC_ANNOSTR_REGEX, r"\1{\2}", string)
        string = re.sub(NO_DICE_COUNT, "1d", string, re.IGNORECASE)
        string = re.sub(THE_DICE_D, r"\1d\2", string, re.IGNORECASE)
        for patt, rep in SPECIAL_FUNCS:
            string = re.sub(patt, rep, string)
        return string
