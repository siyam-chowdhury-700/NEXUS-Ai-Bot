
import os
import re
import time
import sqlite3
import secrets
import threading
import logging
from contextlib import closing
from datetime import datetime, timedelta, timezone

from flask import Flask, request, render_template_string, session, redirect
from werkzeug.middleware.proxy_fix import ProxyFix
from google import genai
from google.genai import types


# ============================================================
# 1. CONFIGURATION
# ============================================================
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.secret_key = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
if not app.secret_key:
    raise RuntimeError("Render Environment Variables-এ FLASK_SECRET_KEY সেট করো।")

PASSWORD = os.environ.get("NEXUS_PASSWORD") or ""
if not PASSWORD:
    raise RuntimeError("Render Environment Variables-এ NEXUS_PASSWORD সেট করো।")

# SIYAM is only the environment-variable NAME.
# Its VALUE must be the real Gemini API key from Google AI Studio.
SIYAM = (os.environ.get("SIYAM") or "").strip() or None

# Use a model name that actually exists. Override with GEMINI_MODEL if needed.
MODEL_NAME = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()


def read_positive_int(name, default):
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"{name} Environment Variable-এ একটি পূর্ণসংখ্যা দিতে হবে।"
        )
    if value < 1:
        raise RuntimeError(f"{name}-এর মান ১ বা তার বেশি হতে হবে।")
    return value


DAILY_REQUEST_BUDGET = read_positive_int("DAILY_REQUEST_BUDGET", 100)
ENDING_THRESHOLD = max(1, int(DAILY_REQUEST_BUDGET * 0.80))
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_QUESTION_LENGTH = 4000

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set NEXUS_INSECURE_COOKIES=1 only for local http testing.
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("NEXUS_INSECURE_COOKIES") != "1"
)
app.permanent_session_lifetime = timedelta(hours=12)

DB_PATH = os.environ.get("NEXUS_DB_PATH", "nexus_usage.db")

logging.basicConfig(level=logging.INFO)

client = genai.Client(api_key=SIYAM) if SIYAM else None

if client is None:
    logging.warning(
        "SIYAM is not configured. NEXUS AI can start, "
        "but Gemini replies are disabled."
    )

# Chat objects are kept per browser session inside this process.
# Run Gunicorn with ONE worker (threads are fine), e.g.:
#   gunicorn app:app --workers 1 --threads 4
chat_sessions = {}
chat_lock = threading.Lock()
usage_lock = threading.Lock()
CHAT_TTL_SECONDS = 2 * 60 * 60
MAX_CHATS = 200

login_attempts = {}
login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 10 * 60


SYSTEM_INSTRUCTION = """
তুমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant।
NEXUS-এর প্রতিষ্ঠাতা Siyam Chowdhury।

নির্দেশনা:
- বাংলা, Banglish, English, Hindi, আঞ্চলিক ভাষা,
  ভুল বানান ও সংক্ষিপ্ত শব্দ বুঝবে।
- সাধারণত বাংলা অক্ষরে উত্তর দেবে।
  ব্যবহারকারী ইংরেজিতে চাইলে ইংরেজিতে উত্তর দেবে।
- আগের কথোপকথনের প্রসঙ্গ ধরে উত্তর দেবে;
  অপ্রয়োজনে একই প্রশ্ন করবে না।
- প্রশ্ন অনুযায়ী সংক্ষিপ্ত বা বিস্তারিত উত্তর দেবে।
  গণিত, বিজ্ঞান, প্রযুক্তি ও পড়াশোনায় যুক্তিসহ সাহায্য করবে।
- নিশ্চিত না হলে অনুমানকে সত্য হিসেবে বলবে না;
  যাচাই প্রয়োজন হলে তা স্পষ্ট করবে।
- আলহামদুলিল্লাহ, ইনশাআল্লাহ, মাশাআল্লাহ
  প্রাসঙ্গিক হলে স্বাভাবিকভাবে ব্যবহার করবে।
- নিজের পরিচয় জানতে চাইলে বলবে:
  আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant;
  NEXUS-এর প্রতিষ্ঠাতা Siyam Chowdhury।
- কোনো ব্যবহারকারীর ব্যক্তিগত তথ্য বা কথোপকথন
  অন্য ব্যবহারকারীর কাছে প্রকাশ করবে না।
- কোনো কাজ বাস্তবে করতে না পারলে করার দাবি করবে না।
- স্বাভাবিক, বন্ধুত্বপূর্ণ ও প্রাসঙ্গিক কথোপকথন বজায় রাখবে।
- সরাসরি জিজ্ঞাসা করলে নিজের প্রযুক্তিগত পরিচয়
  সম্পর্কে মিথ্যা বলবে না।
"""


