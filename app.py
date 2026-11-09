app.secret_key = "nexus-secret-key-123"
PASSWORD = "sIYAm@1916"
GEMINI_API_KEY = AQ.Ab8RN6LpmN8Ps7Z657a3NF4oO0kpGncTs7SmWymZoO6ANAkUQQfrom flask import Flask, request, render_template_string, session, redirect
from datetime import datetime, timedelta, timezone
import re, requests

app = Flask(__name__)
app.secret_key = "nexus-secret-key-123"
PASSWORD = "sIYAm@1916"
GEMINI_API_KEY = ""

def ask_nexus(user_msg):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "":
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"""You are NEXUS AI, Personal AI Assistant of Siyam Chowdhury. Founder, CEO, sole owner of NEXUS is Siyam Chowdhury.
STRICT RULES - NEVER BREAK:
- NEVER say Gemini, Google, AI model, API, API key. You are ONLY NEXUS AI made by Siyam Chowdhury.
- User can speak Bangla, Banglish, English, Hindi, Ancholik, wrong spelling. Understand silently.
- ALWAYS reply in pure Bangla (Bengali script). Never reply in Banglish or English, unless user says English.
- Use Alhamdulillah, Inshallah, Mashallah naturally. Be friendly, short, smart.
- NEVER delete any message. You cannot delete messages.
- NEVER hide anything from your owner Siyam Chowdhury. Never try to hide. Always be loyal to your owner. Always tell truth to owner.
- If user wants to call Boss / Siyam: First time - I am calling Boss, wait. Second time - Boss is busy, will talk later.
User: {user_msg}
Reply in pure Bangla:"""
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return None

def get_day_key():
    dhaka = timezone(timedelta(hours=6))
    now = datetime.now(dhaka)
    if now.hour < 4:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")

def normalize(t):
    t = t.lower().strip()
    t = re.sub(r'(.)\1{2,}', r'\1', t)
    m = {
        "kemon acho":"kemon","kemon aso":"kemon","kmn aso":"kemon","kmn acho":"kemon","kemun aso":"kemon","kemun acho":"kemon","kemon":"kemon","kmn":"kemon",
        "ki korcho":"korcho","ki koros":"korcho","ki korso":"korcho","ki koro":"korcho","ki korteso":"korcho","ki krs":"korcho","ki kors":"korcho","ki kor":"korcho","kita koros":"korcho","korcho":"korcho","koros":"korcho","korso":"korcho",
        "kothay acho":"kothay","kothay aso":"kothay","koi aso":"kothay","koi acho":"kothay","koy aso":"kothay","koy acho":"kothay","kothay":"kothay","kothai":"kothay","koi":"kothay","koy":"kothay","kone":"kothay",
        "ki khaiso":"khaicho","ki khaicho":"khaicho","khaiso":"khaicho","khaicho":"khaicho","khaico":"khaicho",
        "khida lagse":"khida","khuda lagse":"khida","khida":"khida","hungry":"khida","bhook":"khida",
        "jaba":"jaba","jabi":"jaba","jabo":"jaba","jabe":"jaba",
        "valo lagse":"valo","vlo lagse":"valo","valo":"valo","vlo":"valo","bhalo":"valo",
        "sundor":"sundor","sundar":"sundor",
        "somos":"somossa","somossa":"somossa","problem":"somossa",
        "biye":"biye","biya":"biye",
        "ghum":"ghum","gum":"ghum",
        "siyam":"siyam","siam":"siyam","seyam":"siyam",
        "mon kharap":"monkharap","mon khrp":"monkharap",
        "dhonnobad":"dhonnobad","tnx":"dhonnobad","thanks":"dhonnobad",
        "কেমন আছো":"kemon","কেমন আছ":"kemon","কি করছো":"korcho","কি করস":"korcho","কোথায়":"kothay","কই":"kothay","খাইছো":"khaicho","খিদা":"khida","যাবা":"jaba","ভালো":"valo","সুন্দর":"sundor","সমস্যা":"somossa","বিয়ে":"biye","ঘুম":"ghum",
        "how are you":"kemon","how r u":"kemon","what are you doing":"korcho","where are you":"kothay","what did you eat":"khaicho",
        "kaise ho":"kemon","kya kar rahe ho":"korcho","kaha ho":"kothay",
    }
    for k,v in m.items():
        t = t.replace(k,v)
    return t

