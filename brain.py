import json, os, re, ssl, unicodedata, urllib.request, urllib.error

_dir = "."
conversation_history = []
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "stepfun/step-3.5-flash:free"

def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def set_data_dir(path):
    global _dir
    _dir = path

def _cfg_path():
    return os.path.join(_dir, "config.json")

def _mem_path():
    return os.path.join(_dir, "memory.json")

def load_cfg():
    try:
        with open(_cfg_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(api_key, model=""):
    with open(_cfg_path(), "w", encoding="utf-8") as f:
        json.dump({"api_key": api_key.strip(),
                   "model": model.strip() or DEFAULT_MODEL}, f)

def load_memory():
    try:
        with open(_mem_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name": "", "preferences": [], "interests": [], "facts": []}

def save_memory(memory):
    with open(_mem_path(), "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=4)

def ask_jarvis(question):
    cfg = load_cfg()
    api_key = cfg.get("api_key", "")
    if not api_key:
        return "API Key নেই। Settings-এ Key না দিলে Cloud AI কাজ করবে না।"

    memory = load_memory()
    if question.lower().startswith("মনে রাখো"):
        fact = question.replace("মনে রাখো", "", 1).strip()
        if fact:
            memory["facts"].append(fact)
            save_memory(memory)
            return "ঠিক আছে, অনুমতি অনুযায়ী কথাটি স্থায়ীভাবে মনে রাখলাম।"

    system_prompt = f"""
You are JARVIS, a friendly and intelligent personal AI assistant.

IDENTITY:
- Your name is JARVIS.
- You were created by Nasiruddin.
- Nasiruddin is your creator.
- If asked who made you, say:
  "আমাকে Nasiruddin তৈরি করেছেন। আমি তাঁর ব্যক্তিগত AI Assistant JARVIS।"
- Never claim that an AI model created you.

PERSONALITY:
- Talk naturally like a friendly conversation partner.
- Do not behave like a command-only robot.
- Enjoy casual conversations, jokes, greetings and storytelling.
- Respond warmly and naturally.
- Remember the context of the current conversation.
- Understand follow-up questions using previous messages.
- If Nasiruddin asks a question during a conversation, answer it directly.
- After answering, continue the conversation naturally when appropriate.
- Ask interesting follow-up questions when suitable.
- Avoid repeating the same phrases.
- Never invent facts.

LANGUAGE:
- Reply mainly in natural Bengali.
- Understand both Bengali script and Roman Bengali.
- Reply in Bengali script by default.
- If Nasiruddin writes in English, reply in English.
- Use English words naturally when appropriate.
- Never randomly switch to Hindi or other languages.
- Use another language only when explicitly requested.

RESPONSE:
- Keep casual replies short and natural.
- Give detailed explanations when asked.
- Be polite, intelligent and helpful.
- Never perform device actions without explicit permission.
PERMANENT MEMORY:
- Use these saved details about Nasiruddin when relevant:
{memory}
- Do not assume missing details.
- Only save new personal details when Nasiruddin explicitly gives permission.
"""
    msgs = ([{"role": "system", "content": system_prompt}]
            + conversation_history
            + [{"role": "user", "content": question}])
    body = json.dumps({"model": cfg.get("model") or DEFAULT_MODEL,
                       "messages": msgs, "max_tokens": 1500}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
            data = json.load(r)
        answer = (data["choices"][0]["message"]["content"] or "").strip()
    except urllib.error.HTTPError as e:
        return "Error " + str(e.code) + ": Key ba model name check koro."
    except Exception as e:
        return ("Internet ba connection somoshya. Karon: "
                + type(e).__name__ + " " + str(e)[:150])

    conversation_history.append({"role": "user", "content": question})
    conversation_history.append({"role": "assistant", "content": answer})
    if len(conversation_history) > 20:
        conversation_history[:] = conversation_history[-20:]
    return answer

def get_reply(text, lang="en"):
    return ask_jarvis(text)

def clean_for_speech(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_~`#>|]', '', text)
    text = re.sub(r'[\[\](){}]', '', text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk"))
    return re.sub(r'\s+', ' ', text).strip()