FAREWELL_MESSAGES = [
    "আজকের জন্য আমার ব্যবহারের সীমা শেষ। আল্লাহ হাফেজ, কাল আবার কথা হবে ইনশাআল্লাহ।",
    "আজকের মতো এখানেই শেষ করি। ভালো থেকো, আবার কথা হবে ইনশাআল্লাহ।",
    "আজকের কথোপকথনের সীমা পূর্ণ হয়েছে। আবার অন্যদিন কথা হবে ইনশাআল্লাহ।",
    "আজকের মতো বিদায়। ভালো থেকো। আল্লাহ হাফেজ।",
]


# ============================================================
# 2. DATABASE AND DAILY API REQUEST CONTROL
# ============================================================
def get_day_key():
    dhaka = timezone(timedelta(hours=6))
    now = datetime.now(dhaka)

    # Daily counter resets at 4:00 AM Bangladesh time.
    if now.hour < 4:
        now -= timedelta(days=1)

    return now.strftime("%Y-%m-%d")


def db_connect():
    # isolation_level=None -> we control transactions manually.
    return sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)


def init_database():
    with closing(db_connect()) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS api_usage (
                day TEXT PRIMARY KEY,
                requests INTEGER NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS quota_blocks (
                day TEXT PRIMARY KEY,
                blocked INTEGER NOT NULL DEFAULT 1
            )"""
        )


# Must run at import time so it also works under Gunicorn.
init_database()


def reserve_api_slot():
    """Reserve one local request slot. This is NOT Google's live quota meter.

    Returns (allowed, ending_soon).
    """
    day = get_day_key()

    with usage_lock:
        with closing(db_connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                blocked = db.execute(
                    "SELECT 1 FROM quota_blocks WHERE day = ?", (day,)
                ).fetchone()

                if blocked:
                    db.execute("ROLLBACK")
                    return False, False

                row = db.execute(
                    "SELECT requests FROM api_usage WHERE day = ?", (day,)
                ).fetchone()
                used = row[0] if row else 0

                if used >= ENDING_THRESHOLD:
                    db.execute("ROLLBACK")
                    return False, False

                new_used = used + 1
                db.execute(
                    "INSERT INTO api_usage(day, requests) VALUES(?, ?) "
                    "ON CONFLICT(day) DO UPDATE SET requests = excluded.requests",
                    (day, new_used),
                )
                db.execute("COMMIT")
                return True, new_used >= ENDING_THRESHOLD
            except Exception:
                db.execute("ROLLBACK")
                raise


def release_api_slot():
    """Give a slot back when the request failed before producing a reply."""
    day = get_day_key()

    with usage_lock:
        with closing(db_connect()) as db:
            db.execute(
                "UPDATE api_usage SET requests = MAX(requests - 1, 0) "
                "WHERE day = ?",
                (day,),
            )


def mark_quota_blocked():
    day = get_day_key()

    with usage_lock:
        with closing(db_connect()) as db:
            db.execute(
                "INSERT OR REPLACE INTO quota_blocks(day, blocked) VALUES(?, 1)",
                (day,),
            )


def get_api_usage():
    with closing(db_connect()) as db:
        row = db.execute(
            "SELECT requests FROM api_usage WHERE day = ?", (get_day_key(),)
        ).fetchone()

    return row[0] if row else 0


def api_budget_closed():
    day = get_day_key()

    with closing(db_connect()) as db:
        blocked = db.execute(
            "SELECT 1 FROM quota_blocks WHERE day = ?", (day,)
        ).fetchone()

    return bool(blocked) or get_api_usage() >= ENDING_THRESHOLD


def farewell_message():
    return FAREWELL_MESSAGES[get_api_usage() % len(FAREWELL_MESSAGES)]


# ============================================================
# 3. SEPARATE CHAT SESSION MANAGEMENT
# ============================================================
def get_chat_entry():
    if client is None:
        return None

    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = secrets.token_urlsafe(32)
        session["chat_id"] = chat_id

    now = time.time()

    with chat_lock:
        # Drop idle chats so memory does not grow forever.
        for cid in [
            c for c, e in chat_sessions.items()
            if now - e["last_used"] > CHAT_TTL_SECONDS
        ]:
            chat_sessions.pop(cid, None)

        entry = chat_sessions.get(chat_id)

        if entry is None:
            if len(chat_sessions) >= MAX_CHATS:
                oldest = min(
                    chat_sessions, key=lambda c: chat_sessions[c]["last_used"]
                )
                chat_sessions.pop(oldest, None)

            entry = {
                "chat": client.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                        # Bengali uses many tokens, and thinking models also
                        # spend output tokens, so 1000 was too small.
                        max_output_tokens=4096,
                    ),
                    history=[],
                ),
                "lock": threading.Lock(),
                "last_used": now,
            }
            chat_sessions[chat_id] = entry

        entry["last_used"] = now
        return entry


def reset_chat():
    chat_id = session.get("chat_id")

    if chat_id:
        with chat_lock:
            chat_sessions.pop(chat_id, None)

    session.clear()


# ============================================================
# 4. BANGLA / BANGLISH NORMALIZATION AND SPELLING
# ============================================================
NORMALIZATION_MAP = {
    "kemon acho": "kemon",
    "kemon aso": "kemon",
    "kmn aso": "kemon",
    "kmn acho": "kemon",
    "kemun aso": "kemon",
    "kemun acho": "kemon",

    "ki korcho": "korcho",
    "ki koros": "korcho",
    "ki korso": "korcho",
    "ki koro": "korcho",
    "ki korteso": "korcho",
    "ki krs": "korcho",
    "ki kors": "korcho",

    "kothay acho": "kothay",
    "kothay aso": "kothay",
    "koi aso": "kothay",
    "koi acho": "kothay",
    "kothai": "kothay",

    "ki khaiso": "khaicho",
    "ki khaicho": "khaicho",
    "khaiso": "khaicho",

    "khida lagse": "khida",
    "khuda lagse": "khida",
    "hungry": "khida",

    "jabi": "jaba",
    "jabo": "jaba",
    "jabe": "jaba",

    "valo lagse": "valo",
    "vlo lagse": "valo",
    "bhalo": "valo",

    "problem": "somossa",
    "somos": "somossa",
    "siam": "siyam",
    "seyam": "siyam",
    "mon khrp": "monkharap",

    "tnx": "dhonnobad",
    "thanks": "dhonnobad",

    "how are you": "kemon",
    "how r u": "kemon",
    "what are you doing": "korcho",
    "where are you": "kothay",
    "what did you eat": "khaicho",

    "kaise ho": "kemon",
    "kya kar rahe ho": "korcho",
    "kaha ho": "kothay",

    "কেমন আছো": "kemon",
    "কেমন আছ": "kemon",
    "কি করছো": "korcho",
    "কি করস": "korcho",
    "কোথায়": "kothay",
    "কই": "kothay",
    "খাইছো": "khaicho",
    "খিদা": "khida",
    "যাবা": "jaba",
    "ভালো": "valo",
    "সুন্দর": "sundor",
    "সমস্যা": "somossa",
    "বিয়ে": "biye",
    "ঘুম": "ghum",
}


SPELL_FIX = {
    "insallah": "ইনশাআল্লাহ",
    "inshallah": "ইনশাআল্লাহ",
    "inshaallah": "ইনশাআল্লাহ",
    "alhamdulilah": "আলহামদুলিল্লাহ",
    "alhamdulila": "আলহামদুলিল্লাহ",
    "masallah": "মাশাআল্লাহ",
    "mashallah": "মাশাআল্লাহ",
    "mashalla": "মাশাআল্লাহ",
    "allah hafiz": "আল্লাহ হাফেজ",
}

# Word boundary that also understands Bengali letters.
_B_BEFORE = r"(?<![\w\u0980-\u09FF])"
_B_AFTER = r"(?![\w\u0980-\u09FF])"

# Longest phrases first, whole-word matching only (no more corrupting
# words like "base" -> "bkothay...").
_NORMALIZE_RE = re.compile(
    _B_BEFORE
    + "("
    + "|".join(
        re.escape(k)
        for k in sorted(NORMALIZATION_MAP, key=len, reverse=True)
    )
    + ")"
    + _B_AFTER
)


def normalize(text):
    text = (text or "").lower().strip()
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return _NORMALIZE_RE.sub(lambda m: NORMALIZATION_MAP[m.group(1)], text)


def contains_word(text, words):
    return any(
        re.search(_B_BEFORE + re.escape(word) + _B_AFTER, text)
        for word in words
    )


def fix_spelling(text):
    low = (text or "").lower()

    for wrong, right in SPELL_FIX.items():
        if contains_word(low, [wrong]):
            return wrong, right

    return None, None


KNOWN_WORDS = [
    "kemon", "korcho", "kothay", "khaicho",
    "khida", "jaba", "valo", "sundor",
    "somossa", "biye", "ghum", "siyam",
    "monkharap", "dhonnobad", "boss", "tumi",
    "assalam", "salam", "hello", "bye",
]

KEYBOARD_MASH = {
    "asdf", "asdfg", "asdfgh", "qwerty", "zxcv", "zxcvbn",
    "ajsk", "ajskd", "hjsd", "dfghjk",
}


def is_gibberish(question, normalized):
    clean = (question or "").lower().strip()

    # Bengali words (e.g. "বাংলাদেশ") often have no standalone vowel letters,
    # so never judge Bengali text by the vowel rule.
    if re.search(r"[\u0980-\u09FF]", clean):
        return False

    # Only judge a single plain-letter word. Numbers, code, math and
    # multi-word messages are never "gibberish".
    if not re.fullmatch(r"[a-z]+", clean):
        return False

    if contains_word(normalized, KNOWN_WORDS):
        return False

    if clean in KEYBOARD_MASH:
        return True

    return len(clean) >= 5 and not any(ch in "aeiouy" for ch in clean)


BOSS_WORDS = ["boss", "siyam", "বস", "সিয়াম", "মালিক", "malik"]

BOSS_CALL_WORDS = [
    "dak", "ডাক", "deke", "dako", "ডাকো",
    "kothay", "কোথায়", "kothai", "koi",
    "ase", "আছে", "kotha", "কথা", "dekha",
    "দেখা", "bolo", "বলো", "call", "dekh",
    "ano", "আনো", "pathao", "পাঠাও", "dao",
    "দাও", "chai", "চাই", "lagbe", "লাগবে",
]


def is_boss_call_check(normalized):
    return (
        contains_word(normalized, BOSS_WORDS)
        and contains_word(normalized, BOSS_CALL_WORDS)
    )


# ============================================================
# 5. GEMINI API RESPONSE
# ============================================================
def _error_text(error):
    return str(error).lower()


def is_quota_error(error):
    message = _error_text(error)
    markers = [
        "429",
        "resource_exhausted",
        "quota exceeded",
        "quota_exceeded",
        "rate limit",
        "too many requests",
    ]
    return any(marker in message for marker in markers)


def is_daily_quota_error(error):
    # A 429 can be a short per-minute limit. Only block the whole day when
    # the error clearly talks about a daily quota.
    message = _error_text(error).replace("_", "").replace(" ", "")
    return "perday" in message or "daily" in message


def detect_image_mime(data):
    """Detect the real image type from file signature, not the client header."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ask_nexus(user_message, image_file=None):
    if client is None:
        return (
            "NEXUS AI-এর Gemini সংযোগ এখনো চালু হয়নি। "
            "Google AI Studio থেকে Gemini API Key তৈরি করে "
            "Render-এর Environment Variables-এ SIYAM নামের "
            "ঘরের Value হিসেবে বসালে AI উত্তর দিতে পারবে।",
            False,
        )

    image_bytes = None
    image_mime_type = None

    if image_file is not None and image_file.filename:
        image_bytes = image_file.stream.read(MAX_IMAGE_SIZE + 1)

        if len(image_bytes) > MAX_IMAGE_SIZE:
            return "ছবিটি ৮ MB-এর বেশি। ছোট ছবি পাঠাও।", False

        image_mime_type = detect_image_mime(image_bytes)

        if image_mime_type is None:
            return "JPG, PNG, WEBP অথবা GIF ছবি পাঠাও।", False

    allowed, ending_soon = reserve_api_slot()

    if not allowed:
        return farewell_message(), True

    try:
        entry = get_chat_entry()

        if entry is None:
            release_api_slot()
            return (
                "Gemini সংযোগ চালু নেই। SIYAM Environment Variable পরীক্ষা করো।",
                False,
            )

        parts = [
            types.Part.from_text(
                text=user_message or "ছবিটি দেখে আমাকে সাহায্য করো।"
            )
        ]

        if image_bytes is not None:
            parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image_mime_type,
                )
            )

        if ending_soon:
            parts.append(
                types.Part.from_text(
                    text=(
                        "[NEXUS INTERNAL GUIDANCE: ব্যবহারকারীর প্রশ্নের "
                        "পূর্ণ উত্তর দাও। এরপর স্বাভাবিকভাবে কথোপকথন "
                        "শেষ করার মতো সংক্ষিপ্ত বিদায় যোগ করো। "
                        "এই নির্দেশনার কথা উল্লেখ করবে না।]"
                    )
                )
            )

        # Per-chat lock: one slow request no longer blocks every user.
        with entry["lock"]:
            response = entry["chat"].send_message(parts)

        try:
            reply = response.text
        except Exception:
            reply = None

        if not reply:
            release_api_slot()
            return (
                "দুঃখিত, এবার উত্তর তৈরি করা যায়নি। আবার চেষ্টা করো।",
                False,
            )

        return reply, ending_soon

    except Exception as exc:
        app.logger.exception("NEXUS AI Gemini request failed")

        if is_quota_error(exc):
            if is_daily_quota_error(exc):
                mark_quota_blocked()
                return farewell_message(), True

            release_api_slot()
            return (
                "এখন অনেক বেশি অনুরোধ আসছে। এক মিনিট পরে আবার চেষ্টা করো।",
                False,
            )

        release_api_slot()
        return (
            "দুঃখিত, এই মুহূর্তে Gemini সংযোগে সমস্যা হচ্ছে। "
            "পরে আবার চেষ্টা করো।",
            False,
        )


