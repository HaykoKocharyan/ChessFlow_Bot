# bot.py
import logging
import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
import pycountry

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ================== LOAD .env ==================
load_dotenv()

# ================== SETTINGS ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
TUTORS_API_URL = os.getenv("TUTORS_API_URL", "https://chessflow.ae/wp-json/chessflow/v1/tutors")
DEFAULT_TZ = os.getenv("TIMEZONE", "Asia/Dubai")
UAE_TZ = ZoneInfo("Asia/Dubai")
# ==============================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chessflow-bot")

# states
(
    LIST,
    FILTER,
    DATE_PICK,
    TIME_PICK,
    LANG_PICK,
    LEVEL_PICK,
    PHONE,
    EMAIL,
    CONFIRM,
) = range(9)

TUTORS_PER_PAGE = 6

DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
INDEX_TO_KEY = {v: k for k, v in DAY_INDEX.items()}
INDEX_TO_LABEL = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

# ------------------ TITLE CLEANUP ------------------
VALID_TITLES = {"GM", "IM", "FM", "CM", "WGM", "WIM", "WFM", "WCM"}

TITLE_WORD_TO_CODE = {
    "GRANDMASTER": "GM",
    "INTERNATIONAL MASTER": "IM",
    "FIDE MASTER": "FM",
    "CANDIDATE MASTER": "CM",
    "WOMAN GRANDMASTER": "WGM",
    "WOMAN INTERNATIONAL MASTER": "WIM",
    "WOMAN FIDE MASTER": "WFM",
    "WOMAN CANDIDATE MASTER": "WCM",
}


