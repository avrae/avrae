'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
import logging
import random
import re
from math import *

import discord
import numexpr
from DDPClient import DDPClient

from cogs5e.sheets.sheetParser import SheetParser

log = logging.getLogger(__name__)

class DicecloudParser(SheetParser):
    
    def __init__(self, url):
        self.url = url
        self.character = None
    
    async def get_character(self):
        url = self.url
        character = {}
        client = DDPClient('ws://dicecloud.com/websocket', auto_reconnect=False)
        client.is_connected = False
        client.connect()
        def connected():
            client.is_connected = True
        client.on('connected', connected)
        while not client.is_connected:
            await asyncio.sleep(1)
        client.subscribe('singleCharacter', [url])
        def update_character(collection, _id, fields):
            if character.get(collection) is None:
                character[collection] = []
            fields['id'] = _id
            character.get(collection).append(fields)
        client.on('added', update_character)
        await asyncio.sleep(10)
        client.close()
        character['id'] = url
        self.character = character
        return character
            
    def get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        try:
            stats = self.get_stats()
            levels = self.get_levels()
            hp = self.calculate_stat('hitPoints')
            dexArmor = self.calculate_stat('dexterityArmor', base=stats['dexterityMod'])
            armor = self.calculate_stat('armor', replacements={'dexterityArmor':dexArmor})
            attacks = self.get_attacks()
            skills = self.get_skills()
            temp_resist = self.get_resistances()
            resistances = temp_resist['resist']
            immunities = temp_resist['immune']
            vulnerabilities = temp_resist['vuln']
        except:
            raise
        
        saves = {}
        for key in skills:
            if 'Save' in key:
                saves[key] = skills[key]
        
        stat_vars = {}
        stat_vars.update(stats)
        stat_vars.update(levels)
        stat_vars['hp'] = int(hp)
        stat_vars['armor'] = int(armor)
        stat_vars.update(saves)
        
        sheet = {'type': 'dicecloud',
                 'version': 6, #v6: added stat cvars
                 'stats': stats,
                 'levels': levels,
                 'hp': int(hp),
                 'armor': int(armor),
                 'attacks': attacks,
                 'skills': skills,
                 'resist': resistances,
                 'immune': immunities,
                 'vuln': vulnerabilities,
                 'saves': saves,
                 'stat_cvars': stat_vars}
                
        embed = self.get_embed(sheet)
        
        return {'embed': embed, 'sheet': sheet}
    
    def get_embed(self, sheet):
        stats = sheet['stats']
        hp = sheet['hp']
        levels = sheet['levels']
        skills = sheet['skills']
        attacks = sheet['attacks']
        saves = sheet['saves']
        armor = sheet['armor']
        resist= sheet['resist']
        immune= sheet['immune']
        vuln  = sheet['vuln']
        resistStr = ''
        if len(resist) > 0:
            resistStr += "\nResistances: " + ', '.join(resist).title()
        if len(immune) > 0:
            resistStr += "\nImmunities: " + ', '.join(immune).title()
        if len(vuln) > 0:
            resistStr += "\nVulnerabilities: " + ', '.join(vuln).title()
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.title = stats['name']
        embed.set_thumbnail(url=stats['image'])
        embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']) + resistStr)
        embed.add_field(name="AC", value=str(armor))
        embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+})\n" \
                                            "**DEX:** {dexterity} ({dexterityMod:+})\n" \
                                            "**CON:** {constitution} ({constitutionMod:+})\n" \
                                            "**INT:** {intelligence} ({intelligenceMod:+})\n" \
                                            "**WIS:** {wisdom} ({wisdomMod:+})\n" \
                                            "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
        embed.add_field(name="Saves", value="**STR:** {strengthSave:+}\n" \
                                            "**DEX:** {dexteritySave:+}\n" \
                                            "**CON:** {constitutionSave:+}\n" \
                                            "**INT:** {intelligenceSave:+}\n" \
                                            "**WIS:** {wisdomSave:+}\n" \
                                            "**CHA:** {charismaSave:+}".format(**saves))
        
        skillsStr = ''
        tempSkills = {}
        for skill, mod in sorted(skills.items()):
            if 'Save' not in skill:
                skillsStr += '**{}**: {:+}\n'.format(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill), mod)
                tempSkills[skill] = mod
        sheet['skills'] = tempSkills
                
        embed.add_field(name="Skills", value=skillsStr.title())
        
        tempAttacks = []
        for a in attacks:
            if a['attackBonus'] is not None:
                try:
                    bonus = numexpr.evaluate(a['attackBonus'])
                except:
                    bonus = a['attackBonus']
                tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                              bonus,
                                                                              a['damage'] if a['damage'] is not None else 'no'))
            else:
                tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                 a['damage'] if a['damage'] is not None else 'no'))
        if tempAttacks == []:
            tempAttacks = ['No attacks.']
        a = '\n'.join(tempAttacks)
        if len(a) > 1023:
            a = ', '.join(atk['name'] for atk in attacks)
        if len(a) > 1023:
            a = "Too many attacks, values hidden!"
        embed.add_field(name="Attacks", value=a)
        
        return embed
        
    def get_stat(self, stat, base=0):
        """Returns the stat value."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        effects = character.get('effects', [])
        add = 0
        mult = 1
        maxV = None
        minV = None
        for effect in effects:
            if effect.get('stat') == stat and effect.get('enabled', True) and not effect.get('removed', False):
                operation = effect.get('operation', 'base')
                value = int(effect.get('value', 0))
                if operation == 'base' and value > base:
                    base = value
                elif operation == 'add':
                    add += value
                elif operation == 'mul':
                    mult *= value
                elif operation == 'min':
                    minV = value if minV is None else value if value < minV else minV
                elif operation == 'max':
                    maxV = value if maxV is None else value if value > maxV else maxV
        out = (base + add) * mult
        if minV is not None:
            out = max(out, minV)
        if maxV is not None:
            out = min(out, maxV)
        return out
    
    def get_stat_float(self, stat, base=0):
        """Returns the stat value."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        effects = character.get('effects', [])
        add = 0
        mult = 1
        maxV = None
        minV = None
        for effect in effects:
            if effect.get('stat') == stat and effect.get('enabled', True) and not effect.get('removed', False):
                operation = effect.get('operation', 'base')
                value = float(effect.get('value', 0))
                if operation == 'base' and value > base:
                    base = value
                elif operation == 'add':
                    add += value
                elif operation == 'mul':
                    mult *= value
                elif operation == 'min':
                    minV = value if minV is None else value if value < minV else minV
                elif operation == 'max':
                    maxV = value if maxV is None else value if value > maxV else maxV
        out = (base + add) * mult
        if minV is not None:
            out = max(out, minV)
        if maxV is not None:
            out = min(out, maxV)
        return out
        
    def get_stats(self):
        """Returns a dict of stats."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = {"name":"", "image":"", "description":"",
                 "strength":10, "dexterity":10, "constitution":10, "wisdom":10, "intelligence":10, "charisma":10,
                 "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
                 "proficiencyBonus":0}
        stats['name'] = character.get('characters')[0].get('name')
        stats['description'] = character.get('characters')[0].get('description')
        stats['image'] = character.get('characters')[0].get('picture', '')
        profByLevel = floor(self.get_levels()['level'] / 4 + 1.75)
        stats['proficiencyBonus'] = profByLevel + self.get_stat('proficiencyBonus', base=0)
        
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            stats[stat] = self.get_stat(stat)
            stats[stat + 'Mod'] = floor((int(stats[stat]) - 10) / 2)
        
        return stats
            
    def get_levels(self):
        """Returns a dict with the character's level and class levels."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        levels = {"level":0}
        for level in character.get('classes', []):
            if level.get('removed', False): continue
            levels['level'] += level.get('level')
            levelName = level.get('name') + 'Level'
            if levels.get(levelName) is None:
                levels[levelName] = level.get('level')
            else:
                levels[levelName] += level.get('level')
        return levels
            
    def calculate_stat(self, stat, base=0, replacements:dict={}):
        """Calculates and returns the stat value."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        replacements.update(self.get_stats())
        replacements.update(self.get_levels())
        replacements = dict((k.lower(), v) for k,v in replacements.items())
        effects = character.get('effects', [])
        add = 0
        mult = 1
        maxV = None
        minV = None
        for effect in effects:
            if effect.get('stat') == stat and effect.get('enabled', True) and not effect.get('removed', False):
                operation = effect.get('operation', 'base')
                if effect.get('value') is not None:
                    value = effect.get('value')
                else:
                    calculation = effect.get('calculation', '').replace('{', '').replace('}', '').lower()
                    if calculation == '': continue
                    try:
                        value = numexpr.evaluate(calculation, local_dict=replacements)
                    except SyntaxError:
                        continue
                    except KeyError:
                        raise
                if operation == 'base' and value > base:
                    base = value
                elif operation == 'add':
                    add += value
                elif operation == 'mul':
                    mult *= value
                elif operation == 'min':
                    minV = value if minV is None else value if value < minV else minV
                elif operation == 'max':
                    maxV = value if maxV is None else value if value > maxV else maxV
        out = (base + add) * mult
        if minV is not None:
            out = max(out, minV)
        if maxV is not None:
            out = min(out, maxV)
        return out
    
    def get_attack(self, atkIn):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')
        replacements = self.get_stats()
        replacements.update(self.get_levels())

        log.debug(f"Processing attack {atkIn.get('name')}")

        # make a list of safe functions
        safe_list = ['ceil', 'floor']
        # use the list to filter the local namespace
        safe_dict = dict([(k, locals().get(k, None)) for k in safe_list])
        safe_dict['max'] = max
        safe_dict['min'] = min
        safe_dict.update(replacements)

        if atkIn.get('parent', {}).get('collection') == 'Spells':
            spellParentID = atkIn.get('parent', {}).get('id')
            try:
                spellObj = next(s for s in self.character.get('spells', {}) if s.get('id') == spellParentID)
            except StopIteration:
                pass
            else:
                spellListParentID = spellObj.get('parent', {}).get('id')
                try:
                    spellListObj = next(s for s in self.character.get('spellLists', {}) if s.get('id') == spellListParentID)
                except StopIteration:
                    pass
                else:
                    try:
                        replacements['attackBonus'] = str(eval(spellListObj.get('attackBonus'), {"__builtins__": None}, safe_dict))
                        replacements['DC'] = str(eval(spellListObj.get('saveDC'), {"__builtins__": None}, safe_dict))
                    except Exception as e:
                        log.debug(f"Exception parsing spellvars: {e}")

        safe_dict.update(replacements)
        attack = {'attackBonus': '0', 'damage':'0', 'name': atkIn.get('name'), 'details': None}
        
        attackBonus = re.split('([-+*/^().<>= ])', atkIn.get('attackBonus', '').replace('{', '').replace('}', ''))
        attack['attackBonus'] = ''.join(str(replacements.get(word, word)) for word in attackBonus)
        if attack['attackBonus'] == '':
            attack['attackBonus'] = None
        else:
            try:
                attack['attackBonus'] = str(eval(attack['attackBonus'], {"__builtins__": None}, safe_dict))
            except:
                pass
        
        def damage_sub(match):
            out = match.group(1)
            try:
                log.debug(f"damage_sub: evaluating {out}")
                return str(eval(out, {"__builtins__": None}, safe_dict))
            except Exception as ex:
                log.debug(f"exception in damage_sub: {ex}")
                return out
        
        damage = re.sub(r'{(.*)}', damage_sub, atkIn.get('damage', ''))
        damage = re.split('([-+*/^().<>= ])', damage.replace('{', '').replace('}', ''))
        attack['damage'] = ''.join(str(replacements.get(word, word)) for word in damage) + ' [{}]'.format(atkIn.get('damageType'))
        if not attack['damage']:
            attack['damage'] = None

        details = atkIn.get('details', None)

        if details:
            details = re.sub(r'{([^{}]*)}', damage_sub, details)
            attack['details'] = details

        return attack
        
    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        attacks = []
        for attack in character.get('attacks', []):
            if attack.get('enabled') and not attack.get('removed'):
                atkDict = self.get_attack(attack)
                atkNum = 2
                if atkDict['name'] in (a['name'] for a in attacks):
                    while atkDict['name'] + str(atkNum) in (a['name'] for a in attacks):
                        atkNum += 1
                    atkDict['name'] = atkDict['name'] + str(atkNum)
                attacks.append(atkDict)
        return attacks
            
    def get_skills(self):
        """Returns a dict of all the character's skills."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = self.get_stats()
        skillslist = ['acrobatics', 'animalHandling',
                      'arcana', 'athletics',
                      'charismaSave', 'constitutionSave',
                      'deception', 'dexteritySave',
                      'history', 'initiative',
                      'insight', 'intelligenceSave',
                      'intimidation', 'investigation',
                      'medicine', 'nature',
                      'perception', 'performance',
                      'persuasion', 'religion',
                      'sleightOfHand', 'stealth',
                      'strengthSave', 'survival',
                      'wisdomSave']
        skills = {}
        profs = {}
        for skill in skillslist:
            skills[skill] = stats.get(character.get('characters', [])[0].get(skill, {}).get('ability') + 'Mod', 0)
        for prof in character.get('proficiencies', []):
            if prof.get('enabled', False) and not prof.get('removed', False):
                profs[prof.get('name')] = prof.get('value') \
                                          if prof.get('value') > profs.get(prof.get('name', 'None'), 0) \
                                          else profs[prof.get('name')]
            
        for skill in skills:
            skills[skill] = floor(skills[skill] + stats.get('proficiencyBonus') * profs.get(skill, 0))
            skills[skill] = int(self.calculate_stat(skill, base=skills[skill]))
            
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            skills[stat] = stats.get(stat + 'Mod')
        
        return skills
        
    def get_resistances(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        out = {'resist': [], 'immune': [], 'vuln': []}
        damageTypes = ['acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing', 'poison',
                       'psychic', 'radiant', 'slashing', 'thunder']
        for dmgType in damageTypes:
            mult = self.get_stat_float(dmgType + "Multiplier", 1)
            if mult <= 0:
                out['immune'].append(dmgType)
            elif mult < 1:
                out['resist'].append(dmgType)
            elif mult > 1:
                out['vuln'].append(dmgType)
        return out
        
        
        
        
