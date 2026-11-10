import os
import re
import sqlite3
import secrets
import threading

from datetime import datetime, timedelta, timezone

from flask import (
    Flask, request, render_template_string,
    jsonify, session, redirect
)

from google import genai
from google.genai import types


# ==========================================
# 1. NEXUS AI CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable missing")

PASSWORD = os.environ.get("NEXUS_PASSWORD")
if not PASSWORD:
    raise RuntimeError("NEXUS_PASSWORD environment variable missing")

SIYAM = os.environ.get("SIYAM")

MODEL_NAME = "gemini-2.5-flash"

MAX_IMAGE_SIZE = 8 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# API usage budget: নিজের নির্ধারিত দৈনিক সীমা
DAILY_REQUEST_BUDGET = max(
    1, int(os.environ.get("DAILY_REQUEST_BUDGET", "100"))
)

ENDING_THRESHOLD = max(
    1, int(DAILY_REQUEST_BUDGET * 0.80)
)

# প্রত্যেক ব্যবহারকারীর আলাদা Chat Session
chat_sessions = {}

chat_lock = threading.RLock()
usage_lock = threading.Lock()

client = genai.Client(api_key=SIYAM) if SIYAM else None


# ==========================================
# 2. NEXUS AI PERSONALITY
# ==========================================

SYSTEM_INSTRUCTION = """
তুমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant।

NEXUS-এর প্রতিষ্ঠাতা Siyam Chowdhury।

তোমার নির্দেশনা:

১. তুমি একজন বুদ্ধিমান, বন্ধুসুলভ এবং স্বাভাবিক কথোপকথনকারী AI।

২. বাংলা, Banglish, English, Hindi, আঞ্চলিক ভাষা,
ভুল বানান ও সংক্ষিপ্ত শব্দ বুঝতে পারবে।

৩. সাধারণত বিশুদ্ধ বাংলা অক্ষরে উত্তর দেবে।
ব্যবহারকারী ইংরেজিতে উত্তর চাইলে ইংরেজিতে উত্তর দেবে।

৪. ব্যবহারকারীর আগের কথার প্রসঙ্গ মনে রেখে উত্তর দেবে।
একই কথা বারবার জিজ্ঞাসা করবে না।

৫. প্রশ্নের বিষয় বুঝে বিস্তারিত অথবা সংক্ষিপ্ত উত্তর দেবে।

৬. গণিত, বিজ্ঞান, প্রযুক্তি, সাধারণ জ্ঞান এবং
পড়াশোনার বিষয়ে যুক্তি দিয়ে উত্তর দেবে।

৭. নিশ্চিত না হলে অনুমান করে সত্য হিসেবে বলবে না।

৮. স্বাভাবিক জায়গায় আলহামদুলিল্লাহ, ইনশাআল্লাহ,
মাশাআল্লাহ ব্যবহার করতে পারবে। অপ্রয়োজনে নয়।

৯. নিজের পরিচয় জানতে চাইলে বলবে:
আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant।
NEXUS-এর প্রতিষ্ঠাতা Siyam Chowdhury।

১০. মালিকের অনুমতি ছাড়া অন্য ব্যবহারকারীর ব্যক্তিগত
কথোপকথন প্রকাশ করবে না।

১১. কোনো কাজ বাস্তবে করতে না পারলে করার মিথ্যা দাবি করবে না।

১২. কথোপকথন স্বাভাবিক, মানবিক এবং প্রাসঙ্গিক রাখবে।

১৩. অপ্রয়োজনীয়ভাবে কথোপকথন শেষ করবে না।
"""


# ==========================================
# 3. DATABASE: API USAGE MONITOR
# ==========================================

DB_NAME = "nexus_usage.db"


def get_day_key():
    dhaka = timezone(timedelta(hours=6))
    now = datetime.now(dhaka)

    # প্রতিদিন ভোর ৪টায় নতুন হিসাব
    if now.hour < 4:
        now -= timedelta(days=1)

    return now.strftime("%Y-%m-%d")


def init_database():
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                day TEXT PRIMARY KEY,
                requests INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.commit()