def clean_fide_title(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    upper = s.upper()

    if upper in {"UNTITLED", "NONE", "NO TITLE", "N/A", "-", "NULL"}:
        return ""

    if upper in TITLE_WORD_TO_CODE:
        return TITLE_WORD_TO_CODE[upper]

    if upper in VALID_TITLES:
        return upper

    for code in VALID_TITLES:
        if code in upper:
            return code

    return ""


# ------------------ COUNTRY -> FLAG (ALL COUNTRIES) ------------------
COUNTRY_OVERRIDES = {
    "USA": "US",
    "U.S.A.": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "UK": "GB",
    "U.K.": "GB",
    "UNITED KINGDOM": "GB",
    "ENGLAND": "GB",
    "SCOTLAND": "GB",
    "WALES": "GB",
    "UAE": "AE",
    "UNITED ARAB EMIRATES": "AE",
    "SOUTH KOREA": "KR",
    "NORTH KOREA": "KP",
    "KOREA": "KR",
    "VIET NAM": "VN",
    "CZECH REPUBLIC": "CZ",
}


def iso2_to_flag(iso2: str) -> str:
    if not iso2 or len(iso2) != 2:
        return ""
    iso2 = iso2.upper()
    if not ("A" <= iso2[0] <= "Z" and "A" <= iso2[1] <= "Z"):
        return ""
    return chr(0x1F1E6 + ord(iso2[0]) - ord("A")) + chr(0x1F1E6 + ord(iso2[1]) - ord("A"))


def country_name_to_iso2(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    if not n:
        return ""

    up = n.upper()
    if up in COUNTRY_OVERRIDES:
        return COUNTRY_OVERRIDES[up]

    try:
        c = pycountry.countries.get(name=n)
        if c and getattr(c, "alpha_2", None):
            return c.alpha_2
    except Exception:
        pass

    try:
        matches = pycountry.countries.search_fuzzy(n)
        if matches:
            c = matches[0]
            return getattr(c, "alpha_2", "") or ""
    except Exception:
        pass

    return ""


def country_to_flag(country_name: str) -> str:
    return iso2_to_flag(country_name_to_iso2(country_name))


# ------------------ API ------------------
def fetch_tutors(limit=50) -> list[dict]:
    # shorter timeout helps responsiveness
    r = requests.get(TUTORS_API_URL, params={"limit": limit}, timeout=5)
    r.raise_for_status()
    data = r.json()
    return data.get("items", []) or []


async def get_tutors_cached(context: ContextTypes.DEFAULT_TYPE, limit: int = 50) -> list[dict]:
    """
    Small cache (60 seconds) to avoid hitting the API too often and to keep the bot fast.
    Also runs requests in a thread so the event loop doesn't freeze.
    """
    now = datetime.now(UAE_TZ)
    cache_ts = context.application.bot_data.get("tutors_cache_ts")
    cache_items = context.application.bot_data.get("tutors_cache_items")

    if cache_ts and cache_items:
        if (now - cache_ts).total_seconds() < 60:
            return cache_items

    items = await asyncio.to_thread(fetch_tutors, limit)
    context.application.bot_data["tutors_cache_ts"] = now
    context.application.bot_data["tutors_cache_items"] = items
    return items


# ------------------ ATTR HELPERS ------------------
def get_attr_list(t: dict, key: str) -> list[str]:
    attrs = t.get("attributes", {}) or {}
    v = attrs.get(key)
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def get_fide_rating(t: dict) -> str:
    r = get_attr_list(t, "Fide Rating")
    return r[0] if r else ""


def get_title_and_flag(t: dict) -> tuple[str, str]:
    title = ""
    titles = get_attr_list(t, "Fide Title")
    if titles:
        title = clean_fide_title(titles[0])

    flag = ""
    countries = get_attr_list(t, "Nationality")
    if countries:
        flag = country_to_flag(countries[0])

    return title, flag


def format_display_name(t: dict) -> str:
    name = t.get("name", "Tutor")
    title, flag = get_title_and_flag(t)

    display = name
    if title:
        display = f"{display} ({title})"
    if flag:
        display = f"{display} {flag}"
    return display


def format_tutor_list_label(t: dict) -> str:
    display_name = format_display_name(t)
    price = t.get("price", "")
    currency = (t.get("currency") or "AED").strip()
    fide_rating = get_fide_rating(t)

    parts = [display_name]
    if fide_rating:
        parts.append(f"(FIDE {fide_rating})")
    if price:
        parts.append(f"- {price} {currency}")
    return " ".join(parts)


def format_tutor_card_text(t: dict) -> str:
    display_name = format_display_name(t)
    price = t.get("price", "")
    currency = (t.get("currency") or "AED").strip()
    link = t.get("permalink", "")
    attrs = t.get("attributes", {}) or {}
    desc = (t.get("description") or t.get("short_description") or "").strip()

    lines = [f"♟️ {display_name}"]
    if price:
        lines.append(f"💰 Price: {price} {currency}")

    order = ["Fide Rating", "Experience (year)", "Languages", "Nationality", "Level"]
    for key in order:
        v = attrs.get(key)
        if isinstance(v, list) and v:
            lines.append(f"• {key}: {', '.join(map(str, v))}")

    for k, v in attrs.items():
        if k in set(order) or k == "Fide Title":
            continue
        if isinstance(v, list) and v:
            lines.append(f"• {k}: {', '.join(map(str, v))}")

    if desc:
        lines.append("")
        lines.append(desc[:900])

    if link:
        lines.append("")
        lines.append(f"Profile: {link}")

    return "\n".join(lines)


# ------------------ TIMEZONE (user-set) ------------------
def get_user_tz_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (context.user_data.get("tz") or DEFAULT_TZ).strip()


def format_time_for_user(tm: str, date_str: str, tz_name: str) -> str:
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo(DEFAULT_TZ)

    dt_uae = datetime.strptime(f"{date_str} {tm}", "%Y-%m-%d %H:%M").replace(tzinfo=UAE_TZ)
    dt_user = dt_uae.astimezone(user_tz)

    city = tz_name.split("/")[-1].replace("_", " ")
    return f"{tm} UAE / {dt_user.strftime('%H:%M')} ({city})"


async def tz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Send your timezone like:\n"
            "/tz Asia/Dubai\n"
            "/tz Asia/Yerevan\n"
            "/tz Europe/Paris\n"
            "/tz America/Los_Angeles\n\n"
            "After that, you will see times in UAE + your timezone."
        )
        return

    tz = context.args[0].strip()
    try:
        ZoneInfo(tz)
    except Exception:
        await update.message.reply_text("❌ Timezone not valid. Example: Asia/Dubai or Europe/Paris")
        return

    context.user_data["tz"] = tz
    await update.message.reply_text(f"✅ Saved your timezone: {tz}")


# ------------------ DATE UI ------------------
def upcoming_available_dates(t: dict, days_ahead: int = 21) -> list[dict]:
    weekly = t.get("availability_weekly", {}) or {}
    today = datetime.now(UAE_TZ).date()

    out = []
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        day_key = INDEX_TO_KEY[d.weekday()]
        ranges = weekly.get(day_key, [])
        if isinstance(ranges, list) and len(ranges) > 0:
            label = f"{INDEX_TO_LABEL[d.weekday()]} {d.strftime('%d %b')}"
            out.append({"date": d.strftime("%Y-%m-%d"), "label": label, "day_key": day_key})
    return out


def build_date_buttons(t: dict) -> InlineKeyboardMarkup:
    dates = upcoming_available_dates(t, days_ahead=21)
    keyboard = []

    for d in dates[:14]:
        keyboard.append([InlineKeyboardButton(d["label"], callback_data=f"date:{d['date']}:{d['day_key']}")])

    if not keyboard:
        keyboard.append([InlineKeyboardButton("No availability", callback_data="noop")])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:list")])
    return InlineKeyboardMarkup(keyboard)


def expand_times_from_ranges(ranges: list[dict], step_minutes=60) -> list[str]:
    out = []
    for r in ranges:
        start_s = r.get("from")
        end_s = r.get("to")
        if not start_s or not end_s:
            continue

        start = datetime.strptime(start_s, "%H:%M")
        end = datetime.strptime(end_s, "%H:%M")

        if end <= start:
            end = end + timedelta(days=1)

        cur = start
        while cur + timedelta(minutes=step_minutes) <= end:
            out.append(cur.strftime("%H:%M"))
            cur += timedelta(minutes=step_minutes)

    out = sorted(set(out), key=lambda x: datetime.strptime(x, "%H:%M"))
    return out


# ------------------ FILTERS ------------------
def apply_filters(tutors: list[dict], flt: dict) -> list[dict]:
    if not flt:
        return tutors

    out = []
    for t in tutors:
        if flt.get("level"):
            lvl = get_attr_list(t, "Level")
            if flt["level"] not in lvl:
                continue

        if flt.get("lang"):
            langs = get_attr_list(t, "Languages")
            if flt["lang"] not in langs:
                continue

        out.append(t)
    return out


def build_filter_menu(current: dict) -> InlineKeyboardMarkup:
    level = current.get("level")
    lang = current.get("lang")

    keyboard = [
        [InlineKeyboardButton(f"Level: {level or 'Any'}", callback_data="filter:level")],
        [InlineKeyboardButton(f"Language: {lang or 'Any'}", callback_data="filter:lang")],
        [InlineKeyboardButton("✅ Apply", callback_data="filter:apply")],
        [InlineKeyboardButton("🧹 Clear", callback_data="filter:clear")],
        [InlineKeyboardButton("⬅️ Back", callback_data="filter:back")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------ MAIN MENU BUTTON ------------------
async def mainmenu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    tz = context.user_data.get("tz")
    context.user_data.clear()
    if tz:
        context.user_data["tz"] = tz

    try:
        context.user_data["tutors"] = await get_tutors_cached(context)
    except Exception as e:
        log.exception("fetch_tutors failed")
        await q.edit_message_text("⚠️ Sorry, we can't load tutors right now. Please try again in 1 minute.")
        return ConversationHandler.END

    context.user_data.setdefault("filters", {})
    context.user_data["page"] = 0
    return await show_list(update, context)


# ------------------ PICKERS (LANG/LEVEL) ------------------
def build_lang_buttons(t: dict) -> InlineKeyboardMarkup:
    langs = get_attr_list(t, "Languages")
    keyboard = []

    if langs:
        for ln in langs[:20]:
            keyboard.append([InlineKeyboardButton(ln, callback_data=f"lang:{ln}")])
    else:
        keyboard.append([InlineKeyboardButton("Skip (no languages)", callback_data="lang:skip")])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:time")])
    return InlineKeyboardMarkup(keyboard)


def build_level_buttons(t: dict) -> InlineKeyboardMarkup:
    levels = get_attr_list(t, "Level")
    keyboard = []

    if levels:
        for lv in levels[:20]:
            keyboard.append([InlineKeyboardButton(lv, callback_data=f"level:{lv}")])
    else:
        keyboard.append([InlineKeyboardButton("Skip (no levels)", callback_data="level:skip")])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:lang")])
    return InlineKeyboardMarkup(keyboard)


def build_confirm_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Send request", callback_data="send:request")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back:email")],
            [InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")],
        ]
    )


