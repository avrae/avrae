import asyncio

from cogs5e.models.initiative import CombatNotFound, MonsterCombatant
from gamedata import Monster
from gamedata.compendium import compendium
from utils.functions import confirm
from .errors import PrerequisiteFailed
from .models import Tutorial, TutorialEmbed, TutorialState, state


class DMInitiative(Tutorial):
    name = "Initiative (DM)"
    description = """
    *20 minutes*
    When your players fall head first into conflict (despite your warnings), Avrae's combat tracker is a fantastic addition to your DM toolset. This tutorial goes over how to set up and run an encounter using the initiative tracker, as a Dungeon Master.
    """

    @state(first=True)
    class StartingCombat(TutorialState):
        async def setup(self, ctx, state_map):
            # preflight: must be in a guild
            if ctx.guild is None:
                await state_map.end_tutorial(ctx)
                raise PrerequisiteFailed("This tutorial cannot be run in private messages, since initiative tracking "
                                         "is tied to a server's channel. Try again in a server!")

            # preflight: channel not in combat
            try:
                await ctx.get_combat()
            except CombatNotFound:
                pass
            else:
                await state_map.end_tutorial(ctx)
                raise PrerequisiteFailed(
                    "This channel is already in combat. You'll need a channel to yourself to run this tutorial!")

        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Starting Combat"
            embed.description = f"""
            *The creature turns to face you, the sharp fangs of its twin heads gleaming in the moonlight as it rushes to attack.  Roll for initiative!*
            
            When your players fall head first into conflict (despite your warnings), Avrae's combat tracker is a fantastic addition to your DM toolset.  It handles all the fine details so you can focus on what matters: the story.
            
            The first step is a simple one.  Let's start initiative.
            ```
            {ctx.prefix}init begin
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            # The tutorial person ran !init begin and there is an active combat in the channel
            if ctx.command is ctx.bot.get_command('init begin'):
                try:
                    await ctx.get_combat()
                except CombatNotFound:
                    return
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            state_map.persist_data['channel_id'] = ctx.channel.id
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            It begins!  As you can see, Avrae has pinned a new post to your Discord channel.  This post will automatically update as the fight plays out, giving you an easy look at turn order, health, and active effects.  Keep an eye on it as we continue.
            
            In the following steps, we'll be using `{ctx.prefix}i` as a shortcut for `{ctx.prefix}init`.  When Avrae lists a command like `{ctx.prefix}[init|i]`, that means you can use either name for the same command.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.AddCombatants, 5)

    @state()
    class AddCombatants(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Adding Combatants"
            embed.description = f"""
            Now it's time to add our combatants.  Your players can use `{ctx.prefix}i join` to add their active characters while you bring the monsters.  For that, you'll need `{ctx.prefix}init madd <monster_name> [args...]`.
            
            If you've connected your D&D Beyond account, you can use any monster you have unlocked.  But for now, let's use one from the free Basic Rules: the death dog.
            
            Because this monster's name has more than one word, you'll need to place quotes around it for Avrae to add correctly.
            ```
            {ctx.prefix}i madd "death dog"
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            # !init madd and there is a death dog in combat
            if ctx.command is ctx.bot.get_command('i madd'):
                the_combat = await ctx.get_combat()
                if get_the_woofer(the_combat) is not None:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            By default, Avrae gives each monster a unique ID using the first two letters of its name and a number.  If you check your pinned messages, you should see DE1 added to the fight.
            
            There are other arguments you can use here, too, to control how the monster is added.  You can give it a special name (`-name Woofer`), add a few at once (`-n 3`) or (`-n 1d3`), and more.  Check `{ctx.prefix}help i madd` for the full list.
            
            Just for fun, you can also use `{ctx.prefix}monimage death dog` to give your players a frightening look at the monstrosity bearing down on them.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.TurnOrder, 5)

    @state()
    class TurnOrder(TutorialState):
        async def setup(self, ctx, state_map):
            the_combat = await ctx.get_combat()
            await add_orkira(ctx, the_combat)
            await ctx.send("Orkira Illdrex was added to combat with initiative 1.")
            await asyncio.sleep(2)

        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Turn Order"
            embed.description = f"""
            Now that your player, Orkira, has joined the fight too, let's begin.  Use `{ctx.prefix}i next` after each turn to move to the next combatant.  Try it now to start the death dog's turn.
            ```
            {ctx.prefix}i next
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i next'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            There are other commands you can use to control the turn order as well.  While `{ctx.prefix}i next` goes forward, `{ctx.prefix}i prev` goes back.  You can also jump to a specific combatant with `{ctx.prefix}i move <name>`.
            
            If you check your pins again, you'll also see that DE1 is now highlighted, indicating the current turn.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Attacks1, 5)

    @state()
    class Attacks1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Taking Your Turn - Attacks"
            embed.description = f"""
            Your death dog got the higher roll for initiative, so it goes first.  Let's have it move in to attack, which you can do with `{ctx.prefix}init [attack|a] <atk_name> [args]`.  (We'll be using the `{ctx.prefix}i a` shortcut here).
            
            First we'll enter the name of our attack, `bite`.  Then we need to tell it to target our player.  For that, we add `-t` followed by the target's name.  In this case, it's `-t Orkira`.
            ```
            {ctx.prefix}i a bite -t Orkira
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i a') and '-t ' in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            When you attack, Avrae first compares the roll to the target's AC.  On a hit, it automatically rolls the damage and subtracts it from the target's HP.  It even accounts for resistance, immunity, and vulnerability, too.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Attacks2, 5)

    @state()
    class Attacks2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Taking Your Turn - Attacks II"
            embed.description = f"""
            If your first attack didn't land, good news: your death dog has multiattack.  Let's make one more bite attack, but this time we'll make sure it hits by adding `hit`.  If you hit already, you can have some fun here instead.  Try attacking with advantage (`adv`) or giving Orkira resistance (`-resist piercing`) instead.
            ```
            {ctx.prefix}i a bite -t Orkira hit
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i a') and '-t ' in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Good!  Next time you can have it make both attacks at once (by adding `-rr 2`) or by giving it multiple targets (`-t Orkira -t Briv`).  There's plenty of other ways you can adjust your attack, too.  Check `{ctx.prefix}help i a` for the full list.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.HitPoints1, 5)

    @state()
    class HitPoints1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points"
            embed.description = f"""
            Since Orkira has now taken some damage, try checking that pinned message again.  You can see it's been updated to reflect her current HP.
            
            You might also notice, however, that the death dog's exact HP is not shown.  It's simply stated as `<Healthy>`.  Let's manually apply some damage using `{ctx.prefix}init hp <name> [hp]`.
            ```
            {ctx.prefix}i hp DE1 -1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i hp'):
                the_combat = await ctx.get_combat()
                woofer = get_the_woofer(the_combat)
                if woofer is None:
                    await ctx.send(f"Uh oh, looks like I can't find the Death Dog. "
                                   f"Try readding it with `{ctx.prefix}i madd \"Death Dog\"`")
                    return
                if woofer.hp < woofer.max_hp:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.HitPoints2)

    @state()
    class HitPoints2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points II"
            embed.description = f"""
            As you can see, DE1 has changed from `<Healthy>` to `<Injured>`.  This gives players a rough idea of a creature's health without spoiling things entirely.  Since you, the DM, control that creature, you have also received a direct message from Avrae revealing its actual HP.
            
            As the battle continues and our creature drops to half of its max HP, that status will change again.  Let's use `{ctx.prefix}init hp set <name> <hp>` this time to set its HP to a specific value.
            ```
            {ctx.prefix}i hp set DE1 15
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command in (
                    ctx.bot.get_command('i hp set'),
                    ctx.bot.get_command('i hp')
            ):
                the_combat = await ctx.get_combat()
                woofer = get_the_woofer(the_combat)
                if woofer is None:
                    await ctx.send(f"Uh oh, looks like I can't find the Death Dog. "
                                   f"Try readding it with `{ctx.prefix}i madd \"Death Dog\"`")
                    return
                if woofer.hp == 15:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Our death dog is now `<Bloodied>`, indicating that it has taken significant damage.  Its displayed health will change again at 15% to `<Critical>`, and at 0 to `<Dead>`.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.HitPoints3, 5)

    @state()
    class HitPoints3(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Hit Points III"
            embed.description = f"""
            Now since the death dog hasn't actually taken damage in our fight here, let's reset its health using `{ctx.prefix}init hp max <name>`.
            ```
            {ctx.prefix}i hp max DE1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command in (
                    ctx.bot.get_command('i hp max'),
                    ctx.bot.get_command('i hp')
            ):
                the_combat = await ctx.get_combat()
                woofer = get_the_woofer(the_combat)
                if woofer is None:
                    await ctx.send(f"Uh oh, looks like I can't find the Death Dog. "
                                   f"Try readding it with `{ctx.prefix}i madd \"Death Dog\"`")
                    return
                if woofer.hp == woofer.max_hp:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.EndingYourTurn)

    @state()
    class EndingYourTurn(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Ending Your Turn"
            embed.description = f"""
            DE1 is back to `<Healthy>` and ready for the fight, but that's all it can do for now.  Let's end our turn and move to the next combatant.
            ```
            {ctx.prefix}i next
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i next'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Spellcasting)

    @state()
    class Spellcasting(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Taking Your Turn II - Spellcasting"
            embed.description = f"""
            Orkira the cleric is up next.  Normally your players would run their own commands here, but when it's their turn in initiative, you can also act for them.  The same `{ctx.prefix}init` commands always work for the current combatant, whether it's a monster or a player.
            
            As for Orkira herself, she has one big advantage over your death dog: spellcasting!  The command this time is `{ctx.prefix}init cast <spell_name> [args]`.
            
            Let's summon a spiritual weapon and target our death dog (`-t DE1`).  Don't forget those quotes around the spell name since it's more than one word.
            ```
            {ctx.prefix}i cast "spiritual weapon" -t DE1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i cast'):
                the_combat = await ctx.get_combat()
                orkira = get_orkira(combat=the_combat)
                if orkira is None:
                    addback = await confirm(ctx,
                                            "Uh oh, it looks like Orkira isn't in the fight anymore. "
                                            "Would you like me to add her back?")
                    if addback:
                        orkira = await add_orkira(ctx, the_combat)
                        await ctx.send("Ok. I've added her back to the fight - try again!")
                    else:
                        await ctx.send(f"Ok. If you'd like to continue this tutorial later, "
                                       f"run `{ctx.prefix}tutorial` to add Orkira back and continue.")
                        return

                if orkira.get_effect("Spiritual Weapon"):
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Avrae automatically subtracts the spell slot and will stop you from casting if you don't have a slot to spare.  And just like attacks, spell commands can be adjusted in a number of other ways.  You can upcast with `-l <level>` (that's **-l** for **-l**evel), use `-i` to -**i**gnore requirements (when using a spell scroll, for example), and more.  See `!help i cast` for the full list.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Effects, 5)

    @state()
    class Effects(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects"
            embed.description = f"""
            Go ahead and check that pinned message again.  If you look at Orkira, you should see that spell did something more than just make an attack.  That's called an effect.  Among other things, it's used to track the duration for the spell we just cast.
            
            Let's fast forward our combat a little bit.  Use `{ctx.prefix}i skipround` to jump ahead to Orkira's next turn.
            ```
            {ctx.prefix}i skipround
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i skipround'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            As you can see, it's down to just 9 rounds left.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Effects2, 5)

    @state()
    class Effects2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects II"
            embed.description = f"""
            So what else does this effect do?  We can take a closer look at Orkira to find out, using `{ctx.prefix}init status [name] [args]`.
            ```
            {ctx.prefix}i status Orkira
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i status') and 'o' in ctx.message.content.lower():
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Effects3)

    @state()
    class Effects3(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects III"
            embed.description = f"""
            If you look closely, you'll notice this effect comes with a new attack.  This attack has the same name as the effect (in this case, `"spiritual weapon"`), which you can verify by checking her attacks (`{ctx.prefix}i a list Orkira`).
            
            The help text there also says Orkira can spend her bonus action to use that attack now.  Let's give it a try!
            ```
            {ctx.prefix}i a "spiritual weapon" -t DE1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i a') and '-t ' in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Effects can also be used to add a damage bonus, grant resistance, and more.  You can also add them manually as needed.  Check out `{ctx.prefix}help i effect` for the full details.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Effects4, 5)

    @state()
    class Effects4(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects IV"
            embed.description = f"""
            When an effect's duration expires, it will end automatically.  Cases often arise, however, that could cause it to end early.  Perhaps an enemy wizard cast dispel magic.  In such an event, we can end the effect early using `{ctx.prefix}init re <name> [effect]`.
            ```
            {ctx.prefix}i re Orkira "spiritual weapon"
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i re'):
                the_combat = await ctx.get_combat()
                orkira = get_orkira(combat=the_combat)
                if orkira is None:
                    await ctx.send("Uh oh, it looks like Orkira isn't in the fight anymore. "
                                   "Let's move on to the next part of the tutorial.")
                    await self.transition(ctx, state_map)
                    return

                if not orkira.get_effect("Spiritual Weapon"):
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            If you look once more at the pinned message or at Orkira's status, that effect is no longer there.  The attack it provided is also gone, which you can verify with `{ctx.prefix}i a list Orkira`.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.RemovingCombatants, 5)

    @state()
    class RemovingCombatants(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Removing Combatants"
            embed.description = f"""
            Combatants can similarly be removed.  If Orkira defeats the death dog (changing its status to `<Dead>`), it will be removed automatically at the end of its turn.  For now, it's going to avoid that fate and choose to flee instead.  We can remove it manually with `{ctx.prefix}init remove <name>`.
            ```
            {ctx.prefix}i remove DE1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i remove'):
                the_combat = await ctx.get_combat()
                woofer = get_the_woofer(combat=the_combat)
                if woofer is None:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.EndingCombat)

    @state()
    class EndingCombat(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Ending Combat"
            embed.description = f"""
            The death dog runs, tail between its legs, leaving Orkira the victor.  With the fight over, we can now end initiative.
            ```
            {ctx.prefix}i end
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i end'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = """
            Congratulations!  You've run your first successful combat.  Now you can help your players run through the Initiative (Player) tutorial, too.  Then the whole party will be ready for whatever monster you throw at them!
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)


async def add_orkira(ctx, combat):
    priest = compendium.lookup_entity(Monster.entity_type, 16985)
    orkira = MonsterCombatant.from_monster(
        monster=priest,
        ctx=ctx,
        combat=combat,
        name="Orkira Illdrex",
        controller_id=str(ctx.author.id),
        init=1,
        private=False,
        hp=50
    )
    combat.add_combatant(orkira)
    await combat.final()
    return orkira


def get_the_woofer(combat):
    """Gets the next death dog in combat (hopefully DE1?)"""
    return next((c for c in combat.get_combatants()
                 if isinstance(c, MonsterCombatant) and c.monster_name == 'Death Dog'), None)


def get_orkira(combat):
    """Gets Orkira (hopefully?)"""
    return combat.get_combatant("Orkira Illdrex", strict=True)
