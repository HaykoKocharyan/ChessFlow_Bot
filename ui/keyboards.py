from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import INDEX_TO_KEY, INDEX_TO_LABEL, UAE_TZ

def add_mainmenu_row(keyboard: list[list[InlineKeyboardButton]]):
    keyboard.append([InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")])

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
    add_mainmenu_row(keyboard)
    return InlineKeyboardMarkup(keyboard)

def build_lang_buttons(langs: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    if langs:
        for ln in langs[:20]:
            keyboard.append([InlineKeyboardButton(ln, callback_data=f"lang:{ln}")])
    else:
        keyboard.append([InlineKeyboardButton("Skip (no languages)", callback_data="lang:skip")])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:time")])
    add_mainmenu_row(keyboard)
    return InlineKeyboardMarkup(keyboard)

def build_level_buttons(levels: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    if levels:
        for lv in levels[:20]:
            keyboard.append([InlineKeyboardButton(lv, callback_data=f"level:{lv}")])
    else:
        keyboard.append([InlineKeyboardButton("Skip (no levels)", callback_data="level:skip")])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:lang")])
    add_mainmenu_row(keyboard)
    return InlineKeyboardMarkup(keyboard)

def build_confirm_buttons() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ Send request", callback_data="send:request")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:email")],
        [InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")],
    ]
    return InlineKeyboardMarkup(keyboard)

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

def build_date_buttons(t: dict, page: int = 0) -> InlineKeyboardMarkup:
    """
    ✅ Shows 14 days split 7 + 7
    ✅ 2 buttons per row
    """
    dates = upcoming_available_dates(t, days_ahead=21)
    slice_ = dates[0:7] if page == 0 else dates[7:14]

    keyboard = []
    row = []
    for d in slice_:
        row.append(InlineKeyboardButton(d["label"], callback_data=f"date:{d['date']}:{d['day_key']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if not keyboard:
        keyboard = [[InlineKeyboardButton("No availability", callback_data="noop")]]

    nav = []
    if page == 1:
        nav.append(InlineKeyboardButton("⬅️ Prev week", callback_data="datepage:prev"))
    if len(dates) > 7 and page == 0:
        nav.append(InlineKeyboardButton("Next week ➡️", callback_data="datepage:next"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back:list")])
    add_mainmenu_row(keyboard)
    return InlineKeyboardMarkup(keyboard)