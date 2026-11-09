from flask import Flask, request, render_template_string, session, redirect
import time
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "nexus-secret-key-123"
PASSWORD = "sIYAm@1916"

def get_day_key():
    dhaka = timezone(timedelta(hours=6))
    now = datetime.now(dhaka)
    if now.hour < 4:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")

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

def fix_spelling(text):
    low = text.lower()
    for wrong, right in SPELL_FIX.items():
        if wrong in low:
            return wrong, right
    return None, None

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS AI</title>
<style>
body { background: #111; color: white; font-family: sans-serif; display: flex; justify-content: center; padding-top: 30px; }
.box { background: #222; padding: 25px; border-radius: 20px; width: 92%; max-width: 420px; text-align: center; }
input { width: 90%; padding: 12px; border-radius: 10px; border: none; margin: 10px 0; font-size: 16px; }
button { background: #00ff88; border: none; padding: 12px 25px; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; }
.answer { background: #333; padding: 15px; border-radius: 12px; margin-top: 15px; text-align: left; white-space: pre-wrap; }
img { max-width: 100%; border-radius: 12px; margin-top: 10px; }
</style>
</head>
<body>
<div class="box">
{% if not logged %}
<h2>🔒 NEXUS AI - Private</h2>
<p>Password দাও</p>
<form method="post" action="/login">
<input type="password" name="password" placeholder="Password..." required>
<br><button type="submit">Unlock</button>
</form>
{% if error %}<p style="color:red;">ভুল পাসওয়ার্ড!</p>{% endif %}
{% else %}
<h1>🤖 NEXUS AI</h1>
<p>আসসালামু আলাইকুম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?</p>
<form method="post" action="/ask" enctype="multipart/form-data">
<input type="text" name="q" placeholder="লিখো + চাইলে ছবি দাও...">
<br><input type="file" name="image" accept="image/*">
<br><button type="submit">Send</button>
</form>
{% if answer %}<div class="answer"><b>You:</b> {{ q }}<br><br><b>NEXUS:</b> {{ answer }}</div>{% endif %}
{% endif %}
</div>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML, logged=session.get("logged"), error=False)

@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password") == PASSWORD:
        session["logged"] = True
        return redirect("/")
    return render_template_string(HTML, logged=False, error=True)

@app.route("/ask", methods=["POST"])
def ask():
    if not session.get("logged"):
        return redirect("/")
    q = request.form.get("q", "")
    ql = q.lower()
    has_image = "image" in request.files and request.files["image"].filename != ""

    wrong, right = fix_spelling(q)
    fix_note = ""
    if wrong:
        fix_note = f"\n\n(তুমি '{wrong}' লিখছো, সঠিক বানান হলো '{right}'।)"

    today_key = get_day_key()
    daily_prefix = ""
    if session.get("last_intro_day") != today_key:
        session["last_intro_day"] = today_key
        daily_prefix = "আসসালামু আলাইকুম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?\n\n"

    # --- ছবি + লেখা ---
    if has_image:
        if "biye" in ql or "bibaho" in ql or "biya" in ql or "marriage" in ql:
            ans = "মাশাআল্লাহ, ছবিটা পাইছি। বিয়ে নিয়ে তুমি কি জানতে চাও বলো? ইনশাআল্লাহ আমি বুঝিয়ে দিবো। বিয়ে হলো অনেক সুন্দর একটা বিষয়, আলহামদুলিল্লাহ। তুমি একটু বুঝিয়ে লিখো, কিসের ব্যাপারে জানতে চাও?"
        elif "somos" in ql or "somossa" in ql or "problem" in ql or "nosto" in ql or "vanga" in ql or "ki hoise" in ql or "kharap" in ql:
            ans = "ছবিটা পাইছি, আলহামদুলিল্লাহ। তুমি একটু বুঝিয়ে বলো ছবিতে ঠিক কোথায় সমস্যা? ইনশাআল্লাহ আমি সমাধান বলে দিবো।"
        elif "ki" in ql or "dekho" in ql or "eta" in ql or q.strip() == "":
            ans = "ছবিটা পাইছি, মাশাআল্লাহ। একটু বুঝিয়ে বলো, এটা নিয়ে কি জানতে চাও? ইনশাআল্লাহ আমি সাহায্য করবো।"
        else:
            ans = "ছবিটা পাইছি। " + q + " - এই ব্যাপারে একটু বুঝিয়ে বলো, ইনশাআল্লাহ সমাধান দিবো।"
    elif ("boss" in ql and ("kothay" in ql or "kothai" in ql or "where" in ql or "koy" in ql or "dak" in ql or "dako" in ql or "ase nai" in ql or "asen nai" in ql or "ashe nai" in ql or "aschen" in ql)):
        if not session.get("boss_called"):
            session["boss_called"] = True
            ans = "আমি Boss কে ডেকে দিচ্ছি, উনি আসা পর্যন্ত আপনি অপেক্ষা করুন। ইনশাআল্লাহ উনি একটু পরেই আসবে।"
        else:
            ans = "সে কাজে ব্যস্ত, সে একটু পরে আপনার সাথে কথা বলবে বলেছে। ইনশাআল্লাহ একটু অপেক্ষা করেন।"
    elif "tumi ke" in ql or "who are you" in ql or "tomar nam" in ql or "your name" in ql or "porichoy" in ql:
        ans = "আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। NEXUS প্রজেক্টের প্রতিষ্ঠাতা, CEO ও একমাত্র মালিক Siyam Chowdhury। আলহামদুলিল্লাহ আমি Boss এর হয়েই কাজ করি।"
    elif "assalam" in ql or "salam" in ql:
        ans = "ওয়ালাইকুম আসসালাম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি? আলহামদুলিল্লাহ ভালো আছি।"
    elif "hi" in ql or "hello" in ql or "hey" in ql:
        ans = "আসসালামু আলাইকুম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?"
    elif "kemon" in ql or "how are you" in ql:
        ans = "আলহামদুলিল্লাহ ভালো আছি। তুমি কেমন আছো?"
    elif "kalke" in ql and ("jaba" in ql or "jabe" in ql or "asba" in ql or "asbe" in ql or "korba" in ql or "jabi" in ql):
        ans = "ইনশাআল্লাহ যাবো।"
    elif "jaba" in ql or "jabe" in ql or "asba" in ql:
        ans = "ইনশাআল্লাহ যাবো।"
    elif "biye" in ql or "bibaho" in ql or "biya" in ql:
        ans = "মাশাআল্লাহ, বিয়ে নিয়ে বলতেছো। ইনশাআল্লাহ বিয়ে অনেক সুন্দর বিষয়। তুমি কি জানতে চাও, একটু বুঝিয়ে বলো?"
    elif "somos" in ql or "somossa" in ql or "problem" in ql:
        ans = "বলো কি সমস্যা? ইনশাআল্লাহ আমি সমাধান করে দিবো। একটু বুঝিয়ে লিখো।"
    elif "dhonnobad" in ql or "thank" in ql:
        ans = "আপনাকে স্বাগতম। আর কিছু লাগলে বলবেন, ইনশাআল্লাহ আমি আছি।"
    elif "bye" in ql or "allah hafez" in ql:
        ans = "আল্লাহ হাফেজ। আবার কথা হবে ইনশাআল্লাহ।"
    elif "sundor" in ql or "sundar" in ql or "valo lagse" in ql or "beautiful" in ql or "nice" in ql or "dekh" in ql:
        ans = "মাশাআল্লাহ, অনেক সুন্দর। আলহামদুলিল্লাহ অনেক ভালো লাগলো।"
    elif "mashallah" in ql or "masallah" in ql or "mashalla" in ql:
        ans = "মাশাআল্লাহ, অনেক সুন্দর বলছেন।"
    elif "valo" in ql or "valo hoise" in ql or "khub valo" in ql or "great" in ql:
        ans = "আলহামদুলিল্লাহ, অনেক ভালো।"
    else:
        ans = "দুঃখিত, আমি আপনার কথাটি ঠিক বুঝতে পারিনি। একটু বুঝিয়ে বলবেন? ইনশাআল্লাহ বুঝে নিবো।"

    ans = daily_prefix + ans + fix_note
    return render_template_string(HTML, logged=True, answer=ans, q=q)

if __name__ == "__main__":
    app.run()