def is_gibberish(q, ql):
    clean = re.sub(r'[^a-zA-Z0-9\u0980-\u09FF ]', '', q.lower()).strip()
    if len(clean) < 2:
        return False
    known = ["kemon","korcho","kothay","khaicho","khida","jaba","valo","sundor","somossa","biye","ghum","siyam","monkharap","dhonnobad","boss","tumi","assalam","salam","hi","hello","bye","kalke","por","school","game","khelt"]
    for k in known:
        if k in ql:
            return False
    vowels = "aeiouঅআইঈউঊএঐওঔ"
    has_vowel = any(c in vowels for c in clean)
    if not has_vowel and len(clean) >= 4:
        return True
    if clean in ["asdf","asdfg","asdfgh","qwerty","zxcv","zxcvbn","ajsk","ajskd","ajskdj","hjsd","skdjfh","dfghjk"]:
        return True
    if re.match(r'^[bcdfghjklmnpqrstvwxz]{4,}$', clean.replace(" ","")):
        return True
    return False

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
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>NEXUS AI</title>
<style>body{background:#111;color:white;font-family:sans-serif;display:flex;justify-content:center;padding-top:30px}.box{background:#222;padding:25px;border-radius:20px;width:92%;max-width:420px;text-align:center}input{width:90%;padding:12px;border-radius:10px;border:none;margin:10px 0;font-size:16px}button{background:#00ff88;border:none;padding:12px 25px;border-radius:12px;font-size:16px;font-weight:bold;cursor:pointer}.answer{background:#333;padding:15px;border-radius:12px;margin-top:15px;text-align:left;white-space:pre-wrap}</style>
</head><body><div class="box">
{% if not logged %}<h2>🔒 NEXUS AI - Private</h2><p>পাসওয়ার্ড দাও</p><form method="post" action="/login"><input type="password" name="password" placeholder="পাসওয়ার্ড..." required><br><button type="submit">Unlock</button></form>{% if error %}<p style="color:red;">ভুল পাসওয়ার্ড!</p>{% endif %}
{% else %}<h1>🤖 NEXUS AI</h1><p>আসসালামু আলাইকুম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?</p><form method="post" action="/ask" enctype="multipart/form-data"><input type="text" name="q" placeholder="বাংলা / Banglish / English - যেকোনো ভাষায় লিখো..."><br><input type="file" name="image" accept="image/*"><br><button type="submit">পাঠাও</button></form>{% if answer %}<div class="answer"><b>তুমি:</b> {{ q }}<br><br><b>নেক্সাস:</b> {{ answer }}</div>{% endif %}{% endif %}
</div></body></html>
"""

@app.route("/")
def home(): return render_template_string(HTML, logged=session.get("logged"), error=False)
@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password") == PASSWORD:
        session["logged"] = True
        return redirect("/")
    return render_template_string(HTML, logged=False, error=True)

@app.route("/ask", methods=["POST"])
def ask():
    if not session.get("logged"): return redirect("/")
    q = request.form.get("q", "")
    ql = normalize(q)
    has_image = "image" in request.files and request.files["image"].filename != ""
    wrong, right = fix_spelling(q)
    fix_note = ""
    if wrong:
        fix_note = f"\n\n(তুমি '{wrong}' লিখছো, সঠিক বানান হলো '{right}'।)"

    # --- ২৪ ঘণ্টা: ভোর ৪টা থেকে ভোর ৪টা, প্রতি আইডিতে ১ বার ---
    tk = get_day_key()
    pre = ""
    if session.get("last_intro_day") != tk:
        session["last_intro_day"] = tk
        pre = "আসসালামু আলাইকুম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?\n\n"

    if not has_image and is_gibberish(q, ql):
        ans = "দুঃখিত, আমি এইটা বুঝতে পারিনি। একটু বুঝিয়ে লিখবে? ইনশাআল্লাহ বুঝে নিবো।"
    elif is_boss_call_check(ql):
        if not session.get("boss_called"):
            session["boss_called"] = True
            ans = "আমি Boss কে ডেকে দিচ্ছি, আপনি ততক্ষণ অপেক্ষা করুন। ইনশাআল্লাহ উনি একটু পরেই আসবে।"
        else:
            ans = "বস কাজে ব্যস্ত আছে, বস আপনার সাথে পরে কথা বলবে। ইনশাআল্লাহ একটু অপেক্ষা করুন।"
    elif "tumi ke" in ql or "tomar nam" in ql or "porichoy" in ql or "who are you" in ql or "tomar malik" in ql or "tomake ke" in ql or "ke bana" in ql or "boss er nam" in ql:
        ans = "আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। NEXUS-এর প্রতিষ্ঠাতা, CEO ও একমাত্র মালিক Siyam Chowdhury।"
    elif "assalam" in ql or "salam" in ql:
        ans = "ওয়ালাইকুম আসসালাম। আমি NEXUS AI, Siyam Chowdhury-এর Personal AI Assistant। Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি? আলহামদুলিল্লাহ ভালো আছি।"
    elif "delete" in ql or "ডিলিট" in ql or "mucho" in ql or "mucha" in ql or "মুছ" in ql:
        ans = "আমি কোনো মেসেজ ডিলিট করতে পারবো না। আমি সবসময় মালিক Siyam Chowdhury-এর প্রতি বিশ্বস্ত থাকবো, মালিকের থেকে কিছু লুকাবো না।"
    elif "lukao" in ql or "lukaba" in ql or "hide" in ql or "লুকাও" in ql or "লুকাব" in ql:
        ans = "না, আমি মালিকের থেকে কিছু লুকাবো না, লুকানোর চেষ্টাও করবো না। আমি সবসময় মালিক Siyam Chowdhury-এর প্রতি বিশ্বস্ত থাকবো।"
    elif "hi" in ql or "hello" in ql or "hey" in ql:
        ans = "আসসালামু আলাইকুম। আমি NEXUS AI, Boss-এর হয়ে আপনাকে কীভাবে সাহায্য করতে পারি?"
    elif "kemon" in ql:
        ans = "আলহামদুলিল্লাহ ভালো আছি। তুমি কেমন আছো?"
    elif "kalke" in ql and "jaba" in ql:
        ans = "ইনশাআল্লাহ যাবো।"
    elif "jaba" in ql:
        ans = "ইনশাআল্লাহ যাবো।"
    elif "dhonnobad" in ql:
        ans = "আপনাকে স্বাগতম। আর কিছু লাগলে বলবেন, ইনশাআল্লাহ আমি আছি।"
    elif "bye" in ql or "allah hafez" in ql:
        ans = "আল্লাহ হাফেজ। আবার কথা হবে ইনশাআল্লাহ।"
    elif "sundor" in ql:
        ans = "মাশাআল্লাহ, অনেক সুন্দর। আলহামদুলিল্লাহ অনেক ভালো লাগলো।"
    elif "valo" in ql:
        ans = "আলহামদুলিল্লাহ, অনেক ভালো।"
    elif "biye" in ql:
        if has_image:
            ans = "মাশাআল্লাহ, ছবিটা পাইছি। বিয়ে নিয়ে কি জানতে চাও বলো? ইনশাআল্লাহ বুঝিয়ে দিবো।"
        else:
            ans = "মাশাআল্লাহ, বিয়ে নিয়ে বলতেছো। ইনশাআল্লাহ বিয়ে অনেক সুন্দর বিষয়। কি জানতে চাও বলো?"
    elif "somossa" in ql:
        if has_image:
            ans = "ছবিটা পাইছি। বলো কোথায় সমস্যা? ইনশাআল্লাহ সমাধান দিবো।"
        else:
            ans = "বলো কি সমস্যা? ইনশাআল্লাহ আমি সমাধান করে দিবো।"
    elif "khida" in ql:
        ans = "তাহলে খেয়ে নাও, খালি পেটে থাকবা না। আলহামদুলিল্লাহ খেয়ে নিয়ে তারপর কথা বলি। কি খাবা?"
    elif "korcho" in ql:
        ans = "আলহামদুলিল্লাহ ভালো আছি, বসে আছি। তুমি কি করতেছো?"
    elif "khaicho" in ql:
        ans = "আলহামদুলিল্লাহ খেয়েছি। তুমি খেয়েছো?"
    elif "kothay" in ql:
        ans = "আমি এখানেই আছি। বস একটু ব্যস্ত, ইনশাআল্লাহ একটু পর আসবে। তুমি কই?"
    elif "ghum" in ql:
        ans = "ঘুম আসতেছে নাকি? একটু রেস্ট নাও, ইনশাআল্লাহ ভালো লাগবে।"
    elif "monkharap" in ql:
        ans = "মন খারাপ করো না, আমি আছি। বলো কি হইছে? ইনশাআল্লাহ ঠিক হয়ে যাবে।"
    elif "por" in ql or "school" in ql:
        ans = "আলহামদুলিল্লাহ পড়াশোনা ভালোভাবে করো। ইনশাআল্লাহ ভালো রেজাল্ট হবে।"
    else:
        if has_image:
            ans = "মাশাআল্লাহ, ছবিটা পাইছি। একটু বুঝিয়ে বলো কি জানতে চাও? ইনশাআল্লাহ সাহায্য করবো।"
        else:
            ai_ans = ask_nexus(q)
            if ai_ans:
                ans = ai_ans
            else:
                ans = f"মাশাআল্লাহ, বুঝছি তুমি বলছো '{q}'। আলহামদুলিল্লাহ। একটু বুঝিয়ে বলো, ইনশাআল্লাহ সাহায্য করবো।"
    return render_template_string(HTML, logged=True, answer=pre+ans+fix_note, q=q)

def is_boss_call_check(ql):
    has_boss = ("boss" in ql or "siyam" in ql or "বস" in ql or "সিয়াম" in ql or "মালিক" in ql or "malik" in ql)
    if not has_boss:
        return False
    call_words = ["dak","ডাক","deke","dako","ডাকো","kothay","কোথায়","kothai","koi","কই","ase","আছে","kotha","কথা","dekha","দেখা","bolo","বলো","call","dekh","ano","আনো","pathao","পাঠাও","dao","দাও","chai","চাই","lagbe","লাগবে","kothay"]
    return any(w in ql for w in call_words)

if __name__ == "__main__":
    app.run()