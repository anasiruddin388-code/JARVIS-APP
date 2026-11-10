"""app_control.py - Jarvis app control (standalone, no changes to existing code).

Only acts when the user explicitly asks. Never runs shell/eval.
Entry point: handle(text) -> reply string, or None if text is not an app command
(then the normal brain handles it).
"""
import json
import os
import re
import time
from urllib.parse import quote

APPS = {  # spoken name -> Android package
    "whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome", "camera": "com.android.camera",
    "facebook": "com.facebook.katana", "messenger": "com.facebook.orca",
    "telegram": "org.telegram.messenger", "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm", "settings": "com.android.settings",
}
CONFIRM_TTL = 30  # seconds a pending action stays valid
YES = {"ha", "haa", "hae", "yes", "ok", "okay", "thik ache", "kor", "koro", "send"}
NO = {"na", "no", "cancel", "thak", "thamo", "bad dao"}

_pending = None  # {"kind", "args", "expires"}
_data_dir = os.getcwd()


def set_data_dir(path):
    global _data_dir
    _data_dir = path


# ---------- contacts (local file, no READ_CONTACTS permission needed) ----------
def _contacts_path():
    return os.path.join(_data_dir, "contacts.json")


def load_contacts():
    try:
        with open(_contacts_path(), encoding="utf-8") as f:
            data = json.load(f)
        return {str(k).lower(): str(v) for k, v in data.items()}
    except Exception:
        return {}


def add_contact(name, number):
    number = re.sub(r"[^\d+]", "", number)
    if not name or len(re.sub(r"\D", "", number)) < 8:
        return False
    data = load_contacts()
    data[name.strip().lower()] = number
    tmp = _contacts_path() + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _contacts_path())  # atomic: no half-written file
        return True
    except Exception:
        return False


# ---------- parsing ----------
def parse(text):
    t = re.sub(r"\s+", " ", text.strip().lower())
    t = re.sub(r"^(?:hey |hi |ok )?jarvis[,:]? ", "", t)  # optional wake word at the start
    # "Rosid ke massage dao hello" / "Rosid ke hello massage dao" / "Rosid ke hello pathao"
    m = re.match(r"^(?:whatsapp e )?(\w+) ?(?:ke|ko) (.+)$", t)
    if m and re.search(r"massage|message|msg|pathao", t):
        rest = m.group(2)
        rest = re.sub(r"^(?:massage|message|msg) (?:dao|pathao|koro) ", "", rest)
        rest = re.sub(r" (?:massage|message|msg)(?: (?:dao|pathao|koro))?$", "", rest)
        rest = re.sub(r" (?:pathao|dao|bolo|koro)$", "", rest).strip()
        if rest and rest not in ("massage", "message", "msg", "dao", "pathao"):
            return {"kind": "send", "name": m.group(1), "text": rest}
    # "send hello to Rosid"
    m = re.match(r"^(?:send|text) (.+) to (\w+)$", t)
    if m:
        return {"kind": "send", "name": m.group(2), "text": m.group(1).strip()}
    # "open whatsapp" / "whatsapp khol" / "whatsapp khulo"
    m = re.match(r"^(?:open|launch) (\w+)$", t) or re.match(r"^(\w+) (?:khol|kholo|open koro|open)$", t)
    if m and m.group(1) in APPS:
        return {"kind": "open", "app": m.group(1)}
    return None


# ---------- Android actions (pyjnius; every call guarded) ----------
def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _do_open(app):
    try:
        act = _activity()
        intent = act.getPackageManager().getLaunchIntentForPackage(APPS[app])
        if intent is None:
            return "%s ei phone-e pailam na." % app
        act.startActivity(intent)
        return "%s khulchhi." % app
    except Exception:
        return "%s khola gelo na." % app


def _do_send(number, text):
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        digits = re.sub(r"\D", "", number)
        uri = Uri.parse("https://wa.me/%s?text=%s" % (digits, quote(text)))
        intent = Intent(Intent.ACTION_VIEW, uri)
        intent.setPackage("com.whatsapp")
        _activity().startActivity(intent)
        return "WhatsApp-e message ready kore dilam."
    except Exception:
        return "WhatsApp message kholte parlam na."


# ---------- main entry ----------
def handle(text, executor=None):
    """Returns reply or None. `executor` is for tests only."""
    global _pending
    ex = executor or {"open": _do_open, "send": _do_send}
    t = text.strip().lower()

    if _pending:
        if time.time() > _pending["expires"]:
            _pending = None
        elif t in YES:
            p, _pending = _pending, None
            return ex["send"](*p["args"])
        elif t in NO:
            _pending = None
            return "Thik ache, pathalam na."

    cmd = parse(text)
    if not cmd:
        return None
    if cmd["kind"] == "open":
        return ex["open"](cmd["app"])
    number = load_contacts().get(cmd["name"])
    if not number:
        return "%s-er number amar kache nei." % cmd["name"]
    _pending = {"kind": "send", "args": (number, cmd["text"]),
                "expires": time.time() + CONFIRM_TTL}
    return "%s ke '%s' pathachchi, thik ache?" % (cmd["name"], cmd["text"])
