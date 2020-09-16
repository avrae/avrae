# ==== useful constants ====
RESIST_TYPES = ('resist', 'immune', 'vuln', 'neutral')
DAMAGE_TYPES = ('acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing', 'poison',
                'psychic', 'radiant', 'slashing', 'thunder')

STAT_NAMES = ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')

STAT_ABBREVIATIONS = ('str', 'dex', 'con', 'int', 'wis', 'cha')

SKILL_NAMES = ('acrobatics', 'animalHandling', 'arcana', 'athletics', 'deception', 'history', 'initiative', 'insight',
               'intimidation', 'investigation', 'medicine', 'nature', 'perception', 'performance', 'persuasion',
               'religion', 'sleightOfHand', 'stealth', 'survival', 'strength', 'dexterity', 'constitution',
               'intelligence', 'wisdom', 'charisma')

SAVE_NAMES = ('strengthSave', 'dexteritySave', 'constitutionSave', 'intelligenceSave', 'wisdomSave', 'charismaSave')

SKILL_MAP = {'acrobatics': 'dexterity', 'animalHandling': 'wisdom', 'arcana': 'intelligence', 'athletics': 'strength',
             'deception': 'charisma', 'history': 'intelligence', 'initiative': 'dexterity', 'insight': 'wisdom',
             'intimidation': 'charisma', 'investigation': 'intelligence', 'medicine': 'wisdom',
             'nature': 'intelligence', 'perception': 'wisdom', 'performance': 'charisma',
             'persuasion': 'charisma', 'religion': 'intelligence', 'sleightOfHand': 'dexterity', 'stealth': 'dexterity',
             'survival': 'wisdom', 'strengthSave': 'strength', 'dexteritySave': 'dexterity',
             'constitutionSave': 'constitution', 'intelligenceSave': 'intelligence', 'wisdomSave': 'wisdom',
             'charismaSave': 'charisma',
             'strength': 'strength', 'dexterity': 'dexterity', 'constitution': 'constitution',
             'intelligence': 'intelligence', 'wisdom': 'wisdom', 'charisma': 'charisma'}

