import re, threading
from kivy.clock import Clock

try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    from android.permissions import request_permissions, Permission
    ANDROID = True
except Exception:
    ANDROID = False

    def run_on_ui_thread(f):
        return f

# mood tag from the AI -> (pitch, speech rate) of the voice
MOODS = {"খুশি": (1.15, 1.05), "মজা": (1.12, 1.1), "উত্তেজিত": (1.2, 1.15),
         "মন খারাপ": (0.85, 0.85), "দুঃখ": (0.85, 0.85), "চিন্তিত": (0.95, 0.92),
         "আদর": (1.05, 0.95), "ঘুম": (0.9, 0.85)}


def mood_params(mood):
    for key, val in MOODS.items():
        if key in (mood or ""):
            return val
    return (1.0, 1.0)


STOP_WORDS = ["exit", "quit", "stop", "shutdown", "বন্ধ", "বন্ধ করো",
              "বন্ধ হও", "জার্ভিস বন্ধ", "off", "turn off", "goodbye", "বিদায়"]
WAKE_WORDS = ("jarvis", "jarvish", "jervis", "zarvis", "gervis", "জার্ভিস",
              "জারভিস", "জার্ভিশ", "জারভিশ", "জার্বিস", "জারবিস", "জার্ভীস",
              "জারভীস", "জারভিজ", "জার্ভিজ")

ERR_TEXT = {
    1: "Internet slow. Google speech-er jonno internet lagbe.",
    2: "Internet nei. Google speech-er jonno internet lagbe.",
    3: "Microphone-e somoshya.",
    4: "Google speech server-e somoshya.",
    9: "Microphone permission deoa hoyni.",
    10: "Onek beshi request. Ektu pore try koro.",
    11: "Speech service bondho hoye geche.",
    12: "Ei bhasha-r speech phone-e nei. LANG EN kore dekho.",
    13: "Ei bhasha-r speech ekhon pawa jachhe na. LANG EN kore dekho.",
    -1: "Speech recognizer chalu kora gelo na (phone-e Google app ache?).",
}


def should_stop(text):
    return text.lower().strip(" .!?।,") in STOP_WORDS


