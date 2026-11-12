import os, sys, time, asyncio
SRC=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","src"); sys.path.insert(0,os.path.join(SRC,"vendor")); sys.path.insert(0,SRC)
import lgh.backend as B
log=[]
class FakeRemote:
    def __init__(s, **kw): s.kw=kw; s.is_on=True; s.current_app=None; s.volume_info=None; s.cbs=[]
    async def async_generate_cert_if_missing(s): pass
    async def async_connect(s): log.append("connect ime=%s"%s.kw["enable_ime"])
    def disconnect(s): log.append("disconnect")
    def keep_reconnecting(s, cb): log.append("keep_reconnecting")
    def send_key_command(s, k): log.append("key "+k)
    def add_is_on_updated_callback(s,c): pass
    add_current_app_updated_callback=add_volume_info_updated_callback=add_is_available_updated_callback=add_is_on_updated_callback
B.AndroidTVRemote=FakeRemote
be=B.Backend("/tmp/lghcfg2", lambda d:None, lambda d:None, lambda *a:None)
be._loop_thread.start()
be._atv_found("TV","10.0.0.5",6466); time.sleep(0.5)
d=list(be.devices.values())[0]; print("after discovery:", d.atv_state, log)
# fast-forward idle watch: patch idle threshold by setting last_use in past
time.sleep(6); print("after probe idle:", d.atv_state, log[-1])
be.key(d,"KEYCODE_DPAD_UP"); time.sleep(0.3); print("after key:", d.atv_state, log[-2:])
d._atv_last_use -= 100; time.sleep(6); print("after 90s idle:", d.atv_state, log[-1])
be.apply_remote_settings("always", True); time.sleep(0.5); print("always+ime:", d.atv_state, log[-3:])
os._exit(0)
