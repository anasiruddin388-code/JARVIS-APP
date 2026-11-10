"""api_manager.py - 4 API slots for Jarvis with automatic fallback.

Slots 1-2 are the EXISTING ones and keep their existing config.json keys
(api_key = OpenRouter, gemini_key = Gemini), so nothing already saved changes.
Slots 3-4 are new:
    groq_key                                  -> Groq (free, fast)
    custom_key + custom_url + custom_model    -> any OpenAI-compatible provider
                                                 (e.g. Cerebras, Mistral), name in custom_name

Keys live only in config.json on the phone (never in code, never logged).
chat() never raises: it returns (text, None) or (None, short_error).
"""
import json
import time
import urllib.error
import urllib.request

COOLDOWN = 600  # seconds a rate-limited slot is skipped
TIMEOUT = 30
_cooldown_until = {}

# (slot name, config key for the API key, url, default model, extra config keys)
SLOTS = [
    ("openrouter", "api_key",
     "https://openrouter.ai/api/v1/chat/completions", "openrouter/free"),
    ("gemini", "gemini_key",
     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
    ("groq", "groq_key",
     "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    ("custom", "custom_key", None, None),  # url/model come from config
]
EXISTING = {"openrouter", "gemini"}


def configured_slots(config, only_extra=False):
    """Slots that have a key (and for custom: url + model), in priority order."""
    out = []
    for name, key_field, url, model in SLOTS:
        if only_extra and name in EXISTING:
            continue
        key = str(config.get(key_field, "")).strip()
        if not key:
            continue
        if name == "custom":
            url = str(config.get("custom_url", "")).strip()
            model = str(config.get("custom_model", "")).strip()
            if not url.startswith("https://") or not model:
                continue
        elif name == "openrouter" and config.get("model"):
            model = str(config["model"]).strip()  # keep the user's existing model choice
        out.append({"name": name, "key": key, "url": url, "model": model})
    return out


def mask(key):
    key = str(key)
    return key[:3] + "***" if len(key) > 6 else "***"


def _post(slot, messages):
    body = json.dumps({"model": slot["model"], "messages": messages}).encode("utf-8")
    req = urllib.request.Request(slot["url"], data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + slot["key"]})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def chat(messages, config, only_extra=False):
    """Try each configured slot in order; fall through on limit/auth/server errors.
    Returns (text, None) on success or (None, error_text)."""
    slots = configured_slots(config, only_extra)
    if not slots:
        return None, "Kono API key deoa nei."
    errors = []
    for s in slots:
        if time.time() < _cooldown_until.get(s["name"], 0):
            errors.append("%s: cooldown" % s["name"])
            continue
        try:
            text = _post(s, messages)
            if text:
                return text, None
            errors.append("%s: khali uttor" % s["name"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 402, 403):
                _cooldown_until[s["name"]] = time.time() + COOLDOWN  # limit shesh
            errors.append("%s: HTTP %d" % (s["name"], e.code))  # 401 = key bhul
        except Exception:
            errors.append("%s: connection/format error" % s["name"])
    return None, "Sob API fail: " + ", ".join(errors)


def save_new_keys(config, groq_key=None, custom_key=None, custom_url=None,
                  custom_model=None, custom_name=None):
    """Update only the new fields in the config dict (existing keys untouched).
    Empty/None values are ignored, so a blank settings box never erases a saved key."""
    for field, val in (("groq_key", groq_key), ("custom_key", custom_key),
                       ("custom_url", custom_url), ("custom_model", custom_model),
                       ("custom_name", custom_name)):
        if val and str(val).strip():
            config[field] = str(val).strip()
    return config
