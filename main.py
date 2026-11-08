import os, socket, threading
from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.graphics import Color, Ellipse
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import NumericProperty
import brain

Window.clearcolor = (0.01, 0.03, 0.09, 1)
CYAN = (0, 0.9, 1, 1)
BTN_BG = (0, 0.15, 0.25, 1)
FIELD_BG = (0, 0.08, 0.16, 1)

def _bn_font():
    for p in ("/system/fonts/NotoSansBengali-Regular.ttf",
              "/system/fonts/NotoSansBengali-VF.ttf",
              "/system/fonts/NotoSansBengaliUI-Regular.ttf",
              "/system/fonts/Lohit-Bengali.ttf",
              "/system/fonts/NotoSerifBengali-Regular.ttf"):
        if os.path.exists(p):
            return p
    return None

BN_FONT = _bn_font()
FONT_KW = {"font_name": BN_FONT} if BN_FONT else {}

class Core(Widget):
    glow = NumericProperty(0.3)
    scale = NumericProperty(1.0)
    on = False

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self.draw, size=self.draw,
                  glow=self.draw, scale=self.draw)

    def draw(self, *args):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.size) / 2 * self.scale
        with self.canvas:
            for i, k in enumerate((1.0, 0.8, 0.6, 0.4)):
                alpha = self.glow * (0.2 + 0.15 * i) if self.on else 0.07
                Color(0, 0.9, 1, alpha)
                d = 2 * r * k
                Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
            Color(0.7, 1, 1, 0.95 if self.on else 0.2)
            d = r * 0.5
            Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))

    def start(self):
        self.on = True
        a = (Animation(glow=1.0, scale=1.0, d=1.2) +
             Animation(glow=0.4, scale=0.9, d=1.2))
        a.repeat = True
        self._anim = a
        a.start(self)

    def stop(self):
        self.on = False
        if hasattr(self, "_anim"):
            self._anim.cancel(self)
        self.glow, self.scale = 0.3, 1.0
        self.draw()

def btn(text, pos_hint=None, size_hint=(0.28, 0.07)):
    kw = {"pos_hint": pos_hint} if pos_hint else {}
    return Button(text=text, size_hint=size_hint, background_normal="",
                  background_color=BTN_BG, color=CYAN, bold=True, **kw)

class HomeScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.powered = False
        self.lang = "EN"
        root = FloatLayout()
        root.add_widget(Label(text="J.A.R.V.I.S", font_size="34sp", bold=True,
                              color=CYAN, size_hint=(1, 0.1),
                              pos_hint={"center_x": .5, "top": .96}))
        root.add_widget(Label(text="Hello Nasiruddin", font_size="20sp",
                              color=(0.6, 0.85, 1, 1), size_hint=(1, 0.06),
                              pos_hint={"center_x": .5, "top": .88}))
        self.core = Core(size_hint=(0.8, 0.4),
                         pos_hint={"center_x": .5, "center_y": .58})
        root.add_widget(self.core)
        self.status = Label(text="STATUS: OFFLINE", font_size="18sp",
                            color=CYAN, size_hint=(1, 0.05),
                            pos_hint={"center_x": .5, "y": .33})
        self.net = Label(text="Internet: checking...", font_size="14sp",
                         color=(0.5, 0.7, 0.9, 1), size_hint=(1, 0.05),
                         pos_hint={"center_x": .5, "y": .28})
        root.add_widget(self.status)
        root.add_widget(self.net)
        self.b_chat = btn("CHAT", {"x": .05, "y": .18})
        self.b_power = btn("POWER ON", {"center_x": .5, "y": .18})
        self.b_voice = btn("VOICE", {"right": .95, "y": .18})
        self.b_lang = btn("LANG: EN", {"x": .05, "y": .08}, (0.4, 0.07))
        self.b_set = btn("SETTINGS", {"right": .95, "y": .08}, (0.4, 0.07))
        self.b_power.bind(on_release=self.toggle_power)
        self.b_chat.bind(on_release=lambda *a: self.go("chat"))
        self.b_voice.bind(on_release=lambda *a: self.soon("Voice"))
        self.b_lang.bind(on_release=self.toggle_lang)
        self.b_set.bind(on_release=lambda *a: self.go("settings"))
        for b in (self.b_chat, self.b_power, self.b_voice,
                  self.b_lang, self.b_set):
            root.add_widget(b)
        self.add_widget(root)
        Clock.schedule_interval(self.check_net, 5)
        self.check_net()

    def go(self, name):
        self.manager.current = name

    def toggle_power(self, *a):
        self.powered = not self.powered
        if self.powered:
            self.core.start()
            self.b_power.text = "POWER OFF"
            self.status.text = "STATUS: ONLINE"
        else:
            self.core.stop()
            self.b_power.text = "POWER ON"
            self.status.text = "STATUS: OFFLINE"

    def toggle_lang(self, *a):
        self.lang = "BN" if self.lang == "EN" else "EN"
        self.b_lang.text = "LANG: " + self.lang

    def soon(self, name):
        self.status.text = name + ": coming in next step"

    def check_net(self, *a):
        def work():
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2).close()
                ok = True
            except OSError:
                ok = False
            Clock.schedule_once(lambda dt: self.set_net(ok))
        threading.Thread(target=work, daemon=True).start()

    def set_net(self, ok):
        self.net.text = "Internet: " + ("Online" if ok else "Offline")

class ChatScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        top = BoxLayout(size_hint=(1, 0.08), spacing=8)
        back = btn("< BACK", size_hint=(0.3, 1))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "home"))
        top.add_widget(back)
        top.add_widget(Label(text="CHAT", color=CYAN, bold=True,
                             font_size="20sp"))
        box.add_widget(top)
        self.scroll = ScrollView(size_hint=(1, 0.74))
        self.log = Label(text="", color=(0.8, 0.95, 1, 1), size_hint_y=None,
                         halign="left", valign="top", **FONT_KW)
        self.log.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                      texture_size=lambda i, s: setattr(i, "height", s[1]))
        self.scroll.add_widget(self.log)
        box.add_widget(self.scroll)
        row = BoxLayout(size_hint=(1, 0.1), spacing=8)
        self.inp = TextInput(multiline=False, hint_text="Message...",
                             background_color=FIELD_BG,
                             foreground_color=(1, 1, 1, 1),
                             cursor_color=CYAN, **FONT_KW)
        self.inp.bind(on_text_validate=self.send)
        send = btn("SEND", size_hint=(0.28, 1))
        send.bind(on_release=self.send)
        row.add_widget(self.inp)
        row.add_widget(send)
        box.add_widget(row)
        self.add_widget(box)

    def add(self, who, text):
        self.log.text += who + ": " + text + "\n\n"
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def send(self, *a):
        text = self.inp.text.strip()
        if not text:
            return
        self.inp.text = ""
        self.add("You", text)
        self.add("JARVIS", "...")
        lang = "bn" if self.manager.get_screen("home").lang == "BN" else "en"

        def work():
            reply = brain.get_reply(text, lang)
            Clock.schedule_once(lambda dt: self.show(reply))
        threading.Thread(target=work, daemon=True).start()

    def show(self, reply):
        self.log.text = self.log.text.rsplit("JARVIS: ...", 1)[0]
        self.add("JARVIS", reply)

class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        box = BoxLayout(orientation="vertical", padding=14, spacing=10)
        back = btn("< BACK", size_hint=(0.3, 0.08))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "home"))
        box.add_widget(back)
        box.add_widget(Label(text="SETTINGS", color=CYAN, bold=True,
                             font_size="22sp", size_hint=(1, 0.08)))
        box.add_widget(Label(text="OpenRouter API Key (only on this phone)",
                             color=(0.6, 0.85, 1, 1), size_hint=(1, 0.06)))
        self.key = TextInput(multiline=False, password=True,
                             size_hint=(1, 0.08), background_color=FIELD_BG,
                             foreground_color=(1, 1, 1, 1))
        box.add_widget(self.key)
        box.add_widget(Label(text="Model name (khali rakhle default)",
                             color=(0.6, 0.85, 1, 1), size_hint=(1, 0.06)))
        self.model = TextInput(multiline=False, size_hint=(1, 0.08),
                               background_color=FIELD_BG,
                               foreground_color=(1, 1, 1, 1))
        box.add_widget(self.model)
        save = btn("SAVE", size_hint=(1, 0.09))
        save.bind(on_release=self.save)
        box.add_widget(save)
        self.msg = Label(text="", color=CYAN, size_hint=(1, 0.08))
        box.add_widget(self.msg)
        box.add_widget(Widget())
        self.add_widget(box)

    def on_pre_enter(self, *a):
        cfg = brain.load_cfg()
        self.model.text = cfg.get("model", "")
        self.msg.text = "Key saved" if cfg.get("api_key") else "Key nei"

    def save(self, *a):
        k = self.key.text.strip()
        if not k:
            self.msg.text = "Key khali, save hoyni"
            return
        brain.save_cfg(k, self.model.text)
        self.key.text = ""
        self.msg.text = "Saved. Ekhon Chat e jao."

class JarvisApp(App):
    title = "J.A.R.V.I.S"

    def build(self):
        brain.set_data_dir(self.user_data_dir)
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(ChatScreen(name="chat"))
        sm.add_widget(SettingsScreen(name="settings"))
        return sm

JarvisApp().run()
