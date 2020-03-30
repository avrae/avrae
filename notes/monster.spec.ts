// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';
// @ts-ignore
import {BaseStats, Saves, Skills, Spellbook, Attack} from './shared.spec.ts';

class Monster extends DDBEntity {
    // display:
    name: string;
    size: string;
    race: string;
    alignment: string;
    ac: number;
    armortype: string;
    hp: number;
    hitdice: string;
    speed: string;
    ability_scores: BaseStats;
    saves: Saves;
    skills: Skills;
    senses: string;
    passiveperc: number;
    display_resists: Resistances;  // used to display resistances cleanly
    condition_immune: string[];
    languages: string[];
    cr: number;
    xp: number;

    traits: Feature[];
    actions: Feature[];
    reactions: Feature[];
    legactions: Feature[];
    la_per_round: number;

    // augmented data:
    proper: boolean;  // used to determine whether to put an "A" in front of monster name when making checks
    image_url: string;  // token URL
    spellbook: MonsterSpellbook;  // may require augmentation - used to cast spells in initiative
    resistances: Resistances;  // may require augmentation

    attacks: Attack[];  // this field will require augmentation
}

class Resistances {
    resist: Resistance[];
    immune: Resistance[];
    vuln: Resistance[];
    neutral: Resistance[];
}

class Resistance {
    dtype: string;
    unless: string[];
    only: string[];
}

class Feature {
    name: string;
    desc: string;  // note desc, not text
}

class MonsterSpellbook extends Spellbook {
    at_will: string[];
    daily: Map<string, number>;
    daily_max: Map<string, number>;
}

// examples:

// Damage Immunities: fire, poison, psychic, bludgeoning, piercing, slashing from nonmagical attacks that aren't adamantine
// resistances:
/*
{
  "resist": [],
  "immune": [
    {
      "dtype": "fire"
    },
    {
      "dtype": "poison"
    },
    {
      "dtype": "psychic"
    },
    {
      "dtype": "bludgeoning",
      "unless": [
        "magical",
        "adamantine"
      ]
    },
    {
      "dtype": "piercing",
      "unless": [
        "magical",
        "adamantine"
      ]
    },
    {
      "dtype": "slashing",
      "unless": [
        "magical",
        "adamantine"
      ]
    }
  ],
  "vuln": [],
  "neutral": []
}
 */

// display_resists:
/*
{
  "resist": [],
  "immune": [
    {
      "dtype": "fire"
    },
    {
      "dtype": "poison"
    },
    {
      "dtype": "psychic"
    },
    {
      "dtype": "bludgeoning, piercing, slashing from nonmagical attacks that aren't adamantine"
    }
  ],
  "vuln": [],
  "neutral": []
}
 */

// Innate Spellcasting: The oni's innate spellcasting ability is Charisma (spell save DC 13). The oni can innately cast the following spells, requiring no material components:
// At will: darkness, invisibility
// 1/day each: charm person, cone of cold, gaseous form, sleep
/*
{
  "slots": {
    "1": 0,
    "2": 0,
    "3": 0,
    "4": 0,
    "5": 0,
    "6": 0,
    "7": 0,
    "8": 0,
    "9": 0
  },
  "max_slots": {
    "1": 0,
    "2": 0,
    "3": 0,
    "4": 0,
    "5": 0,
    "6": 0,
    "7": 0,
    "8": 0,
    "9": 0
  },
  "spells": [
    {
      "name": "Darkness",
      "strict": true
    },
    {
      "name": "Invisibility",
      "strict": true
    },
    {
      "name": "Charm Person",
      "strict": true
    },
    {
      "name": "Cone of Cold",
      "strict": true
    },
    {
      "name": "Gaseous Form",
      "strict": true
    },
    {
      "name": "Sleep",
      "strict": true
    }
  ],
  "dc": 13,
  "sab": 0,
  "caster_level": 1,
  "spell_mod": 2,
  "at_will": [
    "Darkness",
    "Invisibility"
  ],
  "daily": {
    "Charm Person": 1,
    "Cone of Cold": 1,
    "Gaseous Form": 1,
    "Sleep": 1
  },
  "daily_max": {
    "Charm Person": 1,
    "Cone of Cold": 1,
    "Gaseous Form": 1,
    "Sleep": 1
  }
}
*/

