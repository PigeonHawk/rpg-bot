import discord
from discord.ext import commands
import random
import json
import os
import asyncio

# ── What to do next message ───────────────────────────────────────────────
WHAT_NEXT = (
    "**What would you like to do next?**\n\n"
    "`!openpack` — Open packs\n"
    "`!buypack` — Buy a pack ($30)\n"
    "`!mycards` — View your collection\n"
    "`!pokewallet` — Check balance\n"
    "`!selldupes` — Sell duplicate cards\n"
    "`!trade @user <card>` — Trade with a player\n"
    "`!pokedaily` — Claim $5 once per day\n"
    "`!pokedaily` — Claim $5 Pokédollars once per day"
)

# ── GitHub raw image base URL ──────────────────────────────────────────────
BASE_URL = "https://raw.githubusercontent.com/PigeonHawk/rpg-bot/refs/heads/main/assets/pokemon-cards/"

# ── Data file ──────────────────────────────────────────────────────────────
DATA_FILE = os.path.join(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "."), "pokedata.json")

# ── Economy constants ──────────────────────────────────────────────────────
STARTING_DOLLARS = 15.00
STARTING_PACKS   = 3
PACK_COST        = 4.00
CARDS_PER_PACK   = 5

# ── Duplicate payout per rarity ────────────────────────────────────────────
DUPLICATE_VALUES = {
    "common":      0.10,
    "uncommon":    0.20,
    "rare":        0.50,
    "ultra_rare":  1.00,
    "secret_rare": 2.00,
}

# ── Rarity pull weights ────────────────────────────────────────────────────
RARITY_WEIGHTS = {
    "common":      60,
    "uncommon":    25,
    "rare":        10,
    "ultra_rare":   4,
    "secret_rare":  1,
}

# ── Rarity display labels and colors ──────────────────────────────────────
RARITY_DISPLAY = {
    "common":      ("⚪ Common",      0x95a5a6),
    "uncommon":    ("🟢 Uncommon",    0x2ecc71),
    "rare":        ("🔵 Rare",        0x3498db),
    "ultra_rare":  ("🟣 Ultra Rare",  0x9b59b6),
    "secret_rare": ("🌟 Secret Rare", 0xf1c40f),
}

# ── Card definitions ───────────────────────────────────────────────────────
def make_card(name, rarity):
    filename = name.replace(" ", "_")
    return {"name": name, "rarity": rarity, "image": BASE_URL + filename + ".webp"}

def _cn(s):
    """Convert filename to display name."""
    return (s.replace("_ex_alt2", " EX Alt2")
             .replace("_ex_alt",  " EX Alt")
             .replace("_ex",      " EX")
             .replace("_alt2",    " Alt2")
             .replace("_alt",     " Alt")
             .replace("_",        " "))

COMMON_IDS = [
    "Abra","Aerodactyl","Arcanine","Articuno","Beedrill","Bellsprout",
    "Bulbasaur","Butterfree","Caterpie","Chansey","Charmander","Charmeleon",
    "Clefable","Clefairy","Cloyster","Cubone","Dewgong","Diglett",
    "Ditto","Dodrio","Doduo","Dragonair","Dragonite","Dratini",
    "Drowzee","Dugtrio","Eevee","Ekans","Electabuzz","Electrode",
    "Exeggcute","Exeggutor","Farfetchd","Fearow","Flareon","Gastly",
    "Gengar","Geodude","Gloom","Golbat","Goldeen","Golduck",
    "Graveler","Grimer","Growlithe","Gyarados","Haunter","Hitmonchan",
    "Hitmonlee","Horsea","Hypno","Ivysaur","Jigglypuff","Jolteon",
    "Kabuto","Kabutops","Kadabra","Kakuna","Kingler","Koffing",
    "Krabby","Lapras","Lickitung","Machamp","Machoke","Machop",
    "Magikarp","Magmar","Magnemite","Magneton","Mankey","Marowak",
    "Meowth","Metapod","Mewtwo","Moltres","Mr_Mime","Muk",
    "Nidoking","Nidoqueen","Nidoran_F","Nidoran_M","Nidorina","Nidorino",
    "Oddish","Omanyte","Omastar","Onix","Paras","Parasect",
    "Persian","Pidgeot","Pidgeotto","Pidgey","Pikachu","Pinsir",
    "Poliwag","Poliwhirl","Poliwrath","Ponyta","Porygon","Primeape",
    "Psyduck","Raichu","Rapidash","Raticate","Rattata","Rhydon",
    "Rhyhorn","Sandshrew","Sandslash","Scyther","Seadra","Seaking",
    "Seel","Shellder","Slowbro","Slowpoke","Snorlax","Spearow",
    "Squirtle","Starmie","Staryu","Tangela","Tauros","Tentacool",
    "Tentacruel","Vaporeon","Venomoth","Venonat","Victreebel","Vileplume",
    "Voltorb","Vulpix","Wartortle","Weedle","Weepinbell","Weezing","Zubat",
]

