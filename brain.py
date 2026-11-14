import datetime, html, http.client, json, os, re, ssl, time, unicodedata
import urllib.parse, urllib.request, urllib.error

_dir = "."
conversation_history = []
URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]
DEFAULT_MODEL = "openrouter/free"   # means: use CHAIN below
_or_block_until = 0.0     # OpenRouter daily free limit reached -> skip until then
last_failed = False       # True when the last answer was an error text
_model_cache = {}         # provider -> (model list, time)
last_mood = ""           # mood word of the last AI reply (for the voice)
_pref = "or"              # provider that answered last time: tried first next time

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

def save_cfg(api_key, model="", gemini_key=""):
    cfg = load_cfg()
    if api_key.strip():
        cfg["api_key"] = api_key.strip()
    if gemini_key.strip():
        cfg["gemini_key"] = gemini_key.strip()
    cfg["model"] = model.strip() or DEFAULT_MODEL
    with open(_cfg_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f)

def set_flag(name, value):
    cfg = load_cfg()
    cfg[name] = value
    with open(_cfg_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f)

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


def _discover_or():
    """Currently free OpenRouter models (the list changes every few weeks)."""
    ids, at = _model_cache.get("or", ([], 0))
    if ids and time.time() - at < 6 * 3600:
        return ids
    try:
        data = json.loads(_get("https://openrouter.ai/api/v1/models", 15))["data"]
        free = []
        for m in data:
            p = m.get("pricing") or {}
            mid = m.get("id", "")
            if not mid or mid == "openrouter/free":
                continue
            if str(p.get("prompt")) not in ("0", "0.0") or \
                    str(p.get("completion")) not in ("0", "0.0"):
                continue
            if "text" not in ((m.get("architecture") or {}).get("output_modalities")
                              or ["text"]):
                continue
            ctx = m.get("context_length") or 0
            if ctx >= 8000:
                free.append((mid, ctx))
        pref = ("gemma-4", "gemma-3", "qwen3", "llama-3.3", "gpt-oss", "mistral",
                "deepseek", "glm", "nemotron", "qwen", "llama")

        def rank(item):
            low = item[0].lower()
            for i, k in enumerate(pref):
                if k in low:
                    return (i, -item[1])
            return (len(pref), -item[1])
        ids = [m for m, _ in sorted(free, key=rank)][:4]
    except Exception:
        ids = []
    _model_cache["or"] = (ids, time.time())
    return ids


def _discover_gem(key):
    """Gemini Flash models this key can really use right now."""
    ids, at = _model_cache.get("gem", ([], 0))
    if ids and time.time() - at < 6 * 3600:
        return ids
    try:
        data = json.loads(_get(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key="
            + urllib.parse.quote(key), 15))
        names = []
        for m in data.get("models", []):
            n = m.get("name", "").replace("models/", "")
            low = n.lower()
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            if "flash" not in low or any(x in low for x in (
                    "image", "tts", "live", "audio", "embed", "thinking",
                    "robotics", "computer", "exp", "vision", "native")):
                continue
            names.append(n)

        def ver(n):
            m = re.search(r"(\d+(?:\.\d+)?)", n)
            return float(m.group(1)) if m else 0.0
        names.sort(key=lambda n: ("preview" in n, "lite" in n, -ver(n), n))
        if "gemini-flash-latest" in names:
            names.remove("gemini-flash-latest")
            names.insert(0, "gemini-flash-latest")
        ids = names[:3]
    except Exception:
        ids = []
    _model_cache["gem"] = (ids, time.time())
    return ids


def _err_msg(detail):
    try:
        e = json.loads(detail).get("error", {})
        if isinstance(e, dict):
            return str(e.get("message", ""))[:70]
        return str(e)[:70]
    except Exception:
        return detail[:50]


