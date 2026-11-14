"""Voice/chat commands that control other apps - ONLY when the user says so.

Supported (Bengali / Roman Bengali / English):
  "WhatsApp kholo"                        -> opens the app
  "Rohan ke message dao hello"            -> opens WhatsApp chat with Rohan, text ready
  "Rohan ke call koro"                    -> opens the dialer with Rohan's number
  "YouTube e <kichu> chalao"              -> YouTube search
  "Google e <kichu> search koro"          -> web search
Nothing is sent or called by JARVIS itself: WhatsApp/dialer open with the text/number
filled in and YOU press Send / Call."""
import difflib
import re
import time
import urllib.parse

from kivy.clock import Clock

try:
    from jnius import autoclass, cast
    from android.runnable import run_on_ui_thread
    from android.permissions import (request_permissions, check_permission,
                                     Permission)
    ANDROID = True
except Exception:
    ANDROID = False

    def run_on_ui_thread(f):
        return f

# ------------------------------------------------------------------ parsing
_OPEN = (r"(?:kholo|khulo|khol|khul|khule dao|khule den|open koro|open kor|open|"
         r"on koro|on karo|on kor|onn koro|start koro|launch koro|chalu koro|chalu kor|chalao|"
         r"অন করো|অন কর|চালু করো|চালু কর|চালাও|লঞ্চ করো|খুলে দাও|খুলে দিন|"
         r"খোলো|খোল|খুলো|খুলুন|খুল|ওপেন করো|ওপেন কর|ওপেন)")
_JAO = (r"(?:e jao|e jete chai|e jabo|te jao|এ যাও|তে যাও|এ যেতে চাই|এ চলো|তে চলো)")
_KE = r"(?:ke|কে)"
_MSG = r"(?:message|massage|messege|msg|sms|মেসেজ|ম্যাসেজ|এসএমএস)"
_SEND = (r"(?:pathiye dao|pathao|dao|daw|do|koro|korba|পাঠিয়ে দাও|পাঠাও|দাও|করো)")
_WA = r"(?:whatsapp|হোয়াটসঅ্যাপ|হোয়াটস অ্যাপ|হোয়াটসএপ)"
_E = r"(?:e|এ)"
_FLAGS = re.I

_PATTERNS = [
    ("msg", rf"^(?P<name>.+?)\s*{_KE}\s+(?:{_WA}\s*(?:{_E}\s+)?)?{_MSG}\s+{_SEND}\s*(?P<text>.*)$"),
    ("msg", rf"^(?P<name>.+?)\s*{_KE}\s+(?:{_WA}\s*(?:{_E}\s+)?)?(?P<text>.+?)\s+(?:bole|বলে|লিখে)\s+(?:{_MSG}\s+)?{_SEND}$"),
    ("msg", rf"^{_WA}\s*(?:{_E}\s+)?(?P<name>.+?)\s*{_KE}\s+(?P<text>.+?)(?:\s+{_SEND})?$"),
    ("msg", rf"^send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message|msg)\s+to\s+(?P<name>\S+)\s*(?P<text>.*)$"),
    ("call", rf"^(?P<name>.+?)\s*{_KE}\s+(?:call|phone|fon|ফোন|কল)\s*{_SEND}$"),
    ("call", r"^(?:call|কল)\s+(?P<name>.+)$"),
    ("yt", rf"^(?:youtube|ইউটিউব)\s*(?:{_E}\s+)?(?P<q>.+?)\s+(?:chalao|search koro|khujo|dekhao|চালাও|সার্চ করো|খুঁজো|দেখাও)$"),
    ("web", rf"^(?:google|গুগল)\s*(?:{_E}\s+)?(?P<q>.+?)\s+(?:search koro|khujo|সার্চ করো|খুঁজো|খুঁজে দাও)$"),
    ("web", r"^(?P<q>.+?)\s+(?:search koro|সার্চ করো)$"),
    ("open", rf"^(?P<app>.+?)\s+{_OPEN}$"),
    ("open", r"^(?:open|ওপেন)\s+(?P<app>.+)$"),
    ("open", rf"^(?P<app>.+?)\s+{_JAO}$"),
]


def _norm(text):
    t = re.sub(r"[-,।.!?;:\"']", " ", text)
    return re.sub(r"\s+", " ", t).strip()


def parse(text):
    t = _norm(text)
    for kind, pat in _PATTERNS:
        m = re.match(pat, t, _FLAGS)
        if m:
            d = {"kind": kind}
            d.update({k: (v or "").strip() for k, v in m.groupdict().items()})
            if kind in ("msg", "call") and not d.get("name"):
                continue
            return d
    return None


