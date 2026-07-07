from cogs5e.models.errors import NoCharacter
from .models import Tutorial, TutorialEmbed, TutorialState, checklist, state


class Spellcasting(Tutorial):
    name = "Spellcasting"
    description = """
    *5 minutes*
    This tutorial will help you learn how to cast spells outside of combat, and how to manage your spell slots.
    """

    @state(first=True)
    class CastingSpells(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Casting Spells"
            embed.description = f"""
            Spellcasting is a useful tool in D&D. This tutorial will help you learn how to cast spells outside of combat. To start, you must first be on a character with the ability to cast spells. You must also have the ability to cast that spell, such as having it be in your spell list, and have a spell slot of the appropriate level.

            To have that character, for example, cast the cantrip Ray of Frost, you would use `{ctx.prefix}cast "Ray of Frost"`. Try casting one of your own spells!
            ```
            {ctx.prefix}cast <name of spell>
            ```
            Not sure what spells you have? Use `{ctx.prefix}spellbook` to view your spells!
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cast"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Wonderful! To note, as in the example provided before, when casting a spell with multiple words in its name, surround the name in quotes for best effect. Now, let's try doing something a little more powerful...
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.UpcastingSpells, 5)

    @state()
    class UpcastingSpells(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Casting at a Higher Level"
            embed.description = f"""
            Sometimes, a spell just might not have enough "oomph" for the specific situation you need it for. If said spell supports it, however, you can cast that spell using a higher level slot. To do so, you must, as before, be on a character with the ability to cast spells, have that spell on your character's spell list, and have a spell slot of the appropriate level. Not all spells have greater effects when upcasting, though, so be sure to read a spell's description for an "At Higher Levels" section to see if it does.

            For example, if your Fighter has thought it would be a good idea to touch lava, you can upcast Cure Wounds to heal their injuries (but not their pride) by doing `{ctx.prefix}cast "Cure Wounds" -l 4`. The `-l` argument is the key here, as it denotes that you're trying to cast a spell at a higher `l`evel. Try it now!
            ```
            {ctx.prefix}cast <name of spell> -l <slot level>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cast") and "-l" in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Magical! Now that you know how to cast spells, please use your power responsibly. In the next section, we will talk about how to target a specific creature (or creatures) with your magic.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Targeting, 5)

    @state()
    class Targeting(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Targeting"
            embed.description = f"""
            When casting most spells, you will have to select a target, or designate multiple targets. Whether friend, foe, or self, Avrae has got you covered.

            In order to target a creature with a spell, you must be playing on a character that can cast spells, have the spell that they're trying to cast in their known spells, and have a spell slot of that spell's appropriate level. While you can target creatures outside of initiative using the following command, know that the automation of healing and damage will not play out unless you are in initiative.
            
            Why don't we first try casting a spell that normally only has one target? For example, Chill Touch. In this specific example, you would use `{ctx.prefix}cast "Chill Touch" -t "Adult Blue Dragon"`. Note the `-t` argument! Try it yourself.
            ```
            {ctx.prefix}cast <name of spell> -t <name of target>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("cast") and "-t" in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Marvellous! If you're ever looking to target more than one creature with the same spell, you can use multiple `-t <name of target>` arguments. For example, `{ctx.prefix}cast "Mass Healing Word" -t "Samric Alestorm" -t "Alanna Holimion" -t "Arwyn Terra"`. And, as before, the best results happen when you surround arguments with multiple words in quotes.

            Now that you've learned how to cast your spells on your intended targets, let's move on to learning how to manually gain and lose spell slots.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.SlotManagement, 5)

    @state()
    class SlotManagement(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Using and Recovering Spell Slots"
            embed.description = f"""
            Typically, through normal play, spell slots are gained when resting, or lost when casting. However, there may come a time when you need to manually adjust the amount of spell slots you currently have, such as if you mistakenly cast a spell. To note, these commands can only be used on characters that have spell slots. You also cannot go under the minimum or over the maximum amount of spell slots that your character has for that respective level.

            For example, if you accidentally cast Fireball when you meant to cast Fire Bolt and need that third level spell slot, you can manually regain it by using `{ctx.prefix}game spellslot 3 +1`. Try to manually lose, and then regain, a spell slot now!
            ```
            {ctx.prefix}game spellslot <level of spell slot> -<number of spell slots>
            {ctx.prefix}game spellslot <level of spell slot> +<number of spell slots>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            command = ctx.bot.get_command("game spellslot")
            if ctx.command is command:
                if ctx.message.content.endswith("-1"):
                    state_map.data["has_removed"] = True
                elif ctx.message.content.endswith("+1"):
                    state_map.data["has_added"] = True
                await state_map.commit(ctx)

                embed = TutorialEmbed(self, ctx)
                embed.title = "Objectives"
                embed.description = checklist([
                    (
                        (
                            f"Manually lose a spell slot using `{ctx.prefix}game spellslot <level of spell slot> "
                            "-<number of spell slots>`."
                        ),
                        state_map.data.get("has_removed"),
                    ),
                    (
                        (
                            f"Manually gain a spell slot using `{ctx.prefix}game spellslot <level of spell slot> "
                            "+<number of spell slots>`."
                        ),
                        state_map.data.get("has_added"),
                    ),
                ])
                await ctx.send(embed=embed)

            if state_map.data.get("has_added") and state_map.data.get("has_removed"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Fantastic! While the amount of situations in which you might need to gain or lose a spell slot manually may be low, it is still good to know how to do so for when that situation arises.

            As a note, you can also use a set value instead of adding or subtracting spell slots, like `{ctx.prefix}game spellslot 3 3` to manually set the amount of third-level spell slots to 3. Let’s go over how to take a nice, relaxing long rest to get all of our spell slots back, yes?
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.LongResting, 5)

    @state()
    class LongResting(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Long Resting"

            # if singleclassed warlock not using DDB import, show srslots info
            warlock_info = ""
            try:
                character = await ctx.get_character()
                if warlock_level := character.levels.get("Warlock"):
                    if character.sheet_type == "beyond":
                        warlock_info = "Since you're a Warlock, your pact slots will reset on a Short Rest, too!"
                    elif warlock_level == character.levels.total_level:
                        warlock_info = (
                            "By the way, since you're a Warlock, you can also set your spell slots to recover on a"
                            f" Short Rest with `{ctx.prefix}csettings srslots true`."
                        )
            except NoCharacter:
                pass

            embed.description = f"""
            After a long day of keeping your Barbarian from knocking themself out, or of making sure those pesky melee attacks don’t hit your fragile Wizard body, it is good to take a Long Rest to regain all of your expended power, so you can do it all again tomorrow.

            Simply run the command to Long Rest, and all of your used spell slots will be restored. This also restores your HP and resets other things that might reset on a Long Rest.
            ```
            {ctx.prefix}game longrest
            ```
            {warlock_info}
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("game longrest"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            And with that, you have successfully completed the Spellcasting tutorial. You are well on your way to being a master caster. If you ever need to review how to cast a spell, upcast a spell, manually gain/lose spell slots, or long rest, you can use `{ctx.prefix}help cast` (for casting/upcasting), `{ctx.prefix}help game spellslot` (for manually setting spell slot count), and `{ctx.prefix}game longrest` (for long resting).

            And, as a final note, please understand that, on some of the sheet trackers that Avrae supports, there is a way to differentiate between learned and prepared spells on the sheet; however, Avrae does not keep track of which of your spells are simply learned, versus those that are prepared. It is best to keep track of which spells you have prepared manually.
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
