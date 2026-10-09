"""
birthday.py — a birthday tracker cog for discord.py.

Members log their birthday, the bot announces it automatically on the day, and
admins can view, list, or delete entries. An optional audit log channel records
every add / remove / announcement.

Commands (group: !birthday, alias !bday):
  !birthday set <date>        log your birthday        e.g. "03/05", "March 5", "5 Mar 1998"
  !birthday set @user <date>  (admin) log someone else's
  !birthday remove [@user]    delete your birthday (admins may delete anyone's)
  !birthday view [@user]      show a birthday + days until
  !birthday list              upcoming birthdays, soonest first
  !birthday next              who's up next
  !birthday channel #chan     (admin) where announcements are posted
  !birthday role @role        (admin) optional role to ping in announcements
  !birthday logchannel #chan  (admin) optional audit log channel (set to #none to clear)
  !birthday test              (admin) post today's announcements now, for testing
  !birthday storage           (admin) show where birthdays are saved and whether saving works

Persistence (point at your Railway volume to survive redeploys):
  BIRTHDAY_STATE_PATH   default: data/birthdays.json
  BIRTHDAY_DATA_DIR     default: ./data next to this cog
  BIRTHDAY_TZ           IANA tz for "what day is it" + announce time (default America/Los_Angeles)
  BIRTHDAY_HOUR         hour (0-23) to announce, in that tz (default 9)
"""

import os
import re
import json
import logging
from datetime import date, datetime, time as dtime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