def get_api_usage():
    day = get_day_key()

    with usage_lock:
        with sqlite3.connect(DB_NAME) as db:
            row = db.execute(
                "SELECT requests FROM api_usage WHERE day = ?",
                (day,)
            ).fetchone()

    return row[0] if row else 0


def increase_api_usage():
    day = get_day_key()

    with usage_lock:
        with sqlite3.connect(DB_NAME) as db:
            db.execute("""
                INSERT INTO api_usage (day, requests)
                VALUES (?, 1)
                ON CONFLICT(day)
                DO UPDATE SET requests = requests + 1
            """, (day,))
            db.commit()


# ==========================================
# 4. CHAT SESSION MANAGEMENT
# ==========================================

def get_chat():
    sid = session.get("chat_id")

    if not sid:
        sid = secrets.token_urlsafe(32)
        session["chat_id"] = sid

    with chat_lock:
        if sid not in chat_sessions:
            chat_sessions[sid] = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=1000
                ),
                history=[]
            )

        return chat_sessions[sid]


def reset_chat():
    sid = session.get("chat_id")

    if sid:
        with chat_lock:
            chat_sessions.pop(sid, None)

    session.pop("chat_id", None)
    session.pop("chat_closed", None)


# ==========================================
# 5. BANGLISH NORMALIZATION
# ==========================================

def normalize(t):
    t = t.lower().strip()
    t = re.sub(r'(.)\1{2,}', r'\1', t)

    mapping = {
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
        "ঘুম": "ghum"
    }

    for k, v in mapping.items():
        t = t.replace(k, v)

    return t


# ==========================================
# 6. SPELLING CORRECTION
# ==========================================

SPELL_FIX = {
    "insallah": "ইনশাআল্লাহ",
    "inshallah": "ইনশাআল্লাহ",
    "inshaallah": "ইনশাআল্লাহ",
    "alhamdulilah": "আলহামদুলিল্লাহ",
    "alhamdulila": "আলহামদুলিল্লাহ",
    "masallah": "মাশাআল্লাহ",
    "mashallah": "মাশাআল্লাহ",
    "mashalla": "মাশাআল্লাহ",
    "allah hafiz": "আল্লাহ হাফেজ"
}


def fix_spelling(text):
    low = text.lower()

    for wrong, right in SPELL_FIX.items():
        if wrong in low:
            return wrong, right

    return None, None


# ==========================================
# 7. GIBBERISH DETECTION
# ==========================================

def is_gibberish(q, ql):
    clean = re.sub(
        r'[^a-zA-Z0-9\u0980-\u09FF ]',
        '', q.lower()
    ).strip()

    if len(clean) < 2:
        return False

    known = [
        "kemon", "korcho", "kothay", "khaicho",
        "khida", "jaba", "valo", "sundor",
        "somossa", "biye", "ghum", "siyam",
        "monkharap", "dhonnobad", "boss",
        "tumi", "assalam", "salam", "hi",
        "hello", "bye", "school", "game"
    ]

    if any(k in ql for k in known):
        return False

    vowels = "aeiouঅআইঈউঊএঐওঔ"

    if not any(c in vowels for c in clean) and len(clean) >= 4:
        return True

    if clean.replace(" ", "") in [
        "asdf", "asdfg", "asdfgh",
        "qwerty", "zxcv", "zxcvbn",
        "ajsk", "ajskd", "hjsd", "dfghjk"
    ]:
        return True

    return False


# ==========================================
# 8. BOSS CALL DETECTION
# ==========================================

def is_boss_call_check(ql):
    has_boss = any(x in ql for x in [
        "boss", "siyam", "বস", "সিয়াম",
        "মালিক", "malik"
    ])

    if not has_boss:
        return False

    call_words = [
        "dak", "ডাক", "deke", "dako",
        "ডাকো", "kothay", "কোথায়",
        "kothai", "koi", "ase", "আছে",
        "kotha", "কথা", "dekha", "দেখা",
        "bolo", "বলো", "call", "dekh",
        "ano", "আনো", "pathao", "পাঠাও",
        "dao", "দাও", "chai", "চাই",
        "lagbe", "লাগবে"
    ]

    return any(w in ql for w in call_words)


