class BaseStats {
    prof_bonus: number;
    strength: number;
    dexterity: number;
    constitution: number;
    intelligence: number;
    wisdom: number;
    charisma: number
}

class Skill {
    // value = base_skill + (prof * prof_bonus) + bonus
    value: number; // the final calculated bonus
    prof?: 0 | 0.5 | 1 | 2;  // none, joat, prof, expertise, default 0
    bonus?: number; // misc bonuses, default 0
    adv?: null | true | false; // none, adv, dis, default none
}

class Attack {
    name: string;
    automation: object[];  // see https://avrae.readthedocs.io/en/latest/automation_ref.html
    verb: string;
    proper: boolean;
}

class Spellbook {
    slots: { string: number }; // current slots (dynamic)
    max_slots: { string: number }; // max slots (static): map of {level: number_of_slots}
    spells: SpellbookSpell[]; // list of known spells (static)
    dc: number; // spellcasting DC (static)
    sab: number; // spell attack bonus (static)
    caster_level: number; // actually total class level (used for cantrip scaling; static)
    spell_mod: number; // the spellcasting ability modifier
}

class SpellbookSpell {
    name: string;
    strict: boolean; // whether the spell is homebrew or not
    level: null; // not implemented: the spell level
    dc: null; // not implemented: the spell's explicit DC
    sab: null // not implemented: the spell's explicit SAB
}

class Saves {
    strengthSave: Skill;
    dexteritySave: Skill;
    constitutionSave: Skill;
    intelligenceSave: Skill;
    wisdomSave: Skill;
    charismaSave: Skill;
}

class Skills {
    acrobatics: Skill;
    animalHandling: Skill;
    arcana: Skill;
    athletics: Skill;
    deception: Skill;
    history: Skill;
    initiative: Skill;
    insight: Skill;
    intimidation: Skill;
    investigation: Skill;
    medicine: Skill;
    nature: Skill;
    perception: Skill;
    performance: Skill;
    persuasion: Skill;
    religion: Skill;
    sleightOfHand: Skill;
    stealth: Skill;
    survival: Skill;
    strength: Skill;
    dexterity: Skill;
    constitution: Skill;
    intelligence: Skill;
    wisdom: Skill;
    charisma: Skill;
}
