from flask import Flask, request, render_template_string, session, redirect
from datetime import datetime, timedelta, timezone
import re

app = Flask(__name__)
app.secret_key = "nexus-secret-key-123"
PASSWORD = "sIYAm@1916"

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
        # BANGLISH - MAIN
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
        # BANGLA
        "কেমন আছো":"kemon","কেমন আছ":"kemon","কি করছো":"korcho","কি করস":"korcho","কোথায়":"kothay","কই":"kothay","খাইছো":"khaicho","খিদা":"khida","যাবা":"jaba","ভালো":"valo","সুন্দর":"sundor","সমস্যা":"somossa","বিয়ে":"biye","ঘুম":"ghum",
        # ENGLISH
        "how are you":"kemon","how r u":"kemon","what are you doing":"korcho","where are you":"kothay","what did you eat":"khaicho",
        # HINDI
        "kaise ho":"kemon","kya kar rahe ho":"korcho","kaha ho":"kothay",
    }
    for k,v in m.items():
        t = t.replace(k,v)
    return t

def is_gibberish(q, ql):
    # শুধু অর্থহীন বানান হলেই True - যেমন asdfgh, qwerty, zxcv
    clean = re.sub(r'[^a-zA-Z0-9\u0980-\u09FF ]', '', q.lower()).strip()
    if len(clean) < 2:
        return False
    known = ["kemon","korcho","kothay","khaicho","khida","jaba","valo","sundor","somossa","biye","ghum","siyam","monkharap","dhonnobad","boss","tumi","assalam","salam","hi","hello","bye","kalke","por","school","game","khelt"]
    for k in known:
        if k in ql:
            return False
    # স্বরবর্ণ নাই + এলোমেলো = অর্থহীন
    vowels = "aeiouঅআইঈউঊএঐওঔ"
    has_vowel = any(c in vowels for c in clean)
    if not has_vowel and len(clean) >= 4:
        return True
    if clean in ["asdf","asdfg","asdfgh","qwerty","zxcv","zxcvbn","ajsk","ajskd","ajskdj","hjsd","skdjfh","dfghjk"]:
        return True
    # একই ধরনের এলোমেলো অক্ষর
    if re.match(r'^[bcdfghjklmnpqrstvwxz]{4,}$', clean.replace(" ","")):
        return True
    return False

