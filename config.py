import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()  # Local dev only. Railway variables still work.

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
TUTORS_API_URL = os.getenv("TUTORS_API_URL", "https://chessflow.ae/wp-json/chessflow/v1/tutors")
DEFAULT_TZ = os.getenv("TIMEZONE", "Asia/Dubai")
UAE_TZ = ZoneInfo("Asia/Dubai")

TUTORS_PER_PAGE = 6

DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
INDEX_TO_KEY = {v: k for k, v in DAY_INDEX.items()}
INDEX_TO_LABEL = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

def validate_config():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing. Set it in Railway Variables or .env locally.")
    if not ADMIN_CHAT_ID:
        raise ValueError("ADMIN_CHAT_ID missing. Set it in Railway Variables or .env locally.")
    if not TUTORS_API_URL:
        raise ValueError("TUTORS_API_URL missing. Set it in Railway Variables or .env locally.")