# How to update data

### Monsters
Put `bestiary.json` in `backup` and run `monster_damage_types.py`.
Output will be `backup/bestiary_typed.json`.

### Spells
Put `spells.json` in `backup` and run `spell_saves.py` first.
Then, run `auto_spell_sort.py`.
After that, move `procspells2.json` to `backup` as `auto_spells.json`.
Run `higher_levels.py`.
Move `output/auto_spells.json` to `backup/heal_spell_before_parse.json`
and run `healing_spells.py` and manually add Heal and Regenerate.
