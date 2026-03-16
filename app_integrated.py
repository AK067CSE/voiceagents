"""
app_integrated.py - Streamlit Voice Agent UI (Cloud-Ready)
=========================================================
Modified to work entirely within Streamlit Cloud without subprocess calls.
Integrates voice agent functionality directly into the Streamlit app.
"""
from __future__ import annotations
import json, os, sys, time, asyncio
from pathlib import Path
import threading

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

# ── Session state ─────────────────────────────────────────────────────────────
for key in ("running", "token", "t_len", "agent_worker"):
    if key not in st.session_state:
        st.session_state[key] = None

# ── Voice Agent Integration ────────────────────────────────────────────────────
# Import voice agent components
sys.path.insert(0, os.path.dirname(__file__))

from voice_agent import VoiceAssistant, build_tts, build_stt, build_vad
from agent import root_agent
from adk_llm_bridge import ADKLLMBridge
from livekit.agents import AgentSession
from livekit.api import LiveKitAPI, TokenPermissions

class IntegratedAgentWorker:
    """Integrated voice agent that runs within Streamlit"""
    
    def __init__(self):
        self.session = None
        self.running = False
        
    async def start(self, tts_provider: str, voice: str, use_flux: str):
        """Start the voice agent session"""
        if self.running:
            return
            
        # Set environment for this session
        os.environ["TTS_PROVIDER"] = tts_provider
        os.environ["USE_FLUX"] = use_flux
        os.environ[TTS_PROVIDERS[tts_provider]["model_env"]] = voice
        
        if tts_provider == "elevenlabs":
            os.environ["ELEVENLABS_MODEL"] = "eleven_flash_v2_5"
        
        # Build components
        tts = build_tts()
        stt, needs_vad = build_stt()
        vad = build_vad() if needs_vad else None
        
        # Create session
        self.session = AgentSession(
            stt=stt,
            llm=ADKLLMBridge(root_agent, "voice_agent"),
            tts=tts,
            vad=vad,
        )
        
        self.running = True
        
    async def stop(self):
        """Stop the voice agent session"""
        if self.session:
            # Session will be cleaned up automatically
            self.session = None
        self.running = False

# Global agent worker
agent_worker = IntegratedAgentWorker()

# ── Token generation ───────────────────────────────────────────────────────────
def make_token() -> str:
    """Generate LiveKit room token for the browser client."""
    if not all([LK_URL, LK_KEY, LK_SECRET]):
        return ""
    try:
        api = LiveKitAPI(LK_URL, LK_KEY, LK_SECRET)
        token = api.token.create(
            api.token.VideoGrant(room_join=True, room=ROOM),
            identity="ui-user",
            name="UI User",
            permissions=TokenPermissions(
                can_subscribe=True,
                can_publish=True,
                can_publish_data=True,
            ),
        )
        return token
    except Exception as exc:
        st.error(f"Token error: {exc}")
        return ""

# ── Voice widget HTML ─────────────────────────────────────────────────────────
def voice_widget(token: str, livekit_url: str) -> str:
    """Embed LiveKit mic widget."""
    return f"""
    <div style="border:1px solid #333;border-radius:8px;padding:16px;background:#0e1117;">
      <livekit-mic
        server-url="{livekit_url}"
        token="{token}"
        auto-connect="true"
        echo-cancellation="true"
        noise-suppression="true"
      ></livekit-mic>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/@livekit/components-web@1.6.0/dist/livekit-components.umd.min.js"></script>
    """

# ── Transcript helpers ─────────────────────────────────────────────────────────
def load_transcripts() -> list:
    """Load transcript lines."""
    if not TRANSCRIPT_FILE.exists():
        return []
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except Exception:
        return []

def base_ok() -> bool:
    """Check core env vars."""
    return all([LK_URL, LK_KEY, LK_SECRET, DG_KEY, G_KEY])

def provider_ok(provider: str) -> bool:
    """Check provider-specific env vars."""
    pdef = TTS_PROVIDERS[provider]
    return all(v for v in pdef["env_needed"].values())

# ── Agent Control Functions ───────────────────────────────────────────────────
def start_agent(tts_provider: str, voice: str, use_flux: str):
    """Start the integrated voice agent"""
    if st.session_state.running:
        return
    if TRANSCRIPT_FILE.exists():
        TRANSCRIPT_FILE.unlink()

    # Start agent in a separate thread to avoid blocking Streamlit
    def run_agent():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent_worker.start(tts_provider, voice, use_flux))
        
    thread = threading.Thread(target=run_agent, daemon=True)
    thread.start()
    
    st.session_state.running = True
    st.session_state.token = make_token()

def stop_agent():
    """Stop the integrated voice agent"""
    def stop_worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent_worker.stop())
        
    thread = threading.Thread(target=stop_worker, daemon=True)
    thread.start()
    
    st.session_state.running = False
    st.session_state.token = None

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    
    # TTS Provider selector
    selected_provider = st.selectbox(
        "TTS Provider",
        options=list(TTS_PROVIDERS.keys()),
        format_func=lambda k: f"{TTS_PROVIDERS[k]['icon']} {TTS_PROVIDERS[k]['label']}",
        index=0,
    )
    
    # Voice selector
    pdef = TTS_PROVIDERS[selected_provider]
    voice_options = list(pdef["voices"].keys())
    selected_voice = st.selectbox("Voice", voice_options, index=0)
    voice_name = pdef["voices"][selected_voice]
    
    # STT Model selector
    use_flux = st.selectbox(
        "STT Model",
        options=list(STT_MODELS.keys()),
        format_func=lambda k: k,
        index=1,  # Default to Nova-3
    )
    use_flux = STT_MODELS[use_flux]
    
    # Agent controls
    st.markdown("### 🎛️ Agent Controls")
    c1, c2 = st.columns(2)
    is_running = st.session_state.running
    with c1:
        if st.button("▶ Start", disabled=is_running or not base_ok() or not provider_ok(selected_provider),
                     use_container_width=True):
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
st.markdown("## 🎙️ Voice AI Agent (Cloud-Ready)")
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
st.caption("🚀 Cloud-Ready Version: All audio is handled in-browser via WebRTC — no external redirects or subprocesses needed.")