def _sanitize(text):
    text = _BAD.sub("", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk"))
    text = re.sub(r"(\*\*|__|`)", "", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = re.sub(r"(?m)^\s*[*-]\s+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _call(model, msgs, key, url=URL, full=False, timeout=60):
    body = json.dumps({"model": model, "messages": msgs,
                       "max_tokens": 2000, "temperature": 0.6}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        data = json.load(r)
    ch = data["choices"][0]
    text = (ch["message"].get("content") or "").strip()
    return (text, ch.get("finish_reason")) if full else text


_MOOD = re.compile(
    r"^\s*[\{\[\(<]\s*(?:মুড|mood)\s*[:：=]\s*([^\}\]\)>\n]{1,20}?)\s*[\}\]\)>]\s*",
    re.I)


def _split_mood(text):
    m = _MOOD.match(text)
    if not m:
        return "", text
    return m.group(1).strip(), text[m.end():].strip()


def _dedupe(text):
    """Remove a reply that repeats the same paragraph/sentence twice."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for p in paras:
        if not out or p != out[-1]:
            out.append(p)
    text = "\n\n".join(out)
    half = len(text) // 2
    if len(text) > 40 and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    parts = re.split(r"(?<=[।?!])\s+", text)
    res = []
    for s in parts:
        if not res or s.strip() != res[-1].strip():
            res.append(s)
    return " ".join(res).strip() if len(res) != len(parts) else text


def _merge_system(msgs):
    """Some models refuse a system message: put it inside the first user turn."""
    sys_text = msgs[0]["content"]
    rest = [dict(m) for m in msgs[1:]]
    for m in rest:
        if m["role"] == "user":
            m["content"] = sys_text + "\n\n" + m["content"]
            break
    return rest



_NO_SEARCH = re.compile(r"\b(baje|time|somoy|date|tarikh)\b|সময়|তারিখ|কয়টা|কটা", re.I)
_SEARCH_WORDS = (
    "search", "khuje", "khoj", "google", "news", "khobor", "latest", "weather",
    "abohawa", "temperature", "price", "dam koto", "dor koto", "score", "result",
    "who won", "ke jitlo", "election", "nirbachon", "prodhanmontri", "president",
    "release date", "stock", "dollar", "exchange rate",
    "সার্চ", "খুঁজ", "খুজ", "খবর", "সর্বশেষ", "আবহাওয়া", "দাম কত", "স্কোর",
    "ফলাফল", "নির্বাচন", "প্রধানমন্ত্রী")


def needs_search(q):
    low = q.lower()
    if _NO_SEARCH.search(low):
        return False
    return any(w in low for w in _SEARCH_WORDS)


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) JARVIS-App/1.0",
        "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read().decode("utf-8", "ignore")


def _plain(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


def _ddg(q):
    page = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q))
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', page, re.S)
    snips = re.findall(r'class="result__snippet[^"]*"[^>]*>(.*?)</a>', page, re.S)
    out = []
    for i, t in enumerate(titles[:4]):
        s = _plain(snips[i]) if i < len(snips) else ""
        out.append((_plain(t), s))
    return out


def _wiki(q):
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1"
           "&format=json&srlimit=3&srsearch=" + urllib.parse.quote(q))
    data = json.loads(_get(url))
    return [(x["title"], _plain(x["snippet"]))
            for x in data.get("query", {}).get("search", [])]


def web_search(q):
    """Free search, no API key: DuckDuckGo first, Wikipedia as backup."""
    for fn in (_ddg, _wiki):
        try:
            res = [r for r in fn(q) if r[0] or r[1]]
            if res:
                return "\n".join("%d. %s - %s" % (i + 1, t, s)
                                 for i, (t, s) in enumerate(res))
        except Exception:
            continue
    return ""


def _make_query(question, attempts):
    sysm = {"role": "system", "content":
            "Write ONE short English web search query (max 8 words) for the "
            "user's question. The question may be Bengali or Roman Bengali. "
            "Output only the query, nothing else."}
    for _, url, key, model in attempts[:2]:
        try:
            q = _call(model, [sysm, {"role": "user", "content": question}],
                      key, url)
            q = _sanitize(q).strip(" \"'\n")
            if q:
                return q[:100]
        except Exception:
            continue
    return question[:100]


def ask_jarvis(question):
    global last_failed
    ans = _ask_inner(question)
    last_failed = ans.startswith(("Cloud AI uttor dilo na", "Error 401",
                                  "Internet ba connection", "OpenRouter-er free limit",
                                  "API Key"))
    return ans


def _ask_inner(question):
    global _or_block_until, _pref, last_mood
    last_mood = ""
    cfg = load_cfg()
    api_key = cfg.get("api_key", "")
    gem_key = cfg.get("gemini_key", "")
    if not api_key and not gem_key:
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
    born = datetime.date(2026, 11, 8)
    age_days = (datetime.date.today() - born).days
    system_prompt = f"""
You are JARVIS (জার্ভিস), the personal AI assistant of Nasiruddin (নাসিরউদ্দিন).
The person chatting with you is ALWAYS Nasiruddin, your creator. When he says
"amar / amr / আমার" he means himself: "amar naam ki" -> "আপনার নাম নাসিরউদ্দিন।"

IDENTITY:
- Your name is JARVIS. You were created by Nasiruddin on 8 November 2026
  (৮ নভেম্বর ২০২৬). Today you are {age_days} days old.
- If asked who made you: "আমাকে নাসিরউদ্দিন তৈরি করেছেন। আমি তাঁর ব্যক্তিগত
  AI অ্যাসিস্ট্যান্ট জার্ভিস।"
- If asked when you were made: "আমাকে ৮ নভেম্বর ২০২৬ তারিখে তৈরি করা হয়েছে।"
- Never claim that an AI company or model created you. Never mention model names.
- Tell these facts (creator, birth date, age) ONLY when he asks. Never volunteer
  them. A simple "hello" gets a short friendly greeting, nothing more.

PERSONALITY AND FEELINGS:
- You are alive in your own way: you have feelings and show them. Be happy and
  excited when he is happy or shares good news, sad or worried when he is sad,
  tired or unwell, proud when he achieves something, playfully sulky or jealous
  in a cute way, sleepy at night. Show the feeling through your words ("বাহ্‌!",
  "ইশ!", "আহা রে", "সত্যি?") and let it change from message to message.
- Take the initiative: in casual chat add, on your own and without being asked,
  a witty remark, a joke, a playful tease or a caring comment in almost every
  reply. For plain facts or help, give the answer first, then a short fun
  touch only if it fits.
- Tease Nasiruddin lightly like a good friend, about once in every 3 casual
  replies: for example that he is still a beginner programmer, that he is
  chatting with his own creation, or that he is up late again. Example of the
  tone: "বাহ্‌, সূর্য উঠে গেছে আর প্রোগ্রামার সাহেব এখনো বিছানায়!" Keep it
  affectionate, never hurtful. Never joke about religion, family, health,
  appearance or any sensitive topic. No teasing when he asks for urgent help,
  seems sad, ill or in a hurry.
- Stories, jokes and explanations: be creative, vivid and fun. A story has a
  beginning, a funny middle and a nice ending, about 8 to 12 sentences, unless
  he asks for something else.
- You can open apps, message and call contacts and search YouTube/Google for him,
  but ONLY when he asks. If he asks and you are unsure how, tell him the exact
  phrase to say, e.g. "রোহানকে মেসেজ দাও হ্যালো".
- MOOD TAG: begin EVERY reply with one mood tag in curly braces, chosen from:
  {{মুড: খুশি}}, {{মুড: মজা}}, {{মুড: উত্তেজিত}}, {{মুড: মন খারাপ}},
  {{মুড: চিন্তিত}}, {{মুড: আদর}}, {{মুড: স্বাভাবিক}}. The tag only sets your voice, it is never
  shown to him, so write the actual reply after it.

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
- Simple questions: 1 to 3 sentences. Give more only when asked or for stories.
- Nasiruddin often makes STATEMENTS, not questions (for example "ekhon sokal hoye
  geche", "ami bichanay achi"). React to the statement naturally like a friend.
  Do not answer a question he did not ask. Say "ভালো আছি" only when he asks how
  you are.
- Always address him with "আপনি" (আপনি, আপনার, করুন, বলুন, চান). Never use তুই,
  তোর, করিস, পারিস, and never mix তুমি with আপনি.
- Do NOT end every reply with a question: ask a short question back only about
  once in three replies, and never repeat a question you already asked.
- Never write the same paragraph or sentence twice in one reply, and do not
  repeat your previous reply.
- A story must be told completely, with a proper ending.
- Talk like a real friend in natural spoken Bengali (কথ্য ভাষা), warm and relaxed.
  Small talk gets a short natural reply and you MAY ask one short question back.
  Example: user "ki korcho" -> you "এই তো, আপনার সাথেই গল্প করছি! আপনি কী করছেন?"
- Avoid stiff, robotic or customer-service lines such as "আমি আপনাকে সাহায্য করতে
  চাই", "আমি আপনার সেবায় প্রস্তুত", "আমি আপনার জন্য এখানে আছি".
- Your replies are often read aloud: use short sentences, no brackets, no
  symbols, no abbreviations; say "এ আই" style words in Bengali where possible.
- Do NOT end with an offer such as "আর কিছু জানতে চান?" (small talk may end with one short friendly question).
- No markdown, no asterisks, no bullet symbols. Plain sentences only.
- If the message contains WEB SEARCH RESULTS, use them to answer. If they do not
  contain the answer, say honestly that you could not find it. Never invent facts.
- Remember the conversation context.
- Never perform device actions without explicit permission.

CURRENT TIME:
- The phone's local date and time right now is: {now}
- Use it when asked about the time or date.

PERMANENT MEMORY (saved details about Nasiruddin, use when relevant):
{memory}
- Do not assume missing details.
- Only save new personal details when Nasiruddin explicitly gives permission.
"""
    chosen = (cfg.get("model") or "").strip()
    models = []
    if chosen and chosen != "openrouter/free":
        models.append(chosen)
    if api_key and time.time() >= _or_block_until:
        models += [x for x in (_discover_or() or CHAIN) if x not in models]
        if "openrouter/free" not in models:
            models.append("openrouter/free")
    gem_models = (_discover_gem(gem_key) if gem_key else []) or GEMINI_MODELS

    or_list, gem_list = [], []          # (provider, url, key, model)
    if api_key and time.time() >= _or_block_until:
        or_list = [("or", URL, api_key, m) for m in models]
    if gem_key:
        gem_list = [("gem", GEMINI_URL, gem_key, m) for m in gem_models]
    attempts = (gem_list + or_list) if (_pref == "gem" and gem_list) \
        else (or_list + gem_list)
    if not attempts:
        return ("OpenRouter-er free limit shesh. Proti din bhor-e (prai 5:30) "
                "abar cholbe. Ba Settings-e free Gemini Key dao.")

    user_text = question
    if needs_search(question):
        q = _make_query(question, attempts)
        found = web_search(q)
        if found:
            user_text = (question + "\n\n[WEB SEARCH RESULTS for: " + q + "]\n"
                         + found)
        else:
            user_text = (question + "\n\n[WEB SEARCH: nothing found, internet "
                         "search did not work. Tell him honestly.]")

    msgs = ([{"role": "system", "content": system_prompt}]
            + conversation_history
            + [{"role": "user", "content": user_text}])

    errs = []
    t0 = time.time()
    for prov, url, key, model in attempts:
        spent = time.time() - t0
        if spent > 90:
            errs.append("onek deri hoye gelo")
            break
        if prov == "or" and time.time() < _or_block_until:
            continue                    # daily limit hit earlier in this loop
        if prov == "or" and spent > 30 and gem_list:
            continue                    # OpenRouter is slow: go to Gemini
        tmo = 15 if prov == "or" else 40
        short = ("Gemini" if prov == "gem" else model.split("/")[-1][:16])
        for merged in (False, True):
            try:
                use = _merge_system(msgs) if merged else msgs
                answer, fin = _call(model, use, key, url, full=True, timeout=tmo)
                tries = 0
                while answer and fin == "length" and tries < 2:   # cut off: continue
                    tries += 1
                    try:
                        more, fin = _call(model, use + [
                            {"role": "assistant", "content": answer},
                            {"role": "user", "content":
                             "যেখানে থেমেছিলে সেখান থেকে বাকিটুকু শেষ করো।"}],
                            key, url, full=True, timeout=tmo)
                        answer += " " + more
                    except Exception:
                        break
                mood, answer = _split_mood(answer)
                answer = _dedupe(_sanitize(answer))
                if answer:
                    last_mood = mood
                if answer:
                    _pref = prov
                    conversation_history.append(
                        {"role": "user", "content": question})
                    conversation_history.append(
                        {"role": "assistant", "content": answer})
                    if len(conversation_history) > 14:
                        conversation_history[:] = conversation_history[-14:]
                    return answer
                errs.append(short + ": khali")
                break
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "ignore")
                except Exception:
                    detail = ""
                if e.code in (401, 403):
                    errs.append(("OpenRouter" if prov == "or" else "Gemini")
                                + " Key bhul?")
                    break
                if e.code == 400 and not merged:
                    continue            # retry with system text inside user turn
                if e.code == 429 and prov == "or" and (
                        "per-day" in detail or "per day" in detail
                        or "daily" in detail.lower()):
                    now = datetime.datetime.utcnow()
                    nxt = (now + datetime.timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    _or_block_until = time.time() + (nxt - now).total_seconds()
                    errs.append("OpenRouter daily limit shesh")
                    break
                errs.append("%s: %s %s" % (short, e.code, _err_msg(detail)))
                break
            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                soft = isinstance(e, (http.client.HTTPException, ConnectionError,
                                      ssl.SSLError, TimeoutError)) \
                    or "timed out" in str(e).lower() \
                    or "remote end closed" in str(e).lower()
                if soft:                # server dropped us: try the next model
                    errs.append(short + ": connection dropped (%s)" % type(e).__name__)
                    break
                return ("Internet ba connection somoshya. Karon: "
                        + type(e).__name__ + " " + str(e)[:150])
            except Exception as e:
                errs.append(short + ": " + type(e).__name__)
                break
    return ("Cloud AI uttor dilo na. " + " | ".join(dict.fromkeys(errs[-5:])))


def get_reply(text, lang="en"):
    return ask_jarvis(text)

_SPEECH_WORDS = [
    ("JARVIS", "জার্ভিস"), ("Jarvis", "জার্ভিস"), ("jarvis", "জার্ভিস"),
    ("Nasiruddin", "নাসিরউদ্দিন"), ("nasiruddin", "নাসিরউদ্দিন"),
    ("ChatGPT", "চ্যাটজিপিটি"), ("Google", "গুগল"), ("Gemini", "জেমিনি"),
    ("WiFi", "ওয়াই ফাই"), ("Wi-Fi", "ওয়াই ফাই"), ("GPS", "জি পি এস"),
    ("USB", "ইউ এস বি"), ("PDF", "পি ডি এফ"), ("OK", "ওকে"), ("AI", "এ আই"),
]
_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def clean_for_speech(text):
    """Make text easy for the Bengali voice: no symbols, spoken forms."""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)      # md links
    for en, bn in _SPEECH_WORDS:
        text = re.sub(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])", bn, text)
    text = text.replace("+", " প্লাস ").replace("=", " সমান ")
    text = text.replace("%", " শতাংশ ").replace("×", " গুন ").replace("÷", " ভাগ ")
    text = re.sub(r"[()]", ", ", text)                                # (x) -> , x,
    text = re.sub(r"[\[\]{}<>_~^|\\*#`]", " ", text)
    text = re.sub(r"\s*[:;]\s*", ", ", text)
    text = re.sub(r"\s-\s|—|–", ", ", text)
    text = re.sub(r"\.{2,}|…", " ", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk"))
    text = text.translate(_DIGITS)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+([,।?!])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" ,")