UNCOMMON_IDS = [
    "Antique_Dome_Fossil","Antique_Helix_Fossil","Antique_Old_Amber",
    "Big_Air_Balloon","Bills_Transfer","Cycling_Road","Daisys_Help",
    "Energy_Sticker","Erikas_Invitation","Giovannis_Charisma","Grabber",
    "Leftovers","Protective_Goggles","Rigid_Band","Switch",
]

RARE_IDS = [
    "Alakazam_ex","Arbok_ex","Blastoise_ex","Charizard_ex","Golem_ex",
    "Jynx_ex","Kangaskhan_ex","Mew_ex","Ninetales_ex","Venusaur_ex",
    "Wigglytuff_ex","Zapdos_ex",
]

ULTRA_RARE_IDS = [
    "Alakazam_ex_alt","Arbok_ex_alt","Bills_Transfer_alt","Blastoise_ex_alt",
    "Bulbasaur_alt","Caterpie_alt","Charmander_alt","Charmeleon_alt",
    "Charizard_ex_alt","Daisys_Help_alt","Dragonair_alt","Erikas_Invitation_alt",
    "Giovannis_Charisma_alt","Golem_ex_alt","Ivysaur_alt","Jynx_ex_alt",
    "Kangaskhan_ex_alt","Machoke_alt","Mew_ex_alt","Mr_Mime_alt",
    "Nidoking_alt","Ninetales_ex_alt","Omanyte_alt","Pikachu_alt",
    "Poliwhirl_alt","Psyduck_alt","Squirtle_alt","Tangela_alt",
    "Venusaur_ex_alt","Wartortle_alt","Wigglytuff_ex_alt","Zapdos_ex_alt",
]

SECRET_RARE_IDS = [
    "Alakazam_ex_alt2","Blastoise_ex_alt2","Charizard_ex_alt2",
    "Erikas_Invitation_alt2","Giovannis_Charisma_alt2","Venusaur_ex_alt2",
    "Zapdos_ex_alt2",
]

# Build CARDS dict and canonical order list
CARDS = {}
CARD_ORDER = []

for cid in COMMON_IDS:
    CARDS[cid] = {"name": _cn(cid), "rarity": "common", "image": BASE_URL + cid + ".webp"}
    CARD_ORDER.append(cid)
for cid in UNCOMMON_IDS:
    CARDS[cid] = {"name": _cn(cid), "rarity": "uncommon", "image": BASE_URL + cid + ".webp"}
    CARD_ORDER.append(cid)
for cid in RARE_IDS:
    CARDS[cid] = {"name": _cn(cid), "rarity": "rare", "image": BASE_URL + cid + ".webp"}
    CARD_ORDER.append(cid)
for cid in ULTRA_RARE_IDS:
    CARDS[cid] = {"name": _cn(cid), "rarity": "ultra_rare", "image": BASE_URL + cid + ".webp"}
    CARD_ORDER.append(cid)
for cid in SECRET_RARE_IDS:
    CARDS[cid] = {"name": _cn(cid), "rarity": "secret_rare", "image": BASE_URL + cid + ".webp"}
    CARD_ORDER.append(cid)