// Mage:
/*
{
  "name": "Mage",
  "size": "Medium",
  "race": "humanoid (any race)",
  "alignment": "any alignment",
  "ac": 12,
  "armortype": "15 with mage armor",
  "hp": 40,
  "hitdice": "9d8",
  "speed": "30 ft.",
  "ability_scores": {
    "prof_bonus": 3,
    "strength": 9,
    "dexterity": 14,
    "constitution": 11,
    "intelligence": 17,
    "wisdom": 12,
    "charisma": 11
  },
  "cr": "6",
  "xp": 2300,
  "passiveperc": 11,
  "senses": "",
  "resistances": {
    "resist": [],
    "immune": [],
    "vuln": [],
    "neutral": []
  },
  "condition_immune": [],
  "saves": {
    "strengthSave": {
      "value": -1
    },
    "dexteritySave": {
      "value": 2
    },
    "constitutionSave": {
      "value": 0
    },
    "intelligenceSave": {
      "value": 6,
      "prof": 1
    },
    "wisdomSave": {
      "value": 4,
      "prof": 1
    },
    "charismaSave": {
      "value": 0
    }
  },
  "skills": {
    "acrobatics": {
      "value": 2
    },
    "animalHandling": {
      "value": 1
    },
    "arcana": {
      "value": 6,
      "prof": 1
    },
    "athletics": {
      "value": -1
    },
    "deception": {
      "value": 0
    },
    "history": {
      "value": 6,
      "prof": 1
    },
    "initiative": {
      "value": 2
    },
    "insight": {
      "value": 1
    },
    "intimidation": {
      "value": 0
    },
    "investigation": {
      "value": 3
    },
    "medicine": {
      "value": 1
    },
    "nature": {
      "value": 3
    },
    "perception": {
      "value": 1
    },
    "performance": {
      "value": 0
    },
    "persuasion": {
      "value": 0
    },
    "religion": {
      "value": 3
    },
    "sleightOfHand": {
      "value": 2
    },
    "stealth": {
      "value": 2
    },
    "survival": {
      "value": 1
    },
    "strength": {
      "value": -1
    },
    "dexterity": {
      "value": 2
    },
    "constitution": {
      "value": 0
    },
    "intelligence": {
      "value": 3
    },
    "wisdom": {
      "value": 1
    },
    "charisma": {
      "value": 0
    }
  },
  "languages": [
    "any four languages"
  ],
  "traits": [
    {
      "name": "Spellcasting",
      "desc": "The mage is a 9th-level spellcaster. Its spellcasting ability is Intelligence (spell save DC 14, +6 to hit with spell attacks). The mage has the following wizard spells prepared:\nCantrips (at will): fire bolt, light, mage hand, prestidigitation\n1st level (4 slots): detect magic, mage armor, magic missile, shield\n2nd level (3 slots): misty step, suggestion\n3rd level (3 slots): counterspell, fireball, fly\n4th level (3 slots): greater invisibility, ice storm\n5th level (1 slots): cone of cold"
    }
  ],
  "actions": [
    {
      "name": "Dagger",
      "desc": "Melee or Ranged Weapon Attack: +5 to hit, reach 5 ft. or range 20/60 ft., one target. Hit: 4 (1d4 + 2) piercing damage."
    }
  ],
  "reactions": [],
  "legactions": [],
  "la_per_round": 3,
  "attacks": [
    {
      "name": "Dagger",
      "automation": [
        {
          "type": "target",
          "meta": [],
          "target": "each",
          "effects": [
            {
              "type": "attack",
              "meta": [],
              "hit": [
                {
                  "type": "damage",
                  "meta": [],
                  "damage": "1d4 + 2 [piercing]",
                  "overheal": false
                }
              ],
              "miss": [],
              "attackBonus": "5"
            }
          ]
        },
        {
          "type": "text",
          "meta": [],
          "text": "*Melee or Ranged Weapon Attack:* +5 to hit, reach 5 ft. or range 20/60 ft., one target. *Hit:* 4 (1d4 + 2) piercing damage."
        }
      ],
      "verb": null,
      "proper": null,
      "_v": 2
    }
  ],
  "proper": false,
  "image_url": null,
  "spellbook": {
    "slots": {
      "1": 4,
      "2": 3,
      "3": 3,
      "4": 3,
      "5": 1,
      "6": 0,
      "7": 0,
      "8": 0,
      "9": 0
    },
    "max_slots": {
      "1": 4,
      "2": 3,
      "3": 3,
      "4": 3,
      "5": 1,
      "6": 0,
      "7": 0,
      "8": 0,
      "9": 0
    },
    "spells": [
      {
        "name": "Fire Bolt",
        "strict": true
      },
      {
        "name": "Light",
        "strict": true
      },
      {
        "name": "Mage Hand",
        "strict": true
      },
      {
        "name": "Prestidigitation",
        "strict": true
      },
      {
        "name": "Detect Magic",
        "strict": true
      },
      {
        "name": "Mage Armor",
        "strict": true
      },
      {
        "name": "Magic Missile",
        "strict": true
      },
      {
        "name": "Shield",
        "strict": true
      },
      {
        "name": "Misty Step",
        "strict": true
      },
      {
        "name": "Suggestion",
        "strict": true
      },
      {
        "name": "Counterspell",
        "strict": true
      },
      {
        "name": "Fireball",
        "strict": true
      },
      {
        "name": "Fly",
        "strict": true
      },
      {
        "name": "Greater Invisibility",
        "strict": true
      },
      {
        "name": "Ice Storm",
        "strict": true
      },
      {
        "name": "Cone of Cold",
        "strict": true
      }
    ],
    "dc": 14,
    "sab": 6,
    "caster_level": 9,
    "spell_mod": 3,
    "at_will": [],
    "daily": {},
    "daily_max": {}
  },
  "display_resists": {
    "resist": [],
    "immune": [],
    "vuln": [],
    "neutral": []
  },
  "source": "MM",
  "page": ...,
  "entity_id": ...,
  "url": ...,
  "is_free": true
}
 */
