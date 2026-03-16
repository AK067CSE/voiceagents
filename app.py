"""
app.py — Streamlit Voice Agent UI  ★ UPGRADED ★
=================================================
Changes vs original:
  • TTS provider selector (Deepgram / Cartesia / ElevenLabs)
  • Voice / model picker per provider
  • Real-time env validation per provider
  • Model info panel with latency / quality ratings
  • Better dark-mode UI
  • Injects provider vars to subprocess so voice_agent.py picks them up
  • Install checker — warns if provider plugin is missing

Run:  streamlit run app.py
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Voice Agent", page_icon="🎙️", layout="wide")

# ── Env base ──────────────────────────────────────────────────────────────────
LK_URL    = os.getenv("LIVEKIT_URL", "")
LK_KEY    = os.getenv("LIVEKIT_API_KEY", "")
LK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
DG_KEY    = os.getenv("DEEPGRAM_API_KEY", "")
G_KEY     = os.getenv("GOOGLE_API_KEY", "")
CA_KEY    = os.getenv("CARTESIA_API_KEY", "")
EL_KEY    = os.getenv("ELEVEN_API_KEY", "")

ROOM            = "voice-agent-room"
TRANSCRIPT_FILE = Path(os.getenv("TRANSCRIPT_FILE", "transcripts.json"))

# ── TTS Provider definitions ──────────────────────────────────────────────────
TTS_PROVIDERS = {
    "deepgram": {
        "label": "Deepgram Aura-2",
        "icon": "🔵",
        "latency": "~200ms",
        "quality": "★★★★☆",
        "desc": "Enterprise-grade clarity, 40+ voices, unified STT+TTS infrastructure.",
        "voices": {
            "Luna (Natural conversational)":  "aura-2-luna-en",
            "Thalia (Warm & clear)":          "aura-2-thalia-en",
            "Arcas (Deep, authoritative)":    "aura-2-arcas-en",
            "Stella (Bright & friendly)":     "aura-2-stella-en",
            "Andromeda (Calm & smooth)":      "aura-2-andromeda-en",
            "Helios (Professional male)":     "aura-2-helios-en",
            "Orpheus (Rich & expressive)":    "aura-2-orpheus-en",
        },
        "env_needed": {"DEEPGRAM_API_KEY": DG_KEY},
        "model_env":  "DEEPGRAM_VOICE",
        "pip":        None,
    },
    "cartesia": {
        "label": "Cartesia Sonic-3",
        "icon": "⚡",
        "latency": "~90ms",
        "quality": "★★★★★",
        "desc": "Fastest TTS on the market. Sub-100ms, emotion controls, voice cloning.",
        "voices": {
            "Katie (Warm American, agent-optimized)": "f786b574-daa5-4673-aa0c-cbe3e8534c02",
            "Kiefer (Confident professional male)":   "228fca29-3a0a-435c-8cb483251068",
            "Sophie (British RP)":                    "63ff761f-c1e8-414b-b969-d1833d1c870c",
        },
        "env_needed": {"CARTESIA_API_KEY": CA_KEY},
        "model_env":  "CARTESIA_VOICE",
        "pip":        "livekit-plugins-cartesia",
    },
    "elevenlabs": {
        "label": "ElevenLabs Flash v2.5",
        "icon": "✨",
        "latency": "~75ms",
        "quality": "★★★★★",
        "desc": "Ultra-low 75ms latency, 32 languages, emotion tags, voice cloning.",
        "voices": {
            "Sarah (Warm & natural)":    "EXAVITQu4vr4xnSDxMaL",
            "Alice (British accent)":    "Xb7hH8MSUJpSbSDYk0k2",
            "Bill (Deep & confident)":   "pqHfZKP75CvOlQylNhV4",
            "George (Warm British male)": "JBFqnCBsd6RMkjVDRZzb",
            "Charlotte (Seductive)":     "XB0fDUnXU5powFXDhCwa",
            "Aria (Expressive female)":  "9BWtsMINqrJLrRacOk9x",
        },
        "env_needed": {"ELEVEN_API_KEY": EL_KEY},
        "model_env":  "ELEVENLABS_VOICE",
        "pip":        "livekit-plugins-elevenlabs",
    },
}

STT_MODELS = {
    "Flux (built-in EoT, best for agents)": "true",
    "Nova-3 (multilingual, code-switch)":   "false",
}

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"proc": None, "running": False, "token": None, "t_len": 0}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────
def lk_ok():
    return all([LK_URL, LK_KEY, LK_SECRET])

def base_ok():
    return all([DG_KEY, G_KEY]) and lk_ok()

def provider_ok(provider: str) -> bool:
    pdef = TTS_PROVIDERS[provider]
    return all(pdef["env_needed"].values())

def make_token():
    try:
        from livekit import api
        return (
            api.AccessToken(LK_KEY, LK_SECRET)
            .with_identity("ui-user")
            .with_name("Voice User")
            .with_grants(api.VideoGrants(room_join=True, room=ROOM))
            .to_jwt()
        )
    except Exception as e:
        st.error(f"Token error: {e}")
        return None

def start_agent(tts_provider: str, voice: str, use_flux: str):
    if st.session_state.running:
        return
    if TRANSCRIPT_FILE.exists():
        TRANSCRIPT_FILE.unlink()

    env = {**os.environ,
           "TTS_PROVIDER": tts_provider,
           "USE_FLUX":     use_flux}

    pdef = TTS_PROVIDERS[tts_provider]
    env[pdef["model_env"]] = voice

    # Also set ELEVENLABS_MODEL if using elevenlabs
    if tts_provider == "elevenlabs":
        env["ELEVENLABS_MODEL"] = "eleven_flash_v2_5"

    st.session_state.proc = subprocess.Popen(
        [sys.executable, "voice_agent.py", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    st.session_state.running = True
    st.session_state.token   = make_token()

def stop_agent():
    p = st.session_state.proc
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill()
    st.session_state.proc    = None
    st.session_state.running = False
    st.session_state.token   = None

def sync_state():
    p = st.session_state.proc
    if p and p.poll() is not None:
        st.session_state.running = False
        st.session_state.proc    = None

def load_transcripts():
    if not TRANSCRIPT_FILE.exists():
        return []
    rows = []
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try: rows.append(json.loads(line))
                    except: pass
    except: pass
    return rows[-60:]

def check_plugin(pip_name: str | None) -> bool:
    if pip_name is None:
        return True
    pkg = pip_name.replace("-", "_")
    try:
        __import__(pkg.replace("livekit_plugins_", "livekit.plugins."))
        return True
    except ImportError:
        return False


# ── WebRTC widget (unchanged from original, kept clean) ──────────────────────
def voice_widget(token: str, lk_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--bdr:#334155;--txt:#f1f5f9;--sub:#94a3b8;
       --red:#ef4444;--grn:#22c55e;--blu:#3b82f6;}}
*{{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,sans-serif;}}
body{{background:var(--bg);color:var(--txt);display:flex;flex-direction:column;
      align-items:center;justify-content:center;padding:20px 16px;gap:14px;min-height:100vh;}}
#pill{{font-size:12px;padding:3px 14px;border-radius:999px;
       border:1px solid var(--bdr);color:var(--sub);transition:all .3s;}}
#pill.on {{border-color:var(--grn);color:var(--grn);}}
#pill.err{{border-color:var(--red);color:var(--red);}}
#mic{{width:82px;height:82px;border-radius:50%;
      border:2px solid var(--bdr);background:var(--card);
      font-size:30px;cursor:pointer;
      display:flex;align-items:center;justify-content:center;
      transition:border-color .2s,background .2s,transform .1s;user-select:none;}}
#mic:hover  {{border-color:var(--blu);background:#1e3050;}}
#mic:active {{transform:scale(.94);}}
#mic.live   {{border-color:var(--red);background:#2d1515;animation:rp 1.4s ease-in-out infinite;}}
#mic:disabled{{opacity:.3;cursor:not-allowed;animation:none;}}
@keyframes rp{{0%,100%{{box-shadow:0 0 0 0 rgba(239,68,68,.5);}}50%{{box-shadow:0 0 0 14px rgba(239,68,68,0);}}}}
#vbar{{width:160px;height:4px;background:#1e293b;border-radius:2px;overflow:hidden;}}
#vfill{{height:100%;width:0%;background:var(--grn);border-radius:2px;transition:width .07s;}}
#abars{{display:flex;gap:3px;align-items:flex-end;height:22px;opacity:0;transition:opacity .4s;}}
#abars.show{{opacity:1;}}
#abars span{{width:4px;background:var(--blu);border-radius:2px;animation:bw 1s ease-in-out infinite;}}
#abars span:nth-child(1){{height:8px;animation-delay:0s;}}
#abars span:nth-child(2){{height:16px;animation-delay:.15s;}}
#abars span:nth-child(3){{height:12px;animation-delay:.30s;}}
#abars span:nth-child(4){{height:20px;animation-delay:.10s;}}
#abars span:nth-child(5){{height:9px;animation-delay:.25s;}}
@keyframes bw{{0%,100%{{transform:scaleY(.4);}}50%{{transform:scaleY(1.3);}}}}
#alabel{{font-size:11px;color:var(--blu);opacity:0;transition:opacity .4s;}}
#alabel.show{{opacity:1;}}
.row{{display:flex;gap:8px;}}
.btn{{padding:6px 16px;border-radius:7px;border:1px solid var(--bdr);
      background:var(--card);color:var(--txt);font-size:12.5px;cursor:pointer;
      transition:background .18s,border-color .18s;}}
.btn:hover{{background:#263248;border-color:var(--blu);}}
.btn:disabled{{opacity:.3;cursor:not-allowed;}}
.btn.warn{{border-color:#7f1d1d;}}
.btn.warn:hover{{background:#2a0f0f;border-color:var(--red);}}
#hint{{font-size:11.5px;color:#64748b;text-align:center;max-width:240px;line-height:1.55;}}
</style></head>
<body>
<div id="pill">Disconnected</div>
<button id="mic" disabled>🎤</button>
<div id="vbar"><div id="vfill"></div></div>
<div id="abars"><span></span><span></span><span></span><span></span><span></span></div>
<div id="alabel">Agent speaking…</div>
<div class="row">
  <button class="btn"      id="bc" onclick="connect()">Connect</button>
  <button class="btn"      id="bm" onclick="toggleMute()" disabled>Mute</button>
  <button class="btn warn" id="bd" onclick="disconnect()" disabled>Leave</button>
</div>
<div id="hint">Click <strong>Connect</strong> — mic opens automatically.</div>
<script type="module">
import {{Room,RoomEvent,Track,createLocalAudioTrack,ConnectionState}}
  from 'https://cdn.jsdelivr.net/npm/livekit-client@2/+esm';
const URL="{lk_url}",TOKEN="{token}";
const pill=document.getElementById('pill'),mic=document.getElementById('mic'),
      vfill=document.getElementById('vfill'),abars=document.getElementById('abars'),
      alabel=document.getElementById('alabel'),bc=document.getElementById('bc'),
      bm=document.getElementById('bm'),bd=document.getElementById('bd'),
      hint=document.getElementById('hint');
let room=null,track=null,muted=false,analyser=null,raf=null;
const setStatus=(t,c='')=>{{pill.textContent=t;pill.className=c;}};
const agentSpeak=(on)=>{{abars.classList.toggle('show',on);alabel.classList.toggle('show',on);}};
const ctrl=(on)=>{{mic.disabled=!on;bm.disabled=!on;bd.disabled=!on;bc.disabled=on;}};
function startVis(ms){{
  try{{const ac=new AudioContext(),src=ac.createMediaStreamSource(ms);
    analyser=ac.createAnalyser();analyser.fftSize=256;src.connect(analyser);
    const buf=new Uint8Array(analyser.frequencyBinCount);
    (function t(){{analyser.getByteFrequencyData(buf);
      vfill.style.width=Math.min(buf.reduce((a,b)=>a+b,0)/buf.length*1.8,100)+'%';
      raf=requestAnimationFrame(t);}})();}}catch(e){{}}}}
function stopVis(){{if(raf)cancelAnimationFrame(raf);vfill.style.width='0%';}}
window.connect=async function(){{
  setStatus('Connecting…');bc.disabled=true;
  room=new Room({{adaptiveStream:true,dynacast:true}});
  room.on(RoomEvent.Connected,async()=>{{
    setStatus('Connected','on');hint.innerHTML='Mic is live — speak naturally.';ctrl(true);
    try{{track=await createLocalAudioTrack({{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      await room.localParticipant.publishTrack(track);startVis(track.mediaStream);mic.classList.add('live');
    }}catch(e){{hint.textContent='Mic error: '+e.message;}}
  }});
  room.on(RoomEvent.Disconnected,()=>{{setStatus('Disconnected');ctrl(false);
    stopVis();mic.classList.remove('live');agentSpeak(false);
    hint.innerHTML='Click <strong>Connect</strong> to rejoin.';}});
  room.on(RoomEvent.ConnectionStateChanged,s=>{{
    if(s===ConnectionState.Reconnecting)setStatus('Reconnecting…');
    if(s===ConnectionState.Connected)setStatus('Connected','on');}});
  room.on(RoomEvent.TrackSubscribed,(trk,pub,part)=>{{
    if(trk.kind===Track.Kind.Audio){{
      const el=trk.attach();el.style.display='none';document.body.appendChild(el);
      agentSpeak(true);trk.on('ended',()=>agentSpeak(false));}}
  }});
  room.on(RoomEvent.TrackUnsubscribed,()=>agentSpeak(false));
  room.on(RoomEvent.TrackMuted,()=>agentSpeak(false));
  room.on(RoomEvent.TrackUnmuted,()=>agentSpeak(true));
  try{{await room.connect(URL,TOKEN);}}
  catch(e){{setStatus('Failed','err');hint.textContent='Connection failed: '+e.message;bc.disabled=false;}}
}};
window.toggleMute=async function(){{
  if(!track)return;muted=!muted;await track.mute(muted);
  bm.textContent=muted?'Unmute':'Mute';mic.classList.toggle('live',!muted);
  muted?stopVis():startVis(track.mediaStream);}};
window.disconnect=async function(){{
  stopVis();if(track){{track.stop();track=null;}}
  if(room){{await room.disconnect();room=null;}}agentSpeak(false);}};
mic.addEventListener('click',toggleMute);
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
sync_state()

with st.sidebar:
    st.markdown("## 🎙️ Voice Agent")
    st.caption("Google ADK · LiveKit · Deepgram Flux STT")
    st.divider()

    # ── Core env checks ───────────────────────────────────────────────────────
    st.markdown("**Core Config**")
    core_vars = {
        "LIVEKIT_URL":        bool(LK_URL),
        "LIVEKIT_API_KEY":    bool(LK_KEY),
        "LIVEKIT_API_SECRET": bool(LK_SECRET),
        "DEEPGRAM_API_KEY":   bool(DG_KEY),
        "GOOGLE_API_KEY":     bool(G_KEY),
    }
    for var, ok in core_vars.items():
        st.markdown(f"{'✅' if ok else '❌'} `{var}`")

    st.divider()

    # ── STT Model picker ──────────────────────────────────────────────────────
    st.markdown("**STT Model**")
    stt_choice = st.selectbox(
        "Speech-to-Text",
        list(STT_MODELS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    use_flux = STT_MODELS[stt_choice]
    if "Flux" in stt_choice:
        st.caption("⚡ Flux = built-in end-of-turn detection, no separate VAD needed")
    else:
        st.caption("ℹ️ Nova-3 = multilingual, uses Silero VAD for turn detection")

    st.divider()

    # ── TTS Provider picker ───────────────────────────────────────────────────
    st.markdown("**TTS Provider**")
    provider_labels = {k: f"{v['icon']} {v['label']}  ({v['latency']})"
                       for k, v in TTS_PROVIDERS.items()}
    selected_provider = st.selectbox(
        "TTS Provider",
        list(TTS_PROVIDERS.keys()),
        format_func=lambda k: provider_labels[k],
        label_visibility="collapsed",
    )
    pdef = TTS_PROVIDERS[selected_provider]
    st.caption(pdef["desc"])
    st.caption(f"Latency: **{pdef['latency']}** · Quality: {pdef['quality']}")

    # Plugin check
    if pdef["pip"] and not check_plugin(pdef["pip"]):
        st.warning(f"Missing plugin: `pip install {pdef['pip']}`", icon="📦")

    # Provider env check
    for var, val in pdef["env_needed"].items():
        st.markdown(f"{'✅' if val else '❌'} `{var}`")

    # Voice picker
    st.markdown("**Voice**")
    voice_name = st.selectbox(
        "Voice",
        list(pdef["voices"].keys()),
        label_visibility="collapsed",
    )
    selected_voice = pdef["voices"][voice_name]

    st.divider()

    # ── Agent controls ────────────────────────────────────────────────────────
    st.markdown("**Agent Worker**")
    is_running = st.session_state.running
    st.markdown(f"{'🟢 Running' if is_running else '🔴 Stopped'}")

    can_start = base_ok() and provider_ok(selected_provider) and not is_running
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start", disabled=not can_start,
                     use_container_width=True, type="primary"):
            start_agent(selected_provider, selected_voice, use_flux)
            st.rerun()
    with c2:
        if st.button("⏹ Stop", disabled=not is_running,
                     use_container_width=True):
            stop_agent()
            st.rerun()

    st.divider()

    # ── Info panel ────────────────────────────────────────────────────────────
    st.markdown("**Active Pipeline**")
    st.caption(f"STT · {'Deepgram Flux' if use_flux == 'true' else 'Deepgram Nova-3'}")
    st.caption(f"LLM · Gemini 2.0 Flash (ADK)")
    st.caption(f"TTS · {pdef['label']} — {voice_name}")
    st.caption(f"Room · `{ROOM}`")
    if use_flux == "true":
        st.caption("VAD · Built-in (Flux EoT)")
    else:
        st.caption("VAD · Silero v5 / Krisp")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AREA
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("## 🎙️ Voice AI Agent")
pdef = TTS_PROVIDERS[selected_provider]
st.caption(
    f"STT: {'Deepgram **Flux**' if use_flux == 'true' else 'Deepgram **Nova-3**'} · "
    f"LLM: **Gemini 2.0 Flash** (ADK) · "
    f"TTS: **{pdef['label']}** — {voice_name}"
)

left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown("### 🎤 Talk")

    if not base_ok():
        st.error("Complete core `.env` config first (LiveKit + Deepgram + Google).", icon="🔑")
    elif not provider_ok(selected_provider):
        missing = [k for k, v in pdef["env_needed"].items() if not v]
        st.error(f"Add `{', '.join(missing)}` to `.env` for {pdef['label']}.", icon="🔑")
    elif not st.session_state.running:
        st.info(
            f"Press **▶ Start** in the sidebar to launch the agent with "
            f"**{pdef['label']}** TTS ({voice_name}), then speak here.",
            icon="ℹ️",
        )
    else:
        if st.session_state.token is None:
            st.session_state.token = make_token()
        if st.session_state.token:
            components.html(voice_widget(st.session_state.token, LK_URL), height=370)
        else:
            st.error("Token generation failed — check LIVEKIT_API_KEY / SECRET.")

    # Pipeline diagram
    with st.expander("Pipeline", expanded=False):
        stt_label = "Deepgram Flux (EoT built-in)" if use_flux == "true" else "Deepgram Nova-3 + Silero VAD"
        st.code(
            f"🎤 Browser mic\n"
            f"   ↓ WebRTC\n"
            f"🧠 {stt_label}\n"
            f"   ↓ text + end-of-turn signal\n"
            f"🤖 Google ADK + Gemini 2.0 Flash\n"
            f"   ↓ streamed text chunks\n"
            f"🗣️  {pdef['label']} — {voice_name}\n"
            f"   ↓ WebRTC audio\n"
            f"🔊 Browser speaker",
            language=None,
        )

    # Model comparison table
    with st.expander("Model Comparison", expanded=False):
        st.markdown("""