# ------------------------------------------------------------------ apps
ALIASES = {
    "whatsapp": ["whatsapp", "হোয়াটসঅ্যাপ", "হোয়াটস অ্যাপ", "হোয়াটসএপ"],
    "youtube": ["youtube", "ইউটিউব", "ইউ টিউব"],
    "facebook": ["facebook", "ফেসবুক"],
    "messenger": ["messenger", "মেসেঞ্জার"],
    "instagram": ["instagram", "ইনস্টাগ্রাম", "ইন্সটাগ্রাম"],
    "telegram": ["telegram", "টেলিগ্রাম"],
    "chrome": ["chrome", "ক্রোম"],
    "camera": ["camera", "ক্যামেরা"],
    "gallery": ["gallery", "গ্যালারি"],
    "photos": ["photos", "ফটো", "ফটোস"],
    "settings": ["settings", "setting", "সেটিংস", "সেটিং"],
    "maps": ["maps", "map", "ম্যাপ", "ম্যাপস", "গুগল ম্যাপ"],
    "gmail": ["gmail", "জিমেইল"],
    "phone": ["phone", "dialer", "ফোন", "ডায়ালার"],
    "messages": ["messages", "মেসেজ", "মেসেজেস"],
    "calculator": ["calculator", "ক্যালকুলেটর"],
    "clock": ["clock", "ক্লক", "ঘড়ি"],
    "play store": ["play store", "প্লে স্টোর"],
    "spotify": ["spotify", "স্পটিফাই"],
    "netflix": ["netflix", "নেটফ্লিক্স"],
    "tiktok": ["tiktok", "টিকটক"],
    "files": ["files", "ফাইল", "ফাইলস"],
    "contacts": ["contacts", "কন্টাক্টস", "কন্টাক্ট"],
    "calendar": ["calendar", "ক্যালেন্ডার"],
    "bkash": ["bkash", "বিকাশ"],
    "nagad": ["nagad", "নগদ"],
}


def canonical(name):
    n = name.lower().strip()
    for canon, words in ALIASES.items():
        if n == canon or n in [w.lower() for w in words]:
            return canon
    return n


def match_app(name, apps):
    """apps = [(label, package)]. Returns (label, package) or None."""
    n = canonical(name)
    low = [(l.lower(), l, p) for l, p in apps]
    for ll, l, p in low:
        if ll == n:
            return l, p
    for ll, l, p in low:
        if n and n in ll:
            return l, p
    best = None
    for ll, l, p in low:
        r = difflib.SequenceMatcher(None, n, ll).ratio()
        if r >= 0.78 and (best is None or r > best[0]):
            best = (r, l, p)
    return (best[1], best[2]) if best else None


# ------------------------------------------------------------------ contacts
_BN = {"ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng", "চ": "ch", "ছ": "chh",
       "জ": "j", "ঝ": "jh", "ঞ": "n", "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh",
       "ণ": "n", "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n", "প": "p",
       "ফ": "f", "ব": "b", "ভ": "bh", "ম": "m", "য": "y", "র": "r", "ল": "l",
       "শ": "sh", "ষ": "sh", "স": "s", "হ": "h", "ড়": "r", "ঢ়": "rh", "য়": "y",
       "ৎ": "t", "ং": "ng", "ঃ": "h", "অ": "o", "আ": "a", "ই": "i", "ঈ": "i",
       "উ": "u", "ঊ": "u", "ঋ": "ri", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
       "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri", "ে": "e",
       "ৈ": "oi", "ো": "o", "ৌ": "ou", "্": "", "ঁ": ""}


def to_latin(s):
    s = s.lower()
    if re.search("[\u0980-\u09FF]", s):
        s = "".join(_BN.get(c, c) for c in s)
    return re.sub(r"[^a-z0-9 ]", "", s)


def find_contacts(query, contacts):
    """contacts = [(name, number)]. Returns unique matches, best first."""
    q = to_latin(query).split()
    if not q:
        return []
    scored = {}
    for name, num in contacts:
        toks = to_latin(name).split()
        if not toks:
            continue
        score = 0.0
        for qt in q:
            best = 0.0
            for t in toks:
                if t == qt:
                    best = max(best, 1.0)
                elif t.startswith(qt) or qt.startswith(t) and len(t) >= 3:
                    best = max(best, 0.9)
                else:
                    best = max(best, difflib.SequenceMatcher(None, qt, t).ratio())
            score += best
        score /= len(q)
        if score >= 0.78:
            key = re.sub(r"\D", "", num)
            if key not in scored or score > scored[key][0]:
                scored[key] = (score, name, num)
    return [(n, p) for s, n, p in sorted(scored.values(), key=lambda x: -x[0])]


