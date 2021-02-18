import asyncio

from cogs5e.funcs import targetutils
from cogs5e.models.initiative import CombatNotFound, MonsterCombatant, PlayerCombatant
from gamedata.compendium import compendium
from utils.argparser import ParsedArguments
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
        async def objective(self, ctx, state_map):
            character = await ctx.get_character()
            if not state_map.data.get('has_setup'):
                # preflight: channel not in combat
                try:
                    await ctx.get_combat()
                except CombatNotFound:
                    pass
                else:
                    await ctx.send(
                        "This channel is already in combat. You'll need a channel to yourself to run this tutorial!")
                    await state_map.end_tutorial(ctx)
                    return

            # first message
            embed = TutorialEmbed(self, ctx)
            embed.title = "Joining Initiative"
            embed.description = f"""
            *The massive creature stomps ever closer, its every step felling entire tracts of jungle underfoot.  {character.name}, even from your vantage point atop the bluff, the spiked, scaly monster towers above you still.  You watch across the treetops as the countless jungle birds take flight and flee before it.  Maybe you should have fled, too.
            
            But it’s too late for that now.
            
            The tarrasque has your scent.
            
            Roll for initiative!*
            """
            await ctx.send(embed=embed)

            # set up channel
            if not state_map.data.get('has_setup'):
                await ctx.trigger_typing()
                await asyncio.sleep(4)
                state_map.persist_data['channel_id'] = ctx.channel.id
                await ctx.bot.get_command('init begin')(ctx)
                combat = await ctx.get_combat()
                await add_tarrasque(ctx, combat)
                await ctx.send("TA1 was added to combat with initiative 1d20 (12) + 0 = `12`.")  # rolling dice is hard
                state_map.data['has_setup'] = True
                await ctx.trigger_typing()
                await asyncio.sleep(2)

            # objective
            embed2 = TutorialEmbed(self, ctx, colour=embed.colour)
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
            # The tutorial person ran !init join, there is an active combat, and the character is in combat
            if ctx.command is ctx.bot.get_command('init join'):
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
            await ctx.trigger_typing()
            await asyncio.sleep(5)
            await state_map.transition(ctx, self.tutorial.PlayerStatus)

    @state()
    class PlayerStatus(TutorialState):
        async def objective(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
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
            embed.title = "Player Status"
            embed.description = f"""
            That Discord notification you just got means it’s now your turn!  Avrae starts each turn by displaying the combatant’s current status, which you can see above.  And if you check the pinned messages, your name is now highlighted as well, signaling that it’s currently your turn.
            
            If you ever need that status again, you can call for it at will with `{ctx.prefix}init status [name]`.  Let’s use that to take a quick peek at the tarrasque’s status instead.  You’ll need to use it’s combatant name for this: TA1.
            ```
            {ctx.prefix}init status TA1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command is ctx.bot.get_command('i status'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Looks a little different than yours, doesn’t it?  By default, enemy stats are hidden from players.  The mystery is part of the fun!
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(3)
            await state_map.transition(ctx, self.tutorial.Attacks1)

    @state()
    class Attacks1(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Attacks in Combat"
            embed.description = f"""
            Now even though all those villagers -- and your DM -- warned you not to, let’s pick a fight with this tarrasque anyway.  For that, you’ll need the command `{ctx.prefix}[attack|a] [atk_name] [args]`.
            
            We’ll use the `{ctx.prefix}a` shortcut for this tutorial.  After that, we need the attack name.  You can use `{ctx.prefix}a list` to see your available options.  If you pick a name that contains more than one word, be sure to add quotes around it, too, like `"unarmed strike"`.
            
            Now since we’re in initiative, we can also direct that attack at our tarrasque.  For that, you’ll add `-t` (for `-t`arget), plus the name of the creature we want to attack (TA1).
            
            Let’s give it a try, using any attack you like.
            ```
            {ctx.prefix}a "unarmed strike" -t TA1
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command in (
                    ctx.bot.get_command('i a'),
                    ctx.bot.get_command('a')
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            When you attack, Avrae first compares the roll to the target's AC.  On a hit, it automatically rolls the damage and subtracts it from the target's HP.  It even accounts for resistance, immunity, and vulnerability, too.
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(3)
            await state_map.transition(ctx, self.tutorial.Attacks2)

    @state()
    class Attacks2(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Attacks in Combat II"
            embed.description = f"""
            You always attack using your own character using `{ctx.prefix}attack`.  However, initiative has a matching command, `{ctx.prefix}init attack` (`{ctx.prefix}i a` for short), that uses the current combatant instead.  Since it’s currently your turn, right now that’s you.  On the tarrasque’s turn, `{ctx.prefix}init attack` can therefore be used to attack as the tarrasque.
            
            Whichever version you use, there are plenty of other arguments you can add to attacks, too.  If your first attack didn't land, try adding `hit` this time.  If you hurt the tarrasque already, you can have some other fun here.  You might try attacking with advantage (`adv`) or changing the damage type (`-dtype fire`) instead.
            ```
            {ctx.prefix}init a "unarmed strike" -t TA1 hit
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.channel.id != state_map.persist_data.get('channel_id'):
                return
            if ctx.command in (
                    ctx.bot.get_command('i a'),
                    ctx.bot.get_command('a')
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            That’s it!  You can use `!help attack` for the full list of available arguments.
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(2)
            await state_map.transition(ctx, self.tutorial.Health1)

    # todo health1 on


async def add_tarrasque(ctx, combat):
    tarrasque = compendium.lookup_by_entitlement('monster', 17034)
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
    caster, _, _ = targetutils.maybe_combat(ctx, character, ParsedArguments.empty_args())
    if isinstance(caster, PlayerCombatant):
        return caster
    raise PrerequisiteFailed(f"You are no longer in combat. Try rejoining with `{ctx.prefix}init join`!")
