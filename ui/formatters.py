from datetime import datetime
from zoneinfo import ZoneInfo

from config import DEFAULT_TZ, UAE_TZ
from utils.country import clean_fide_title, country_to_flag

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

    # ✅ Prefer full description from API if you add it
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

def get_user_tz_name(context) -> str:
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