_CC = {"bd": "880", "in": "91", "pk": "92", "np": "977", "lk": "94", "us": "1",
       "gb": "44", "ae": "971", "sa": "966", "my": "60", "sg": "65", "ca": "1",
       "au": "61", "qa": "974", "kw": "965", "om": "968"}


def wa_number(num, country_iso):
    """Number -> digits with country code, for wa.me links."""
    n = re.sub(r"[^\d+]", "", num)
    if n.startswith("+"):
        return n[1:]
    if n.startswith("00"):
        return n[2:]
    cc = _CC.get((country_iso or "").lower(), "")
    if n.startswith("0"):
        return cc + n[1:] if cc else n[1:]
    return (cc + n) if (cc and len(n) <= 10) else n


_CANCEL = ("না", "na", "thak", "থাক", "cancel", "বাদ", "bad dao", "bad", "ধন্যবাদ")
_ORD = [("1", "১", "এক", "ek", "first", "প্রথম", "prothom"),
        ("2", "২", "দুই", "dui", "second", "দ্বিতীয়", "ditiyo"),
        ("3", "৩", "তিন", "tin", "third", "তৃতীয়", "tritiyo")]


# ------------------------------------------------------------------ android
if ANDROID:
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")
    PhoneData = autoclass("android.provider.ContactsContract$CommonDataKinds$Phone")
    Locale = autoclass("java.util.Locale")

    @run_on_ui_thread
    def _start(intent):
        try:
            PythonActivity.mActivity.startActivity(intent)
        except Exception:
            pass


class AndroidBackend:
    def __init__(self):
        self.act = PythonActivity.mActivity
        self._contacts = None
        self._contacts_at = 0

    def apps(self):
        pm = self.act.getPackageManager()
        mi = Intent(Intent.ACTION_MAIN)
        mi.addCategory(Intent.CATEGORY_LAUNCHER)
        lst = pm.queryIntentActivities(mi, 0)
        out = []
        for i in range(int(lst.size())):
            ri = cast("android.content.pm.ResolveInfo", lst.get(i))
            out.append((str(ri.loadLabel(pm)), str(ri.activityInfo.packageName)))
        return out

    def has_pkg(self, pkg):
        try:
            return self.act.getPackageManager().getLaunchIntentForPackage(pkg) is not None
        except Exception:
            return False

    def has_contacts_perm(self):
        return bool(check_permission(Permission.READ_CONTACTS))

    def request_contacts_perm(self, cb):
        request_permissions([Permission.READ_CONTACTS],
                            lambda p, g: cb(bool(g) and all(g)))

    def contacts(self):
        if self._contacts is not None and time.time() - self._contacts_at < 60:
            return self._contacts
        cr = self.act.getContentResolver()
        cur = cr.query(PhoneData.CONTENT_URI,
                       [PhoneData.DISPLAY_NAME, PhoneData.NUMBER],
                       None, None, None)
        out = []
        try:
            while cur.moveToNext():
                out.append((str(cur.getString(0)), str(cur.getString(1))))
        finally:
            cur.close()
        self._contacts, self._contacts_at = out, time.time()
        return out

    def country_iso(self):
        try:
            return str(Locale.getDefault().getCountry()).lower()
        except Exception:
            return ""

    def open_pkg(self, pkg):
        it = self.act.getPackageManager().getLaunchIntentForPackage(pkg)
        it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        _start(it)

    def _view(self, url, pkg=None):
        it = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        if pkg:
            it.setPackage(pkg)
        it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        _start(it)

    def whatsapp(self, digits, text):
        url = "https://wa.me/%s?text=%s" % (digits, urllib.parse.quote(text))
        for pkg in ("com.whatsapp", "com.whatsapp.w4b"):
            if self.has_pkg(pkg):
                self._view(url, pkg)
                return
        self._view(url)

    def dial(self, number):
        it = Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + number))
        it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        _start(it)

    def url(self, url):
        self._view(url)