if ANDROID:
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Locale = autoclass("java.util.Locale")
    Bundle = autoclass("android.os.Bundle")
    HashMap = autoclass("java.util.HashMap")
    Intent = autoclass("android.content.Intent")
    TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
    RecognizerIntent = autoclass("android.speech.RecognizerIntent")
    LayoutParams = autoclass("android.view.WindowManager$LayoutParams")

    class _TtsInit(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"

        def __init__(self, cb):
            super().__init__()
            self.cb = cb

        @java_method("(I)V")
        def onInit(self, status):
            self.cb(status)

    class _RecListener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/RecognitionListener"]
        __javacontext__ = "app"

        def __init__(self, on_result, on_error, on_begin=None):
            super().__init__()
            self.on_result = on_result
            self.on_error = on_error
            self.on_begin = on_begin

        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, params):
            pass

        @java_method("()V")
        def onBeginningOfSpeech(self):
            if self.on_begin:
                self.on_begin()

        @java_method("(F)V")
        def onRmsChanged(self, rms):
            pass

        @java_method("([B)V")
        def onBufferReceived(self, buf):
            pass

        @java_method("()V")
        def onEndOfSpeech(self):
            pass

        @java_method("(I)V")
        def onError(self, code):
            self.on_error(code)

        @java_method("(Landroid/os/Bundle;)V")
        def onResults(self, bundle):
            texts = []
            try:
                lst = bundle.getStringArrayList(
                    SpeechRecognizer.RESULTS_RECOGNITION)
                if lst is not None:
                    for i in range(min(int(lst.size()), 5)):
                        texts.append(str(lst.get(i)))
            except Exception:
                texts = []
            self.on_result(texts)

        @java_method("(Landroid/os/Bundle;)V")
        def onPartialResults(self, bundle):
            pass

        @java_method("(ILandroid/os/Bundle;)V")
        def onEvent(self, etype, params):
            pass

    @run_on_ui_thread
    def _ui_start(h, lang):
        try:
            if h.rec is None:
                h.lis = _RecListener(h._res, h._err, h._began)
                h.rec = SpeechRecognizer.createSpeechRecognizer(
                    PythonActivity.mActivity)
                h.rec.setRecognitionListener(h.lis)
            it = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            it.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            it.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang)
            h.lang = lang
            try:     # more alternatives + wait longer before cutting the sentence
                ex = Bundle()
                ex.putInt(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
                ex.putLong(RecognizerIntent
                           .EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1800)
                ex.putLong(RecognizerIntent
                           .EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1500)
                ex.putLong(RecognizerIntent
                           .EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 2500)
                it.putExtras(ex)
            except Exception:
                pass
            h.rec.startListening(it)
        except Exception:
            h._err(-1)

    @run_on_ui_thread
    def _ui_stop(h, destroy):
        try:
            if h.rec is not None:
                h.rec.cancel()
                if destroy:
                    h.rec.destroy()
                    h.rec = None
        except Exception:
            pass

    @run_on_ui_thread
    def _dim_ui(level):
        """level 0.01 = almost black screen, -1 = back to normal brightness."""
        try:
            w = PythonActivity.mActivity.getWindow()
            lp = w.getAttributes()
            lp.screenBrightness = float(level)
            w.setAttributes(lp)
        except Exception:
            pass

    @run_on_ui_thread
    def _keep_on(flag):
        try:
            w = PythonActivity.mActivity.getWindow()
            if flag:
                w.addFlags(LayoutParams.FLAG_KEEP_SCREEN_ON)
            else:
                w.clearFlags(LayoutParams.FLAG_KEEP_SCREEN_ON)
        except Exception:
            pass
else:
    def _dim_ui(level): pass
    def _ui_start(h, lang): pass
    def _ui_stop(h, destroy): pass
    def _keep_on(flag): pass


class Speaker:
    def __init__(self):
        self.tts = None
        self.ready = False
        self.msg = "Voice output ekhono ready hoyni."
        self.engine = ""
        self.lang = ""

    def init(self):
        if self.tts is not None:
            return
        try:
            self._l = _TtsInit(self._on_init)
            self.tts = TextToSpeech(PythonActivity.mActivity, self._l)
        except Exception as e:
            self.msg = "Voice output chalu hoyni: " + type(e).__name__

    def _on_init(self, status):
        if self.tts is None:                      # callback came too early
            Clock.schedule_once(lambda dt: self._on_init(status), 0.1)
            return
        if status != 0:
            self.msg = ("Voice output chalu hoyni (TTS engine nei ba block). "
                        "Phone Settings-e Text-to-speech engine thik koro.")
            return
        try:
            self.engine = str(self.tts.getDefaultEngine())
        except Exception:
            self.engine = "?"
        code = -2
        for loc in (Locale("bn", "BD"), Locale("bn", "IN"), Locale("bn")):
            try:
                r = self.tts.setLanguage(loc)
            except Exception:
                r = -2
            code = r
            if r >= 0:
                self.lang = str(loc.toString())
                break
        if code < 0:
            self.msg = ("Phone-e Bengali voice nei (code %s). Bengali uttor "
                        "shona jabe na." % code)
        else:
            self.msg = ""
        self.ready = True

    def info(self):
        if not self.ready:
            return self.msg
        eng = self.engine.split(".")[-1] if self.engine else "?"
        if self.lang:
            return "Voice engine: %s | Bengali: OK (%s)" % (eng, self.lang)
        return "Voice engine: %s | Bengali voice NEI. %s" % (eng, self.msg)

    @staticmethod
    def _chunks(text, limit=180):
        parts = re.split(r"(?<=[।?!.])\s+|\n+", text)
        out, cur = [], ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if cur and len(cur) + len(p) > limit:
                out.append(cur)
                cur = p
            else:
                cur = (cur + " " + p).strip()
        if cur:
            out.append(cur)
        return out or [text]

    def _speak_one(self, text, mode):
        first_err = ""
        for how in (0, 1, 2):
            try:
                if how == 0:
                    r = self.tts.speak(text, mode, Bundle(), "jarvis")
                elif how == 1:
                    r = self.tts.speak(text, mode, None)
                else:
                    r = self.tts.speak(text, mode, HashMap())
                if r == 0:
                    return True, ""
                if not first_err:
                    first_err = "code %s" % r
            except Exception as e:
                if not first_err:
                    first_err = repr(e)[:160]
        return False, first_err

    def speak(self, text, add=False):
        """Speaks sentence by sentence (more natural, nothing gets cut)."""
        if not self.ready or not text:
            return False
        flush = TextToSpeech.QUEUE_FLUSH
        queue = TextToSpeech.QUEUE_ADD
        ok_all = True
        for i, chunk in enumerate(self._chunks(text)):
            mode = flush if (i == 0 and not add) else queue
            ok, err = self._speak_one(chunk, mode)
            if not ok:
                self.msg = "speak() fail: " + err
                ok_all = False
                break
        return ok_all

    def set_mood(self, mood):
        pitch, rate = mood_params(mood)
        try:
            if self.ready:
                self.tts.setPitch(float(pitch))
                self.tts.setSpeechRate(float(rate))
        except Exception:
            pass

    def busy(self):
        try:
            return bool(self.ready and self.tts.isSpeaking())
        except Exception:
            return False

    def stop(self):
        try:
            if self.ready:
                self.tts.stop()
        except Exception:
            pass

    def shutdown(self):
        try:
            if self.tts is not None:
                self.tts.stop()
                self.tts.shutdown()
        except Exception:
            pass
        self.tts = None
        self.ready = False


class Listener:
    def __init__(self):
        self.rec = None
        self.lis = None
        self.cb = None
        self.lang = ""
        self.began = False

    def _began(self):
        self.began = True

    def listen(self, lang, cb):
        self.cb = cb
        self.began = False
        _ui_start(self, lang)

    def _res(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        texts = [t for t in texts if t and t.strip()]
        best = texts[0] if texts else ""
        if str(getattr(self, "lang", "")).startswith("bn"):
            for t in texts:                      # prefer an answer in Bengali script
                if re.search("[\u0980-\u09FF]", t):
                    best = t
                    break
        Clock.schedule_once(lambda dt: self.cb and self.cb(best, None), 0)

    def _err(self, code):
        Clock.schedule_once(lambda dt: self.cb and self.cb("", code), 0)

    def cancel(self):
        self.cb = None
        _ui_stop(self, False)

    def reset(self):
        _ui_stop(self, True)


class Voice:
    """Wake-word loop is the same logic as the Termux controller.py:
    wait for 'Jarvis' -> 'জি, বলুন।' -> listen command -> answer by voice."""

    def __init__(self, ask, clean, on_status, on_text, lang_fn,
                 actions=None, mood_fn=None, err_fn=None):
        self.actions, self.mood_fn, self.err_fn = actions, mood_fn, err_fn
        self.ask, self.clean = ask, clean
        self.on_status, self.on_text, self.lang_fn = on_status, on_text, lang_fn
        self.speaker = Speaker() if ANDROID else None
        self.listener = Listener() if ANDROID else None
        self.active = False
        self.mode = "wake"
        self.stage = "wake"
        self.errs = 0
        self.finish = False
        self.buf = ""
        self._tok = 0

    def start(self, mode):
        if not ANDROID:
            self.on_status("Eta shudhu Android phone-e kaj kore")
            return
        if self.active:
            return
        self.mode = mode
        self.on_status("Mic permission chaichhi...")
        request_permissions([Permission.RECORD_AUDIO], self._perm)

    def _perm(self, perms, grants):
        ok = bool(grants) and all(grants)
        Clock.schedule_once(lambda dt: self._begin() if ok else self._deny(), 0)

    def _deny(self):
        self.on_status("READY")
        self.on_text("JARVIS", "Mic permission deoa hoyni, tai Voice cholbe na.")

    def _begin(self):
        self.active = True
        self.errs = 0
        self.finish = False
        self.stage = "wake" if self.mode == "wake" else "command"
        self.speaker.init()
        _keep_on(True)
        Clock.schedule_once(self._boot, 1.2)

    def _boot(self, dt=0):
        if not self.active:
            return
        self._tries = getattr(self, "_tries", 0) + 1
        if not self.speaker.ready and self._tries < 8:
            Clock.schedule_once(self._boot, 0.5)     # wait for TTS engine
            return
        self._tries = 0
        self.on_text("JARVIS", self.speaker.info())
        if self.mode == "wake":
            self._warn(self.speaker.speak("হ্যালো নাসিরউদ্দিন। জার্ভিস প্রস্তুত।"))
            self.on_text("JARVIS", "'Jarvis' bolo.")
        Clock.schedule_once(self._next, 0.6)

    def _warn(self, ok):
        if not ok and not getattr(self, "_warned", False):
            self._warned = True
            self.on_text("JARVIS", "(Voice output hochhe na: "
                         + (self.speaker.msg or "karon jani na") + ")")

    def test(self):
        """TEST VOICE button: speaks a Bengali and an English sample."""
        if not ANDROID:
            self.on_status("Eta shudhu Android phone-e kaj kore")
            return
        self.speaker.init()
        self._tries = 0
        self._test_wait()

    def _test_wait(self, dt=0):
        self._tries = getattr(self, "_tries", 0) + 1
        if not self.speaker.ready and self._tries < 8:
            Clock.schedule_once(self._test_wait, 0.5)
            return
        self._tries = 0
        self.on_text("JARVIS", self.speaker.info())
        ok = self.speaker.speak("আমি জার্ভিস। আপনি কি আমার কথা শুনতে পাচ্ছেন?")
        self.speaker.speak("হ্যালো নাসিরউদ্দিন। জার্ভিস প্রস্তুত।", add=True)
        if not ok:
            self.on_text("JARVIS", "(Voice output hochhe na: "
                         + (self.speaker.msg or "karon jani na") + ")")

    def _next(self, dt=0):
        if not self.active:
            return
        if self.speaker.busy():
            Clock.schedule_once(self._next, 0.3)
            return
        if self.finish:
            self.stop()
            return
        Clock.schedule_once(self._listen, 0.4)

    def _listen(self, dt):
        if not self.active:
            return
        if self.speaker.busy():
            Clock.schedule_once(self._next, 0.3)
            return
        self.on_status("LISTENING")
        self.listener.listen(self.lang_fn(), self._heard)

    def _say(self, text, then_stop=False, mood=""):
        self.on_status("SPEAKING")
        self.speaker.set_mood(mood)
        self._warn(self.speaker.speak(text))
        self.finish = then_stop
        Clock.schedule_once(self._next, 0.7)

    def _fatal(self, msg):
        self.on_text("JARVIS", msg)
        self.stop()

    def _heard(self, text, err):
        if not self.active:
            return
        if err is not None:
            if err in (6, 7):
                return self._silence()
            if err in (5, 8):
                self.errs += 1
                if self.errs >= 4:
                    return self._fatal("Speech recognizer chalu hochhe na.")
                self.listener.reset()
                Clock.schedule_once(self._next, 1.0)
                return
            self.errs += 1
            msg = ERR_TEXT.get(err, "Speech error " + str(err))
            if err in (9, 12, 13, -1) or self.errs >= 3:
                return self._fatal(msg)
            Clock.schedule_once(self._next, 1.5)
            return
        self.errs = 0
        low = text.lower().strip()
        if not low:
            return self._silence()
        if should_stop(low):
            self.on_text("You", text)
            self._say("জার্ভিস বন্ধ হচ্ছে।")
            Clock.schedule_once(lambda dt: self.stop(), 3.0)
            return
        if self.stage == "wake":
            hit = next((w for w in WAKE_WORDS if w in low), None)
            if not hit:
                Clock.schedule_once(self._next, 0.1)
                return
            rest = low.replace(hit, "", 1).strip(" ,.!?।")
            if len(rest) > 2:
                return self._collect(rest)
            self.stage = "command"
            return self._say("জি, বলুন।")
        self._collect(text)

    # ---- long questions: keep listening a little after a pause ----
    def _collect(self, text):
        self.buf = (self.buf + " " + text).strip()
        self._tok += 1
        tok = self._tok
        self.on_status("LISTENING")
        self.listener.listen(self.lang_fn(),
                             lambda t, e, tk=tok: self._cont(t, e, tk))
        Clock.schedule_once(lambda dt: self._cont_timeout(tok), 1.7)

    def _cont(self, text, err, tok):
        if not self.active or tok != self._tok:
            return
        if err is not None or not text.strip():
            return self._finish_collect()
        self._collect(text)                      # more words came: keep joining

    def _cont_timeout(self, tok):
        if not self.active or tok != self._tok:
            return
        if self.listener.began:                  # he is speaking again: wait
            Clock.schedule_once(lambda dt: self._cont_timeout(tok), 1.0)
            return
        self.listener.cancel()
        self._finish_collect()

    def _finish_collect(self):
        self._tok += 1
        text, self.buf = self.buf.strip(), ""
        if not text:
            return self._silence()
        self.on_text("You", text)
        self._ask(text)

    def _silence(self):
        if self.stage == "command":
            self.stage = "wake" if self.mode == "wake" else "command"
            self._say("আবার বলুন।", then_stop=(self.mode != "wake"))
        else:
            Clock.schedule_once(self._next, 0.2)

    # ---- device commands (open apps, WhatsApp, call ...): only when he says so ----
    def _act_reply(self, msg, launch=None):
        if not self.active:
            return
        self.on_text("JARVIS", msg)
        keep = bool(self.actions and self.actions.pending)
        self.stage = "command" if keep else ("wake" if self.mode == "wake"
                                              else "command")
        self.on_status("SPEAKING")
        self.speaker.set_mood("খুশি")
        self._warn(self.speaker.speak(self.clean(msg)))
        self.finish = (self.mode != "wake") and not keep
        if launch:
            Clock.schedule_once(lambda dt: self._launch_when_quiet(launch, 0), 0.8)
        else:
            Clock.schedule_once(self._next, 0.7)

    def _launch_when_quiet(self, launch, waited):
        if not self.active:
            return
        if self.speaker.busy() and waited < 7:
            Clock.schedule_once(
                lambda dt: self._launch_when_quiet(launch, waited + 0.3), 0.3)
            return
        try:
            launch()                   # the other app opens; Android pauses us
        except Exception as e:
            self.on_text("JARVIS", "(খুলতে পারলাম না: %s)" % type(e).__name__)
        Clock.schedule_once(self._next, 2.5)

    def _ask(self, text):
        if self.actions:
            try:
                if self.actions.handle(text, self._act_reply):
                    self.on_status("THINKING")
                    return
            except Exception:
                pass
        self.on_status("THINKING")

        def work():
            try:
                ans = self.ask(text)
            except Exception:
                ans = "দুঃখিত, এখন উত্তর দিতে পারছি না।"
            Clock.schedule_once(lambda dt: self._answer(ans), 0)
        threading.Thread(target=work, daemon=True).start()

    def _answer(self, ans):
        if not self.active:
            return
        self.on_text("JARVIS", ans)
        self.stage = "wake" if self.mode == "wake" else "command"
        mood = self.mood_fn() if self.mood_fn else ""
        spoken = self.clean(ans)[:3900]
        if self.err_fn and self.err_fn():       # do not read error details aloud
            spoken, mood = "দুঃখিত, এখন উত্তর দিতে পারছি না।", "মন খারাপ"
        self._say(spoken, then_stop=(self.mode != "wake"), mood=mood)

    def stop(self):
        was = self.active
        self.active = False
        self.finish = False
        if ANDROID:
            try:
                self.listener.cancel()
                self.speaker.stop()
                _keep_on(False)
            except Exception:
                pass
        if was:
            self.on_status("READY")

    def dim(self, flag):
        _dim_ui(0.01 if flag else -1.0)

    def shutdown(self):
        self.active = False
        if ANDROID:
            try:
                self.listener.cancel()
                self.listener.reset()
                self.speaker.shutdown()
                _keep_on(False)
            except Exception:
                pass
