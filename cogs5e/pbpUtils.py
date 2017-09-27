"""
Created on Jan 13, 2017

@author: andrew
"""
import shlex

import discord
from discord.ext import commands

from utils.functions import list_get
from math import sqrt


class PBPUtils:
    """Commands to help streamline playing-by-post over Discord."""
    
    def __init__(self, bot):
        self.bot = bot
        
    def parse_args(self, args):
        out = {}
        index = 0
        for a in args:
            if a == '-f':
                if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = [list_get(index + 1, None, args)]
                else: out[a.replace('-', '')].append(list_get(index + 1, None, args))
            elif a.startswith('-'):
                nextArg = list_get(index + 1, None, args)
                if nextArg is None or nextArg.startswith('-'): nextArg = True
                out[a.replace('-', '')] = nextArg
            else:
                out[a] = 'True'
            index += 1
        return out
        
    @commands.command(pass_context=True)
    async def echo(self, ctx, *, msg):
        """Echos a message."""
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        await self.bot.say(ctx.message.author.display_name + ": " + msg)
        
    @commands.command(pass_context=True)
    async def embed(self, ctx, *, args):
        """Creates and prints an Embed.
        Arguments: -title [title]
        -desc [description text]
        -thumb [image url]
        -image [image url]
        -footer [footer text]
        -f ["Field Title|Field Text"]
        -color [hex color]
        """
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        embed = discord.Embed()
        embed.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.avatar_url)
        args = shlex.split(args)
        args = self.parse_args(args)
        embed.title = args.get('title')
        embed.description = args.get('desc')
        embed.set_thumbnail(url=args.get('thumb', ''))
        embed.set_image(url=args.get('image', ''))
        embed.set_footer(text=args.get('footer', ''))
        try:
            embed.colour = int(args.get('color', "0").strip('#'), base=16)
        except:
            pass
        for f in args.get('f', []):
            title = f.split('|')[0]
            value = "|".join(f.split('|')[1:])
            embed.add_field(name=title, value=value)
        
        await self.bot.say(embed=embed)
        
    @commands.command(pass_context=True)
    async def br(self, ctx):
        """Prints a scene break."""
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        await self.bot.say("``` ```")
        
    @commands.command()
    async def pythag(self, num1:int, num2:int):
        """Performs a pythagorean theorem calculation to calculate diagonals."""
        await self.bot.say(sqrt(num1 ** 2 + num2 ** 2))
        
