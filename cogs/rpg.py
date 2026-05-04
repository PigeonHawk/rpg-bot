import discord
from discord.ext import commands
import asyncio
import random
import os
from pathlib import Path

import data_manager as db
from compositor import render_battle_frame, clear_background_for_battle

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_HP      = 50
MAX_MP      = 30          # reserved for future spells
HIT_DAMAGE  = 10
GIL_MIN     = 20
GIL_MAX     = 80

# Element chart: attacker → beaten_by (what it loses TO)
# Fire beats Ice, Ice beats Wind, Wind beats Fire
ELEMENT_BEATS = {
    "fire": "ice",    # fire melts ice  → fire wins vs ice
    "ice":  "wind",   # ice blocks wind  → ice wins vs wind
    "wind": "fire",   # wind extinguishes fire → wind wins vs fire
}
# What each element loses to (inverse)
ELEMENT_LOSES_TO = {v: k for k, v in ELEMENT_BEATS.items()}

ELEMENT_EMOJI = {"fire": "🔥", "ice": "❄️", "wind": "🌪️"}

# Placeholder avatars/enemies — replace filenames once you add real sprites
AVAILABLE_AVATARS = [
    {"name": "Knight",    "file": "unit_ills_100000102.png"},
    {"name": "Shadow",    "file": "unit_ills_100000202.png"},
    {"name": "Archer",    "file": "unit_ills_100000302_-_Copy.png"},
    {"name": "Pirate",    "file": "unit_ills_100000315.png"},
    {"name": "Glacius",   "file": "unit_ills_100000403.png"},
    {"name": "Ember",     "file": "unit_ills_100000503.png"},
    {"name": "Corsair",   "file": "unit_ills_100019905.png"},
    {"name": "Wizard",    "file": "unit_ills_209001405.png"},
    {"name": "Cloud",     "file": "unit_ills_207002007.png"},
    {"name": "Scarlet",   "file": "unit_ills_207000305.png"},
    {"name": "Tails",     "file": "unit_ills_214000105.png"},
]

AVAILABLE_ENEMIES = [
    {"name": "Dark Knight",  "file": "unit_ills_201000203.png",  "level": 3},
    {"name": "Sea Dragon",   "file": "unit_ills_203000803.png",  "level": 4},
    {"name": "Warlord",      "file": "unit_ills_205000703.png",  "level": 5},
    {"name": "Dark Angel",   "file": "unit_ills_204001403.png",  "level": 6},
    {"name": "Demon Jester", "file": "unit_ills_206001703.png",  "level": 5},
    {"name": "Sephiroth",    "file": "unit_ills_207001005.png",  "level": 8},
    {"name": "Gold Reaper",  "file": "unit_ills_100007705.png",  "level": 7},
    {"name": "Green Knight", "file": "unit_ills_100007804.png",  "level": 4},
    {"name": "Death Mage",   "file": "unit_ills_100007904.png",  "level": 5},
    {"name": "Orc Brute",    "file": "unit_ills_100008005.png",  "level": 3},
    {"name": "Illidan",      "file": "unit_ills_100008104.png",  "level": 9},
    {"name": "Frost Wraith", "file": "unit_ills_100008205.png",  "level": 6},
    {"name": "Pirate Boss",  "file": "unit_ills_100000315.png",  "level": 4},
    {"name": "Sun Warrior",  "file": "unit_ills_205000805.png",  "level": 5},
]

# ── Active battle store (in-memory) ──────────────────────────────────────────
# key: channel_id → battle state dict
active_battles: dict[int, dict] = {}

# ── UI Views ──────────────────────────────────────────────────────────────────

