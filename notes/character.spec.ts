// TypeScript syntax is oddly satisfying to write schemas in.
// typescript-json-schema notes/character.spec.ts Character > notes/character.spec.json
class Character {
    // Avrae-internal metadata
    owner: string;
    upstream: string;
    active: boolean;
    sheet_type: "beyond" | "dicecloud" | "google"; // older versions may be null, pdf, or beyond-pdf
    import_version: number;

    // static character information
    name: string;
    description: string;
    image: string;
    stats: {
        prof_bonus: number;
        strength: number;
        dexterity: number;
        constitution: number;
        intelligence: number;
        wisdom: number;
        charisma: number
    };
    levels: {
        total_level: number;
        classes: { string: number }; // mapping of {class_name: level}
    };
    attacks: Attack[];
    skills: { string: Skill }; // see utils/constants.py:SKILL_NAMES
    resistances: {
        resist: string[];
        immune: string[];
        vuln: string[]
    };
    saves: { string: Skill }; // see utils/constants.py:SAVE_NAMES
    ac: number;
    max_hp: number;

    // dynamic character information
    hp: number;
    temp_hp: number;
    cvars: { string: string };
    options: {
        options: { string: string }
    };
    overrides: {
        desc: string | null;
        image: string | null;
        attacks: Attack[];
        spells: SpellbookSpell[]
    };
    consumables: Consumable[];
    death_saves: {
        successes: 0;
        fails: 0
    };

    // spellbook: half-static
    spellbook: {
        slots: { string: number }; // current slots (dynamic)
        max_slots: { string: number }; // max slots (static): map of {level: number_of_slots}
        spells: SpellbookSpell[]; // list of known spells (static)
        dc: number; // spellcasting DC (static)
        sab: number; // spell attack bonus (static)
        caster_level: number; // actually total class level (used for cantrip scaling; static)
    };

    // misc metadata
    live: string | null;
    race: string;
    background: string;
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

class Consumable {
    name: string;
    value: number; // dynamic, remaining charges in counter
    minv: string; // static, min value calculation
    maxv: string; // static, max value calculation
    reset: "short" | "long" | "hp" | "none" | null; // static, when the counter should reset
    display_type: "bubble" | null; // static, how the counter should be displayed
    live_id: string | null; // metadata for live sync
}

class SpellbookSpell {
    name: string;
    strict: boolean; // whether the spell is homebrew or not
    level: null; // not implemented: the spell level
    dc: null; // not implemented: the spell's explicit DC
    sab: null // not implemented: the spell's explicit SAB
}