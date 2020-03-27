// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

class Item extends DDBEntity {
    name: string;

    // displayed below the item's name
    // includes, potentially, formatted as follows:
    // {item type}, {rarity}, {rarity tier}
    // {value}, {weight} --- {weapon damage} - {weapon properties}
    // {any other information}
    meta: string | null;

    // the item's description (and weapon property long descriptions, if applicable)
    desc: string;

    // the item's image URL, if applicable
    image: string | null;

    // whether the item requires attunement, or the attunement restrictions if applicable
    attunement: boolean | string;
}

// examples:
/*
{
    "name": "Glamoured Studded Leather",
    "meta": "*Light Armor, Rare, Major*\n13 lbs. --- AC 13 + DEX\n",
    "desc": "While wearing this armor,...",
    "attunement": false,
    "image": "...",
    "source": "DMG",
    "page": 172,
    "entity_id": ...
},
{
    "name": "Staff of the Magi",
    "meta": "*Staff, Legendary, Major*\n4 lbs.\n",
    "desc": "...",
    "attunement": "by a Sorcerer, Warlock, or Wizard",
    "image": "...",
    "source": "DMG",
    "page": 203,
    "entity_id": ...
},
{
    "name": "Longsword",
    "meta": "*Melee Weapon, Martial*\n15gp, 3 lbs. --- 1d8 slashing - versatile (1d10)\n",
    "desc": "**Versatile**: This weapon can be used with one or two hands...",
    "attunement": false,
    "image": "...",
    "source": "PHB",
    "page": 149,
    "entity_id": ...
}
 */