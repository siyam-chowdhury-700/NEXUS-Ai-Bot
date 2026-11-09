from flask import Flask, request, jsonify, render_template_string
import os

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS AI</title>
<style>
body{background:#0f0f0f;color:white;font-family:sans-serif;padding:20px;text-align:center}
#box{max-width:500px;margin:auto;background:#1e1e1e;padding:20px;border-radius:15px}
input{width:80%;padding:12px;border-radius:10px;border:none}
button{padding:12px 20px;border-radius:10px;border:none;background:#00ff88;font-weight:bold;margin-top:10px}
#chat{text-align:left;margin-top:20px}
.msg{background:#2a2a2a;padding:10px;border-radius:10px;margin:8px 0}
</style></head>
<body><div id="box">
<h1>🤖 NEXUS AI</h1>
<p>Ask me anything!</p>
<input id="q" placeholder="Type your question...">
<br><button onclick="ask()">Send</button>
<div id="chat"></div>
</div>
<script>
async function ask(){
let q=document.getElementById('q').value;
if(!q) return;
document.getElementById('chat').innerHTML += '<div class=msg><b>You:</b> '+q+'</div>';
let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({msg:q})});
let d=await r.json();
document.getElementById('chat').innerHTML += '<div class=msg><b>NEXUS:</b> '+d.reply+'</div>';
document.getElementById('q').value='';
}
</script></body></html>
"""

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/chat', methods=['POST'])
def chat():
    msg = request.json.get('msg','').lower()
    if 'hello' in msg or 'hi' in msg or 'hey' in msg:
        reply = "Hello! I am NEXUS AI. How can I help you today?"
    elif 'name' in msg:
        reply = "My name is NEXUS AI, created by Siyam!"
    elif 'who are you' in msg:
        reply = "I am NEXUS AI, your personal AI assistant."
    elif 'how are you' in msg:
        reply = "I am great! Thanks for asking. What about you?"
    elif 'thank' in msg:
        reply = "You are most welcome!"
    elif 'bye' in msg:
        reply = "Bye bye! Come back soon."
    else:
        reply = f"You said: '{msg}'. I am still learning, but I am here to help you! Try asking my name or saying hello."
    return jsonify({'reply': reply})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)