// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

class Spell extends DDBEntity {
    // display
    name: string;
    level: number;
    school: string;
    classes: string[];  // list of classes that have on spell list
    subclasses: string[];  // list of subclasses that implicitly grant spell
    casttime: string;
    range: string;
    components: string;  // formatted e.g. "V, S, M (an IP address)"
    duration: string;  // if concentration, "Concentration, up to ..."
    description: string;
    ritual: boolean;
    higherlevels: string;

    // augmented
    concentration: boolean;
    automation: object[];  // will require augmentation
}

// examples:
/*
{
  "name": "Fireball",
  "level": 3,
  "school": "Evocation",
  "casttime": "1 action",
  "range": "150 feet",
  "components": "V, S, M (a tiny ball of bat guano and sulfur)",
  "duration": "Instantaneous",
  "description": "A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame. Each creature in a 20-foot-radius sphere centered on that point must make a Dexterity saving throw. A target takes 8d6 fire damage on a failed save, or half as much damage on a successful one.\nThe fire spreads around corners. It ignites flammable objects in the area that aren't being worn or carried.",
  "classes": [
    "Sorcerer",
    "Wizard"
  ],
  "subclasses": [
    "Cleric (Light)",
    "Warlock (Fiend)"
  ],
  "ritual": false,
  "higherlevels": "When you cast this spell using a spell slot of 4th level or higher, the damage increases by 1d6 for each slot level above 3rd.",
  "concentration": false,
  "automation": [
    {
      "type": "target",
      "target": "all",
      "effects": [
        {
          "type": "save",
          "stat": "dex",
          "fail": [
            {
              "type": "damage",
              "damage": "{damage}"
            }
          ],
          "success": [
            {
              "type": "damage",
              "damage": "({damage})/2"
            }
          ]
        }
      ],
      "meta": [
        {
          "type": "roll",
          "dice": "8d6[fire]",
          "name": "damage",
          "higher": {
            "4": "1d6[fire]",
            "5": "2d6[fire]",
            "6": "3d6[fire]",
            "7": "4d6[fire]",
            "8": "5d6[fire]",
            "9": "6d6[fire]"
          }
        }
      ]
    },
    {
      "type": "text",
      "text": "Each creature in a 20-foot radius must make a Dexterity saving throw. A target takes 8d6 fire damage on a failed save, or half as much damage on a successful one."
    }
  ],
  "source": "PHB",
  "page": 241,
  "entity_id": ...,
  "url": ...,
  "is_free": true
}
 */