def format_booking_summary(context: ContextTypes.DEFAULT_TYPE) -> str:
    t = context.user_data.get("tutor", {})
    date_str = context.user_data.get("date", "")
    time_value = context.user_data.get("time_value", "")
    tz_name = get_user_tz_name(context)
    lang = context.user_data.get("student_language", "")
    level = context.user_data.get("student_level", "")
    phone = context.user_data.get("phone", "")
    email = context.user_data.get("email", "")

    lines = [
        "📌 Please confirm your booking request:",
        "",
        f"Tutor: {format_display_name(t)}",
        f"Price: {t.get('price','')} {t.get('currency','AED')}",
        f"Date: {date_str}",
        f"Time: {time_value} (UAE)",
        f"Your timezone: {tz_name}",
    ]
    if lang:
        lines.append(f"Lesson language: {lang}")
    if level:
        lines.append(f"Student level: {level}")

    lines += [
        f"Phone: {phone}",
        f"Email: {email}",
    ]
    return "\n".join(lines)


# ------------------ USER FLOW ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        tutors = await get_tutors_cached(context)
    except Exception:
        log.exception("fetch_tutors failed")
        await update.message.reply_text("⚠️ Sorry, we can't load tutors right now. Please try again in 1 minute.")
        return ConversationHandler.END

    context.user_data["tutors"] = tutors
    context.user_data.setdefault("filters", {})
    context.user_data.setdefault("tz", context.user_data.get("tz") or DEFAULT_TZ)
    context.user_data["page"] = 0
    return await show_list(update, context)


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tutors_all = context.user_data.get("tutors", [])
    flt = context.user_data.get("filters", {})
    tutors = apply_filters(tutors_all, flt)
    context.user_data["tutors_view"] = tutors

    page = context.user_data.get("page", 0)
    start_i = page * TUTORS_PER_PAGE
    end_i = start_i + TUTORS_PER_PAGE
    chunk = tutors[start_i:end_i]

    keyboard = []
    for t in chunk:
        keyboard.append([InlineKeyboardButton(format_tutor_list_label(t), callback_data=f"tutor:{t['id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data="page:prev"))
    if end_i < len(tutors):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data="page:next"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔎 Filter", callback_data="open:filter")])

    flt_txt = []
    if flt.get("level"):
        flt_txt.append(f"Level={flt['level']}")
    if flt.get("lang"):
        flt_txt.append(f"Lang={flt['lang']}")
    flt_line = f"\nFilters: {', '.join(flt_txt)}" if flt_txt else "\nFilters: None"

    tz_name = get_user_tz_name(context)
    tz_line = f"\nYour timezone: {tz_name}  (change: /tz)"

    text = "Welcome to ChessFlow! Choose a tutor:" + flt_line + tz_line
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=markup)
    else:
        await update.message.reply_text(text=text, reply_markup=markup)

    return LIST


async def list_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "page:prev":
        context.user_data["page"] = max(0, context.user_data.get("page", 0) - 1)
        return await show_list(update, context)

    if data == "page:next":
        context.user_data["page"] = context.user_data.get("page", 0) + 1
        return await show_list(update, context)

    if data == "open:filter":
        context.user_data.setdefault("filters", {})
        await q.edit_message_text("Filter tutors:", reply_markup=build_filter_menu(context.user_data["filters"]))
        return FILTER

    if data.startswith("tutor:"):
        tutor_id = int(data.split(":")[1])
        tutors = context.user_data.get("tutors_view") or context.user_data.get("tutors", [])
        t = next((x for x in tutors if int(x.get("id")) == tutor_id), None)
        if not t:
            await q.edit_message_text("Tutor list updated. Type /start again.")
            return ConversationHandler.END

        # reset booking fields for this flow (keep tz, filters, tutors)
        context.user_data.pop("date", None)
        context.user_data.pop("day_key", None)
        context.user_data.pop("time_value", None)
        context.user_data.pop("student_language", None)
        context.user_data.pop("student_level", None)
        context.user_data.pop("phone", None)
        context.user_data.pop("email", None)

        context.user_data["tutor"] = t

        await q.edit_message_text(
            text=format_tutor_card_text(t) + "\n\nChoose a date:",
            reply_markup=build_date_buttons(t),
            disable_web_page_preview=True,
        )

        photo_url = t.get("image")
        if photo_url:
            try:
                await context.bot.send_photo(chat_id=q.message.chat_id, photo=photo_url)
            except Exception as e:
                log.warning("Photo send failed: %s", e)

        return DATE_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


async def filter_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    flt = context.user_data.get("filters", {})

    if data == "filter:back":
        return await show_list(update, context)

    if data == "filter:clear":
        context.user_data["filters"] = {}
        await q.edit_message_text("Filter tutors:", reply_markup=build_filter_menu(context.user_data["filters"]))
        return FILTER

    if data == "filter:level":
        options = [None, "Beginner", "Intermediate", "Advanced"]
        cur = flt.get("level")
        idx = options.index(cur) if cur in options else 0
        nxt = options[(idx + 1) % len(options)]
        if nxt is None:
            flt.pop("level", None)
        else:
            flt["level"] = nxt
        context.user_data["filters"] = flt
        await q.edit_message_text("Filter tutors:", reply_markup=build_filter_menu(flt))
        return FILTER

    if data == "filter:lang":
        options = [None, "English", "Russian", "Armenian", "Arabic"]
        cur = flt.get("lang")
        idx = options.index(cur) if cur in options else 0
        nxt = options[(idx + 1) % len(options)]
        if nxt is None:
            flt.pop("lang", None)
        else:
            flt["lang"] = nxt
        context.user_data["filters"] = flt
        await q.edit_message_text("Filter tutors:", reply_markup=build_filter_menu(flt))
        return FILTER

    if data == "filter:apply":
        context.user_data["page"] = 0
        return await show_list(update, context)

    return FILTER


async def date_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:list":
        return await show_list(update, context)

    if data == "noop":
        return DATE_PICK

    if data.startswith("date:"):
        _, date_str, day_key = data.split(":", 2)
        context.user_data["date"] = date_str
        context.user_data["day_key"] = day_key

        weekly = t.get("availability_weekly", {}) or {}
        ranges = weekly.get(day_key, []) if isinstance(weekly, dict) else []

        times = expand_times_from_ranges(ranges, step_minutes=60)
        if not times:
            await q.edit_message_text("No times for this date. Choose another date.", reply_markup=build_date_buttons(t))
            return DATE_PICK

        tz_name = get_user_tz_name(context)
        keyboard = [
            [InlineKeyboardButton(format_time_for_user(tm, date_str, tz_name), callback_data=f"time:{tm}")]
            for tm in times[:24]
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:dates")])

        await q.edit_message_text(
            text=(f"Tutor: {format_display_name(t)}\nDate: {date_str}\nTimezone: {tz_name}\n\nChoose a time:"),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return TIME_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


async def time_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:dates":
        await q.edit_message_text(
            text=format_tutor_card_text(t) + "\n\nChoose a date:",
            reply_markup=build_date_buttons(t),
            disable_web_page_preview=True,
        )
        return DATE_PICK

    if data.startswith("time:"):
        time_value = data.split(":", 1)[1]
        context.user_data["time_value"] = time_value

        await q.edit_message_text(
            text="Choose lesson language:",
            reply_markup=build_lang_buttons(t),
        )
        return LANG_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


async def lang_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:time":
        date_str = context.user_data.get("date", "")
        day_key = context.user_data.get("day_key", "")
        weekly = t.get("availability_weekly", {}) or {}
        ranges = weekly.get(day_key, []) if isinstance(weekly, dict) else []
        times = expand_times_from_ranges(ranges, step_minutes=60)

        tz_name = get_user_tz_name(context)
        keyboard = [
            [InlineKeyboardButton(format_time_for_user(tm, date_str, tz_name), callback_data=f"time:{tm}")]
            for tm in times[:24]
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:dates")])

        await q.edit_message_text(
            text=(f"Tutor: {format_display_name(t)}\nDate: {date_str}\nTimezone: {tz_name}\n\nChoose a time:"),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return TIME_PICK

    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        context.user_data["student_language"] = "" if lang == "skip" else lang
        await q.edit_message_text("Choose your level:", reply_markup=build_level_buttons(t))
        return LEVEL_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


async def level_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:lang":
        await q.edit_message_text("Choose lesson language:", reply_markup=build_lang_buttons(t))
        return LANG_PICK

    if data.startswith("level:"):
        lvl = data.split(":", 1)[1]
        context.user_data["student_level"] = "" if lvl == "skip" else lvl
        await q.edit_message_text("Please type your mobile number (example: +9715xxxxxxx):")
        return PHONE

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = (update.message.text or "").strip()
    context.user_data["phone"] = phone
    await update.message.reply_text("Now type your email address:")
    return EMAIL


async def email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = (update.message.text or "").strip()
    context.user_data["email"] = email

    await update.message.reply_text(
        text=format_booking_summary(context),
        reply_markup=build_confirm_buttons(),
    )
    return CONFIRM


async def confirm_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "mainmenu":
        return await mainmenu_click(update, context)

    if data == "back:email":
        await q.edit_message_text("Please type your email address:")
        return EMAIL

    if data == "send:request":
        t = context.user_data.get("tutor", {})
        student = update.effective_user
        username = student.username or "NoUsername"

        date_str = context.user_data.get("date", "")
        time_value = context.user_data.get("time_value", "")
        tz_name = get_user_tz_name(context)

        lang = context.user_data.get("student_language", "")
        level = context.user_data.get("student_level", "")
        phone = context.user_data.get("phone", "")
        email = context.user_data.get("email", "")

        await q.edit_message_text(
            text=(
                "✅ Booking request sent!\n\n"
                "We received your request. Please wait while we confirm tutor availability. "
                "Once confirmed, you will receive a payment link.\n\n"
                f"Tutor: {format_display_name(t)}\n"
                f"Price: {t.get('price','')} {t.get('currency','AED')}\n"
                f"Date: {date_str}\n"
                f"Time: {time_value} (UAE)\n"
                f"Your timezone: {tz_name}\n"
                + (f"Lesson language: {lang}\n" if lang else "")
                + (f"Student level: {level}\n" if level else "")
                + f"Phone: {phone}\nEmail: {email}\n"
            )
        )

        admin_text = (
            "🚨 NEW CHESSFLOW BOOKING REQUEST\n"
            f"Student: @{username} (ID: {student.id})\n"
            f"Phone: {phone}\n"
            f"Email: {email}\n\n"
            f"Tutor: {format_display_name(t)} (Product ID: {t.get('id','')})\n"
            f"Price: {t.get('price','')} {t.get('currency','AED')}\n"
            f"Date: {date_str}\n"
            f"Time: {time_value} (UAE)\n"
            + (f"Lesson language: {lang}\n" if lang else "")
            + (f"Student level: {level}\n" if level else "")
            + f"Link: {t.get('permalink','')}\n\n"
            "Commands:\n"
            f"/confirm {student.id} <ZIINA_LINK>\n"
            f"/decline {student.id} Sorry, tutor is not available at this time. Please choose another slot.\n"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
        except Exception as e:
            log.warning("Failed to send admin message: %s", e)

        # Keep timezone + filters, but clear the booking fields
        tz_keep = context.user_data.get("tz")
        filters_keep = context.user_data.get("filters")

        context.user_data.clear()
        if tz_keep:
            context.user_data["tz"] = tz_keep
        if filters_keep is not None:
            context.user_data["filters"] = filters_keep

        return ConversationHandler.END

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END


# ------------------ ADMIN COMMANDS ------------------
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_CHAT_ID


async def confirm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /confirm <student_id> <ziina_link>")
        return

    try:
        student_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("student_id must be a number.")
        return

    ziina_link = context.args[1].strip()

    msg = (
        "✅ Booking confirmed!\n\n"
        "Your tutor is available. Please proceed to payment using the link below:\n"
        f"{ziina_link}\n\n"
        "After payment, we will share the meeting details."
    )

    try:
        await context.bot.send_message(chat_id=student_id, text=msg, disable_web_page_preview=True)
        await update.message.reply_text("Sent confirmation + payment link to student.")
    except Exception as e:
        await update.message.reply_text(f"Failed to message student: {e}")


async def decline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /decline <student_id> <message...>")
        return

    try:
        student_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("student_id must be a number.")
        return

    reason = " ".join(context.args[1:]).strip()
    msg = (
        "❌ Booking not confirmed\n\n"
        f"{reason}\n\n"
        "Tap Main menu to choose another tutor/time."
    )

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")]])

    try:
        await context.bot.send_message(chat_id=student_id, text=msg, reply_markup=markup)
        await update.message.reply_text("Sent decline message to student (with Main menu button).")
    except Exception as e:
        await update.message.reply_text(f"Failed to message student: {e}")


# ------------------ MAIN ------------------
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing. Put it in .env (BOT_TOKEN=...)")
    if not ADMIN_CHAT_ID:
        raise ValueError("ADMIN_CHAT_ID missing. Put it in .env (ADMIN_CHAT_ID=...)")
    if not TUTORS_API_URL:
        raise ValueError("TUTORS_API_URL missing. Put it in .env (TUTORS_API_URL=...)")

    app = Application.builder().token(BOT_TOKEN).build()

    # Global main menu button (from decline message)
    app.add_handler(CallbackQueryHandler(mainmenu_click, pattern="^mainmenu$"))

    # Commands (DO NOT add separate /start here, ConversationHandler must own it)
    app.add_handler(CommandHandler("tz", tz_cmd))
    app.add_handler(CommandHandler("confirm", confirm_cmd))
    app.add_handler(CommandHandler("decline", decline_cmd))

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LIST: [CallbackQueryHandler(list_click)],
            FILTER: [CallbackQueryHandler(filter_click)],
            DATE_PICK: [CallbackQueryHandler(date_click)],
            TIME_PICK: [CallbackQueryHandler(time_click)],
            LANG_PICK: [CallbackQueryHandler(lang_click)],
            LEVEL_PICK: [CallbackQueryHandler(level_click)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_input)],
            CONFIRM: [CallbackQueryHandler(confirm_click)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)

    print("Bot running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()