import discord
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("BIRTHDAY_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("BIRTHDAY_STATE_PATH", os.path.join(DATA_DIR, "birthdays.json"))
TZ_NAME = os.getenv("BIRTHDAY_TZ", "America/Los_Angeles")
ANNOUNCE_HOUR = int(os.getenv("BIRTHDAY_HOUR", "9"))

try:
    TZ = ZoneInfo(TZ_NAME) if ZoneInfo else timezone.utc
except Exception:  # bad tz name or missing tzdata
    log.warning("Birthday: could not load tz %s, falling back to UTC", TZ_NAME)
    TZ = timezone.utc

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


# ---------- date parsing / math (module-level, easy to test) ----------

def parse_birthday(text: str):
    """Parse a birthday string into (month, day, year|None), or None if unrecognized."""
    t = text.strip().lower()
    t = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", t)   # 5th -> 5
    t = t.replace(",", " ").replace(".", " ")
    t = re.sub(r"\s+", " ", t).strip()

    with_year = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d %Y", "%d %B %Y", "%b %d %Y", "%d %b %Y"]
    no_year = ["%m/%d", "%m-%d", "%B %d", "%d %B", "%b %d", "%d %b"]

    for fmt in with_year:
        try:
            d = datetime.strptime(t, fmt)
            return d.month, d.day, d.year
        except ValueError:
            pass
    for fmt in no_year:
        try:
            # append a leap year so Feb 29 parses; strptime otherwise defaults to 1900 (non-leap)
            d = datetime.strptime(t + " 2000", fmt + " %Y")
            return d.month, d.day, None
        except ValueError:
            pass
    return None


def parse_entries(tokens):
    """Parse a flat token list like [vivi, oct, 5, wreck, oct, 7] into
    [(name, (month, day, year)), ...], plus a list of leftover name tokens we
    couldn't attach a date to. Dates may be 1-3 tokens; we take the longest that parses."""
    entries, leftovers = [], []
    i = 0
    while i < len(tokens):
        # strip list punctuation (bullets, dashes, commas, numbering) from the name token
        name = tokens[i].strip(" \t\r\n.,;:!?*•·()[]-\u2013\u2014")
        i += 1
        if not name or name.isdigit():
            continue  # bullet marker or list number — skip silently
        parsed, consumed = None, 0
        for length in (3, 2, 1):
            if i + length <= len(tokens):
                cand = " ".join(tokens[i:i + length])
                p = parse_birthday(cand)
                if p:
                    parsed, consumed = p, length
                    break
        if parsed:
            entries.append((name, parsed))
            i += consumed
        else:
            leftovers.append(name)
    return entries, leftovers


def fmt_date(month: int, day: int, year=None) -> str:
    s = f"{MONTHS[month - 1]} {day}"
    return f"{s}, {year}" if year else s


def next_occurrence(month: int, day: int, today: date) -> date:
    """Next calendar date this birthday lands on (Feb 29 -> Feb 28 in non-leap years)."""
    def make(y):
        try:
            return date(y, month, day)
        except ValueError:
            return date(y, 2, 28)  # Feb 29 in a non-leap year
    d = make(today.year)
    if d < today:
        d = make(today.year + 1)
    return d


def days_until(month: int, day: int, today: date) -> int:
    return (next_occurrence(month, day, today) - today).days


def age_on(month: int, day: int, year, on: date):
    if not year:
        return None
    age = on.year - year
    if (on.month, on.day) < (month, day):
        age -= 1
    return age


UNSAVED_WARNING = ("\n⚠️ I couldn't write that to disk, so it will be lost on the next restart. "
                   "Run `!birthday storage` to see why.")


class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {"guilds": {}}
        self._load()
        self.birthday_loop.start()

    def cog_unload(self):
        self.birthday_loop.cancel()

    # ---------- persistence ----------

    def _count(self):
        return sum(len(g.get("birthdays", {})) for g in self.data.get("guilds", {}).values())

    def _load(self):
        self._last_save_error = None
        self._last_save_at = None
        try:
            with open(STATE_PATH) as f:
                self.data = json.load(f)
            self.data.setdefault("guilds", {})
            self._load_note = "loaded OK"
        except FileNotFoundError:
            self.data = {"guilds": {}}
            self._load_note = "no file found, starting empty"
        except (ValueError, OSError) as e:
            # keep the unreadable file instead of silently overwriting it with an empty list
            bad = f"{STATE_PATH}.corrupt-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
            try:
                os.replace(STATE_PATH, bad)
            except OSError:
                bad = "(could not move it aside)"
            self.data = {"guilds": {}}
            self._load_note = f"file unreadable ({type(e).__name__}); moved to {bad}, starting empty"
        # warning level on purpose: this bot doesn't configure logging, so info lines never appear in Railway
        log.warning("Birthday: save file %s: %s; %d birthday(s) loaded", STATE_PATH, self._load_note, self._count())

    def _save(self):
        """Write to disk. Returns True on success. Never raises: a failure is recorded and shown to the user."""
        try:
            os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            self._last_save_error = f"{type(e).__name__}: {e}"
            log.error("Birthday: COULD NOT SAVE to %s: %s", STATE_PATH, self._last_save_error)
            return False
        self._last_save_error = None
        self._last_save_at = datetime.now(timezone.utc)
        return True

    def _guild(self, gid):
        g = self.data["guilds"].setdefault(str(gid), {})
        g.setdefault("announce_channel", None)
        g.setdefault("mention_role", None)
        g.setdefault("log_channel", None)
        g.setdefault("last_announced", None)
        g.setdefault("birthdays", {})
        return g

    # ---------- audit logging ----------

    async def _audit(self, guild, text):
        log.info("Birthday[%s]: %s", getattr(guild, "id", "?"), text)
        g = self._guild(guild.id)
        cid = g.get("log_channel")
        if cid:
            ch = guild.get_channel(cid)
            if ch:
                try:
                    await ch.send(embed=discord.Embed(description=text, color=0x95a5a6))
                except discord.HTTPException:
                    pass

    # ---------- commands ----------

    @commands.group(name="birthday", aliases=["bday"], invoke_without_command=True)
    async def birthday(self, ctx):
        """Birthday tracker. Try `!birthday set <date>` or `!birthday list`."""
        await ctx.send_help(ctx.command)

    def _resolve_name(self, ctx, token):
        """Resolve a name token or mention to a member."""
        mo = re.fullmatch(r"<@!?(\d+)>", token)
        if mo:
            return ctx.guild.get_member(int(mo.group(1)))
        return ctx.guild.get_member_named(token)

    @birthday.command(name="set", aliases=["add", "log"])
    async def set_birthday(self, ctx, *, text: str = None):
        """Log birthdays. Yourself: `!birthday set March 5`.
        Someone else: `!birthday set @user 03/05`.
        Many at once: `!birthday set vivi oct 5 wreck oct 7 jojo november 20`."""
        if not text:
            return await ctx.send("Tell me a date, e.g. `!birthday set March 5`, "
                                  "or set several: `!birthday set vivi oct 5 wreck nov 20`.")
        text = text.strip()

        # 1) whole thing is just a date -> you're setting your own
        whole = parse_birthday(text)
        if whole:
            m, d, y = whole
            g = self._guild(ctx.guild.id)
            g["birthdays"][str(ctx.author.id)] = {"month": m, "day": d, "year": y}
            ok = self._save()
            await self._audit(ctx.guild, f"🎂 {ctx.author.mention} set their birthday to **{fmt_date(m, d, y)}**")
            when = days_until(m, d, date.today())
            tail = "today! 🎉" if when == 0 else f"in **{when}** day{'s' if when != 1 else ''}"
            return await ctx.send(f"Saved your birthday: **{fmt_date(m, d, y)}** — next one is {tail}"
                                  + ("" if ok else UNSAVED_WARNING))

        # 2) otherwise parse name->date pairs (one or many)
        entries, leftovers = parse_entries(text.split())
        if not entries:
            return await ctx.send("I couldn't read that. Try `!birthday set @user March 5` "
                                  "or `!birthday set vivi oct 5 wreck nov 20`.")

        # resolve members and enforce permission for setting others
        resolved, unknown = [], list(leftovers)
        for name, (m, d, y) in entries:
            member = self._resolve_name(ctx, name)
            if member is None:
                unknown.append(name)
            else:
                resolved.append((member, m, d, y))

        others = [r for r in resolved if r[0].id != ctx.author.id]
        if others and not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("You need **Manage Server** to set other people's birthdays.")
        if len(resolved) > 50:
            return await ctx.send("That's a lot at once — keep it to 50 per command.")

        g = self._guild(ctx.guild.id)
        saved = []
        for member, m, d, y in resolved:
            g["birthdays"][str(member.id)] = {"month": m, "day": d, "year": y}
            saved.append(f"**{member.display_name}** — {fmt_date(m, d, y)}")
        ok = self._save()

        if saved:
            await self._audit(ctx.guild, f"🎂 {ctx.author.mention} set {len(saved)} birthday(s): "
                                         + "; ".join(saved))

        emb = discord.Embed(
            title=f"🎂 Saved {len(saved)} birthday{'s' if len(saved) != 1 else ''}",
            description="\n".join(saved) if saved else "Nothing saved.",
            color=0xe67e22)
        if unknown:
            emb.add_field(name="Couldn't find", value=", ".join(f"`{u}`" for u in unknown), inline=False)
        if not ok:
            emb.add_field(name="⚠️ Not saved to disk", value=UNSAVED_WARNING.strip(), inline=False)
        await ctx.send(embed=emb)

    @birthday.command(name="remove", aliases=["delete", "clear", "del"])
    async def remove_birthday(self, ctx, member: discord.Member = None):
        """Delete a birthday. Yours by default; admins can delete anyone's."""
        target = member or ctx.author
        if member and member != ctx.author and not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("You need **Manage Server** to delete someone else's birthday.")
        g = self._guild(ctx.guild.id)
        if str(target.id) not in g["birthdays"]:
            return await ctx.send(f"No birthday on file for {target.mention}.")
        removed = g["birthdays"].pop(str(target.id))
        ok = self._save()
        await self._audit(ctx.guild, f"🗑️ {ctx.author.mention} removed {target.mention}'s birthday "
                                     f"(was {fmt_date(removed['month'], removed['day'], removed.get('year'))})")
        await ctx.send(f"Deleted {target.mention}'s birthday." + ("" if ok else UNSAVED_WARNING))

    @birthday.command(name="view", aliases=["show", "get"])
    async def view_birthday(self, ctx, member: discord.Member = None):
        """Show a birthday and how long until it."""
        target = member or ctx.author
        g = self._guild(ctx.guild.id)
        rec = g["birthdays"].get(str(target.id))
        if not rec:
            return await ctx.send(f"No birthday on file for {target.mention}. "
                                  f"Set one with `!birthday set <date>`.")
        m, day, year = rec["month"], rec["day"], rec.get("year")
        today = date.today()
        d = days_until(m, day, today)
        when = "**today!** 🎉" if d == 0 else f"in **{d}** day{'s' if d != 1 else ''}"
        emb = discord.Embed(title=f"🎂 {target.display_name}'s birthday",
                            description=f"**{fmt_date(m, day, year)}** — {when}", color=0xe67e22)
        nxt = next_occurrence(m, day, today)
        a = age_on(m, day, year, nxt)
        if a is not None:
            emb.set_footer(text=f"Turning {a} on the next one")
        await ctx.send(embed=emb)

    @birthday.command(name="list", aliases=["all", "upcoming"])
    async def list_birthdays(self, ctx):
        """List upcoming birthdays, soonest first."""
        g = self._guild(ctx.guild.id)
        if not g["birthdays"]:
            return await ctx.send("No birthdays logged yet. Add yours with `!birthday set <date>`.")
        today = date.today()
        rows = []
        for uid, rec in g["birthdays"].items():
            m, day, year = rec["month"], rec["day"], rec.get("year")
            rows.append((days_until(m, day, today), uid, m, day, year))
        rows.sort(key=lambda r: r[0])
        lines = []
        for d, uid, m, day, year in rows[:25]:
            when = "🎉 today" if d == 0 else f"in {d}d"
            lines.append(f"<@{uid}> — **{fmt_date(m, day)}** ({when})")
        emb = discord.Embed(title="🎂 Upcoming birthdays", description="\n".join(lines), color=0xe67e22)
        if len(rows) > 25:
            emb.set_footer(text=f"+{len(rows) - 25} more")
        await ctx.send(embed=emb)

    @birthday.command(name="next")
    async def next_birthday(self, ctx):
        """Show whose birthday is coming up next."""
        g = self._guild(ctx.guild.id)
        if not g["birthdays"]:
            return await ctx.send("No birthdays logged yet.")
        today = date.today()
        best = min(g["birthdays"].items(),
                   key=lambda kv: days_until(kv[1]["month"], kv[1]["day"], today))
        uid, rec = best
        d = days_until(rec["month"], rec["day"], today)
        when = "today! 🎉" if d == 0 else f"in **{d}** day{'s' if d != 1 else ''}"
        await ctx.send(f"Next up: <@{uid}> — **{fmt_date(rec['month'], rec['day'])}**, {when}")

    # ---------- admin config ----------

    @birthday.command(name="channel")
    @commands.has_guild_permissions(manage_guild=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """(Admin) Set where birthday announcements are posted."""
        g = self._guild(ctx.guild.id)
        g["announce_channel"] = channel.id
        self._save()
        await ctx.send(f"Birthday announcements will post in {channel.mention}.")

    @birthday.command(name="role")
    @commands.has_guild_permissions(manage_guild=True)
    async def set_role(self, ctx, role: discord.Role = None):
        """(Admin) Optional role to ping in announcements. Omit the role to clear."""
        g = self._guild(ctx.guild.id)
        g["mention_role"] = role.id if role else None
        self._save()
        await ctx.send(f"Announcement ping set to {role.mention}." if role else "Announcement ping cleared.")

    @birthday.command(name="logchannel")
    @commands.has_guild_permissions(manage_guild=True)
    async def set_logchannel(self, ctx, channel: discord.TextChannel = None):
        """(Admin) Optional audit log channel for add/remove/announce events. Omit to clear."""
        g = self._guild(ctx.guild.id)
        g["log_channel"] = channel.id if channel else None
        self._save()
        await ctx.send(f"Audit log will post in {channel.mention}." if channel else "Audit log cleared.")

    @birthday.command(name="storage", aliases=["debug", "where"])
    @commands.has_guild_permissions(manage_guild=True)
    async def storage_info(self, ctx):
        """(Admin) Show where birthdays are saved and whether saving is working."""
        folder = os.path.dirname(STATE_PATH) or "."
        try:
            st = os.stat(STATE_PATH)
            when = datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            on_disk = f"yes ({st.st_size} bytes, last changed {when})"
        except FileNotFoundError:
            on_disk = "**no**, the file doesn't exist"
        except OSError as e:
            on_disk = f"couldn't check ({e})"
        if os.getenv("BIRTHDAY_STATE_PATH"):
            env = "yes"
        else:
            env = "**no**, using the default folder inside the app, which Railway wipes on every redeploy"
        if self._last_save_error:
            last = f"❌ failed: `{self._last_save_error}`"
        elif self._last_save_at:
            last = f"✅ {self._last_save_at:%Y-%m-%d %H:%M UTC}"
        else:
            last = "nothing saved since the bot started"
        g = self._guild(ctx.guild.id)
        lines = [
            f"**Saving to:** `{STATE_PATH}`",
            f"**BIRTHDAY_STATE_PATH set:** {env}",
            f"**Folder exists / writable:** {os.path.isdir(folder)} / {os.path.isdir(folder) and os.access(folder, os.W_OK)}",
            f"**File on disk:** {on_disk}",
            f"**At startup:** {self._load_note}",
            f"**Birthdays in memory:** {len(g['birthdays'])} in this server ({self._count()} total)",
            f"**Last save:** {last}",
        ]
        await ctx.send(embed=discord.Embed(title="🎂 Birthday storage", description="\n".join(lines), color=0x95a5a6))

    @birthday.command(name="test")
    @commands.has_guild_permissions(manage_guild=True)
    async def test_announce(self, ctx):
        """(Admin) Post today's birthday announcements now, ignoring the once-a-day guard."""
        posted = await self._announce_for_guild(ctx.guild, force=True)
        if not posted:
            await ctx.send("No birthdays today (or no announcement channel set — `!birthday channel #chan`).")

    # ---------- announcement engine ----------

    async def _announce_for_guild(self, guild, force=False):
        g = self._guild(guild.id)
        cid = g.get("announce_channel")
        if not cid:
            return False
        channel = guild.get_channel(cid)
        if not channel:
            return False

        today = datetime.now(TZ).date()
        if not force and g.get("last_announced") == today.isoformat():
            return False

        celebrants = []
        for uid, rec in g["birthdays"].items():
            m, day = rec["month"], rec["day"]
            hit = (m == today.month and day == today.day)
            # Feb 29 birthdays: celebrate on Feb 28 in non-leap years
            if not hit and m == 2 and day == 29 and today.month == 2 and today.day == 28:
                try:
                    date(today.year, 2, 29)
                except ValueError:
                    hit = True
            if hit:
                celebrants.append((uid, rec))

        if celebrants:
            role = guild.get_role(g["mention_role"]) if g.get("mention_role") else None
            ping = f"{role.mention} " if role else ""
            for uid, rec in celebrants:
                a = age_on(rec["month"], rec["day"], rec.get("year"), today)
                extra = f" They're turning **{a}**! 🎈" if a is not None else ""
                emb = discord.Embed(
                    title="🎉 Happy Birthday!",
                    description=f"{ping}Everyone wish <@{uid}> a happy birthday!{extra}",
                    color=0xf1c40f)
                try:
                    await channel.send(content=(role.mention if role else None), embed=emb)
                except discord.HTTPException:
                    pass
            await self._audit(guild, f"🎉 Announced {len(celebrants)} birthday(s) in {channel.mention}")

        if not force:
            g["last_announced"] = today.isoformat()
            self._save()
        return bool(celebrants)

    @tasks.loop(time=dtime(hour=ANNOUNCE_HOUR, tzinfo=TZ))
    async def birthday_loop(self):
        for guild in list(self.bot.guilds):
            try:
                await self._announce_for_guild(guild)
            except Exception:
                log.exception("Birthday: announce failed for guild %s", guild.id)

    @birthday_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Birthday(bot))
