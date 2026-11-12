import os, sys, types
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(HERE,"..","src","vendor")); sys.path.insert(0,os.path.join(HERE,"..","src"))
import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk
from lgh.webtiles import WebTile
from lgh import tray as T
tiles=[dict(key="Salon/Kamera", name="KameraC210PIŁS", sub="", kind="generic", on=None, room="Salon", toggle=False),
       dict(key="S/Hub", name="HubH100TAPO", sub="Wyłączono", kind="on-off", on=False, room="Sypialnia", toggle=True),
       dict(key="S/l", name="Lampka_sypialnia_Meross", sub="Włączono", kind="on-off", on=True, room="Sypialnia", toggle=True)]
toggled=[]
app=types.SimpleNamespace(theme=types.SimpleNamespace(dark=True), config={}, backend=types.SimpleNamespace(playing_devices=lambda:[]),
  webtiles=types.SimpleNamespace(state="ok", tiles=[WebTile(t) for t in tiles], toggle=toggled.append), open_web=lambda: toggled.append("WEB"), show_window=lambda:0)
tr=T.Tray(app); m=tr.ind.get_menu()
for it in m.get_children():
    img = it.get_image() if isinstance(it, Gtk.ImageMenuItem) else None
    print(("[dot]" if img else "     "), "SEP" if isinstance(it,Gtk.SeparatorMenuItem) else it.get_label(), "" if it.get_sensitive() else "(disabled)")
    if it.get_label()=="Lampka_sypialnia_Meross": it.activate()
    if it.get_label()=="KameraC210PIŁS": it.activate()
print("activated:", toggled)
for st,name in ((True,"on"),(False,"off"),(None,"na")): T.dot_pixbuf(st).savev(f"/tmp/dot_{name}.png","png",[],[])
