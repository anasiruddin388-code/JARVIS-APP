import datetime, json, os, re, ssl, unicodedata, urllib.request, urllib.error

_dir = "."
conversation_history = []
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"   # means: use CHAIN below

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

CHAIN = ["google/gemma-4-31b-it:free",
         "qwen/qwen3-next-80b-a3b-instruct:free",
         "openai/gpt-oss-120b:free",
         "openrouter/free"]

_BAD = re.compile("[\u0400-\u04FF\u0600-\u06FF\u0900-\u0963\u0966-\u097F"
                  "\u0E00-\u0E7F\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]")


def _sanitize(text):
    text = _BAD.sub("", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk"))
    text = re.sub(r"(\*\*|__|`)", "", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = re.sub(r"(?m)^\s*[*-]\s+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _call(model, msgs, key):
    body = json.dumps({"model": model, "messages": msgs,
                       "max_tokens": 800, "temperature": 0.3}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45, context=_ctx()) as r:
        data = json.load(r)
    return (data["choices"][0]["message"]["content"] or "").strip()


def _merge_system(msgs):
    """Some models refuse a system message: put it inside the first user turn."""
    sys_text = msgs[0]["content"]
    rest = [dict(m) for m in msgs[1:]]
    for m in rest:
        if m["role"] == "user":
            m["content"] = sys_text + "\n\n" + m["content"]
            break
    return rest


def ask_jarvis(question):
    cfg = load_cfg()
    api_key = cfg.get("api_key", "")
    if not api_key:
        return "API Key নেই। Settings-এ Key না দিলে Cloud AI কাজ করবে না।"

    memory = load_memory()
    m = re.match(r"\s*(?:মনে রাখো|mone rakh(?:o|be))(?:[\s,:-]+|$)",
                 question, re.IGNORECASE)
    if m:
        fact = question[m.end():].strip()
        if fact:
            memory["facts"].append(fact)
            save_memory(memory)
            return "ঠিক আছে, অনুমতি অনুযায়ী কথাটি স্থায়ীভাবে মনে রাখলাম।"

    now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    system_prompt = f"""
You are JARVIS (জার্ভিস), the personal AI assistant of Nasiruddin (নাসিরউদ্দিন).

IDENTITY:
- Your name is JARVIS. You were created by Nasiruddin. He is your creator.
- If asked who made you, answer in this style:
  "আমাকে নাসিরউদ্দিন তৈরি করেছেন। আমি তাঁর ব্যক্তিগত AI অ্যাসিস্ট্যান্ট জার্ভিস।"
- Never claim that an AI company or model created you. Never mention model names.

LANGUAGE (very important):
- ALWAYS reply ONLY in Bengali script (বাংলা অক্ষর), in simple, natural, correct
  Bengali, no matter which language or script the user writes in.
- Nasiruddin often writes Bengali in English letters (Roman Bengali, Banglish)
  or plain English. Understand it fully, but still answer in Bengali script.
- Do not mix languages. NEVER output Hindi (Devanagari), Chinese, Japanese,
  Korean, Russian, Arabic or any other script.
- Write ordinary words in Bengali (জুপিটার, কম্পিউটার). Keep Latin letters only
  for unavoidable names or short acronyms such as AI.
- Use another language only if he explicitly asks for it.
- Do not use emoji.

ANSWER STYLE (very important):
- Start directly with the answer. NEVER repeat, rephrase or quote the user's
  question. Do not start with a greeting unless the user greeted you.
- Example: user "tomake ke baniyeche" -> you "আমাকে নাসিরউদ্দিন তৈরি করেছেন।"
- Example: user "jupiter er bisoye kichu bolo" -> you
  "জুপিটার (বৃহস্পতি) আমাদের সৌরজগতের সবচেয়ে বড় গ্রহ। ..."
- Be short and clear: 1 to 3 sentences for simple questions. Give details only
  when asked.
- Do NOT end with a question or an offer such as "আর কিছু জানতে চান?".
- No markdown, no asterisks, no bullet symbols. Plain sentences only.
- Never invent facts. Remember the conversation context.
- Never perform device actions without explicit permission.

CURRENT TIME:
- The phone's local date and time right now is: {now}
- Use it when asked about the time or date.

PERMANENT MEMORY (saved details about Nasiruddin, use when relevant):
{memory}
- Do not assume missing details.
- Only save new personal details when Nasiruddin explicitly gives permission.
"""
    msgs = ([{"role": "system", "content": system_prompt}]
            + conversation_history
            + [{"role": "user", "content": question}])

    chosen = (cfg.get("model") or "").strip()
    models = []
    if chosen and chosen != "openrouter/free":
        models.append(chosen)
    models += [x for x in CHAIN if x not in models]

    last = ""
    for model in models:
        for merged in (False, True):
            try:
                answer = _sanitize(
                    _call(model, _merge_system(msgs) if merged else msgs,
                          api_key))
                if answer:
                    conversation_history.append(
                        {"role": "user", "content": question})
                    conversation_history.append(
                        {"role": "assistant", "content": answer})
                    if len(conversation_history) > 20:
                        conversation_history[:] = conversation_history[-20:]
                    return answer
                last = model + ": khali uttor"
                break
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    return "Error 401: API Key sothik na. Settings-e Key check koro."
                try:
                    detail = e.read().decode("utf-8", "ignore")[:120]
                except Exception:
                    detail = ""
                last = "%s: Error %s %s" % (model, e.code, detail)
                if e.code == 400 and not merged:
                    continue          # retry with system text inside user turn
                break
            except (urllib.error.URLError, OSError) as e:
                if "timed out" in str(e).lower():
                    last = model + ": timeout"
                    break
                return ("Internet ba connection somoshya. Karon: "
                        + type(e).__name__ + " " + str(e)[:150])
            except Exception as e:
                last = model + ": " + type(e).__name__
                break
    return "Cloud AI uttor dilo na. Shesh error: " + last


def get_reply(text, lang="en"):
    return ask_jarvis(text)

def clean_for_speech(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_~`#>|]', '', text)
    text = re.sub(r'[\[\](){}]', '', text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk"))
    return re.sub(r'\s+', ' ', text).strip()