# ------------------------------------------------------------------ brain of the commands
class Actions:
    def __init__(self, backend=None):
        self.b = backend if backend is not None else (
            AndroidBackend() if ANDROID else None)
        self.pending = None

    def handle(self, text, cb):
        """True if `text` was a device command (cb(msg, launch) will answer)."""
        if self.b is None:
            return False
        if self.pending:
            return self._pending(text, cb)
        cmd = parse(text)
        if not cmd:
            return False
        k = cmd["kind"]
        try:
            if k == "open":
                return self._open(cmd, cb)
            if k in ("msg", "call"):
                self._need_contacts(cmd, cb)
                return True
            if k == "yt":
                q = cmd["q"]
                self._reply(cb, "ইউটিউবে \"%s\" খুঁজছি।" % q,
                            lambda: self.b.url("https://www.youtube.com/results?search_query="
                                               + urllib.parse.quote(q)))
                return True
            if k == "web":
                q = cmd["q"]
                self._reply(cb, "গুগলে \"%s\" খুঁজছি।" % q,
                            lambda: self.b.url("https://www.google.com/search?q="
                                               + urllib.parse.quote(q)))
                return True
        except Exception as e:
            self._reply(cb, "কাজটা করতে পারলাম না (%s)।" % type(e).__name__)
            return True
        return False

    # -- helpers
    def _reply(self, cb, msg, launch=None):
        Clock.schedule_once(lambda dt: cb(msg, launch), 0)

    def _open(self, cmd, cb):
        name = cmd["app"]
        found = match_app(name, self.b.apps())
        if found:
            label, pkg = found
            self._reply(cb, "%s খুলছি।" % label, lambda: self.b.open_pkg(pkg))
            return True
        if canonical(name) in ALIASES:          # a known app, but not installed
            self._reply(cb, "%s ফোনে ইনস্টল করা নেই।" % name)
            return True
        return False                             # not an app command: normal chat

    def _need_contacts(self, cmd, cb):
        if self.b.has_contacts_perm():
            self._contact_step(cmd, cb)
            return

        def got(ok):
            if ok:
                Clock.schedule_once(lambda dt: self._contact_step(cmd, cb), 0)
            else:
                self._reply(cb, "কন্টাক্ট দেখার অনুমতি না দিলে নাম দেখে কাজ করতে পারব না।")
        self._reply(cb, "কন্টাক্ট থেকে নম্বর খুঁজতে আপনার অনুমতি লাগবে।")
        self.b.request_contacts_perm(got)

    def _contact_step(self, cmd, cb):
        name = cmd["name"]
        matches = find_contacts(name, self.b.contacts())
        if not matches:
            self._reply(cb, "\"%s\" নামে কোনো কন্টাক্ট খুঁজে পেলাম না।" % name)
            return
        if len(matches) > 1:
            top = matches[:3]
            exact = [m for m in top if to_latin(m[0]) == to_latin(name)]
            if len(exact) == 1:
                matches = exact
            else:
                self.pending = {"kind": "choose", "cmd": cmd, "matches": top}
                listing = "। ".join("%d নম্বর %s" % (i + 1, m[0]) for i, m in enumerate(top))
                self._reply(cb, "একাধিক পেয়েছি: %s। কোনটা, বলুন।" % listing)
                return
        self._act(cmd, matches[0], cb)

    def _act(self, cmd, contact, cb):
        cname, number = contact
        if cmd["kind"] == "call":
            self._reply(cb, "%s-এর নম্বর ডায়ালারে খুলছি। কল বাটন আপনি চাপবেন।" % cname,
                        lambda: self.b.dial(number))
            return
        text = cmd.get("text", "").strip()
        if not text:
            self.pending = {"kind": "text", "cmd": cmd, "contact": contact}
            self._reply(cb, "%s-কে কী লিখব?" % cname)
            return
        digits = wa_number(number, self.b.country_iso())
        self._reply(cb, "%s-কে লেখাটা সাজিয়ে হোয়াটসঅ্যাপ খুলছি। সেন্ড বাটন আপনি চাপবেন।" % cname,
                    lambda: self.b.whatsapp(digits, text))

    def _pending(self, text, cb):
        p, self.pending = self.pending, None
        low = _norm(text).lower()
        if low in _CANCEL:
            self._reply(cb, "ঠিক আছে, বাদ দিলাম।")
            return True
        if p["kind"] == "text":
            cmd = dict(p["cmd"])
            cmd["text"] = text.strip()
            self._act(cmd, p["contact"], cb)
            return True
        if p["kind"] == "choose":
            pick = None
            for i, words in enumerate(_ORD[:len(p["matches"])]):
                if any(re.search(r"(?<!\S)%s(?!\S)" % re.escape(w), low) for w in words):
                    pick = p["matches"][i]
            if pick is None:
                hit = find_contacts(low, p["matches"])
                if len(hit) == 1:
                    pick = hit[0]
            if pick is None:
                self.pending = p
                self._reply(cb, "বুঝতে পারিনি। ১, ২ বা ৩ নম্বর বলুন, ঠিক না হলে \"থাক\" বলুন।")
                return True
            self._act(p["cmd"], pick, cb)
            return True
        return False