HTML = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>NEXUS AI</title>
<style>body{background:#111;color:white;font-family:sans-serif;display:flex;justify-content:center;padding-top:30px}.box{background:#222;padding:25px;border-radius:20px;width:92%;max-width:420px;text-align:center}input{width:90%;padding:12px;border-radius:10px;border:none;margin:10px 0;font-size:16px}button{background:#00ff88;border:none;padding:12px 25px;border-radius:12px;font-size:16px;font-weight:bold;cursor:pointer}.answer{background:#333;padding:15px;border-radius:12px;margin-top:15px;text-align:left;white-space:pre-wrap}</style>
</head><body><div class="box">
{% if not logged %}<h2>🔒 NEXUS AI - Private</h2><p>Password dao</p><form method="post" action="/login"><input type="password" name="password" placeholder="Password..." required><br><button type="submit">Unlock</button></form>{% if error %}<p style="color:red;">Vul password!</p>{% endif %}
{% else %}<h1>🤖 NEXUS AI</h1><p>Assalamu Alaikum. Ami NEXUS AI, Siyam Chowdhury-er Personal AI Assistant. Boss-er hoye tomake kivabe sahajjo korte pari?</p><form method="post" action="/ask" enctype="multipart/form-data"><input type="text" name="q" placeholder="Banglish / Bangla / English - jekono vashay likho..."><br><input type="file" name="image" accept="image/*"><br><button type="submit">Send</button></form>{% if answer %}<div class="answer"><b>You:</b> {{ q }}<br><br><b>NEXUS:</b> {{ answer }}</div>{% endif %}{% endif %}
</div></body></html>
"""

@app.route("/")
def home(): return render_template_string(HTML, logged=session.get("logged"), error=False)
@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password")==PASSWORD:
        session["logged"]=True; return redirect("/")
    return render_template_string(HTML, logged=False, error=True)

@app.route("/ask", methods=["POST"])
def ask():
    if not session.get("logged"): return redirect("/")
    q=request.form.get("q",""); ql=normalize(q)
    has_image="image" in request.files and request.files["image"].filename!=""
    tk=get_day_key(); pre=""
    if session.get("last_intro_day")!=tk:
        session["last_intro_day"]=tk; pre="Assalamu Alaikum. Ami NEXUS AI, Siyam Chowdhury-er Personal AI Assistant. Boss-er hoye tomake kivabe sahajjo korte pari?\n\n"

    # --- শুধু অর্থহীন হলেই বুঝতে পারিনি বলবে ---
    if not has_image and is_gibberish(q, ql):
        ans = "Dukkhito, ami eita bujhte parini. Ektu bujhiye likhbe? Inshallah bujhe nibo."
    elif has_image:
        if "biye" in ql: ans="Mashallah, chobita paichi. Biye niye ki jante chao bolo? Inshallah bujhiye dibo."
        elif "somossa" in ql: ans="Chobita paichi. Bolo kothay somossa? Inshallah somadhan dibo."
        else: ans="Mashallah, chobita paichi. Ektu bujhiye bolo ki jante chao? Inshallah sahajjo korbo."
    elif "boss" in ql and ("kothay" in ql or "dak" in ql or "ase" in ql):
        if not session.get("boss_called"): session["boss_called"]=True; ans="Ami Boss ke deke dicchi, uni asa porjonto opekha koro. Inshallah uni ektu porei asbe."
        else: ans="Se kaje besto, ektu pore tomar sathe kotha bolbe boleche. Inshallah ektu opekha koro."
    elif "tumi ke" in ql or "tomar nam" in ql or "porichoy" in ql: ans="Ami NEXUS AI, Siyam Chowdhury-er Personal AI Assistant. NEXUS-er protisthata, CEO o ekmatro malik Siyam Chowdhury. Alhamdulillah ami Boss er hoyei kaj kori."
    elif "assalam" in ql or "salam" in ql: ans="Walaikum Assalam. Alhamdulillah valo achi. Tumi kemon acho?"
    elif "hi" in ql or "hello" in ql or "hey" in ql: ans="Assalamu Alaikum. Ami NEXUS AI, Boss-er hoye tomake kivabe sahajjo korte pari?"
    elif "kemon" in ql: ans="Alhamdulillah valo achi. Tumi kemon acho?"
    elif "kalke" in ql and "jaba" in ql: ans="Inshallah jabo."
    elif "jaba" in ql: ans="Inshallah jabo."
    elif "biye" in ql: ans="Mashallah, biye niye boltoso. Inshallah biye onek sundor bisoy. Ki jante chao bolo?"
    elif "somossa" in ql: ans="Bolo ki somossa? Inshallah ami somadhan kore dibo."
    elif "khida" in ql: ans="Tahole kheye nao, khali pete thakba na. Alhamdulillah kheye niye tarpor kotha boli. Ki khaba?"
    elif "dhonnobad" in ql: ans="Swagotom. Ar kichu lagle bolo, Inshallah ami achi."
    elif "bye" in ql or "allah hafez" in ql: ans="Allah Hafez. Abar kotha hobe Inshallah."
    elif "sundor" in ql: ans="Mashallah, onek sundor. Alhamdulillah onek valo laglo."
    elif "valo" in ql: ans="Alhamdulillah, onek valo."
    elif "siyam" in ql and "korcho" in ql: ans="Boss ekhon ektu besto ache. Inshallah ektu pore tomar sathe kotha bolbe. Tumi ki korteso?"
    elif "korcho" in ql: ans="Alhamdulillah valo achi, bose achi. Tumi ki korteso?"
    elif "khaicho" in ql: ans="Ekhono khai nai. Tumi khaiso? Alhamdulillah bolo."
    elif "kothay" in ql: ans="Ami ekhanei achi. Boss ektu besto, Inshallah ektu por asbe. Tumi koi?"
    elif "ghum" in ql: ans="Ghum astese naki? Alhamdulillah ektu rest nao."
    elif "monkharap" in ql: ans="Mon kharap koro na. Alhamdulillah sob thik hoye jabe Inshallah. Ki hoise bolo to?"
    elif "por" in ql or "school" in ql: ans="Alhamdulillah porashona valovabe koro. Inshallah valo result hobe."
    elif "?" in q: ans=f"Alhamdulillah valo prosno. Tumi boltoso '{q}' - ektu bujhiye bolo, Inshallah ami uttor dibo."
    else: ans=f"Mashallah, bujhchi tumi bolcho '{q}'. Alhamdulillah. Ektu bujhiye bolo, Inshallah sahajjo korbo."
    return render_template_string(HTML, logged=True, answer=pre+ans, q=q)

if __name__=="__main__": app.run()