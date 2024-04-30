from cogs5e.models.errors import NoCharacter
from cogs5e.models.sheet.player import CustomCounter
from .errors import PrerequisiteFailed
from .models import Tutorial, TutorialEmbed, TutorialState, state


class PlayingTheGame(Tutorial):
    name = "Playing the Game"
    description = """
    *5 minutes*
    Now that you've imported a character, learn how to view your character sheet, manage your resources, take rests, and more!
    """

    @state(first=True)
    class Sheet(TutorialState):
        async def setup(self, ctx, state_map):
            try:
                await ctx.get_character()  # ensure active character
            except NoCharacter:
                await state_map.end_tutorial(ctx)
                raise PrerequisiteFailed(
                    "You need an active character to run this tutorial. Switch to one using "
                    f"`{ctx.prefix}character <name>`, or try out the quickstart tutorial to learn how to import one!"
                )

        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Character Sheet"
            embed.description = f"""
            Now that you've imported a character, let's go over how to view your character sheet, manage your resources, take rests, and more! You can view your character's sheet using `{ctx.prefix}sheet`. It will list your statistics and attacks. Try it now to see what's stored!
            ```
            {ctx.prefix}sheet
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("sheet"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Status)

    @state()
    class Status(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Character Status"
            embed.description = f"""
            You can also use `{ctx.prefix}game status`, which shows your current, maximum, and temporary hit points. It also shows any counters the character has associated with them, such as spell slots or special abilities like a Dragonborn's Breath Weapon or a Druid's Wild Shape. Try it out now to see your character's resources!
            ```
            {ctx.prefix}game status
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("g status"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx, footer=False)
            embed.description = f"""
            You got it! These are the two primary ways to view your character's information in Avrae, and any changes to your character's health, spell slots, or resources will be reflected here. Next, let's go over how to manage some of these resources.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.HitPoints1, 5)

    @state()
    class HitPoints2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points II"
            embed.description = f"""
                Next, to manage your hit points, we use `{ctx.prefix}game hp` with one of three options. The first is `{ctx.prefix}game hp <amount>`, which modifies your health by the given amount. If you use a negative value it removes that much health. Try it now to remove your previously set temporary hit points!
                ```
                {ctx.prefix}game hp -5
                ```
                """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            character = await ctx.get_character()
            if ctx.command is ctx.bot.get_command("g hp") and not character.temp_hp:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.HitPoints3)

    @state()
    class HitPoints1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points and Temporary Hit Points"
            embed.description = f"""
            You can manage your hit points and temporary hit points with the `{ctx.prefix}game` command too. First, let's look at temporary hit points, which uses the `{ctx.prefix}game thp <amount>` command. Try it now to give yourself some temporary hit points!
            ```
            {ctx.prefix}game thp 5
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            character = await ctx.get_character()
            if ctx.command is ctx.bot.get_command("g thp") and character.temp_hp:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.HitPoints2)

    @state()
    class HitPoints2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points II"
            embed.description = f"""
            Next, to manage your hit points, we use `{ctx.prefix}game hp` with one of three options. The first is `{ctx.prefix}game hp <amount>`, which modifies your health by the given amount. If you use a negative value it removes that much health. Try it now to remove your previously set temporary hit points!
            ```
            {ctx.prefix}game hp -5
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            character = await ctx.get_character()
            if ctx.command is ctx.bot.get_command("g hp") and not character.temp_hp:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.HitPoints3)

    @state()
    class HitPoints3(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points III"
            embed.description = f"""
            Now, let's look at `{ctx.prefix}game hp set <hp>`, which sets your hit points to a certain value. Try it to set your hit points to one!
            ```
            {ctx.prefix}game hp set 1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            character = await ctx.get_character()
            if ctx.command is ctx.bot.get_command("g hp set") and (
                character.hp < character.max_hp or character.hp == 1
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.HitPoints4)

    @state()
    class HitPoints4(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points IV"
            embed.description = f"""
            Ouch! The final way is `{ctx.prefix}game hp max`, which sets your current hit points to your maximum hit points. Try it now to heal back up!
            ```
            {ctx.prefix}game hp max
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("g hp max"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Now you know how to manage your hit points and temporary hit points in Avrae. Note that these changes are only in Avrae, and won't be reflected on your character sheet! 
            Next, let's take a look at how to track other resources using Custom Counters.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Counters1, 5)

    @state()
    class Counters1(TutorialState):
        async def setup(self, ctx, state_map):
            character = await ctx.get_character()
            new_counter = CustomCounter.new(
                character, name="Tutorial Counter", maxv="3", minv="0", reset="long", display_type="bubble"
            )
            character.consumables.append(new_counter)
            await character.commit(ctx)

        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Custom Counters"
            embed.description = f"""
            You can track custom resources through the use of Custom Counters. For example, you might track how many uses of a class feature you have left, or how many arrows you have.
            
            Usually, these are made for you automatically when you import a character or run certain user-made commands, but you can also create them yourself. 
            
            To see what custom counters are attached to your character, use `{ctx.prefix}customcounter list`. Try it now!
            ```
            {ctx.prefix}customcounter list
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cc list"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Counters2)

    @state()
    class Counters2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Custom Counters II"
            embed.description = f"""
            See the one named Tutorial Counter? That was created automatically for this tutorial - let's learn how to use it!
            
            To use a Custom Counter, use `{ctx.prefix}customcounter <name> <amount>`, where "amount" is how much you want to add or subtract. Try using some of the Tutorial Counter!
            
            Since the name of the counter has a space in it, remember to put quotes around it! We'll also use the shortcut `{ctx.prefix}cc` instead of `{ctx.prefix}customcounter` from now on.
            ```
            {ctx.prefix}cc "tutorial counter" -2
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cc"):
                character = await ctx.get_character()
                counter = character.get_consumable("Tutorial Counter")
                if counter is None:
                    await self.tutorial.Counters1.setup(ctx, state_map)  # recreate the counter
                elif counter.value < counter.get_max():
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Great! Some counters have a minimum or maximum, and you won't be able to go below the minimum or above the maximum.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Counters3, 5)

    @state()
    class Counters3(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Custom Counters III"
            embed.description = f"""
            Now that you know how to modify a counter, let's reset it to its default value. To do so, use `{ctx.prefix}cc reset <name>`. Try it now to reset Tutorial Counter back to its default!
            ```
            {ctx.prefix}cc reset "tutorial counter"
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cc reset"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            # delete the counter
            character = await ctx.get_character()
            counter = character.get_consumable("Tutorial Counter")
            if counter is not None:
                character.consumables.remove(counter)
                await character.commit(ctx)

            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Counters can specify what value they want to reset to, how much they want to change by on a reset, and whether or not they automatically reset when you rest. We'll take a look at resting later, but first, let's look at a special counter.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.DeathSaves, 5)

    @state()
    class DeathSaves(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Death Saves"
            embed.description = f"""
            Death Saves are a special type of saving throw. Avrae tracks your death saves automatically when you have to make them; to roll one, use `{ctx.prefix}save death`. Try making one now!
            ```
            {ctx.prefix}game deathsave
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("save death") or ctx.command is ctx.bot.get_command("g ds"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            See how it tracks your failures and successes? If you need to manually fail or succeed a death save, the command is a little different: `{ctx.prefix}game deathsave fail` or `{ctx.prefix}game deathsave success`.
            
            Similarly, to reset your death saves, you can use `{ctx.prefix}game deathsave reset`. Let's take a look at a different way to reset everything: resting!
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Rests, 5)

    @state()
    class Rests(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Rests"
            embed.description = f"""
            After a day of adventuring, a long rest is the best way to relax. Avrae will automatically recover your hit points, custom counters, death saves, and spell slots on a rest - all you have to do is run the command! Let's take a long rest now:
            ```
            {ctx.prefix}game longrest
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("g lr"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            You're all refreshed and ready for the next day! Similarly, you can make a short rest with `{ctx.prefix}game shortrest`. 
            
            That's it for this tutorial! Now you know how to manage your hit points, custom counters, death saves, and rest. If you're a spellcaster, you'll want to take a look at the Spellcasting tutorial next with `{ctx.prefix}tutorial spellcasting`!
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
