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
    prof: 0 | 0.5 | 1 | 2;  // none, joat, prof, expertise
    bonus: number; // misc bonuses
    adv: null | true | false; // none, adv, dis
}

class Attack {
    name: string;
    bonus: number; // to-hit bonus, can be null
    damage: string; // damage dice string, can be null
    details: string; // text to output (attack description)
    bonus_calc: string; // the bonus calculation (usually for user-added attacks)
    damage_calc: string; // the damage calculation (usually for user-added attacks)
}

class Spellbook {
    slots: { string: number }; // current slots (dynamic)
    max_slots: { string: number }; // max slots (static): map of {level: number_of_slots}
    spells: SpellbookSpell[]; // list of known spells (static)
    dc: number; // spellcasting DC (static)
    sab: number; // spell attack bonus (static)
    caster_level: number; // actually total class level (used for cantrip scaling; static)
}

class SpellbookSpell {
    name: string;
    strict: boolean; // whether the spell is homebrew or not
    level: null; // not implemented: the spell level
    dc: null; // not implemented: the spell's explicit DC
    sab: null // not implemented: the spell's explicit SAB
}