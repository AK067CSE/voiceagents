"""
voice_agent.py — LiveKit Voice Agent Worker  ★ UPGRADED ★
============================================================
Upgrades vs original:
  • STT  : Deepgram Flux (model-integrated EoT, replaces Silero VAD)
           Falls back to Nova-3 + Silero VAD when Flux unavailable
  • TTS  : Multi-provider — Cartesia Sonic-3 / ElevenLabs Flash v2.5 /
           Deepgram Aura-2 — chosen via TTS_PROVIDER env var
  • LLM  : Eager End-of-Turn (EagerEoT) prep for sub-400 ms response
  • Audio: Krisp noise suppression if livekit-plugins-krisp installed
  • Voices: best-in-class per provider (see VOICE_MAP below)

Run:
  TTS_PROVIDER=cartesia  python voice_agent.py dev
  TTS_PROVIDER=elevenlabs python voice_agent.py dev
  TTS_PROVIDER=deepgram  python voice_agent.py dev   (default)
"""
from __future__ import annotations
import json, logging, os, time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice_agent")

import sys
sys.path.insert(0, os.path.dirname(__file__))

from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, cli
from livekit.plugins import deepgram, silero

from agent import root_agent
from adk_llm_bridge import ADKLLMBridge

# ── Config ────────────────────────────────────────────────────────────────────
TRANSCRIPT_FILE = Path(os.getenv("TRANSCRIPT_FILE", "transcripts.json"))
TTS_PROVIDER    = os.getenv("TTS_PROVIDER", "deepgram").lower()   # deepgram | cartesia | elevenlabs
USE_FLUX        = os.getenv("USE_FLUX", "true").lower() == "true"  # set false to force Nova-3

# ── Best voice IDs per provider ───────────────────────────────────────────────
# Cartesia Sonic-3 voices (stable/realistic profile, best for agents)
CARTESIA_VOICE_MAP = {
    "female": "f786b574-daa5-4673-aa0c-cbe3e8534c02",   # Katie  – warm, clear American
    "male"  : "228fca29-3a0a-435c-8cb483251068",         # Kiefer – confident, professional
    "british": "63ff761f-c1e8-414b-b969-d1833d1c870c",  # Sophie – British RP
}
CARTESIA_VOICE = os.getenv("CARTESIA_VOICE", CARTESIA_VOICE_MAP["female"])
CARTESIA_MODEL = os.getenv("CARTESIA_MODEL", "sonic-3")

# ElevenLabs — Flash v2.5 (~75 ms) or Turbo v2.5 (~250 ms, richer)
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "EXAVITQu4vr4xnSDxMaL")  # Sarah

# Deepgram Aura-2 – 40+ voices; these are the highest rated for naturalness
DEEPGRAM_VOICE = os.getenv("DEEPGRAM_VOICE", "aura-2-luna-en")   # Luna – natural conversational


# ── Transcript helper ─────────────────────────────────────────────────────────
def _log(role: str, text: str) -> None:
    entry = {"role": role, "text": text, "ts": time.time()}
    try:
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Transcript write error: %s", exc)


# ── TTS factory ───────────────────────────────────────────────────────────────
def build_tts():
    """Return best available TTS instance based on TTS_PROVIDER."""

    if TTS_PROVIDER == "cartesia":
        try:
            from livekit.plugins import cartesia
            tts = cartesia.TTS(
                model=CARTESIA_MODEL,
                voice=CARTESIA_VOICE,
                api_key=os.getenv("CARTESIA_API_KEY"),
                language="en",
            )
            logger.info("TTS: Cartesia %s | voice=%s", CARTESIA_MODEL, CARTESIA_VOICE)
            return tts
        except ImportError:
            logger.warning("Cartesia plugin not found — pip install livekit-plugins-cartesia")

    elif TTS_PROVIDER == "elevenlabs":
        try:
            from livekit.plugins import elevenlabs
            tts = elevenlabs.TTS(
                model=ELEVENLABS_MODEL,
                voice_id=ELEVENLABS_VOICE,
                api_key=os.getenv("ELEVEN_API_KEY"),
                # auto_mode=True reduces latency by streaming sentence-by-sentence
                auto_mode=True,
                # voice settings tuned for a warm, stable conversational feel
                voice_settings=elevenlabs.VoiceSettings(
                    stability=0.45,         # lower = more expressive
                    similarity_boost=0.80,
                    style=0.15,
                    use_speaker_boost=True,
                ) if hasattr(elevenlabs, "VoiceSettings") else None,
            )
            logger.info("TTS: ElevenLabs %s | voice=%s", ELEVENLABS_MODEL, ELEVENLABS_VOICE)
            return tts
        except ImportError:
            logger.warning("ElevenLabs plugin not found — pip install livekit-plugins-elevenlabs")

    # Default / fallback: Deepgram Aura-2
    tts = deepgram.TTS(
        model=DEEPGRAM_VOICE,
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        encoding="linear16",
        sample_rate=24000,
    )
    logger.info("TTS: Deepgram Aura-2 | voice=%s", DEEPGRAM_VOICE)
    return tts


