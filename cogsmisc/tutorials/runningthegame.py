from .models import Tutorial, TutorialEmbed, TutorialState, checklist, state


class RunningTheGame(Tutorial):
    name = "Running the Game (DM)"
    description = """
    *5 minutes*
    Avrae helps Dungeon Masters run the game with a set of commands to act as the monstrous foes your players might face! This tutorial for Dungeon Masters covers how to act as a creature, and some tips and tricks for running the game.
    """

    @state(first=True)
    class ChecksAndSaves(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Monster Checks & Saves"
            embed.description = f"""
            Avrae is a useful tool, and, as such, even has support for automating rolls done by monsters, inside of and outside of combat. In this tutorial, we will go over some of the basic commands that a DM can use to help run monsters effectively. Even if you're a player, knowing these commands can be useful, in case you ever want to run a game of your own.

            If you have your D&D Beyond account linked, you can use [your unlocked monsters](https://www.dndbeyond.com/monsters?utm_source=avrae&utm_medium=reference) here in Avrae, too. See the D&D Beyond Link tutorial for more information.

            First, let's run a check for a monster. After that, try a save for a monster. These are both similar to how they would be run as a player.
            
            As an example, to make a Sleight of Hand check for a Commoner, you would use  `{ctx.prefix}moncheck Commoner "Sleight of Hand"`. To have that same Commoner roll a Dexterity saving throw, you would use `{ctx.prefix}monsave Commoner Dexterity`. Try it yourself!
            ```
            {ctx.prefix}moncheck <name of monster> <skill>
            {ctx.prefix}monsave <name of monster> <ability>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            mc = ctx.bot.get_command("mc")
            ms = ctx.bot.get_command("ms")
            if ctx.command in (mc, ms):
                if ctx.command is mc:
                    state_map.data["has_check"] = True
                elif ctx.command is ms:
                    state_map.data["has_save"] = True
                await state_map.commit(ctx)
                embed = TutorialEmbed(self, ctx)
                embed.title = "Objectives"
                embed.description = checklist([
                    (
                        f"Make a skill check for a monster with `{ctx.prefix}moncheck <name of monster> <skill>`.",
                        state_map.data.get("has_check"),
                    ),
                    (
                        (
                            f"Make an ability save for a monster with `{ctx.prefix}monsave <name of monster>"
                            " <ability>`."
                        ),
                        state_map.data.get("has_save"),
                    ),
                ])
                await ctx.send(embed=embed)

            if state_map.data.get("has_check") and state_map.data.get("has_save"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Good! Now you know how to do skill checks and ability saves for monsters. These commands work both in and out of combat, too, so feel free to use them as you see fit.

            When using these commands for monsters with multiple words in their name, make sure to surround the monster's name in quotes.
            
            As a note, if `{ctx.prefix}moncheck` and `{ctx.prefix}monsave` seem like a handful to type out, you can also use `{ctx.prefix}mc` and `{ctx.prefix}ms`, respectively, to achieve the same effect, so long as you use the proper arguments.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.ListMonsterAttacks, 5)

    @state()
    class ListMonsterAttacks(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Listing Monster Attacks"
            embed.description = f"""
            One of the most common actions that a monster will take in D&D is the Attack action. Here, you will learn how to list off and use these attacks while outside of combat.

            Firstly, to have an effective idea of what attacks a monster can use, you can list them off.
            
            For example, doing `{ctx.prefix}monattack "Silver Dragon Wyrmling" list` would list off the attacks of a Silver Dragon Wyrmling. Try that!
            ```
            {ctx.prefix}monattack <monster name> list
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command in (ctx.bot.get_command("ma"), ctx.bot.get_command("ma list")):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Great! Knowing what attacks a monster can do is quintessential to using them.
            
            To note, you can also use `{ctx.prefix}ma` instead of `{ctx.prefix}monattack`, as shorthand, so long as you use the proper arguments. And, again, if a monster's name is multiple words, surround the monster's name in quotes for the best effect.
            
            Now, let's put that knowledge to use.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.UseMonsterAttacks, 5)

    @state()
    class UseMonsterAttacks(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Using Monster Attacks"
            embed.description = f"""
            Using monster attacks is similar to how one would use attacks as a player. To note, these attacks will not deal any damage to players automatically. You may want to consider using the initiative tracker for combats. To view the tutorial for how to run combats as a DM, view the "Initiative (DM)" tutorial once you have finished here.
            
            For example, to have the Silver Dragon Wyrmling from before attack with its bite, you would use `{ctx.prefix}monattack "Silver Dragon Wyrmling" bite`. Try attacking with a monster now.
            ```
            {ctx.prefix}monattack <name of monster> <name of attack>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("ma"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Excellent! Having the knowledge of how to use monster attacks outside of initiative is good knowledge to have.
            
            Like before, if an attack name has multiple words, surround that argument in quotes for best effect. You can also use `{ctx.prefix}ma` as shorthand for `{ctx.prefix}monattack`, so long as you use the proper arguments to achieve your desired effect.
            
            Let's move on to the next part of this tutorial.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.CastMonsterSpells, 5)

    @state()
    class CastMonsterSpells(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Casting Monster Spells"
            embed.description = f"""
            Like with the other aspects of using monster actions, casting their spells is similar to a player.
            
            To cast a spell using a monster, you must first ensure that that monster has spells that it can cast. To view the list of spells a monster can cast, you can use `{ctx.prefix}monster <name of monster>`.
            
            Let's use a Lich as an example. To have a Lich cast Blight, you would use `{ctx.prefix}moncast Lich Blight`.
            
            Once you have found a monster that has spellcasting, try casting one of its spells.
            ```
            {ctx.prefix}moncast <name of monster> <name of spell>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("mcast"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Superb! Keep in mind that, like with monster attacks, monster spells will not automatically deal damage to your players' characters. To do that, you must be using the initiative tracker, which is covered in the Initiative (DM) section of the tutorial.

            Like with the previous commands, when casting using a monster with multiple words in its name or using a spell with multiple words in its name, you should surround the argument in quotes. Also, you can also use `{ctx.prefix}mcast` as shorthand for `{ctx.prefix}moncast`, providing you use all the proper arguments in their proper places.
            
            All of the commands covered in this tutorial have in-depth `{ctx.prefix}help` entries for them which list off more in-depth and specific arguments for each command. To view these help entries, use `{ctx.prefix}help moncheck`, `{ctx.prefix}help monsave`, `{ctx.prefix}help monattack`, or `{ctx.prefix}help moncast`, respectively.
            
            One final note. While it was touched upon before, you should know that, as a DM, you cannot change or alter your players' stats in any way (such as modifying their HP or spell slots) without using the initiative tracker. You can learn more about the initiative tracker and how to use it by viewing the "Initiative (DM)" tutorial.
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