TOTAL_CARDS = len(CARD_ORDER)

# ── Message earning ────────────────────────────────────────────────────────
def calculate_earnings(length: int) -> float:
    if length <= 3:   return 0.00
    if length <= 10:  return round(random.uniform(0.03, 0.30), 2)
    if length <= 30:  return round(random.uniform(0.30, 0.75), 2)
    if length <= 100: return round(random.uniform(0.75, 2.00), 2)
    if length <= 200: return round(random.uniform(2.00, 3.50), 2)
    return round(random.uniform(3.50, 5.00), 2)

# ── Pack pulling ───────────────────────────────────────────────────────────
def pull_pack() -> list:
    rarities = list(RARITY_WEIGHTS.keys())
    weights  = list(RARITY_WEIGHTS.values())
    pulled   = []
    for _ in range(CARDS_PER_PACK):
        rarity = random.choices(rarities, weights=weights, k=1)[0]
        pool   = [c for c in CARDS if CARDS[c]["rarity"] == rarity]
        pulled.append(random.choice(pool) if pool else random.choice(CARD_ORDER))
    return pulled

# ── Persistence ────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def ensure_user(data, uid, name):
    if uid not in data["users"]:
        data["users"][uid] = {
            "name": name, "pokedollars": 0.0,
            "packs": 0, "cards": [], "registered": False,
        }
    data["users"][uid]["name"] = name

# ── Helper: delete a message safely ───────────────────────────────────────
async def safe_delete(msg):
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════════ #
#  UI VIEWS                                                                  #
# ══════════════════════════════════════════════════════════════════════════ #