SOURCE_MAP = {
    'BR': 'Basic Rules', 'PHB': "Player's Handbook", 'DMG': "Dungeon Master's Guide",
    'EE': "Elemental Evil Player's Companion", 'MM': 'Monster Manual', 'CoS': 'Curse of Strahd',
    'HotDQ': 'Hoard of the Dragon Queen', 'LMoP': 'Lost Mine of Phandelver', 'OotA': 'Out of the Abyss',
    'PotA': 'Princes of the Apocalypse', 'RoT': 'Rise of Tiamat', 'SKT': "Storm King's Thunder",
    'SCAG': "Sword Coast Adventurer's Guide", 'TftYP': 'Tales from the Yawning Portal',
    'VGtM': "Volo's Guide to Monsters", 'TSC': 'The Sunless Citadel', 'TFoF': 'The Forge of Fury',
    'THSoT': 'The Hidden Shrine of Tamoachan', 'WPM': 'White Plume Mountain', 'DiT': 'Dead in Thay',
    'AtG': 'Against the Giants', 'ToH': 'Tomb of Horrors', 'ToA': 'Tomb of Annihilation',
    'CoSCO': 'Curse of Strahd: Character Options', 'XGtE': "Xanathar's Guide to Everything",
    'TTP': 'The Tortle Package', 'UA': 'Unearthed Arcana', 'DDB': 'D&D Beyond', 'CR': 'Critical Role',
    'TCS': "Tal'Dorei Campaign Setting", 'MToF': 'Mordenkainen’s Tome of Foes', 'DDIA-MORD': 'Rrakkma',
    'WDH': 'Waterdeep: Dragon Heist', 'WDotMM': 'Waterdeep: Dungeon of the Mad Mage',
    'WGtE': "Wayfinder's Guide to Eberron", 'GGtR': "Guildmasters' Guide to Ravnica", '_APT': 'Archived Playtest',
    'LLoK': 'Lost Laboratory of Kwalish', 'DoIP': 'Dragon of Icespire Peak', 'TMR': 'Tactical Maps Reincarnated',
    'GoS': 'Ghosts of Saltmarsh', 'AI': 'Acquisitions Incorporated', 'HftT': 'Hunt for the Thessalhydra',
    'BGDiA': "Baldur's Gate: Descent into Avernus", 'ERftLW': 'Eberron: Rising from the Last War',
    'SLW': 'Storm Lord’s Wrath', 'SDW': 'Sleeping Dragon’s Wake', 'DC': 'Divine Contention',
    'SAC': 'Sage Advice Compendium', 'DDvRaM': 'Dungeons & Dragons vs. Rick and Morty', 'LR': 'Locathah Rising',
    'IMR': 'Infernal Machine Rebuild', 'MFFV1': "Mordenkainen's Fiendish Folio Volume 1", 'SD': 'Sapphire Dragon',
    'EGtW': "Explorer's Guide to Wildemount", 'OGA': 'One Grung Above', 'MOoT': 'Mythic Odysseys of Theros',
    'WA': 'Frozen Sick', 'TSCF': 'The Sunless Citadel (Free)', 'TFoFF': 'The Forge of Fury (Free)',
    'LRDToB': 'Legends of Runeterra: Dark Tides of Bilgewater', 'IDRotF': 'Icewind Dale: Rime of the Frostmaiden',
    'TCoE': 'Tasha’s Cauldron of Everything'
}
SOURCE_SLUG_MAP = {
    'BR': 'basic-rules', 'PHB': 'players-handbook', 'DMG': 'dungeon-masters-guide',
    'EE': 'elemental-evil-players-companion', 'MM': 'monster-manual', 'CoS': 'curse-of-strahd',
    'HotDQ': 'hoard-of-the-dragon-queen', 'LMoP': 'lost-mine-of-phandelver', 'OotA': 'out-of-the-abyss',
    'PotA': 'princes-of-the-apocalypse', 'RoT': 'rise-of-tiamat', 'SKT': 'storm-kings-thunder',
    'SCAG': 'sword-coast-adventurers-guide', 'TftYP': 'tales-from-the-yawning-portal',
    'VGtM': 'volos-guide-to-monsters', 'TSC': 'the-sunless-citadel', 'TFoF': 'the-forge-of-fury',
    'THSoT': 'the-hidden-shrine-of-tamoachan', 'WPM': 'white-plume-mountain', 'DiT': 'dead-in-thay',
    'AtG': 'against-the-giants', 'ToH': 'tomb-of-horrors', 'ToA': 'tomb-of-annihilation',
    'CoSCO': 'curse-of-strahd-character-options', 'XGtE': 'xanathars-guide-to-everything', 'TTP': 'the-tortle-package',
    'UA': 'unearthed-arcana', 'DDB': 'dnd-beyond', 'CR': 'critical-role', 'TCS': 'taldorei-campaign-setting',
    'MToF': 'mordenkainens-tome-of-foes', 'DDIA-MORD': 'rrakkma', 'WDH': 'waterdeep-dragon-heist',
    'WDotMM': 'waterdeep-dungeon-of-the-mad-mage', 'WGtE': 'wayfinders-guide-to-eberron',
    'GGtR': 'guildmasters-guide-to-ravnica', '_APT': 'archived-playtest', 'LLoK': 'lost-laboratory-of-kwalish',
    'DoIP': 'dragon-of-icespire-peak', 'TMR': 'tactical-maps-reincarnated', 'GoS': 'ghosts-of-saltmarsh',
    'AI': 'acquisitions-incorporated', 'HftT': 'hunt-for-the-thessalhydra',
    'BGDiA': 'baldurs-gate-descent-into-avernus', 'ERftLW': 'eberron-rising-from-the-last-war',
    'SLW': 'storm-lords-wrath', 'SDW': 'sleeping-dragons-wake', 'DC': 'divine-contention',
    'SAC': 'sage-advice-compendium', 'DDvRaM': 'dungeons-dragons-vs-rick-and-morty', 'LR': 'locathah-rising',
    'IMR': 'infernal-machine-rebuild', 'MFFV1': 'mordenkainens-fiendish-folio-volume-1', 'SD': 'sapphire-dragon',
    'EGtW': 'explorers-guide-to-wildemount', 'OGA': 'one-grung-above', 'MOoT': 'mythic-odysseys-of-theros',
    'WA': 'frozen-sick', 'TSCF': 'the-sunless-citadel-free', 'TFoFF': 'the-forge-of-fury-free',
    'LRDToB': 'legends-of-runeterra-dark-tides-of-bilgewater', 'IDRotF': 'icewind-dale-rime-of-the-frostmaiden',
    'TCoE': 'tashas-cauldron-of-everything'
}
PARTNERED_SOURCES = ('LRDToB',)
UA_SOURCES = ('UA',)
CR_SOURCES = ('CR', 'EGtW', 'WA')
NONCORE_SOURCES = ('DDIA-MORD', 'LLoK', 'LR', 'IMR', 'MFFV1', 'OGA')