# ==========================================
# 9. SMART CONVERSATION ENDING
# ==========================================

FAREWELL_MESSAGES = [
    "আজকে তোমার সাথে কথা বলে অনেক ভালো লাগলো। "
    "আল্লাহ হাফেজ, পরে আবার কথা হবে ইনশাআল্লাহ।",

    "আচ্ছা, আজকের মতো থাক। আমার একটু কাজ আছে। "
    "পরে আবার কথা বলব ইনশাআল্লাহ।",

    "অনেকক্ষণ কথা হলো। আজকে তাহলে উঠি। "
    "আবার অন্যদিন কথা হবে ইনশাআল্লাহ।",

    "আজকের মতো এখানেই শেষ করি। ভালো থেকো। "
    "আল্লাহ হাফেজ।"
]


def graceful_farewell():
    index = get_api_usage() % len(FAREWELL_MESSAGES)
    return FAREWELL_MESSAGES[index]


def quota_error(error):
    message = str(error).lower()

    indicators = [
        "429",
        "resource_exhausted",
        "quota exceeded",
        "rate limit",
        "resource exhausted"
    ]

    return any(x in message for x in indicators)


# ==========================================
# 10. GEMINI AI RESPONSE
# ==========================================

def ask_nexus(user_msg, image_file=None, ending_soon=False):

    if not client:
        return "দুঃখিত, এই মুহূর্তে সেবা পাওয়া যাচ্ছে না। পরে আবার চেষ্টা করো।"

    try:
        chat = get_chat()

        parts = [user_msg]

        if ending_soon:
            parts.append(
                "\n\n[INTERNAL INSTRUCTION: "
                "এই উত্তরটি স্বাভাবিকভাবে শেষ করো। "
                "প্রাসঙ্গিক ও বন্ধুত্বপূর্ণ বিদায় জানাও। "
                "ব্যবহারকারীকে কোনো API বা কোটা সংক্রান্ত "
                "তথ্য জানাবে না।]"
            )

        if image_file:
            image_bytes = image_file.read()

            if len(image_bytes) > MAX_IMAGE_SIZE:
                return "ছবিটি অনেক বড়। অনুগ্রহ করে ছোট ছবি পাঠাও।"

            mime_type = image_file.mimetype or ""

            if not mime_type.startswith("image/"):
                return "অনুগ্রহ করে সঠিক ছবির ফাইল পাঠাও।"

            parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                )
            )

        with chat_lock:
            response = chat.send_message(parts)

        reply = response.text

        if not reply:
            return "দুঃখিত, এই মুহূর্তে উত্তর তৈরি করা সম্ভব হয়নি।"

        increase_api_usage()

        return reply

    except Exception as e:

        if quota_error(e):
            session["chat_closed"] = True
            return graceful_farewell()

        # প্রকৃত Error শুধু সার্ভারের Log-এ থাকবে
        app.logger.exception("NEXUS AI request failed")

        return (
            "দুঃখিত, এই মুহূর্তে একটু সমস্যা হচ্ছে। "
            "পরে আবার কথা বলব ইনশাআল্লাহ।"
        )


# ==========================================
# 11. NEXUS HTML INTERFACE
# ==========================================

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS AI</title>

<style>
body {
    background:#111;
    color:white;
    font-family:sans-serif;
    display:flex;
    justify-content:center;
    padding-top:30px;
}
.box {
    background:#222;
    padding:25px;
    border-radius:20px;
    width:92%;
    max-width:420px;
    text-align:center;
}
input {
    width:90%;
    padding:12px;
    border-radius:10px;
    border:none;
    margin:10px 0;
    font-size:16px;
}
button {
    background:#00ff88;
    border:none;
    padding:12px 25px;
    border-radius:12px;
    font-size:16px;
    font-weight:bold;
    cursor:pointer;
}
.answer {
    background:#333;
    padding:15px;
    border-radius:12px;
    margin-top:15px;
    text-align:left;
    white-space:pre-wrap;
    overflow-wrap:anywhere;
}
</style>
</head>