| TTS | Latency | Quality | Best for |
|-----|---------|---------|----------|
| ⚡ Cartesia Sonic-3 | ~90ms | ★★★★★ | Ultra-low latency, emotion |
| ✨ ElevenLabs Flash v2.5 | ~75ms | ★★★★★ | Fastest + voice cloning |
| 🔵 Deepgram Aura-2 | ~200ms | ★★★★☆ | Enterprise, unified STT+TTS |

| STT | WER | Latency | Best for |
|-----|-----|---------|----------|
| Flux | ~6.84% | <300ms | Voice agents, auto EoT |
| Nova-3 | ~6.84% | <300ms | Multilingual, code-switch |
""")

with right:
    st.markdown("### 📝 Transcript")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔄 Refresh", use_container_width=True): st.rerun()
    with b2:
        if st.button("🗑️ Clear", use_container_width=True):
            if TRANSCRIPT_FILE.exists(): TRANSCRIPT_FILE.unlink()
            st.session_state.t_len = 0
            st.rerun()

    rows = load_transcripts()
    if not rows:
        st.markdown(
            "<div style='color:#94a3b8;text-align:center;padding:48px 0;'>"
            "No transcript yet.<br>Connect and start speaking.</div>",
            unsafe_allow_html=True,
        )
    else:
        for r in rows:
            role = r.get("role", "system")
            text = r.get("text", "")
            ts   = time.strftime("%H:%M:%S", time.localtime(r.get("ts", 0)))
            if role == "user":
                with st.chat_message("user"):
                    st.write(text); st.caption(ts)
            elif role == "agent":
                with st.chat_message("assistant"):
                    st.write(text); st.caption(ts)
            else:
                st.caption(f"[{ts}] {text}")

    if st.session_state.running:
        new_len = len(rows)
        if new_len != st.session_state.t_len:
            st.session_state.t_len = new_len
        time.sleep(1)
        st.rerun()

st.divider()
st.caption("All audio is handled in-browser via WebRTC — no external redirects.")