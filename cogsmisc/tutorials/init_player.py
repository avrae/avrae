import asyncio

from cogs5e.initiative import CombatNotFound, InitiativeEffect, MonsterCombatant, PlayerCombatant
from cogs5e.utils import targetutils
from gamedata import Monster
from gamedata.compendium import compendium
from utils.argparser import ParsedArguments, argparse
from .errors import PrerequisiteFailed
from .models import Tutorial, TutorialEmbed, TutorialState, state


class PlayerInitiative(Tutorial):
    name = "Initiative (Player)"
    description = """
    *15 minutes*
    Initiative lets your party track time at the smallest scale, a useful tool for combat and other fast-paced scenarios. This tutorial goes over how to join an encounter using the initiative tracker, as a player.
    """

    @state(first=True)
    class JoiningInitiative(TutorialState):
        async def setup(self, ctx, state_map):
            # preflight: must be in a guild
            if ctx.guild is None:
                await state_map.end_tutorial(ctx)
                raise PrerequisiteFailed(
                    "This tutorial cannot be run in private messages, since initiative tracking "
                    "is tied to a server's channel. Try again in a server!"
                )

            # preflight: channel not in combat
            try:
                await ctx.get_combat()
            except CombatNotFound:
                pass
            else:
                await state_map.end_tutorial(ctx)
                raise PrerequisiteFailed(
                    "This channel is already in combat. You'll need a channel to yourself to run this tutorial!"
                )

            # first message
            character = await ctx.get_character()
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            *The massive creature stomps ever closer, its every step felling entire tracts of jungle underfoot.  {character.name}, even from your vantage point atop the bluff, the spiked, scaly monster towers above you still.  You watch across the treetops as the countless jungle birds take flight and flee before it.  Maybe you should have fled, too.

            But it’s too late for that now.

            The tarrasque has your scent.

            Roll for initiative!*
            """
            await ctx.send(embed=embed)

            await ctx.trigger_typing()
            await asyncio.sleep(4)
            state_map.persist_data["channel_id"] = ctx.channel.id
            await state_map.commit(ctx)

            await ctx.bot.get_command("init begin")(ctx)
            combat = await ctx.get_combat()
            await add_tarrasque(ctx, combat)
            await ctx.send("TA1 was added to combat with initiative 1d20 (12) + 0 = `12`.")  # rolling dice is hard
            await ctx.trigger_typing()
            await asyncio.sleep(2)

        async def objective(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                await ctx.send(f"This tutorial can only be run in <#{state_map.persist_data.get('channel_id')}>.")
                return

            # objective
            embed2 = TutorialEmbed(self, ctx)
            embed2.title = "Joining Initiative"
            embed2.description = f"""
            Initiative lets your party track time at the smallest scale, a useful tool for combat and other fast-paced scenarios.  Avrae can make that process even easier.  It will track the turn order, alert you when your turn arrives, let you target specific creatures with attacks or spells, and automatically manage health and other effects.
            
            Now that your DM has started initiative with Avrae, take a look at the pinned messages for your channel.  You’ll see that Avrae has pinned the turn order there for easy reference.  The tarrasque has already joined using the name TA1.
            
            Let’s add your character, too.
            ```
            {ctx.prefix}init join
            ```
            """
            await ctx.send(embed=embed2)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return

            # The tutorial person ran !init join, there is an active combat, and the character is in combat
            if ctx.command is ctx.bot.get_command("init join"):
                pc = await get_pc(ctx)
                if pc:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            character = await ctx.get_character()
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            It’s that easy!  Avrae automatically rolled initiative for you and added you to the turn order.  If you check that pinned message again, {character.name} is already there in the list, right at the number you rolled.

            The next time you join, you can try adding `-p <value>` to use a specific number for your roll instead, like `{ctx.prefix}init join -p 10`.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.PlayerStatus, 5)

    @state()
    class PlayerStatus(TutorialState):
        async def objective(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                await ctx.send(f"This tutorial can only be run in <#{state_map.persist_data.get('channel_id')}>.")
                return

            # go to character in init
            combat = await ctx.get_combat()
            pc = await get_pc(ctx)
            if combat.current_combatant is not pc:
                combat.goto_turn(pc, is_combatant=True)
                await ctx.send(combat.get_turn_str(), allowed_mentions=combat.get_turn_str_mentions())
                await combat.final()

            embed = TutorialEmbed(self, ctx)
            embed.title = "Combatant Status"
            embed.description = f"""
            That Discord notification you just got means it’s now your turn!  Avrae starts each turn by displaying the combatant’s current status, which you can see above.  And if you check the pinned messages, your name is now highlighted as well, signaling that it’s currently your turn.
            
            If you ever need that status again, you can call for it at will with `{ctx.prefix}init status [name]`.  Let’s use that to take a quick peek at the tarrasque’s status instead.  You’ll need to use it’s combatant name for this: TA1.
            ```
            {ctx.prefix}init status TA1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command is ctx.bot.get_command("i status"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Looks a little different than yours, doesn’t it?  By default, enemy stats are hidden from players.  The mystery is part of the fun!
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Attacks1, 5)

    @state()
    class Attacks1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Attacks in Initiative"
            embed.description = f"""
            Now even though all those villagers -- and your DM -- warned you not to, let’s pick a fight with this tarrasque anyway.  For that, you’ll need the command `{ctx.prefix}[action|attack|a] [action_name] [args]`.
            
            We’ll use the `{ctx.prefix}a` shortcut for this tutorial.  After that, we need the attack name.  You can use `{ctx.prefix}a list` to see your available options.  If you pick a name that contains more than one word, be sure to add quotes around it, too, like `"unarmed strike"`.
            
            Now since we’re in initiative, we can also direct that attack at our tarrasque.  For that, you’ll add `-t` (for `-t`arget), plus the name of the creature we want to attack (TA1).
            
            Let’s give it a try, using any attack you like.
            ```
            {ctx.prefix}a "unarmed strike" -t TA1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command in (ctx.bot.get_command("i a"), ctx.bot.get_command("a")):
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
            embed.title = "Attacks in Initiative II"
            embed.description = f"""
            You always attack with your own character using `{ctx.prefix}action`.  However, initiative has a matching command, `{ctx.prefix}init attack` (`{ctx.prefix}i a` for short), that uses the current combatant instead.  Since it’s currently your turn, right now that’s you.  On the tarrasque’s turn, `{ctx.prefix}init attack` can therefore be used to attack as the tarrasque.
            
            Whichever version you use, there are plenty of other arguments you can add to attacks, too.  If your first attack didn't land, try adding `hit` this time.  If you hurt the tarrasque already, you can have some other fun here.  You might try attacking with advantage (`adv`) or changing the damage type (`-dtype fire`) instead.
            ```
            {ctx.prefix}init a "unarmed strike" -t TA1 hit
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command is ctx.bot.get_command("i a"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            That’s it!  You can use `!help action` for the full list of available arguments.
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(2)

            character = await ctx.get_character()
            if character.spellbook.spells:
                await state_map.transition(ctx, self.tutorial.Spells1)
            else:
                await state_map.transition(ctx, self.tutorial.Health1)

    @state()
    class Spells1(TutorialState):
        async def objective(self, ctx, state_map):
            character = await ctx.get_character()
            embed = TutorialEmbed(self, ctx)
            embed.title = "Spells in Initiative"
            embed.description = f"""
            In addition to attacks, {character.name} has another useful ability: spellcasting.  Initiative lets you target your spells at other combatants, too, both friends and foes alike.
            
            You can use `{ctx.prefix}spellbook` to see which spells you have available.  To cast any other spells (if you were using a spell scroll, for example), you can add `-i` to ignore the usual spellcasting requirements.  And once again, be sure to use quotes around any spell whose name is more than one word, like `"vicious mockery"`.
            
            Try targeting the tarrasque now using Vicious Mockery or another spell of your choice.
            ```
            {ctx.prefix}cast "vicious mockery" -t TA1 -i
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command in (ctx.bot.get_command("i cast"), ctx.bot.get_command("cast")):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Spells2)

    @state()
    class Spells2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Spells in Initiative II"
            embed.description = f"""
            Like attacks, `{ctx.prefix}cast` has an initiative counterpart called `{ctx.prefix}init cast`.  The same condition applies here as well: `{ctx.prefix}cast` uses your active character, and `{ctx.prefix}init cast` uses the active combatant.
            
            Now since he didn’t go away, we shall taunt him a second time.  With **meteors**.
            ```
            {ctx.prefix}init cast "meteor swarm" -t TA1 -i -phrase "A Dinosaur’s Best Friend!"
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command is ctx.bot.get_command("i cast"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Oh right.  It’s immune to fire.  Welp...
            
            Be sure to check `{ctx.prefix}help cast` or try the Spellcasting tutorial for more magical options.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Health1, 5)

    @state()
    class Health1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Managing Health"
            embed.description = f"""
            Go ahead and check that pinned message one more time.  If you were lucky enough to cause any damage there, you probably noticed the tarrasque changed from `<Healthy>` to `<Injured>`.
            
            Your own health won’t display with such colorful descriptions, however.  Avrae shows your exact HP so you can plan your turn accordingly.  When monsters target you and cause damage, this number will update automatically.
            
            Let’s manually change your health for now to see it in action.
            ```
            {ctx.prefix}game hp -5
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            character = await ctx.get_character()
            if (
                ctx.command in (ctx.bot.get_command("i hp"), ctx.bot.get_command("g hp"))
                and character.hp < character.max_hp
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            You can use `{ctx.prefix}help game hp` or try the *Playing the Game* tutorial for more ways to manage your HP.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Health2, 5)

    @state()
    class Health2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Managing Health II"
            embed.description = f"""
            Like attacks, initiative also has its own command for managing health: `{ctx.prefix}init hp <name> [hp]`.  The last command, `{ctx.prefix}game hp` is used for your character.  By specifying a name for this one, we can access any combatant.
            
            Go ahead and adjust the tarrasque’s HP.  We’ll set it to 300.
            ```
            {ctx.prefix}init hp set TA1 300
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            terry = await get_terry(ctx)
            if (
                ctx.command
                in (ctx.bot.get_command("i hp"), ctx.bot.get_command("i hp mod"), ctx.bot.get_command("i hp set"))
                and terry.hp == 300
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Now the tarrasque has changed from `<Healthy>` or `<Injured>` to `<Bloodied>`!  As the battle progresses (assuming you live long enough ~~and we stop cheating~~), it will eventually drop to `<Critical>`, then `<Dead>`.
            
            And as a general note: cheating is fine in a tutorial, but use this command wisely.  Your DM will get a message from Avrae any time the monster’s health is changed.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Effects, 5)

    @state()
    class Effects(TutorialState):
        async def setup(self, ctx, state_map):
            combat = await ctx.get_combat()
            pc = await get_pc(ctx)
            effect_obj = InitiativeEffect.new(
                combat,
                pc,
                name="Future Lunch",
                duration=-1,
                effect_args=argparse("-vuln piercing -vuln acid"),
                desc="A hungry tarrasque has your scent!",
            )
            pc.add_effect(effect_obj)
            await ctx.send(f"Added effect Future Lunch to {pc.name}.")
            await combat.final()

        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects"
            embed.description = f"""
            Aside from health, Avrae can also track conditions, spell durations, and other temporary effects.  If you check that pinned message again, you should see a new one next to your character.
            
            We can use `{ctx.prefix}init status` again to take a closer look.
            ```
            {ctx.prefix}init status
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command is ctx.bot.get_command("i status"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.Effects2)

    @state()
    class Effects2(TutorialState):
        async def objective(self, ctx, state_map):
            pc = await get_pc(ctx)
            pc_name = pc.name if " " not in pc.name else f'"{pc.name}"'
            embed = TutorialEmbed(self, ctx)
            embed.title = "Effects II"
            embed.description = f"""
            Well that doesn’t look good.  We’d better remove that before the tarrasque takes its turn.  You might also need to remove effects if its condition ends or if you lose your concentration on a spell.  If your effect has a duration, however, that will end automatically when the duration expires.
            
            For now, we can use `{ctx.prefix}init re <name> [effect]`.  If you provide an effect name, it will end only that effect.  Otherwise, it ends all effects on that combatant.
            ```
            {ctx.prefix}init re {pc_name} "future lunch"
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            pc = await get_pc(ctx)
            if ctx.command is ctx.bot.get_command("i re") and pc.get_effect("Future Lunch") is None:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Effects can also be used to add a damage bonus, grant new attacks, and more. Usually, your abilities will add them automatically, but you can also add them manually as needed.  Check out `{ctx.prefix}help init effect` for the full details.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.EndingTurn, 5)

    @state()
    class EndingTurn(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Ending Your Turn"
            embed.description = f"""
            That’s all we can do for now.  It’s time to accept our fate and end our turn.  You can use `{ctx.prefix}init next` to pass the baton to the next creature in the initiative order.
            ```
            {ctx.prefix}init next
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get("channel_id"):
                return
            if ctx.command is ctx.bot.get_command("i next"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            *As you complete the ancient Avrae ritual, there is far less **gnashing of teeth** than you had come to expect.  In fact, the titanic tarrasque appears strangely accepting of your presence.
            
            It seems your mastery of initiative commands has earned its respect.  It is ready to join you on your adventures.  You can call it Terry and ride together into legend.
            
            And if your DM says no to this... well, you can just introduce them to Terry.*
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
            await asyncio.sleep(7)
            try:
                combat = await ctx.get_combat()
                summary = combat.get_summary_msg()
                await combat.end()
                await ctx.send("Combat ended.")
                await summary.edit(content=combat.get_summary() + " ```-----COMBAT ENDED-----```")
                await summary.unpin()
            except Exception:
                pass


async def add_tarrasque(ctx, combat):
    tarrasque = compendium.lookup_entity(Monster.entity_type, 17034)
    terry = MonsterCombatant.from_monster(
        monster=tarrasque,
        ctx=ctx,
        combat=combat,
        name="TA1",
        controller_id=str(ctx.bot.user.id),
        init=12,
        private=True,
    )
    combat.add_combatant(terry)
    await combat.final()
    return terry


async def get_pc(ctx):
    character = await ctx.get_character()
    caster, _, _ = await targetutils.maybe_combat(ctx, character, ParsedArguments.empty_args())
    if isinstance(caster, PlayerCombatant):
        return caster
    raise PrerequisiteFailed(f"You are no longer in combat. Try rejoining with `{ctx.prefix}init join`!")


async def get_terry(ctx):
    combat = await ctx.get_combat()
    terry = next(
        (c for c in combat.get_combatants() if isinstance(c, MonsterCombatant) and c.monster_id == 17034), None
    )
    if terry is None:
        raise PrerequisiteFailed(
            f"The tarrasque appears to no longer be in combat. Try readding it with `{ctx.prefix}i madd tarrasque`!"
        )
    return terry
