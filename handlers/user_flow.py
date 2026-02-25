import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes

from api.tutors import get_tutors_cached
from config import DEFAULT_TZ, TUTORS_PER_PAGE, UAE_TZ
from ui.formatters import (
    format_tutor_list_label,
    format_tutor_card_text,
    format_display_name,
    get_user_tz_name,
    format_time_for_user,
    get_attr_list,
)
from ui.keyboards import (
    build_filter_menu,
    build_date_buttons,
    build_lang_buttons,
    build_level_buttons,
    build_confirm_buttons,
)

log = logging.getLogger("chessflow-bot")

# states
(LIST, FILTER, DATE_PICK, TIME_PICK, LANG_PICK, LEVEL_PICK, PHONE, EMAIL, CONFIRM) = range(9)

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

async def mainmenu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    tz = context.user_data.get("tz")
    context.user_data.clear()
    if tz:
        context.user_data["tz"] = tz

    try:
        context.user_data["tutors"] = await get_tutors_cached(context)
    except Exception:
        log.exception("fetch_tutors failed")
        await q.edit_message_text("⚠️ Sorry, we can't load tutors right now. Please try again in 1 minute.")
        return ConversationHandler.END

    context.user_data.setdefault("filters", {})
    context.user_data["page"] = 0
    return await show_list(update, context)

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
    keyboard.append([InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")])

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

    if data == "mainmenu":
        return await mainmenu_click(update, context)

    if data.startswith("tutor:"):
        tutor_id = int(data.split(":")[1])
        tutors = context.user_data.get("tutors_view") or context.user_data.get("tutors", [])
        t = next((x for x in tutors if int(x.get("id")) == tutor_id), None)
        if not t:
            await q.edit_message_text("Tutor list updated. Type /start again.")
            return ConversationHandler.END

        # reset booking fields
        for k in ["date", "day_key", "time_value", "student_language", "student_level", "phone", "email"]:
            context.user_data.pop(k, None)

        context.user_data["tutor"] = t
        context.user_data["date_page"] = 0  # ✅ week page for dates

        await q.edit_message_text(
            text=format_tutor_card_text(t) + "\n\nChoose a date:",
            reply_markup=build_date_buttons(t, page=0),
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

    if data == "mainmenu":
        return await mainmenu_click(update, context)

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

    if data == "mainmenu":
        return await mainmenu_click(update, context)

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:list":
        return await show_list(update, context)

    # ✅ week pagination
    if data == "datepage:next":
        context.user_data["date_page"] = 1
        await q.edit_message_reply_markup(reply_markup=build_date_buttons(t, page=1))
        return DATE_PICK

    if data == "datepage:prev":
        context.user_data["date_page"] = 0
        await q.edit_message_reply_markup(reply_markup=build_date_buttons(t, page=0))
        return DATE_PICK

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
            page = int(context.user_data.get("date_page", 0))
            await q.edit_message_text("No times for this date. Choose another date.", reply_markup=build_date_buttons(t, page=page))
            return DATE_PICK

        tz_name = get_user_tz_name(context)
        keyboard = [
            [InlineKeyboardButton(format_time_for_user(tm, date_str, tz_name), callback_data=f"time:{tm}")]
            for tm in times[:24]
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:dates")])
        keyboard.append([InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")])

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

    if data == "mainmenu":
        return await mainmenu_click(update, context)

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:dates":
        page = int(context.user_data.get("date_page", 0))
        await q.edit_message_text(
            text=format_tutor_card_text(t) + "\n\nChoose a date:",
            reply_markup=build_date_buttons(t, page=page),
            disable_web_page_preview=True,
        )
        return DATE_PICK

    if data.startswith("time:"):
        time_value = data.split(":", 1)[1]
        context.user_data["time_value"] = time_value

        langs = get_attr_list(t, "Languages")
        await q.edit_message_text(text="Choose lesson language:", reply_markup=build_lang_buttons(langs))
        return LANG_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END

async def lang_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "mainmenu":
        return await mainmenu_click(update, context)

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
        keyboard.append([InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")])

        await q.edit_message_text(
            text=(f"Tutor: {format_display_name(t)}\nDate: {date_str}\nTimezone: {tz_name}\n\nChoose a time:"),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return TIME_PICK

    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        context.user_data["student_language"] = "" if lang == "skip" else lang

        levels = get_attr_list(t, "Level")
        await q.edit_message_text("Choose your level:", reply_markup=build_level_buttons(levels))
        return LEVEL_PICK

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END

async def level_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "mainmenu":
        return await mainmenu_click(update, context)

    t = context.user_data.get("tutor")
    if not t:
        await q.edit_message_text("Type /start again.")
        return ConversationHandler.END

    if data == "back:lang":
        langs = get_attr_list(t, "Languages")
        await q.edit_message_text("Choose lesson language:", reply_markup=build_lang_buttons(langs))
        return LANG_PICK

    if data.startswith("level:"):
        lvl = data.split(":", 1)[1]
        context.user_data["student_level"] = "" if lvl == "skip" else lvl
        await q.edit_message_text("Please type your mobile number (example: +9715xxxxxxx):\n\n🏠 Main menu: /start")
        return PHONE

    await q.edit_message_text("Type /start again.")
    return ConversationHandler.END

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = (update.message.text or "").strip()
    context.user_data["phone"] = phone
    await update.message.reply_text("Now type your email address:")
    return EMAIL

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

    lines += [f"Phone: {phone}", f"Email: {email}"]
    return "\n".join(lines)

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
            from config import ADMIN_CHAT_ID
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