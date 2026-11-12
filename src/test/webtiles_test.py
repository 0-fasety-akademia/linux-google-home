import os, sys, json
SRC=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","src"); sys.path.insert(0,SRC)
os.environ["LGH_HOME_URL"]="file://"+os.path.join(os.path.dirname(os.path.abspath(__file__)),"replica.html")
import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk, GLib
from lgh.webtiles import WebTiles, shared_context
log=[]
def upd():
    log.append([(t.key,t.on) for t in wt.tiles]); print("UPDATE", wt.state, log[-1], flush=True)
wt=WebTiles(shared_context(), upd)
GLib.timeout_add(5000, lambda: (print("TOGGLE"), wt.toggle("Sypialnia/Lampka_sypialnia_Meross"), False)[2])
GLib.timeout_add(10000, lambda: (Gtk.main_quit(), False)[1])
Gtk.main()
final=dict(log[-1]); print("FINAL", final)
assert final["Sypialnia/Lampka_sypialnia_Meross"] is True and final["Salon/KameraC210PIŁS"] is None and len(final)==5
print("PASS")
