// @ts-ignore
import DDBEntity from './ddbentity.spec.ts';

class Background extends DDBEntity {
    name: string;
    traits: Trait[];
}

class Trait {
    name: string;
    text: string; // Markdown-formatted
}

// examples:
// note: traits with the name
// ['suggested characteristics', 'personality trait', 'ideal', 'bond', 'flaw', 'specialty', 'harrowing event']
// are ignored and not displayed in lookups, since they're big tables of text
// these traits can be simply not included in the data
/*
{
    "name": "Acolyte",
    "traits": [
        {
            "name": "Skill Proficiencies",
            "text": "Insight, Religion"
        },
        {
            "name": "Languages",
            "text": "Two of your choice"
        },
        {
            "name": "Equipment",
            "text": "A holy symbol (a gift to you when you entered the priesthood),..."
        },
        {
            "name": "Feature: Shelter of the Faithful",
            "text": "As an acolyte, you command the respect of those who share your faith,..."
        },
        {
            "name": "Suggested Characteristics",
            "text": "..."
        }
    ],
    "source": "PHB",
    "page": 127,
    "entity_id": ...,
    "url": ...
}
 */