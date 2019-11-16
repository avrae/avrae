import {BaseStats, Skill} from './shared.spec';
import Feature from './feature.spec'

class Monster {
    name: string;
    size: "Tiny" | "Small" | "Medium" | "Large" | "Huge" | "Gargantuan";
    race: string;
    alignment: string;
    ac: number;
    armortype: string;
    hp: number;
    hitdice: string;
    speed: string;
    ability_scores: BaseStats;
    cr: number;
    xp: number;
    passiveperc: number;
    senses: string;
    vuln: string[];
    resist: string[];
    immune: string[];
    condition_immune: string[];
    saves: { string: Skill }; // see utils/constants.py:SAVE_NAMES;
    skills: { string: Skill }; // see utils/constants.py:SKILL_NAMES;
    languages: string[];
    traits: Feature[];
    actions: Feature[];
    reactions: Feature[];
    legactions: Feature[];
    la_per_round: number;
    srd: boolean;
    source: string;
    attacks: Attack[];
    proper: boolean;
    image_url: string;
    spellbook: Spellbook;
    raw_resists: string;
}