// TypeScript syntax is oddly satisfying to write schemas in.
// typescript-json-schema notes/character.spec.ts Character > notes/character.spec.json
class Character {
    owner: string;
    upstream: string;
    active: boolean;
    sheet_type: "beyond" | "dicecloud" | "google"; // older versions may be null, pdf, or beyond-pdf
    import_version: number;
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
        classes: { string: number }[];
    };
    attacks: Attack[];
    skills: { string: Skill };
    resistances: {
        resist: string[];
        immune: string[];
        vuln: string[]
    };
    saves: { string: Skill };
    ac: number;
    max_hp: number;
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
    spellbook: {
        slots: { string: number };
        max_slots: { string: number };
        spells: SpellbookSpell[];
        dc: number;
        sab: number;
        caster_level: number;
    };
    live: string | null;
    race: string;
    background: string;
}

class Skill {
    value: number;
    prof: 0 | 0.5 | 1 | 2;
    bonus: number;
    adv: null | true | false;
}

class Attack {
    name: string;
    bonus: number;
    damage: string;
    details: string;
    bonus_calc: string;
    damage_calc: string;
}

class Consumable {
    name: string;
    value: number;
    minv: string;
    maxv: string;
    reset: "short" | "long" | "hp" | "none" | null;
    display_type: "bubble" | null;
    live_id: string | null;
}

class SpellbookSpell {
    name: string;
    strict: boolean;
    level: number;
    dc: null;
    sab: null
}