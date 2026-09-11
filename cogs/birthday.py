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


class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {"guilds": {}}
        self._load()
        self.birthday_loop.start()

    def cog_unload(self):
        self.birthday_loop.cancel()

    # ---------- persistence ----------

    def _load(self):
        try:
            with open(STATE_PATH) as f:
                self.data = json.load(f)
            self.data.setdefault("guilds", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {"guilds": {}}

    def _save(self):
        os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, STATE_PATH)

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

    @birthday.command(name="set", aliases=["add", "log"])
    async def set_birthday(self, ctx, member: discord.Member = None, *, date_str: str = None):
        """Log a birthday. `!birthday set March 5` (yourself) or `!birthday set @user 03/05` (admin)."""
        # allow "!birthday set March 5" (no member) — shift args
        if member is None or (date_str is None and member is not None):
            # if the first token wasn't a member, discord.py leaves member=None and puts all in date_str
            pass
        target = member or ctx.author
        if member and member != ctx.author and not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("You need **Manage Server** to set someone else's birthday.")
        if date_str is None:
            return await ctx.send("Tell me a date, e.g. `!birthday set March 5` or `!birthday set 03/05/1998`.")

        parsed = parse_birthday(date_str)
        if not parsed:
            return await ctx.send("I couldn't read that date. Try `03/05`, `March 5`, or `5 Mar 1998`.")
        month, day, year = parsed

        g = self._guild(ctx.guild.id)
        g["birthdays"][str(target.id)] = {"month": month, "day": day, "year": year}
        self._save()
        await self._audit(ctx.guild, f"🎂 {ctx.author.mention} set {target.mention}'s birthday to **{fmt_date(month, day, year)}**")

        d = days_until(month, day, date.today())
        when = "today! 🎉" if d == 0 else f"in **{d}** day{'s' if d != 1 else ''}"
        await ctx.send(f"Saved {target.mention}'s birthday: **{fmt_date(month, day, year)}** — next one is {when}")

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
        self._save()
        await self._audit(ctx.guild, f"🗑️ {ctx.author.mention} removed {target.mention}'s birthday "
                                     f"(was {fmt_date(removed['month'], removed['day'], removed.get('year'))})")
        await ctx.send(f"Deleted {target.mention}'s birthday.")

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
