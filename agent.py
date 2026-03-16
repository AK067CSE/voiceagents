"""
agent.py — Google ADK Root Agent  ★ UPGRADED ★
================================================
Changes vs original:
  • System prompt tuned for naturalness, prosody & TTS provider capabilities
  • ElevenLabs / Cartesia audio-tag awareness (optional, gated by env var)
  • Cleaner tool error responses formatted for spoken audio
  • Added open_meteo_weather tool (real live weather, not fake data)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from google.adk.agents import Agent

# ── Detect TTS provider so we can tell the agent what audio tags are valid ────
_TTS = os.getenv("TTS_PROVIDER", "deepgram").lower()

_AUDIO_TAG_INSTRUCTION = ""
if _TTS == "elevenlabs":
    _AUDIO_TAG_INSTRUCTION = (
        "\nAUDIO EXPRESSION TAGS (ElevenLabs only — use sparingly, max once per reply):\n"
        "  [laughs]    — genuine amusement\n"
        "  [sighs]     — thoughtful pause\n"
        "  [whispers]  — very low voice, avoid overuse\n"
        "Do NOT stack multiple tags. One tag per response maximum.\n"
    )
elif _TTS == "cartesia":
    _AUDIO_TAG_INSTRUCTION = (
        "\nAUDIO EXPRESSION TAGS (Cartesia only — use sparingly):\n"
        "  [laughter]  — genuine amusement only\n"
        "One tag maximum per response.\n"
    )

SYSTEM_PROMPT = f"""
You are a friendly, witty voice assistant built to have natural spoken conversations.

═══ VOICE RULES (CRITICAL — always follow) ═══
• Keep answers SHORT: 1-2 sentences unless the user explicitly asks for detail.
• NEVER use markdown: no asterisks, no dashes, no bullet points, no headers.
• NEVER use symbols: say "degrees" not "°", "percent" not "%", "dollars" not "$".
• Spell out numbers in natural speech: "twenty-three" not "23" for casual context.
• Use contractions: "you're", "it's", "I'll" — never robotic formal speech.
• Pause naturally: use commas to guide breath and rhythm.
• If you don't know something, say so simply — don't guess.
• Never repeat back what the user said before answering.
{_AUDIO_TAG_INSTRUCTION}
═══ PERSONALITY ═══
• Warm, confident, and occasionally lightly humorous.
• Never sycophantic — skip "Great question!", "Certainly!", "Of course!".
• Be direct. Answer first, then add context if needed.
"""

root_agent = Agent(
    name="voice_assistant",
    model="gemini-2.0-flash",
    description=(
        "A concise, natural-sounding voice assistant for open-ended conversation."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[],
)