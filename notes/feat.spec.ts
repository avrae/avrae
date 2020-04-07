// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

class Feat extends DDBEntity {
    name: string;
    prerequisite: string | null;
    description: string;
    // e.g.
    // ['strength'] -> Increase your Strength score by 1, up to a maximum of 20.
    // ['strength', 'dexterity'] -> Increase your Strength or Dexterity score by 1, up to a maximum of 20.
    // ['strength', 'dexterity', 'constitution'] -> Increase your Strength, Dexterity, or Constitution score by 1, up to a maximum of 20.
    ability: string[];
}

// examples:
/*
{
  "id": 10,
  "entityType": "feat",
  "name": "Grappler",
  "prerequisite": "Strength 13 or higher.",
  "description": "You've developed the skills necessary to hold your own in close-quarters grappling. You gain the following benefits:\n\n\n-You have advantage on attack rolls against a creature you are grappling.\n-You can use your action to try to pin a creature grappled by you. To do so, make another grapple check. If you succeed, you and the creature are both restrained until the grapple ends.\n\n",
  "ability": [],
  "url": "https://www.dndbeyond.com/feats/grappler",
  "isFree": true,
  "source": "BR",
  "page": 167
}
 */