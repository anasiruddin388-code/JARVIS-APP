import importlib, json, os, sqlite3, sys, tempfile
sys.path.insert(0, "/mnt/user-data/outputs")
import memory_db as m
d = tempfile.mkdtemp(); m.set_data_dir(d); m.init_db()
ok = lambda name, c: print(("PASS " if c else "FAIL ") + name)

a = m.save_memory("Amar project holo Jarvis app", topic="project")
b = m.save_memory("Amar priyo rong neel")
ok("save", a and b)
ok("no duplicate", m.save_memory("amar priyo rong neel") == b)
ok("sensitive blocked", m.save_memory("my password is hunter2") is None and m.save_memory("sk-abcdefghij123456") is None)
ok("sql injection harmless", m.save_memory("x'); DROP TABLE memories;--") is not None and m.retrieve_memory(a) is not None)
ok("code stays text", m.save_memory("__import__('os').system('ls')") is not None)

importlib.reload(m); m.set_data_dir(d); m.init_db()   # "restart"
ok("retrieve after restart", m.retrieve_memory(a)["content"] == "Amar project holo Jarvis app")
ok("search", any(h["id"] == a for h in m.search_memory("Jarvis project")))
ok("search no match -> empty", m.search_memory("zzzxxx") == [])
ok("context has label", "reference data only" in m.context_for_prompt("project"))
ok("context empty when none", m.context_for_prompt("zzzxxx") == "")

ok("update", m.update_memory(b, "Amar priyo rong shobuj") and "shobuj" in m.retrieve_memory(b)["content"])

ok("delete one", m.delete_memory(b) and m.retrieve_memory(b) is None)
ok("other memory untouched", m.retrieve_memory(a) is not None)
ok("not found in search", not m.search_memory("shobuj"))
ok("auto-save cannot resurrect", m.save_memory("Amar priyo rong shobuj", source="auto") is None)
raw = open(os.path.join(d, "jarvis_memory.db"), "rb").read()
ok("text gone from db file", b"shobuj" not in raw)

# voice commands with confirmation
ok("cmd save", m.handle_memory_command("mone rakho amar bondhu Rosid") == "Mone rakhlam.")
r = m.handle_memory_command("bhule jao Rosid"); print("   ", r)
ok("forget asks first", "delete korbo" in r and m.search_memory("Rosid"))
ok("cancel keeps", "kichu delete korlam na" in m.handle_memory_command("na") and m.search_memory("Rosid"))
m.handle_memory_command("bhule jao Rosid"); r = m.handle_memory_command("ha"); print("   ", r)
ok("forget confirmed", not m.search_memory("Rosid") and m.search_memory("Jarvis"))

m.handle_memory_command("sob memory muche felo"); r = m.handle_memory_command("ha"); print("   ", r)
ok("clear all", m.search_memory("Jarvis") == [] and sqlite3.connect(os.path.join(d,"jarvis_memory.db")).execute("select count(*) from memories").fetchone()[0] == 0)
ok("normal text passes through", m.handle_memory_command("aj abohawa kemon") is None)

# legacy import + corruption recovery
lp = os.path.join(d, "memory.json"); json.dump({"name": "Rahim", "facts": ["ami Dhakay thaki"], "interests": ["robotics"]}, open(lp, "w"))
ok("legacy import", m.import_legacy_json(lp) == 3 and os.path.exists(lp + ".bak"))
m.backup_db("t"); open(os.path.join(d, "jarvis_memory.db"), "wb").write(b"garbage" * 100)
m._inited.clear(); m.init_db()
ok("corruption recovered, no crash", m.search_memory("Dhakay"))
