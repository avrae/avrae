class LegacyRawCharacter:
    def __init__(self, character):
        self.character = character
        self.result = None

    def to_dict(self):
        if not self.result:
            self.parse()
        return self.result

    def parse(self):
        skills, skill_effects = self.legacy_skills()
        out = {
            "owner": self.character.owner,
            "upstream": self.character.upstream,
            "type": self.character.sheet_type,

            "armor": self.character.ac,
            "hp": self.character.max_hp,

            "immune": self.character.resistances.immune,
            "resist": self.character.resistances.resist,
            "vuln": self.character.resistances.vuln,

            "background": self.character.background,
            "race": self.character.race,

            "attacks": self.legacy_attacks(),
            "levels": self.legacy_levels(),
            "consumables": self.legacy_consumables(),

            "skill_effects": skill_effects,
            "skills": skills,
            "saves": self.legacy_saves(),

            "spellbook": self.legacy_spellbook(),

            "settings": self.character.options.options
        }
        self.result = out
        return out

    def legacy_attacks(self):
        out = []
        for attack in self.character.attacks:
            out.append(attack.to_old())
        return out

    def legacy_levels(self):
        out = {
            "level": self.character.levels.total_level
        }
        for cls, lvl in self.character.levels:
            out[f"{cls}Level"] = lvl
        return out

    def legacy_consumables(self):
        out = {}
        for counter in self.character.consumables:
            out[counter.name] = {
                'value': counter.value, 'max': counter.max, 'min': counter.min, 'reset': counter.reset_on,
                'type': counter.display_type
            }
        return {"custom": out}

    def legacy_skills(self):
        skills = {}
        effects = {}
        for name, skill in self.character.skills.skills.items():
            skills[name] = skill.value
            if skill.adv is True:
                effects[name] = 'adv'
            elif skill.adv is False:
                effects[name] = 'dis'
        return skills, effects

    def legacy_saves(self):
        saves = {}
        for name, save in self.character.saves.saves.items():
            saves[name] = save.value
        return saves

    def legacy_spellbook(self):
        spells = []
        for spell in self.character.spellbook.spells:
            spells.append({"name": spell.name, "strict": spell.strict})
        out = {
            "spellslots": self.character.spellbook.max_slots,
            "spells": spells,
            "dc": self.character.spellbook.dc,
            "attackBonus": self.character.spellbook.sab
        }
        return out
