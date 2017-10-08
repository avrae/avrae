import random
import random
import re
import shlex
from math import floor

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll, SingleDiceGroup, Constant, Operator
from cogs5e.funcs.lookupFuncs import searchMonsterFull
from cogs5e.funcs.sheetFuncs import sheet_attack
from utils import checks
from utils.functions import fuzzy_search, a_or_an, discord_trim, \
    parse_args_2, parse_args_3


class Dice:
    """Dice and math related commands."""
    def __init__(self, bot):
        self.bot = bot
        
    async def on_message(self, message):
        if message.content.startswith('!d20'):
            self.bot.botStats["dice_rolled_session"] += 1
            self.bot.db.incr('dice_rolled_life')
            rollStr = message.content.replace('!', '1').split(' ')[0]
            try:
                rollFor = ' '.join(message.content.split(' ')[1:])
            except:
                rollFor = ''
            adv = 0
            if re.search('(^|\s+)(adv|dis)(\s+|$)', rollFor) is not None:
                adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollFor) is not None else -1
                rollFor = re.sub('(adv|dis)(\s+|$)', '', rollFor)
            out = roll(rollStr, adv=adv, rollFor=rollFor, inline=True)
            out = out.result
            try:
                await self.bot.delete_message(message)
            except:
                pass
            await self.bot.send_message(message.channel, message.author.mention + '  :game_die:\n' + out)
            
    @commands.command(name='2', hidden=True, pass_context=True)
    async def quick_roll(self, ctx, *, mod:str='0'):
        """Quickly rolls a d20."""
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        rollStr = '1d20+' + mod
        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        out = roll(rollStr, adv=adv, inline=True)
        out = out.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '  :game_die:\n' + out)
                        
        
    @commands.command(pass_context=True, name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr:str):
        """Rolls dice in xdy format.
        Usage: !r xdy Attack!
               !r xdy+z adv Attack with Advantage!
               !r xdy-z dis Hide with Heavy Armor!
               !r xdy+xdy*z
               !r XdYkhZ
               !r 4d6mi2[fire] Elemental Adept, Fire
        Supported Operators: k (keep)
                             ro (reroll once)
                             rr (reroll infinitely)
                             mi/ma (min/max result)
                             >/< (test if result is greater than/less than)
        Supported Selectors: lX (lowest X)
                             hX (highest X)"""
        
        adv = 0
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
            
    @commands.command(pass_context=True, name='debugroll', aliases=['dr'], hidden=True)
    @checks.is_owner()
    async def debug_roll(self, ctx, *, rollStr:str):
        adv = 0
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv, debug=True)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
        
        debug = ""
        for p in res.raw_dice.parts:
            if isinstance(p, SingleDiceGroup):
                debug += "SingleDiceGroup:\nnum_dice={0.num_dice}, max_value={0.max_value}, annotation={0.annotation}, operators={0.operators}".format(p) + \
                "\nrolled={}\n\n".format(', '.join(repr(r) for r in p.rolled))
            elif isinstance(p, Constant):
                debug += "Constant:\nvalue={0.value}, annotation={0.annotation}\n\n".format(p)
            elif isinstance(p, Operator):
                debug += "Operator:\nop={0.op}, annotation={0.annotation}\n\n".format(p)
            else:
                debug += "Comment:\ncomment={0.comment}\n\n".format(p)
        for t in discord_trim(debug):
            await self.bot.say(t)
    
    @commands.command(pass_context=True, name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations:int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rrr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.db.incr('dice_rolled_life')
        adv = 0
        out = []
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for _ in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            out.append(res)
        outStr = "Rolling {} iterations...\n".format(iterations)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} total.'.format(sum(o.total for o in out))
        else:
            outStr = "Rolling {} iterations...\n[Output truncated due to length]\n".format(iterations) + \
            '{} total.'.format(sum(o.total for o in out))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
        
    @commands.command(pass_context=True, name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations:int, rollStr, dc:int=0, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.db.incr('dice_rolled_life')
        adv = 0
        out = []
        successes = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for r in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            if res.plain >= dc:
                successes += 1
            out.append(res)
        outStr = "Rolling {} iterations, DC {}...\n".format(iterations, dc)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} successes.'.format(str(successes))
        else:
            outStr = "Rolling {} iterations, DC {}...\n[Output truncated due to length]\n".format(iterations, dc) + '{} successes.'.format(str(successes))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
                
    @commands.command(pass_context=True, aliases=['ma', 'monster_attack'])
    async def monster_atk(self, ctx, monster_name, atk_name='list', *, args=''):
        """Rolls a monster's attack.
        Attack name can be "list" for a list of all of the monster's attacks.
        Valid Arguments: adv/dis
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -d# [applies damage to the first # hits]
                         -rr [times to reroll]
                         -t [target]
                         -phrase [flavor text]
                         crit (automatically crit)"""
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        monster = await searchMonsterFull(monster_name, ctx)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        attacks = monster.get('attacks')
        monster_name = a_or_an(monster.get('name'))[0].upper() + a_or_an(monster.get('name'))[1:]
        if atk_name == 'list':
            attacks_string = '\n'.join("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  a['attackBonus'],
                                                                                  a['damage'] or 'no') for a in attacks)
            return await self.bot.say("{}'s attacks:\n{}".format(monster_name, attacks_string))
        attack = fuzzy_search(attacks, 'name', atk_name)
        if attack is None:
            return await self.bot.say("No attack with that name found.", delete_after=15)
        
        args = shlex.split(args)
        args = parse_args_2(args)
        args['name'] = monster_name
        attack['details'] = attack.get('desc')
        
        result = sheet_attack(attack, args)
        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff)
        
        await self.bot.say(embed=embed)
    
    @commands.command(pass_context=True, aliases=['mc'])
    async def monster_check(self, ctx, monster_name, check, *args):
        """Rolls a check for a monster.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -title [title] *note: [mname] and [cname] will be replaced automatically*"""
        
        monster = await searchMonsterFull(monster_name, ctx)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        _skills = monster.get('skill', "")
        if isinstance(_skills, str):
            _skills = _skills.split(', ')
        monster_name = a_or_an(monster.get('name'))[0].upper() + a_or_an(monster.get('name'))[1:]
        skills = {}
        for s in _skills:
            if s:
                _name = ' '.join(s.split(' ')[:-1]).lower()
                _value = int(s.split(' ')[-1])
                skills[_name] = _value
        
        skillslist = ['acrobatics', 'animal handling', 'arcana', 'athletics',
                      'deception', 'history', 'initiative', 'insight',
                      'intimidation', 'investigation', 'medicine', 'nature',
                      'perception', 'performance', 'persuasion', 'religion',
                      'sleight of hand', 'stealth', 'survival',
                      'strength', 'dexterity', 'constitution', 'intelligence',
                      'wisdom', 'charisma']
        skillsmap = ['dex', 'wis', 'int', 'str',
                     'cha', 'int', 'dex', 'wis',
                     'cha', 'int', 'wis', 'int',
                     'wis', 'cha', 'cha', 'int',
                     'dex', 'dex', 'wis',
                     'str', 'dex', 'con', 'int',
                     'wis', 'cha']
        for i, s in enumerate(skillslist):
            if not s in skills:
                skills[s] = floor((int(monster.get(skillsmap[i]))-10)/2)
        
        
        try:
            skill = next(a for a in skills.keys() if check.lower() == a.lower())
        except StopIteration:
            try:
                skill = next(a for a in skills.keys() if check.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid check.')
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        
        args = parse_args_3(args)
        adv = 0 if args.get('adv', []) and args.get('dis', []) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = "+".join(args.get('b', [])) or None
        phrase = '\n'.join(args.get('phrase', [])) or None
        formatted_d20 = '1d20' if adv == 0 else '2d20' + ('kh1' if adv == 1 else 'kl1')
        
        if b is not None:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
        else:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]), adv=adv, inline=True)
        
        embed.title = '{} makes {} check!'.format(monster_name,
                                                  a_or_an(skill.title()))
        embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        
        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
    
    @commands.command(pass_context=True, aliases=['ms'])
    async def monster_save(self, ctx, monster_name, save, *args):
        """Rolls a check for a monster.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -title [title] *note: [mname] and [cname] will be replaced automatically*"""
        
        monster = await searchMonsterFull(monster_name, ctx)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        monster_name = a_or_an(monster.get('name'))[0].upper() + a_or_an(monster.get('name'))[1:]
        
        saves = {'strengthSave': floor((int(monster['str'])-10)/2),
                 'dexteritySave': floor((int(monster['dex'])-10)/2),
                 'constitutionSave': floor((int(monster['con'])-10)/2),
                 'intelligenceSave': floor((int(monster['int'])-10)/2),
                 'wisdomSave': floor((int(monster['wis'])-10)/2),
                 'charismaSave': floor((int(monster['cha'])-10)/2)}
        save_overrides = monster.get('save', '').split(', ')
        for s in save_overrides:
            try:
                _type = next(sa for sa in ('strengthSave',
                                           'dexteritySave',
                                           'constitutionSave',
                                           'intelligenceSave',
                                           'wisdomSave',
                                           'charismaSave') if s.split(' ')[0].lower() in sa.lower())
                mod = int(s.split(' ')[1])
                saves[_type] = mod
            except:
                pass
        
        
        try:
            save = next(a for a in saves.keys() if save.lower() == a.lower())
        except StopIteration:
            try:
                save = next(a for a in saves.keys() if save.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid save.')
            
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        
        args = parse_args_3(args)
        adv = 0 if args.get('adv', []) and args.get('dis', []) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = "+".join(args.get('b', [])) or None
        phrase = '\n'.join(args.get('phrase', [])) or None
        
        if b is not None:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]) + '+' + b, adv=adv, inline=True)
        else:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]), adv=adv, inline=True)
            
        embed.title = '{} makes {}!'.format(monster_name,
                                            a_or_an(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title()))
            
        embed.description = save_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        
        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