class PackBuyView(discord.ui.View):
    """Buttons to open 1, 3, or 5 packs."""
    def __init__(self, cog, user, prev_msg=None):
        super().__init__(timeout=60)
        self.cog      = cog
        self.user     = user
        self.prev_msg = prev_msg
        self._update_buttons()

    def _update_buttons(self):
        packs   = self.cog.db["users"][str(self.user.id)]["packs"]
        dollars = self.cog.db["users"][str(self.user.id)]["pokedollars"]
        for btn in self.children:
            n = int(btn.label.split()[1])
            btn.disabled = packs < n

    async def on_timeout(self):
        await safe_delete(self.prev_msg)
        uid = str(self.user.id)
        self.cog.user_messages.pop(uid, None)

    async def _open(self, interaction, count):
        uid  = str(self.user.id)
        user = self.cog.db["users"][uid]
        await safe_delete(self.prev_msg)

        if user["packs"] < count:
            await interaction.response.send_message(
                f"You only have **{user['packs']} packs**!", ephemeral=True
            )
            return

        user["packs"] -= count
        all_pulled, new_cards, dupes = [], [], []
        dupe_value = 0.0

        for _ in range(count):
            for cid in pull_pack():
                all_pulled.append(cid)
                card = CARDS[cid]
                if cid in user["cards"]:
                    val = DUPLICATE_VALUES.get(card["rarity"], 0.10)
                    dupe_value += val
                    dupes.append((cid, card, val))
                else:
                    user["cards"].append(cid)
                    new_cards.append((cid, card))

        save_data(self.cog.db)

        # Build one embed per card with its image
        card_embeds = []
        for cid, card in new_cards:
            label, color = RARITY_DISPLAY[card["rarity"]]
            e = discord.Embed(title=f"✨ {card['name']}", description=label, color=color)
            e.set_thumbnail(url=card["image"])
            card_embeds.append(e)
        for cid, card, val in dupes:
            label, color = RARITY_DISPLAY[card["rarity"]]
            e = discord.Embed(title=f"🔄 {card['name']} *(duplicate)*", description=f"{label} · +${val:.2f}", color=color)
            e.set_thumbnail(url=card["image"])
            card_embeds.append(e)

        # Summary embed
        new_lines  = [f"✨ **{c['name']}** — {RARITY_DISPLAY[c['rarity']][0]}" for _, c in new_cards]
        dupe_lines = [f"🔄 **{c['name']}** — {RARITY_DISPLAY[c['rarity']][0]} *(+${v:.2f})*" for _, c, v in dupes]

        desc_parts = []
        if new_lines:
            desc_parts.append(f"**🆕 {len(new_cards)} New Card(s):**\n" + "\n".join(new_lines))
        if dupe_lines:
            desc_parts.append(f"**🔄 {len(dupes)} Duplicate(s):**\n" + "\n".join(dupe_lines))

        summary = discord.Embed(
            title=f"📦 {self.user.display_name} opens {count} pack{'s' if count > 1 else ''}!",
            description="\n\n".join(desc_parts) or "No cards pulled.",
            color=0x3498db
        )
        if new_cards:
            summary.add_field(name="New Cards", value=str(len(new_cards)), inline=True)
        if dupes:
            summary.add_field(name="Duplicates", value=f"{len(dupes)} (+${dupe_value:.2f})", inline=True)
        summary.set_footer(text=f"Packs left: {user['packs']} · Balance: ${user['pokedollars']:.2f}")

        # Discord allows max 10 embeds per message — send card images in batches first
        await interaction.response.defer()
        channel = interaction.channel

        batches = [card_embeds[i:i+10] for i in range(0, len(card_embeds), 10)]
        for batch in batches:
            await channel.send(embeds=batch)

        # Send summary + dupe buttons last
        if dupes:
            view = DupeView(self.cog, self.user, dupes, dupe_value)
            msg  = await channel.send(embed=summary, view=view)
            self.cog.user_messages[uid] = msg
        else:
            msg = await channel.send(embed=summary)
            self.cog.user_messages[uid] = msg

        # What next prompt — auto delete after 60s if no action
        next_msg = await channel.send(WHAT_NEXT)
        await asyncio.sleep(60)
        await safe_delete(next_msg)

    @discord.ui.button(label="Open 1", style=discord.ButtonStyle.primary, emoji="📦")
    async def open1(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        await self._open(interaction, 1)

    @discord.ui.button(label="Open 3", style=discord.ButtonStyle.primary, emoji="📦")
    async def open3(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        await self._open(interaction, 3)

    @discord.ui.button(label="Open 5", style=discord.ButtonStyle.primary, emoji="📦")
    async def open5(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        await self._open(interaction, 5)


class DupeView(discord.ui.View):
    """Keep or sell duplicate cards."""
    def __init__(self, cog, user, dupes, dupe_value):
        super().__init__(timeout=60)
        self.cog        = cog
        self.user       = user
        self.dupes      = dupes
        self.dupe_value = dupe_value
        self.msg        = None

    @discord.ui.button(label="Sell All Dupes", style=discord.ButtonStyle.danger, emoji="💰")
    async def sell(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        uid  = str(self.user.id)
        user = self.cog.db["users"][uid]
        user["pokedollars"] = round(user["pokedollars"] + self.dupe_value, 2)
        save_data(self.cog.db)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"💰 Sold {len(self.dupes)} dupe(s) for **+${self.dupe_value:.2f}**! Balance: **${user['pokedollars']:.2f}**",
            view=self
        )

    @discord.ui.button(label="Keep All Dupes", style=discord.ButtonStyle.secondary, emoji="📦")
    async def keep(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        uid  = str(self.user.id)
        user = self.cog.db["users"][uid]
        # Add dupes to collection
        for cid, _, _ in self.dupes:
            user["cards"].append(cid)
        save_data(self.cog.db)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"📦 Kept {len(self.dupes)} dupe(s)!", view=self
        )


class CardBrowserView(discord.ui.View):
    """Paginated card browser — 5 cards per page with images."""
    PAGE_SIZE = 5

    def __init__(self, cog, user, page=0, prev_msg=None):
        super().__init__(timeout=120)
        self.cog      = cog
        self.user     = user
        self.page     = page
        self.prev_msg = prev_msg
        self.pages    = (TOTAL_CARDS + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.pages - 1

    def build_embeds(self):
        uid       = str(self.user.id)
        owned     = self.cog.db["users"][uid]["cards"]
        owned_set = {}
        for c in owned:
            owned_set[c] = owned_set.get(c, 0) + 1

        start  = self.page * self.PAGE_SIZE
        slice_ = CARD_ORDER[start: start + self.PAGE_SIZE]
        embeds = []

        for i, cid in enumerate(slice_):
            card   = CARDS[cid]
            num    = start + i + 1
            label, color = RARITY_DISPLAY[card["rarity"]]

            if cid in owned_set:
                count   = owned_set[cid]
                cnt_str = f" ×{count}" if count > 1 else ""
                e = discord.Embed(
                    title=f"✅ #{num} {card['name']}{cnt_str}",
                    description=label,
                    color=color
                )
                e.set_image(url=card["image"])
            else:
                e = discord.Embed(
                    title=f"⬜ #{num} {card['name']}",
                    description=f"{label} — *Not yet collected*",
                    color=0x2f3136
                )
            embeds.append(e)

        # Nav embed
        total_unique = len(set(owned))
        nav = discord.Embed(color=0x9b59b6)
        nav.set_footer(
            text=f"Page {self.page + 1}/{self.pages} · "
                 f"{total_unique}/{TOTAL_CARDS} unique · "
                 f"${self.cog.db['users'][uid]['pokedollars']:.2f} Pokédollars"
        )
        embeds.append(nav)
        return embeds

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embeds=self.build_embeds(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embeds=self.build_embeds(), view=self)


class SellDupesView(discord.ui.View):
    """Confirm selling all duplicates via !selldupes."""
    def __init__(self, cog, user, dupe_cards, total_value):
        super().__init__(timeout=30)
        self.cog        = cog
        self.user       = user
        self.dupe_cards = dupe_cards  # list of (cid, count, per_card_value)
        self.total      = total_value

    @discord.ui.button(label="Sell All", style=discord.ButtonStyle.danger, emoji="💰")
    async def confirm(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        uid  = str(self.user.id)
        user = self.cog.db["users"][uid]
        # Remove extra copies, keep one of each
        cleaned = []
        seen    = {}
        for cid in user["cards"]:
            seen[cid] = seen.get(cid, 0) + 1
            if seen[cid] == 1:
                cleaned.append(cid)
        user["cards"] = cleaned
        user["pokedollars"] = round(user["pokedollars"] + self.total, 2)
        save_data(self.cog.db)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"💰 Sold all duplicates for **+${self.total:.2f} Pokédollars**! Balance: **${user['pokedollars']:.2f}**",
            view=self
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Cancelled.", view=self)


class TradeView(discord.ui.View):
    """Accept or decline a trade offer."""
    def __init__(self, cog, sender, receiver, card_id):
        super().__init__(timeout=30)
        self.cog      = cog
        self.sender   = sender
        self.receiver = receiver
        self.card_id  = card_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction, button):
        if interaction.user.id != self.receiver.id:
            return await interaction.response.send_message("This trade isn't for you!", ephemeral=True)

        sid  = str(self.sender.id)
        rid  = str(self.receiver.id)
        card = CARDS[self.card_id]

        # Verify sender still has the card
        if self.card_id not in self.cog.db["users"][sid]["cards"]:
            for item in self.children: item.disabled = True
            return await interaction.response.edit_message(
                content="❌ Trade cancelled — the sender no longer has that card.", view=self
            )

        # Transfer card
        self.cog.db["users"][sid]["cards"].remove(self.card_id)
        self.cog.db["users"][rid]["cards"].append(self.card_id)
        save_data(self.cog.db)

        for item in self.children: item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Trade complete! **{self.sender.display_name}** gave **{card['name']}** to **{self.receiver.display_name}**.",
            view=self
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction, button):
        if interaction.user.id != self.receiver.id:
            return await interaction.response.send_message("This trade isn't for you!", ephemeral=True)
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(
            content=f"❌ **{self.receiver.display_name}** declined the trade.", view=self
        )


# ══════════════════════════════════════════════════════════════════════════ #
#  COG                                                                       #
# ══════════════════════════════════════════════════════════════════════════ #

class PokeCog(commands.Cog):
    def __init__(self, bot):
        self.bot          = bot
        self.db           = load_data()
        self.user_messages = {}  # uid -> last interactive message (for auto-delete)

    async def _delete_prev(self, uid):
        msg = self.user_messages.pop(str(uid), None)
        await safe_delete(msg)

    # ------------------------------------------------------------------ #
    #  !pokecard — register                                               #
    # ------------------------------------------------------------------ #
    @commands.command(name="pokecard")
    async def pokecard(self, ctx):
        uid  = str(ctx.author.id)
        name = ctx.author.display_name
        ensure_user(self.db, uid, name)

        if self.db["users"][uid]["registered"]:
            user = self.db["users"][uid]
            embed = discord.Embed(
                title=f"🎴  {name}'s Pokécard Status",
                description=(
                    f"💰 **${user['pokedollars']:.2f}** Pokédollars\n"
                    f"📦 **{user['packs']}** packs\n"
                    f"🎴 **{len(set(user['cards']))}**/{TOTAL_CARDS} unique cards\n\n"
                    + WHAT_NEXT
                ),
                color=0xf1c40f
            )
            return await ctx.send(embed=embed)

        self.db["users"][uid].update(
            registered=True, pokedollars=STARTING_DOLLARS, packs=STARTING_PACKS
        )
        save_data(self.db)

        embed = discord.Embed(
            title="🎴  Welcome to the Card Collector!",
            description=(
                f"**{name}** has joined!\n\n"
                f"💰 **${STARTING_DOLLARS:.2f}** Pokédollars\n"
                f"📦 **{STARTING_PACKS}** packs to open\n\n"
                f"`!openpack` — open packs\n"
                f"`!buypack` — buy more packs (${PACK_COST:.0f} each)\n"
                f"`!mycards` — view collection\n"
                f"`!pokehelp` — all commands"
            ),
            color=0xf1c40f
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  !openpack — open packs with 1/3/5 buttons                         #
    # ------------------------------------------------------------------ #
    @commands.command(name="openpack")
    async def openpack(self, ctx):
        uid  = str(ctx.author.id)
        name = ctx.author.display_name
        ensure_user(self.db, uid, name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send("Use `!pokecard` to register first!")

        user = self.db["users"][uid]
        if user["packs"] == 0:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"**{name}**, you have no packs! Use `!buypack` to get more.",
                    color=0xe74c3c
                )
            )

        await self._delete_prev(uid)

        embed = discord.Embed(
            title="📦  Open Packs",
            description=(
                f"You have **{user['packs']} pack(s)**. How many would you like to open?\n\n"
                f"Each pack contains **{CARDS_PER_PACK} cards**."
            ),
            color=0x3498db
        )
        view = PackBuyView(self, ctx.author)
        msg  = await ctx.send(embed=embed, view=view)
        view.prev_msg = msg
        self.user_messages[uid] = msg

    # ------------------------------------------------------------------ #
    #  !buypack — buy a pack                                              #
    # ------------------------------------------------------------------ #
    @commands.command(name="buypack")
    async def buypack(self, ctx):
        uid  = str(ctx.author.id)
        name = ctx.author.display_name
        ensure_user(self.db, uid, name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send("Use `!pokecard` to register first!")

        user = self.db["users"][uid]
        if user["pokedollars"] < PACK_COST:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"**{name}**, you need **${PACK_COST:.0f}** but only have **${user['pokedollars']:.2f}**. Keep chatting to earn more!",
                    color=0xe74c3c
                )
            )

        user["pokedollars"] = round(user["pokedollars"] - PACK_COST, 2)
        user["packs"] += 1
        save_data(self.db)

        await ctx.send(embed=discord.Embed(
            title="📦  Pack Purchased!",
            description=(
                f"**{name}** bought a pack!\n\n"
                f"📦 Packs: **{user['packs']}**\n"
                f"💰 Balance: **${user['pokedollars']:.2f}**\n\n"
                f"Use `!openpack` to open it!"
            ),
            color=0x2ecc71
        ))

    # ------------------------------------------------------------------ #
    #  !mycards — paginated card browser                                  #
    # ------------------------------------------------------------------ #
    @commands.command(name="mycards")
    async def mycards(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        uid    = str(target.id)
        name   = target.display_name
        ensure_user(self.db, uid, name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send(f"**{name}** hasn't registered yet!")

        await self._delete_prev(str(ctx.author.id))

        view   = CardBrowserView(self, target)
        embeds = view.build_embeds()
        msg    = await ctx.send(embeds=embeds, view=view)
        self.user_messages[str(ctx.author.id)] = msg

    # ------------------------------------------------------------------ #
    #  !pokewallet — check balance                                        #
    # ------------------------------------------------------------------ #
    @commands.command(name="pokewallet")
    async def pokewallet(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        uid    = str(target.id)
        ensure_user(self.db, uid, target.display_name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send(f"**{target.display_name}** hasn't registered!")

        user = self.db["users"][uid]
        owned_unique = len(set(user["cards"]))
        embed = discord.Embed(
            title=f"💰  {target.display_name}'s Pokéwallet",
            description=(
                f"💵 **Pokédollars:** ${user['pokedollars']:.2f}\n"
                f"📦 **Packs:** {user['packs']}\n"
                f"🎴 **Cards:** {owned_unique}/{TOTAL_CARDS} unique · {len(user['cards'])} total"
            ),
            color=0xf1c40f
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  !selldupes — sell all duplicate cards                              #
    # ------------------------------------------------------------------ #
    @commands.command(name="selldupes")
    async def selldupes(self, ctx):
        uid  = str(ctx.author.id)
        ensure_user(self.db, uid, ctx.author.display_name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send("Use `!pokecard` to register first!")

        cards = self.db["users"][uid]["cards"]
        counts = {}
        for c in cards:
            counts[c] = counts.get(c, 0) + 1

        dupes = [(cid, cnt, DUPLICATE_VALUES.get(CARDS[cid]["rarity"], 0.10))
                 for cid, cnt in counts.items() if cnt > 1]

        if not dupes:
            return await ctx.send("You have no duplicate cards to sell!")

        total_value = sum((cnt - 1) * val for _, cnt, val in dupes)
        lines       = []
        for cid, cnt, val in dupes:
            card  = CARDS[cid]
            extra = cnt - 1
            lines.append(f"• **{card['name']}** ×{extra} extra → +${extra * val:.2f}")

        embed = discord.Embed(
            title="💰  Sell Duplicates",
            description="\n".join(lines) + f"\n\n**Total: +${total_value:.2f} Pokédollars**",
            color=0xe74c3c
        )

        await self._delete_prev(uid)
        view = SellDupesView(self, ctx.author, dupes, total_value)
        msg  = await ctx.send(embed=embed, view=view)
        self.user_messages[uid] = msg

    # ------------------------------------------------------------------ #
    #  !trade @user CardName — initiate a trade                          #
    # ------------------------------------------------------------------ #
    @commands.command(name="trade")
    async def trade(self, ctx, member: discord.Member, *, card_name: str):
        sid  = str(ctx.author.id)
        rid  = str(member.id)
        ensure_user(self.db, sid, ctx.author.display_name)
        ensure_user(self.db, rid, member.display_name)

        if member.id == ctx.author.id:
            return await ctx.send("You can't trade with yourself!")
        if member.bot:
            return await ctx.send("You can't trade with a bot!")
        if not self.db["users"][sid]["registered"]:
            return await ctx.send("You need to register with `!pokecard` first!")
        if not self.db["users"][rid]["registered"]:
            return await ctx.send(f"**{member.display_name}** hasn't registered yet!")

        # Find the card in sender's collection
        card_key = card_name.strip().replace(" ", "_")
        sender_cards = self.db["users"][sid]["cards"]

        # Try exact match first, then case-insensitive
        matched_id = None
        if card_key in sender_cards and card_key in CARDS:
            matched_id = card_key
        else:
            for cid in sender_cards:
                if cid.lower() == card_key.lower():
                    matched_id = cid
                    break
            if not matched_id:
                for cid in sender_cards:
                    if card_key.lower() in cid.lower():
                        matched_id = cid
                        break

        if not matched_id:
            owned_names = [CARDS[c]["name"] for c in set(sender_cards) if c in CARDS]
            return await ctx.send(
                f"You don't have a card matching **{card_name}**. "
                f"Use `!mycards` to see your collection."
            )

        card = CARDS[matched_id]
        label, color = RARITY_DISPLAY[card["rarity"]]

        embed = discord.Embed(
            title="🔄  Trade Request",
            description=(
                f"**{ctx.author.display_name}** wants to trade:\n\n"
                f"**{card['name']}** — {label}\n\n"
                f"<@{member.id}> — do you accept? *(30 seconds to respond)*"
            ),
            color=color
        )
        embed.set_thumbnail(url=card["image"])

        view = TradeView(self, ctx.author, member, matched_id)
        msg  = await ctx.send(embed=embed, view=view)

        # Auto-expire after 30s
        await asyncio.sleep(30)
        if not view.is_finished():
            view.stop()
            for item in view.children:
                item.disabled = True
            try:
                await msg.edit(
                    content="⏰ Trade request expired.",
                    embed=None, view=view
                )
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  !pokedaily — claim 5 Pokédollars once per day                     #
    # ------------------------------------------------------------------ #
    @commands.command(name="pokedaily")
    async def pokedaily(self, ctx):
        import datetime
        uid  = str(ctx.author.id)
        name = ctx.author.display_name
        ensure_user(self.db, uid, name)

        if not self.db["users"][uid]["registered"]:
            return await ctx.send("Use `!pokecard` to register first!")

        user    = self.db["users"][uid]
        today   = datetime.date.today().isoformat()
        last    = user.get("last_daily")

        if last == today:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"**{name}**, you already claimed your daily today! Come back tomorrow.",
                    color=0xe74c3c
                )
            )

        user["last_daily"]   = today
        user["pokedollars"]  = round(user["pokedollars"] + 5.00, 2)
        save_data(self.db)

        await ctx.send(embed=discord.Embed(
            title="📅  Daily Reward!",
            description=f"**{name}** claimed their daily **+$5.00 Pokédollars**!\n\n💰 Balance: **${user['pokedollars']:.2f}**",
            color=0x2ecc71
        ))

    # ------------------------------------------------------------------ #
    #  !pokehelp                                                          #
    # ------------------------------------------------------------------ #
    @commands.command(name="pokehelp")
    async def pokehelp(self, ctx):
        embed = discord.Embed(
            title="🎴  Pokécard Collector — Commands",
            description=(
                "`!pokecard` — Register and get **3 packs + $15**\n"
                "`!openpack` — Open packs (1, 3, or 5 at once)\n"
                "`!buypack` — Buy a pack for **$30**\n"
                "`!mycards [@user]` — Browse your card collection (paginated)\n"
                "`!pokewallet [@user]` — Check balance & stats\n"
                "`!selldupes` — Sell all duplicate cards for Pokédollars\n"
                "`!trade @user <card>` — Trade a card with another player\n\n"
                "💬 **Earn Pokédollars by chatting** — longer messages earn more!\n"
                "🔄 **Duplicates** can be kept or sold when opening packs."
            ),
            color=0xf1c40f
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  on_message — earn Pokédollars by chatting                         #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        uid  = str(message.author.id)
        name = message.author.display_name
        ensure_user(self.db, uid, name)
        if not self.db["users"][uid]["registered"]:
            return
        earned = calculate_earnings(len(message.content))
        if earned > 0:
            self.db["users"][uid]["pokedollars"] = round(
                self.db["users"][uid]["pokedollars"] + earned, 2
            )
            save_data(self.db)


async def setup(bot):
    await bot.add_cog(PokeCog(bot))