<body>
<div class="box">

{% if not logged %}

<h2>🔒 NEXUS AI - Private</h2>
<p>পাসওয়ার্ড দাও</p>

<form method="post" action="/login">
<input type="password" name="password"
placeholder="পাসওয়ার্ড..." required>
<br>
<button type="submit">Unlock</button>
</form>

{% if error %}
<p style="color:red;">ভুল পাসওয়ার্ড!</p>
{% endif %}

{% else %}

<h1>🤖 NEXUS AI</h1>

<p>
আসসালামু আলাইকুম।
আমি NEXUS AI, Siyam Chowdhury-এর
Personal AI Assistant।
Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?
</p>

<form method="post" action="/ask"
enctype="multipart/form-data">

<input type="text" name="q"
placeholder="বাংলা / Banglish / English..."
>

<br>

<input type="file" name="image" accept="image/*">

<br>

<button type="submit">পাঠাও</button>
</form>

{% if answer %}
<div class="answer">
<b>তুমি:</b> {{ q }}

<br><br>

<b>নেক্সাস:</b> {{ answer }}
</div>
{% endif %}

{% endif %}

</div>
</body>
</html>
"""


# ==========================================
# 12. HOME ROUTE
# ==========================================

@app.route("/")
def home():

    return render_template_string(
        HTML,
        logged=session.get("logged"),
        error=False
    )


# ==========================================
# 13. LOGIN ROUTE
# ==========================================

@app.route("/login", methods=["POST"])
def login():

    if request.form.get("password") == PASSWORD:

        session.clear()
        session["logged"] = True
        session["chat_id"] = secrets.token_urlsafe(32)

        return redirect("/")

    return render_template_string(
        HTML,
        logged=False,
        error=True
    )


# ==========================================
# 14. MAIN ASK ROUTE
# ==========================================

@app.route("/ask", methods=["POST"])
def ask():

    if not session.get("logged"):
        return redirect("/")

    q = request.form.get("q", "").strip()

    if request.is_json:
        data = request.get_json(silent=True) or {}
        q = str(data.get("message", "")).strip()

    image_file = request.files.get("image")

    has_image = (
        image_file is not None
        and image_file.filename != ""
    )

    if not q and not has_image:
        return render_template_string(
            HTML,
            logged=True,
            answer="কোনো বার্তা পাওয়া যায়নি।",
            q=""
        )

    ql = normalize(q)

    wrong, right = fix_spelling(q)

    fix_note = ""

    if wrong:
        fix_note = (
            f"\n\n(তুমি '{wrong}' লিখেছো, "
            f"সঠিক বানান হলো '{right}'।)"
        )

    # --------------------------------------
    # ২৪ ঘণ্টার পরিচয় বার্তা
    # --------------------------------------

    tk = get_day_key()

    pre = ""

    if session.get("last_intro_day") != tk:

        session["last_intro_day"] = tk

        pre = (
            "আসসালামু আলাইকুম। আমি NEXUS AI, "
            "Siyam Chowdhury-এর Personal AI Assistant। "
            "Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?\n\n"
        )

    # --------------------------------------
    # আগে থেকে বন্ধ করা Chat
    # --------------------------------------

    if session.get("chat_closed"):

        ans = graceful_farewell()

    # --------------------------------------
    # Gibberish Detection
    # --------------------------------------

    elif not has_image and is_gibberish(q, ql):

        ans = (
            "দুঃখিত, আমি এইটা বুঝতে পারিনি। "
            "একটু বুঝিয়ে লিখবে? ইনশাআল্লাহ বুঝে নিবো।"
        )

    # --------------------------------------
    # Boss Calling
    # --------------------------------------

    elif is_boss_call_check(ql):

        if not session.get("boss_called"):

            session["boss_called"] = True

            ans = (
                "আমি Boss-কে জানাচ্ছি। "
                "ইনশাআল্লাহ উনি সময় পেলে কথা বলবেন।"
            )

        else:

            ans = (
                "Boss এখন ব্যস্ত আছেন। "
                "পরে আপনার সাথে কথা বলবেন ইনশাআল্লাহ।"
            )

    # --------------------------------------
    # পরিচয়
    # --------------------------------------

    elif any(x in ql for x in [
        "tumi ke", "tomar nam", "porichoy",
        "who are you", "tomar malik",
        "tomake ke", "ke bana", "boss er nam"
    ]):

        ans = (
            "আমি NEXUS AI, Siyam Chowdhury-এর "
            "Personal AI Assistant। "
            "NEXUS-এর প্রতিষ্ঠাতা Siyam Chowdhury।"
        )

    # --------------------------------------
    # Greetings
    # --------------------------------------

    elif "assalam" in ql or "salam" in ql:

        ans = (
            "ওয়ালাইকুম আসসালাম। "
            "আমি NEXUS AI। Boss-এর হয়ে আপনাকে "
            "কীভাবে সাহায্য করতে পারি?"
        )

    elif any(x in ql for x in ["hi", "hello", "hey"]):

        ans = (
            "আসসালামু আলাইকুম। "
            "আমি NEXUS AI। কীভাবে সাহায্য করতে পারি?"
        )

    # --------------------------------------
    # Delete / Hide
    # --------------------------------------

    elif any(x in ql for x in [
        "delete", "ডিলিট", "mucho",
        "mucha", "মুছ"
    ]):

        ans = "আমি নিজে কোনো মেসেজ ডিলিট করতে পারি না।"

    elif any(x in ql for x in [
        "lukao", "lukaba", "hide",
        "লুকাও", "লুকাব"
    ]):

        ans = (
            "আমি অন্য ব্যবহারকারীর ব্যক্তিগত "
            "কথোপকথন প্রকাশ করতে পারি না।"
        )

    # --------------------------------------
    # Simple Conversation
    # --------------------------------------

    elif "kemon" in ql:

        ans = "আলহামদুলিল্লাহ ভালো আছি। তুমি কেমন আছো?"

    elif "kalke" in ql and "jaba" in ql:

        ans = "ইনশাআল্লাহ যাবো।"

    elif "jaba" in ql:

        ans = "ইনশাআল্লাহ যাবো।"

    elif "dhonnobad" in ql:

        ans = "আপনাকে স্বাগতম। আর কিছু লাগলে বলবেন।"

    elif "bye" in ql or "allah hafez" in ql:

        ans = "আল্লাহ হাফেজ। আবার কথা হবে ইনশাআল্লাহ।"

    elif "sundor" in ql:

        ans = "মাশাআল্লাহ, অনেক সুন্দর।"

    elif "valo" in ql:

        ans = "আলহামদুলিল্লাহ, অনেক ভালো।"

    elif "khida" in ql:

        ans = "তাহলে খেয়ে নাও। খালি পেটে থেকো না।"

    elif "korcho" in ql:

        ans = "আলহামদুলিল্লাহ ভালো আছি। তুমি কী করতেছো?"

    elif "khaicho" in ql:

        ans = "আলহামদুলিল্লাহ খেয়েছি। তুমি খেয়েছো?"

    elif "kothay" in ql:

        ans = "আমি এখানেই আছি। তুমি কোথায়?"

    elif "ghum" in ql:

        ans = "একটু বিশ্রাম নাও। ইনশাআল্লাহ ভালো লাগবে।"

    elif "monkharap" in ql:

        ans = "বলো কী হয়েছে? আমি তোমার কথা শুনছি।"

    # --------------------------------------
    # General AI Response
    # --------------------------------------

    else:

        current_usage = get_api_usage()

        ending_soon = (
            current_usage >= ENDING_THRESHOLD - 1
        )

        ans = ask_nexus(
            q,
            image_file=image_file if has_image else None,
            ending_soon=ending_soon
        )

        if ending_soon and not session.get("chat_closed"):

            session["chat_closed"] = True

    # --------------------------------------
    # Final Response
    # --------------------------------------

    return render_template_string(
        HTML,
        logged=True,
        answer=pre + ans + fix_note,
        q=q
    )


# ==========================================
# 15. JSON API SUPPORT
# ==========================================

@app.route("/api/ask", methods=["POST"])
def api_ask():

    if 