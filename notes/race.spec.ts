// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

type Ability = 'str' | 'dex' | 'con' | 'int' | 'wis' | 'cha';

class Race extends DDBEntity {
    name: string;
    size: string;
    speed: string;
    ability: { Ability: number };  // e.g. {'str': 1, 'dex': 2}
    traits: Trait[];
}

class Trait {
    name: string;
    text: string; // Markdown-formatted
}

// examples:
/*
{
  "name": "Elf (High)",
  "size": "Medium",
  "speed": "30 ft.",
  "ability": {
    "dex": 2,
    "int": 1
  },
  "traits": [
    {
      "name": "Age",
      "text": "Although elves reach physical maturity at about the same age as humans, the elven understanding of adulthood goes beyond physical growth to encompass worldly experience. An elf typically claims adulthood and an adult name around the age of 100 and can live to be 750 years old."
    },
    {
      "name": "Alignment",
      "text": "Elves love freedom, variety, and self-expression, so they lean strongly toward the gentler aspects of chaos. They value and protect others' freedom as well as their own, and they are more often good than not."
    },
    {
      "name": "Size",
      "text": "Elves range from under 5 to over 6 feet tall and have slender builds. Your size is Medium."
    },
    {
      "name": "Darkvision",
      "text": "Accustomed to twilit forests and the night sky, you have superior vision in dark and dim conditions. You can see in dim light within 60 feet of you as if it were bright light, and in darkness as if it were dim light. You can't discern color in darkness, only shades of gray."
    },
    {
      "name": "Keen Senses",
      "text": "You have proficiency in the Perception skill."
    },
    {
      "name": "Fey Ancestry",
      "text": "You have advantage on saving throws against being charmed, and magic can't put you to sleep."
    },
    {
      "name": "Trance",
      "text": "Elves don't need to sleep. Instead, they meditate deeply, remaining semiconscious, for 4 hours a day. (The Common word for such meditation is \"trance.\") While meditating, you can dream after a fashion; such dreams are actually mental exercises that have become reflexive through years of practice. After resting in this way, you gain the same benefit that a human does from 8 hours of sleep.\nIf you meditate during a long rest, you finish the rest after only 4 hours. You otherwise obey all the rules for a long rest; only the duration is changed."
    },
    {
      "name": "Languages",
      "text": "You can speak, read, and write Common and Elvish. Elvish is fluid, with subtle intonations and intricate grammar. Elven literature is rich and varied, and their songs and poems are famous among other races. Many bards learn their language so they can add Elvish ballads to their repertoires."
    },
    {
      "name": "Elf Weapon Training",
      "text": "You have proficiency with the longsword, shortsword, shortbow, and longbow."
    },
    {
      "name": "Cantrip",
      "text": "You know one cantrip of your choice from the wizard spell list. Intelligence is your spellcasting ability for it."
    },
    {
      "name": "Extra Language",
      "text": "You can speak, read, and write one extra language of your choosing."
    }
  ],
  "source": "PHB",
  "page": ...,
  "entity_id": ...,
  "url": ...,
  "is_free": true
}
 */