import {Attack, BaseStats, Skill, Spellbook, SpellbookSpell} from './shared.spec'
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
    stats: BaseStats;
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
    spellbook: Spellbook;

    // misc metadata
    live: string | null;
    race: string;
    background: string;
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

