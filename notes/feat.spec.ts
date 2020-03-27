// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

class Feat extends DDBEntity {
    name: string;
    prerequisite: string;
    desc: string;
    // e.g.
    // ['strength'] -> Increase your Strength score by 1, up to a maximum of 20.
    // ['strength', 'dexterity'] -> Increase your Strength or Dexterity score by 1, up to a maximum of 20.
    // ['strength', 'dexterity', 'constitution'] -> Increase your Strength, Dexterity, or Constitution score by 1, up to a maximum of 20.
    ability: string[];
}

// examples:
/*
{
    "name": "Grappler",
    "prerequisite": "Strength 13",
    "desc": "You've developed the skills necessary to hold your own in close-quarters grappling. You gain the following benefits:\n- You have advantage on attack rolls against a creature you are grappling.\n- You can use your action to try to pin a creature grappled by you. To do so, make another grapple check. If you succeed, you and the creature are both restrained until the grapple ends.",
    "ability": [],
    "source": "PHB",
    "page": 167,
    "entity_id": ...
}
 */