class AvatarSelectView(discord.ui.View):
    """Lets a new player pick their avatar."""
    def __init__(self, user: discord.User):
        super().__init__(timeout=60)
        self.user = user
        self.chosen = None
        for i, avatar in enumerate(AVAILABLE_AVATARS):
            btn = discord.ui.Button(
                label=avatar["name"],
                style=discord.ButtonStyle.primary,
                custom_id=f"avatar_{i}"
            )
            btn.callback = self._make_callback(avatar)
            self.add_item(btn)

    def _make_callback(self, avatar: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("This isn't your registration!", ephemeral=True)
                return
            self.chosen = avatar
            self.stop()
            await interaction.response.defer()
        return callback


class ElementView(discord.ui.View):
    """Fire / Ice / Wind action buttons + Stop for a battle turn."""
    def __init__(self, battle_id: int, acting_user_id: int):
        super().__init__(timeout=60)
        self.battle_id      = battle_id
        self.acting_user_id = acting_user_id
        self.chosen         = None
        self.stopped        = False

        for elem in ["fire", "ice", "wind"]:
            btn = discord.ui.Button(
                label=f"{ELEMENT_EMOJI[elem]} {elem.capitalize()}",
                style=discord.ButtonStyle.primary,
                custom_id=f"elem_{elem}"
            )
            btn.callback = self._make_callback(elem)
            self.add_item(btn)

        stop_btn = discord.ui.Button(
            label="⏹️ Stop",
            style=discord.ButtonStyle.danger,
            custom_id="elem_stop"
        )
        stop_btn.callback = self._stop_callback
        self.add_item(stop_btn)

    def _make_callback(self, element: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.acting_user_id:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            self.chosen = element
            self.stop()
            await interaction.response.defer()
        return callback

    async def _stop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.acting_user_id:
            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
            return
        self.stopped = True
        self.stop()
        await interaction.response.defer()


class PostBossView(discord.ui.View):
    """After a PvE win — Fight Again or Pause."""
    def __init__(self, user_id: int):
        super().__init__(timeout=30)
        self.user_id  = user_id
        self.decision = None  # "continue" | "pause"

    @discord.ui.button(label="⚔️ Fight Another Boss", style=discord.ButtonStyle.success)
    async def fight_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
            return
        self.decision = "continue"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
            return
        self.decision = "pause"
        self.stop()
        await interaction.response.defer()


class ResumeView(discord.ui.View):
    """Shown when a paused player types !rpg."""
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id  = user_id
        self.decision = None

    @discord.ui.button(label="▶️ Continue Battle", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your save!", ephemeral=True)
            return
        self.decision = "resume"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ Abandon", style=discord.ButtonStyle.danger)
    async def abandon(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your save!", ephemeral=True)
            return
        self.decision = "abandon"
        self.stop()
        await interaction.response.defer()


# ── Cog ───────────────────────────────────────────────────────────────────────

class RPGCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Helper: build and send/edit battle embed ──────────────────────────────
    async def _send_battle_frame(
        self,
        channel: discord.TextChannel,
        state: dict,
        log_lines: list[str],
        view: discord.ui.View | None,
        existing_message: discord.Message | None = None,
    ) -> discord.Message:
        """Render a new frame and send or edit the battle message."""

        right_is_player = state.get("pvp", False)
        right_folder    = "avatars" if right_is_player else "enemies"

        img_path = render_battle_frame(
            battle_id      = str(state["id"]),
            left_name      = state["p1_name"],
            left_level     = state["p1_level"],
            left_hp        = state["p1_hp"],
            left_max_hp    = MAX_HP,
            left_mp        = state["p1_mp"],
            left_max_mp    = MAX_MP,
            left_sprite    = state["p1_sprite"],
            right_name     = state["p2_name"],
            right_level    = state["p2_level"],
            right_hp       = state["p2_hp"],
            right_max_hp   = MAX_HP,
            right_mp       = state["p2_mp"],
            right_max_mp   = MAX_MP,
            right_sprite   = state["p2_sprite"],
            right_is_player= right_is_player,
        )

        # ── Build embed ───────────────────────────────────────────────────
        turn_label = state.get("turn_label", "Your turn")
        embed = discord.Embed(color=0x7c3aed)
        embed.set_author(name=f"⚔️  {state['p1_name']}  vs  {state['p2_name']}")
        embed.set_image(url="attachment://battle.png")

        # ── HP/MP bars as text below the image ───────────────────────────
        def make_bar(current, maximum, length=16, fill="█", empty="░"):
            filled = round((current / maximum) * length)
            filled = max(0, min(length, filled))
            return fill * filled + empty * (length - filled)

        p1_hp_bar  = make_bar(state["p1_hp"], MAX_HP)
        p1_mp_bar  = make_bar(state["p1_mp"], MAX_MP)
        p2_hp_bar  = make_bar(state["p2_hp"], MAX_HP)
        p2_mp_bar  = make_bar(state["p2_mp"], MAX_MP)

        p1_hp_col  = "🟩" if state["p1_hp"] > MAX_HP * 0.3 else "🟥"
        p2_hp_col  = "🟩" if state["p2_hp"] > MAX_HP * 0.3 else "🟥"

        enemy_stats = (
            f"**{state['p2_name']}**  ·  LV{state['p2_level']}
"
            f"{p2_hp_col} HP `{p2_hp_bar}` {state['p2_hp']}/{MAX_HP}
"
            f"🟦 MP `{p2_mp_bar}` {state['p2_mp']}/{MAX_MP}"
        )
        player_stats = (
            f"**{state['p1_name']}**  ·  LV{state['p1_level']}
"
            f"{p1_hp_col} HP `{p1_hp_bar}` {state['p1_hp']}/{MAX_HP}
"
            f"🟦 MP `{p1_mp_bar}` {state['p1_mp']}/{MAX_MP}"
        )

        embed.add_field(name="👾 Enemy", value=enemy_stats, inline=True)
        embed.add_field(name="​", value="​", inline=True)   # spacer
        embed.add_field(name="🧙 Player", value=player_stats, inline=True)

        # Battle log
        log_text = "\n".join(log_lines[-4:]) if log_lines else "Battle begins!"
        embed.add_field(name="📜 Battle Log", value=f"```{log_text}```", inline=False)
        embed.set_footer(text=f"Round {state['round']}  ·  {turn_label}")

        file = discord.File(img_path, filename="battle.png")

        if existing_message:
            await existing_message.edit(embed=embed, attachments=[file], view=view)
            return existing_message
        else:
            return await channel.send(embed=embed, file=file, view=view)

    # ── Element resolution ────────────────────────────────────────────────────
    def _resolve_elements(self, attacker_elem: str, defender_elem: str) -> str:
        """Return 'win', 'lose', or 'draw'."""
        if attacker_elem == defender_elem:
            return "draw"
        if ELEMENT_BEATS[attacker_elem] == defender_elem:
            return "win"
        return "lose"

    # ── PvE battle loop ───────────────────────────────────────────────────────
    async def _run_pve_battle(self, ctx: commands.Context, player: dict, enemy: dict):
        channel = ctx.channel
        battle_id = ctx.author.id

        state = {
            "id":         battle_id,
            "pvp":        False,
            "p1_id":      ctx.author.id,
            "p1_name":    player["username"],
            "p1_level":   1,
            "p1_hp":      MAX_HP,
            "p1_mp":      MAX_MP,
            "p1_sprite":  player["avatar"],
            "p2_name":    enemy["name"],
            "p2_level":   enemy["level"],
            "p2_hp":      MAX_HP,
            "p2_mp":      MAX_MP,
            "p2_sprite":  enemy["file"],
            "round":      1,
            "turn_label": "Choose your element!",
            "log":        [f"A wild {enemy['name']} (Lv{enemy['level']}) appears!"],
        }
        active_battles[channel.id] = state

        msg = None
        while state["p1_hp"] > 0 and state["p2_hp"] > 0:
            view = ElementView(battle_id=battle_id, acting_user_id=ctx.author.id)
            state["turn_label"] = "🎯 Choose your element!"
            msg = await self._send_battle_frame(channel, state, state["log"], view, msg)

            await view.wait()

            if view.stopped:
                # Player clicked Stop — pause the battle
                db.update_player(ctx.author.id, paused_battle=state)
                active_battles.pop(channel.id, None)
                clear_background_for_battle(str(battle_id))
                await channel.send(
                    f"⏹️ **{ctx.author.display_name}** stopped the battle. "
                    f"Type `!rpgcontinue` to resume anytime!"
                )
                return

            if view.chosen is None:
                # Timed out — pause the battle
                db.update_player(ctx.author.id, paused_battle=state)
                active_battles.pop(channel.id, None)
                clear_background_for_battle(str(battle_id))
                await channel.send(
                    f"⏸️ **{ctx.author.display_name}** didn't respond in time. "
                    f"Battle paused! Type `!rpgcontinue` to resume."
                )
                return

            p_elem = view.chosen

            # CPU picks random element
            cpu_elem = random.choice(["fire", "ice", "wind"])
            result   = self._resolve_elements(p_elem, cpu_elem)

            p_emoji   = ELEMENT_EMOJI[p_elem]
            cpu_emoji = ELEMENT_EMOJI[cpu_elem]
            log_lines = list(state["log"])

            if result == "win":
                state["p2_hp"] -= HIT_DAMAGE
                log_lines.append(
                    f"{p_emoji} {state['p1_name']} used {p_elem.upper()} "
                    f"vs {cpu_emoji} {cpu_elem.upper()} → Hit! -{HIT_DAMAGE} HP"
                )
            elif result == "lose":
                state["p1_hp"] -= HIT_DAMAGE
                log_lines.append(
                    f"{cpu_emoji} {state['p2_name']} used {cpu_elem.upper()} "
                    f"vs {p_emoji} {p_elem.upper()} → {state['p1_name']} took -{HIT_DAMAGE} HP"
                )
            else:
                log_lines.append(
                    f"{p_emoji} {p_elem.upper()} vs {cpu_emoji} {cpu_elem.upper()} → Draw! No damage."
                )

            state["log"]   = log_lines
            state["round"] += 1
            state["p1_hp"] = max(0, state["p1_hp"])
            state["p2_hp"] = max(0, state["p2_hp"])

        # ── Battle over ───────────────────────────────────────────────────────
        active_battles.pop(channel.id, None)
        clear_background_for_battle(str(battle_id))
        state["turn_label"] = "Battle Over!"

        if state["p1_hp"] > 0:
            # Player wins
            gil_earned = random.randint(GIL_MIN, GIL_MAX)
            db.add_gil(ctx.author.id, gil_earned)
            db.update_player(ctx.author.id, wins=player.get("wins", 0) + 1, paused_battle=None)
            state["log"].append(f"🏆 {state['p1_name']} wins! Earned {gil_earned} gil!")
            msg = await self._send_battle_frame(channel, state, state["log"], None, msg)

            # Ask fight again or pause
            post_view = PostBossView(user_id=ctx.author.id)
            prompt = await channel.send(
                f"✨ Victory! You earned **{gil_earned} gil**! What's next?",
                view=post_view
            )
            await post_view.wait()
            await prompt.delete()

            if post_view.decision == "continue" or post_view.decision is None:
                if post_view.decision is None:
                    # Timed out — save paused state (no active battle, just flag)
                    db.update_player(ctx.author.id, paused_battle={"type": "post_win"})
                    await channel.send(
                        f"⏸️ No response. Paused! Type `!rpg` to start a new fight."
                    )
                    return
                # Start next boss
                db.reset_hp(ctx.author.id)
                new_enemy = random.choice(AVAILABLE_ENEMIES)
                updated_player = db.get_player(ctx.author.id)
                await self._run_pve_battle(ctx, updated_player, new_enemy)
            else:
                db.update_player(ctx.author.id, paused_battle={"type": "post_win"})
                await channel.send("⏸️ Paused! Type `!rpg` to start a new fight when ready.")
        else:
            # Player loses
            db.update_player(ctx.author.id, losses=player.get("losses", 0) + 1, paused_battle=None)
            state["log"].append(f"💀 {state['p1_name']} was defeated...")
            msg = await self._send_battle_frame(channel, state, state["log"], None, msg)
            db.reset_hp(ctx.author.id)
            await channel.send(
                f"💀 You were defeated by **{enemy['name']}**. "
                f"Your HP has been restored. Type `!rpg` to try again!"
            )

    # ── PvP battle loop ───────────────────────────────────────────────────────
    async def _run_pvp_battle(self, ctx: commands.Context, challenger: dict, opponent_member: discord.Member, opponent: dict):
        channel   = ctx.channel
        battle_id = ctx.author.id

        state = {
            "id":         battle_id,
            "pvp":        True,
            "p1_id":      ctx.author.id,
            "p1_name":    challenger["username"],
            "p1_level":   1,
            "p1_hp":      MAX_HP,
            "p1_mp":      MAX_MP,
            "p1_sprite":  challenger["avatar"],
            "p2_id":      opponent_member.id,
            "p2_name":    opponent["username"],
            "p2_level":   1,
            "p2_hp":      MAX_HP,
            "p2_mp":      MAX_MP,
            "p2_sprite":  opponent["avatar"],
            "round":      1,
            "turn_label": "Both players choose!",
            "log":        [f"⚔️ Duel: {challenger['username']} vs {opponent['username']}!"],
        }
        active_battles[channel.id] = state

        msg = None
        while state["p1_hp"] > 0 and state["p2_hp"] > 0:
            state["turn_label"] = "Both players choose simultaneously!"

            # Send views to both players simultaneously (ephemeral DMs not ideal in channel)
            # Instead: send one view that accepts input from either player,
            # collect both choices within timeout
            view_p1 = ElementView(battle_id=battle_id, acting_user_id=ctx.author.id)
            view_p2 = ElementView(battle_id=battle_id, acting_user_id=opponent_member.id)

            msg = await self._send_battle_frame(channel, state, state["log"], None, msg)
            prompt = await channel.send(
                f"{ctx.author.mention} & {opponent_member.mention} — both choose your element!\n"
                f"*(Each player will see their own button set below)*"
            )

            p1_msg = await ctx.author.send("⚔️ Choose your element for this round:", view=view_p1)
            p2_msg = await opponent_member.send("⚔️ Choose your element for this round:", view=view_p2)

            # Wait for both with timeout
            done, _ = await asyncio.wait(
                [asyncio.create_task(view_p1.wait()), asyncio.create_task(view_p2.wait())],
                timeout=60
            )

            await prompt.delete()

            # Check for timeouts
            if view_p1.chosen is None or view_p2.chosen is None:
                active_battles.pop(channel.id, None)
                timed_out = []
                if view_p1.chosen is None: timed_out.append(ctx.author.display_name)
                if view_p2.chosen is None: timed_out.append(opponent_member.display_name)
                await channel.send(
                    f"⏱️ {', '.join(timed_out)} didn't respond in time. Duel cancelled!"
                )
                return

            p1_elem = view_p1.chosen
            p2_elem = view_p2.chosen
            result  = self._resolve_elements(p1_elem, p2_elem)

            p1_emoji = ELEMENT_EMOJI[p1_elem]
            p2_emoji = ELEMENT_EMOJI[p2_elem]
            log_lines = list(state["log"])

            if result == "win":
                state["p2_hp"] -= HIT_DAMAGE
                log_lines.append(
                    f"{p1_emoji} {state['p1_name']} used {p1_elem.upper()} "
                    f"vs {p2_emoji} {p2_elem.upper()} → Hit! -{HIT_DAMAGE} HP"
                )
            elif result == "lose":
                state["p1_hp"] -= HIT_DAMAGE
                log_lines.append(
                    f"{p2_emoji} {state['p2_name']} used {p2_elem.upper()} "
                    f"vs {p1_emoji} {p1_elem.upper()} → Hit! -{HIT_DAMAGE} HP"
                )
            else:
                log_lines.append(
                    f"{p1_emoji} {p1_elem.upper()} vs {p2_emoji} {p2_elem.upper()} → Draw! No damage."
                )

            state["log"]   = log_lines
            state["round"] += 1
            state["p1_hp"] = max(0, state["p1_hp"])
            state["p2_hp"] = max(0, state["p2_hp"])

        # ── Duel over ─────────────────────────────────────────────────────────
        active_battles.pop(channel.id, None)
        clear_background_for_battle(str(battle_id))
        state["turn_label"] = "Duel Over!"

        if state["p1_hp"] > 0:
            winner, loser = ctx.author, opponent_member
            winner_name = state["p1_name"]
        else:
            winner, loser = opponent_member, ctx.author
            winner_name = state["p2_name"]

        gil_earned = random.randint(GIL_MIN, GIL_MAX)
        db.add_gil(winner.id, gil_earned)
        db.update_player(winner.id, wins=db.get_player(winner.id).get("wins", 0) + 1)
        db.update_player(loser.id,  losses=db.get_player(loser.id).get("losses", 0) + 1)
        db.reset_hp(ctx.author.id)
        db.reset_hp(opponent_member.id)

        state["log"].append(f"🏆 {winner_name} wins the duel! +{gil_earned} gil!")
        await self._send_battle_frame(channel, state, state["log"], None, msg)
        await channel.send(
            f"🏆 **{winner.mention}** wins the duel and earns **{gil_earned} gil**!"
        )

    # ── !rpg command ──────────────────────────────────────────────────────────
    @commands.command(name="rpg")
    async def rpg(self, ctx: commands.Context, opponent: discord.Member = None):

        user    = ctx.author
        channel = ctx.channel

        # ── Block if battle already running in channel ─────────────────────
        if channel.id in active_battles:
            await ctx.send("⚔️ A battle is already in progress in this channel! Wait for it to finish.")
            return

        # ── Fetch or prompt registration ───────────────────────────────────
        player = db.get_player(user.id)

        if not player:
            # First time — avatar selection
            embed = discord.Embed(
                title="⚔️ Welcome to ArcaneRPG!",
                description="This is your first time here, adventurer. Choose your avatar to begin!",
                color=0x7c3aed
            )
            view = AvatarSelectView(user=user)
            reg_msg = await ctx.send(embed=embed, view=view)
            await view.wait()

            if view.chosen is None:
                await reg_msg.edit(content="❌ Registration timed out. Type `!rpg` to try again.", embed=None, view=None)
                return

            player = db.register_player(
                user_id  = user.id,
                username = user.display_name,
                avatar   = view.chosen["file"]
            )
            await reg_msg.edit(
                content=f"✅ **{view.chosen['name']}** registered! Starting with **200 gil**. Good luck!",
                embed=None, view=None
            )

        # ── Notify if paused battle exists ────────────────────────────────
        paused = player.get("paused_battle")
        if paused and opponent is None:
            await ctx.send(
                f"⏸️ You have a paused battle! Type `!rpgcontinue` to resume it, "
                f"or `!rpgcontinue abandon` to start fresh."
            )
            return

        # ── PvP duel: !rpg @user ───────────────────────────────────────────
        if opponent:
            if opponent.id == user.id:
                await ctx.send("❌ You can't duel yourself!")
                return
            if opponent.bot:
                await ctx.send("❌ You can't duel a bot!")
                return

            if not db.is_registered(opponent.id):
                await ctx.send(
                    f"❌ **{opponent.display_name}** hasn't registered yet! "
                    f"They need to type `!rpg` first to create their character."
                )
                return

            opponent_data = db.get_player(opponent.id)

            # Send duel challenge
            challenge_embed = discord.Embed(
                title="⚔️ Duel Challenge!",
                description=(
                    f"**{user.display_name}** challenges **{opponent.display_name}** to a duel!\n\n"
                    f"{opponent.mention} — do you accept?"
                ),
                color=0xe74c3c
            )

            class AcceptView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.accepted = None

                @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
                async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != opponent.id:
                        await interaction.response.send_message("This isn't your challenge!", ephemeral=True)
                        return
                    self.accepted = True
                    self.stop()
                    await interaction.response.defer()

                @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
                async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != opponent.id:
                        await interaction.response.send_message("This isn't your challenge!", ephemeral=True)
                        return
                    self.accepted = False
                    self.stop()
                    await interaction.response.defer()

            accept_view = AcceptView()
            challenge_msg = await ctx.send(embed=challenge_embed, view=accept_view)
            await accept_view.wait()
            await challenge_msg.delete()

            if not accept_view.accepted:
                reason = "declined" if accept_view.accepted is False else "didn't respond in time"
                await ctx.send(f"❌ **{opponent.display_name}** {reason}. Duel cancelled.")
                return

            await self._run_pvp_battle(ctx, player, opponent, opponent_data)
            return

        # ── PvE: fight a random boss ───────────────────────────────────────
        enemy = random.choice(AVAILABLE_ENEMIES)
        db.reset_hp(user.id)
        player = db.get_player(user.id)   # refresh after reset
        await self._run_pve_battle(ctx, player, enemy)

    # ── !rpgcontinue command ─────────────────────────────────────────────────
    @commands.command(name="rpgcontinue")
    async def rpgcontinue(self, ctx: commands.Context, action: str = None):
        user    = ctx.author
        channel = ctx.channel

        if channel.id in active_battles:
            await ctx.send("⚔️ A battle is already running in this channel!")
            return

        player = db.get_player(user.id)
        if not player:
            await ctx.send("❌ You haven't registered yet! Type `!rpg` to begin.")
            return

        paused = player.get("paused_battle")
        if not paused:
            await ctx.send("❌ You don't have a paused battle. Type `!rpg` to start one!")
            return

        if action and action.lower() == "abandon":
            db.update_player(user.id, paused_battle=None)
            db.reset_hp(user.id)
            await ctx.send("🗑️ Paused battle abandoned. Type `!rpg` to start fresh!")
            return

        # Resume — show confirm view
        resume_view = ResumeView(user_id=user.id)
        prompt = await ctx.send(
            f"⏸️ You have a paused battle! Would you like to continue or abandon it?",
            view=resume_view
        )
        await resume_view.wait()
        await prompt.delete()

        if resume_view.decision == "abandon" or resume_view.decision is None:
            db.update_player(user.id, paused_battle=None)
            db.reset_hp(user.id)
            player = db.get_player(user.id)
            await ctx.send("🗑️ Abandoned. Type `!rpg` to start a new fight!")
        else:
            db.update_player(user.id, paused_battle=None)
            db.reset_hp(user.id)
            player = db.get_player(user.id)
            await ctx.send("▶️ Resuming! Sending you into a new fight...")
            enemy = random.choice(AVAILABLE_ENEMIES)
            await self._run_pve_battle(ctx, player, enemy)

    # ── !stats command ────────────────────────────────────────────────────────
    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context):
        player = db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ You haven't registered yet! Type `!rpg` to begin.")
            return
        embed = discord.Embed(title=f"📊 {player['username']}'s Stats", color=0x7c3aed)
        embed.add_field(name="Gil",    value=f"💰 {player['gil']}", inline=True)
        embed.add_field(name="Wins",   value=f"🏆 {player['wins']}", inline=True)
        embed.add_field(name="Losses", value=f"💀 {player['losses']}", inline=True)
        embed.add_field(name="Avatar", value=player['avatar'], inline=False)
        await ctx.send(embed=embed)

    # ── !help_rpg command ─────────────────────────────────────────────────────
    @commands.command(name="help_rpg")
    async def help_rpg(self, ctx: commands.Context):
        embed = discord.Embed(
            title="⚔️ ArcaneRPG — Help",
            description="A Final Fantasy-inspired turn-based RPG bot!",
            color=0x7c3aed
        )
        embed.add_field(
            name="Commands",
            value=(
                "`!rpg` — Start a PvE boss fight (or resume if paused)\n"
                "`!rpg @user` — Challenge another player to a duel\n"
                "`!stats` — View your stats and gil\n"
                "`!help_rpg` — Show this help message"
            ),
            inline=False
        )
        embed.add_field(
            name="⚗️ Elements",
            value=(
                "🔥 **Fire** beats ❄️ Ice\n"
                "❄️ **Ice** beats 🌪️ Wind\n"
                "🌪️ **Wind** beats 🔥 Fire\n"
                "Same element = Draw (no damage)"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 Gil",
            value="Win PvE fights to earn random gil rewards (20–80 gil per win). Start with 200 gil.",
            inline=False
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGCog(bot))
