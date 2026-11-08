import json, os, urllib.request, urllib.error

_dir = "."
_history = []
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

def set_data_dir(path):
    global _dir
    _dir = path

def _cfg_path():
    return os.path.join(_dir, "config.json")

def load_cfg():
    try:
        with open(_cfg_path()) as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(api_key, model=""):
    with open(_cfg_path(), "w") as f:
        json.dump({"api_key": api_key.strip(),
                   "model": model.strip() or DEFAULT_MODEL}, f)

def get_reply(text, lang="en"):
    cfg = load_cfg()
    key = cfg.get("api_key", "")
    if not key:
        return "API Key nei. Settings-e Key na dile Cloud AI kaj korbe na."
    system = ("You are J.A.R.V.I.S, a helpful assistant for Nasiruddin. "
              "Reply in the same language the user writes in (Bengali or English). "
              "Keep answers short.")
    _history.append({"role": "user", "content": text})
    msgs = [{"role": "system", "content": system}] + _history[-10:]
    body = json.dumps({"model": cfg.get("model", DEFAULT_MODEL),
                       "messages": msgs}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
        reply = data["choices"][0]["message"]["content"]
        _history.append({"role": "assistant", "content": reply})
        return reply
    except urllib.error.HTTPError as e:
        _history.pop()
        return "Error " + str(e.code) + ": Key ba model name check koro."
    except Exception:
        _history.pop()
        return "Internet ba connection somoshya."
