import threading
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

STOP_WORDS = ["exit", "quit", "stop", "shutdown", "বন্ধ", "বন্ধ করো",
              "বন্ধ হও", "জার্ভিস বন্ধ", "off", "turn off", "goodbye", "বিদায়"]
WAKE_WORDS = ("jarvis", "জার্ভিস", "জারভিস")

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

        def __init__(self, on_result, on_error):
            super().__init__()
            self.on_result = on_result
            self.on_error = on_error

        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, params):
            pass

        @java_method("()V")
        def onBeginningOfSpeech(self):
            pass

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
            text = ""
            try:
                lst = bundle.getStringArrayList(
                    SpeechRecognizer.RESULTS_RECOGNITION)
                if lst is not None and lst.size() > 0:
                    text = str(lst.get(0))
            except Exception:
                text = ""
            self.on_result(text)

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
                h.lis = _RecListener(h._res, h._err)
                h.rec = SpeechRecognizer.createSpeechRecognizer(
                    PythonActivity.mActivity)
                h.rec.setRecognitionListener(h.lis)
            it = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            it.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            it.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang)
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

    def speak(self, text, add=False):
        if not self.ready or not text:
            return False
        try:
            mode = (TextToSpeech.QUEUE_ADD if add
                    else TextToSpeech.QUEUE_FLUSH)
            r = self.tts.speak(text, mode, Bundle(), "jarvis")
            if r != 0:
                self.msg = "speak() error code %s" % r
                return False
            return True
        except Exception as e:
            self.msg = "speak() fail: " + type(e).__name__
            return False

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

    def listen(self, lang, cb):
        self.cb = cb
        _ui_start(self, lang)

    def _res(self, text):
        Clock.schedule_once(lambda dt: self.cb and self.cb(text, None), 0)

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

    def __init__(self, ask, clean, on_status, on_text, lang_fn):
        self.ask, self.clean = ask, clean
        self.on_status, self.on_text, self.lang_fn = on_status, on_text, lang_fn
        self.speaker = Speaker() if ANDROID else None
        self.listener = Listener() if ANDROID else None
        self.active = False
        self.mode = "wake"
        self.stage = "wake"
        self.errs = 0
        self.finish = False

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
            self._warn(self.speaker.speak("Hello Nasiruddin. Jarvis is ready."))
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
        self.speaker.speak("Hello Nasiruddin. This is a voice test.", add=True)
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

    def _say(self, text, then_stop=False):
        self.on_status("SPEAKING")
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
                self.on_text("You", text)
                return self._ask(rest)
            self.stage = "command"
            return self._say("জি, বলুন।")
        self.on_text("You", text)
        self._ask(text)

    def _silence(self):
        if self.stage == "command":
            self.stage = "wake" if self.mode == "wake" else "command"
            self._say("আবার বলুন।", then_stop=(self.mode != "wake"))
        else:
            Clock.schedule_once(self._next, 0.2)

    def _ask(self, text):
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
        self._say(self.clean(ans)[:3900], then_stop=(self.mode != "wake"))

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