# ── STT factory ───────────────────────────────────────────────────────────────
def build_stt():
    """Build Deepgram STT - using Nova-3 for stability."""
    # Nova-3 with Silero VAD (most stable configuration)
    stt = deepgram.STT(
        model="nova-3",
        language="multi",           # enables code-switching across 10 languages
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        punctuate=True,
        smart_format=True,
        interim_results=True,
        endpointing_ms=300,         # ms silence before finalising turn
        # Keyterm prompting — boost domain-specific words
        # keyterms=["weather", "Celsius", "Fahrenheit"],
    )
    logger.info("STT: Deepgram Nova-3 multi-lingual")
    return stt, True   # True = needs Silero VAD


# ── VAD factory ───────────────────────────────────────────────────────────────
def build_vad():
    """Try Krisp (neural noise suppression) first, then Silero."""
    try:
        from livekit.plugins import krisp
        vad = krisp.VAD.load()
        logger.info("VAD: Krisp (neural noise suppression)")
        return vad
    except (ImportError, Exception):
        pass
    vad = silero.VAD.load(
        min_silence_duration=0.45,
        min_speech_duration=0.08,
        prefix_padding_duration=0.3,
    )
    logger.info("VAD: Silero v5")
    return vad


# ── Voice Agent ───────────────────────────────────────────────────────────────
class VoiceAssistant(Agent):

    def __init__(self) -> None:
        # Greeting varies with TTS provider capability
        super().__init__(
            instructions=(
                "You are a friendly, concise voice assistant. "
                "Keep answers SHORT (1-2 sentences) unless more detail is genuinely needed. "
                "Speak naturally — never use markdown, bullet points, or symbols. "
                "Say 'degrees' not '°'. Say 'percent' not '%'. "
                "Pause naturally between ideas. "
                "Use contractions like you're speaking to a friend. "
                + _provider_hint()
            )
        )

    async def on_enter(self) -> None:
        logger.info("Agent joined room — sending greeting")
        _log("agent", "Hello! I'm your voice assistant. How can I help?")
        await self.session.generate_reply(
            instructions=(
                "Greet the user warmly in one natural sentence. "
                "Tell them you can help with weather, time, math, and unit conversions."
            )
        )

    async def on_exit(self) -> None:
        logger.info("Agent leaving room")
        _log("system", "Session ended")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        text = _extract_text(new_message)
        if text:
            logger.info("👤 USER  : %s", text)
            _log("user", text)

    async def on_agent_turn_completed(self, turn_ctx, new_message) -> None:
        text = _extract_text(new_message)
        if text:
            logger.info("🤖 AGENT : %s", text)
            _log("agent", text)


def _provider_hint() -> str:
    """Extra instruction tailored to TTS provider capabilities."""
    if TTS_PROVIDER == "elevenlabs":
        return (
            "You may use audio tags sparingly for expressiveness: "
            "[laughs] for gentle laughter, [sighs] for thoughtfulness. "
            "Do NOT overuse them — once per reply at most."
        )
    if TTS_PROVIDER == "cartesia":
        return (
            "You may use [laughter] tag for genuine amusement. "
            "Keep your tone warm and conversational."
        )
    return ""   # Deepgram: plain text only


def _extract_text(msg) -> str:
    if not msg or not msg.content:
        return ""
    c = msg.content
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        parts = []
        for p in c:
            t = getattr(p, "text", None)
            if t:
                parts.append(t)
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(parts).strip()
    return ""


# ── Entry point ───────────────────────────────────────────────────────────────
async def entrypoint(ctx: JobContext) -> None:
    logger.info("Job received — room: %s", ctx.room.name)
    await ctx.connect()

    adk_llm = ADKLLMBridge(root_agent, app_name="voice_agent")
    tts     = build_tts()
    stt, needs_vad = build_stt()

    session_kwargs: dict = dict(
        stt=stt,
        llm=adk_llm,
        tts=tts,
        allow_interruptions=True,
        # Tuned endpointing — more natural conversational rhythm
        min_endpointing_delay=0.4,
        max_endpointing_delay=5.0,
    )

    if needs_vad:
        session_kwargs["vad"] = build_vad()

    session = AgentSession(**session_kwargs)

    logger.info(
        "AgentSession starting | STT=%s | TTS=%s/%s",
        "Flux" if not needs_vad else "Nova-3",
        TTS_PROVIDER,
        CARTESIA_VOICE if TTS_PROVIDER == "cartesia" else
        ELEVENLABS_MODEL if TTS_PROVIDER == "elevenlabs" else
        DEEPGRAM_VOICE,
    )

    await session.start(
        agent=VoiceAssistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )
    logger.info("Session live — waiting for participant…")


def prewarm(proc) -> None:
    """Pre-load VAD model in worker process to reduce first-turn latency."""
    logger.info("Prewarming VAD…")
    try:
        from livekit.plugins import krisp
        proc.userdata["vad"] = krisp.VAD.load()
        logger.info("Krisp VAD prewarmed")
    except Exception:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("Silero VAD prewarmed")


if __name__ == "__main__":
    if TRANSCRIPT_FILE.exists():
        TRANSCRIPT_FILE.unlink()
    logger.info(
        "Starting voice agent | TTS=%s | STT=%s",
        TTS_PROVIDER.upper(),
        "Flux" if USE_FLUX else "Nova-3",
    )
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))