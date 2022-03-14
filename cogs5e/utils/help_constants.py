"""
Constants to help write help docs.
"""

__all__ = ("VALID_CHECK_ARGS", "VALID_SAVE_ARGS", "VALID_AUTOMATION_ARGS", "VALID_SPELLCASTING_ARGS")

# ==== check args ====
VALID_CHECK_ARGS = """
__Valid Arguments__
*adv/dis* - Give advantage/disadvantage to the check roll(s).
*-b <bonus>* - Adds a bonus to the roll.
-dc <dc> - Sets a DC and counts successes/failures.
-mc <minimum roll> - Sets the minimum roll on the dice (e.g. Reliable Talent, Glibness)
-rr <iterations> - How many checks to roll.
str/dex/con/int/wis/cha - Rolls using a different skill base (e.g. Strength (Intimidation))

-phrase <phrase> - Adds flavor text.
-title <title> - Changes the title of the attack. Replaces [name] with caster's name and [cname] with the check's name.
-f "Field Title|Field Text" - Creates a field with the given title and text (see `!help embed`).
-thumb <url> - Adds a thumbnail to the result.
-h - Hides the name and image of the caster.
[user snippet]

An italicized argument means the argument supports ephemeral arguments - e.g. `-b1` applies a bonus to one check.
""".strip()

# ==== save args ====
VALID_SAVE_ARGS = """
__Valid Arguments__
*adv/dis* - Give advantage/disadvantage to the save roll(s).
*-b <bonus>* - Adds a bonus to the roll.
-dc <dc> - Sets a DC and counts successes/failures.
-rr <iterations> - How many saves to roll (does not apply to Death Saves).

-phrase <phrase> - Adds flavor text.
-title <title> - Changes the title of the attack. Replaces [name] with caster's name and [sname] with the save's name.
-f "Field Title|Field Text" - Creates a field with the given title and text (see `!help embed`).
-thumb <url> - Adds a thumbnail to the result.
-h - Hides the name and image of the caster.
[user snippet]

An italicized argument means the argument supports ephemeral arguments - e.g. `-b1` applies a bonus to one save.
""".strip()

# ==== automation args ====
VALID_AUTOMATION_ARGS = """
**Targeting**
-t "<target>" - Sets targets for the attack. You can pass as many as needed.
-t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)
-rr <num> - How many attacks to make at each target.

An italicized argument below means the argument supports ephemeral arguments - e.g. `-d1` applies damage to the first hit, `-b1` applies a bonus to one attack, and so on.

**To Hit**
*adv/dis* - Give advantage or disadvantage to the attack roll(s).
*ea* - Elven Accuracy, double advantage on the attack roll.
*hit* - The attack automatically hits.
*miss* - The attack automatically misses.
*-attackroll <value>* - Force the rolled attack to be a fixed number plus modifiers.
*crit* - The attack automatically crits.
-ac <target ac> - Overrides target AC.
*-b <bonus>* - Adds a bonus to hit.
-criton <value> - The number the attack crits on if rolled on or above.

**Saves**
*pass* - Target automatically succeeds the saving throw.
*fail* - Target automatically fails the saving throw.
sadv/sdis - Gives the target advantage/disadvantage on the saving throw.
-dc <dc> - Overrides the DC of the save.
-dc <+X/-X> - Modifies the DC by a certain amount.
*-sb <bonus>* - Adds a bonus to saving throws.
-save <save type> - Overrides the spell save type (e.g. `-save str`).

**Damage**
*max* - Maximizes damage rolls.
*nocrit* - Does not double the dice on a crit.
*-d <damage>* - Adds additional damage.
*-c <damage>* - Adds additional damage for when the attack crits, not doubled.
*-mi <value>* - Minimum value of each die on the damage roll.

__Damage Types__
*magical* - Makes the damage type of the attack magical.
*silvered* - Makes the damage type of the attack silvered.
*-dtype <new type>* - Changes all damage types to a new damage type.
*-dtype "old>new"* - Changes all parts of the damage roll that do "old" damage type to deal "new" damage type (e.g. `-dtype fire>cold`)
*-resist <damage type>* - Gives the target resistance to the given damage type.
*-immune <damage type>* - Gives the target immunity to the given damage type.
*-vuln <damage type>* - Gives the target vulnerability to the given damage type.
*-neutral <damage type>* - Removes the target's immunity, resistance, or vulnerability to the given damage type.

**Effects**
-dur <duration> - Overrides the duration of any effect applied by the attack.

**Counters**
-amt <amount> - Overrides the amount of the resource used.
-l <level> - Specifies the level of the spell slot to use.
nopact - Uses a normal spell slot instead of a Pact Magic slot, if applicable.
-i - Skips using any resources.

**Other**
-h - Hides rolled values.
-phrase <phrase> - Adds flavor text.
-title <title> - Changes the title of the attack. Replaces [name] with the caster's name, [aname] with the action's name, and [verb] with the action's verb.
-f "Field Title|Field Text" - Creates a field with the given title and text.
-thumb <url> - Adds a thumbnail to the attack.
[user snippet] - Allows the user to use snippets on the attack.
""".strip()

# ==== spellcasting args ====
VALID_SPELLCASTING_ARGS = """
**Spellcasting**
-i - Ignores Spellbook restrictions (e.g. when casting from an item, as a ritual, etc.)
-l <level> - Specifies the level to cast the spell at.
-mod <spellcasting mod> - Overrides the value of the spellcasting ability modifier.
-with <int/wis/cha> - Uses a different skill base for DC/AB (will not account for extra bonuses)
noconc - Ignores concentration requirements.
nopact - Uses a normal spell slot instead of a Pact Magic slot, if applicable.
""".strip()
