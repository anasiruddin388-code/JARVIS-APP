[app]
title = J.A.R.V.I.S
package.name = jarvis
package.domain = org.nasiruddin
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
version = 0.1
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,openssl
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,RECORD_AUDIO
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