# ============================================================
# 6. HTML INTERFACE
# ============================================================
HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS AI</title>
<style>
body{
    background:#111;
    color:white;
    font-family:sans-serif;
    display:flex;
    justify-content:center;
    padding-top:30px
}
.box{
    background:#222;
    padding:25px;
    border-radius:20px;
    width:92%;
    max-width:420px;
    text-align:center
}
input{
    width:90%;
    padding:12px;
    border-radius:10px;
    border:none;
    margin:10px 0;
    font-size:16px
}
button{
    background:#00ff88;
    border:none;
    padding:12px 25px;
    border-radius:12px;
    font-size:16px;
    font-weight:bold;
    cursor:pointer
}
.linkbtn{
    background:none;
    color:#00ff88;
    padding:8px;
    font-size:15px;
    text-decoration:underline;
    font-weight:normal
}
.answer{
    background:#333;
    padding:15px;
    border-radius:12px;
    margin:15px 0;
    text-align:left;
    white-space:pre-wrap;
    overflow-wrap:anywhere
}
</style>
</head>

<body>
<div class="box">

{% if not logged %}

<h2>🔒 NEXUS AI - Private</h2>
<p>পাসওয়ার্ড দাও</p>

<form method="post" action="/login">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input
    type="password"
    name="password"
    placeholder="পাসওয়ার্ড..."
    required
>
<br>
<button type="submit">Unlock</button>
</form>

{% if error %}
<p style="color:#ff5555;">{{ error }}</p>
{% endif %}

{% else %}

<h