# 🎙️ Voice Agent — Google ADK + Deepgram + LiveKit

A production-ready voice AI agent that combines:

| Layer | Technology |
|-------|-----------|
| **Transport** | LiveKit (WebRTC) |
| **STT** | Deepgram Nova-3 |
| **LLM / Brain** | Google ADK + Gemini 2.0 Flash |
| **TTS** | Deepgram Aura-2 Thalia |
| **Frontend** | Streamlit |

---

## Architecture

```
🎤 User speaks
    │
    ▼  WebRTC (LiveKit room)
┌───────────────────────────────────────────────┐
│  voice_agent.py  (LiveKit Agent Worker)       │
│                                               │
│  Deepgram STT ──► ADKLLMBridge ──► Deepgram TTS
│    Nova-3            │              Aura-2     │
│                      │                         │
│              Google ADK Runner                 │
│              └─ Gemini 2.0 Flash               │
│                 ├─ get_current_datetime        │
│                 ├─ get_weather                 │
│                 ├─ calculate                   │
│                 ├─ convert_units               │
│                 └─ get_fact                    │
└───────────────────────────────────────────────┘
    │
    ▼  WebRTC (LiveKit room)
🔊 User hears response

         ┌──────────────────────┐
         │   app.py (Streamlit) │   ← Live transcript display
         │   - Start/stop agent │       & LiveKit mic embed
         │   - Token generation │
         └──────────────────────┘
```

---

## File Structure

```
voice_agent_project/
├── app.py               ← Streamlit UI (run this)
├── voice_agent.py       ← LiveKit agent worker (started by Streamlit or manually)
├── adk_llm_bridge.py    ← Bridges Google ADK ↔ LiveKit LLM interface
├── tools.py             ← Google ADK tool functions
├── adk_agent/
│   ├── __init__.py
│   └── agent.py         ← ADK root_agent definition
├── requirements.txt
├── .env.example         ← Copy to .env and fill in keys
└── README.md
```

---

## Setup

### 1. Get API Keys

| Service | URL | Notes |
|---------|-----|-------|
| **LiveKit** | https://cloud.livekit.io | Free tier available — grab URL, API Key & Secret |
| **Deepgram** | https://console.deepgram.com | Free $200 credit — grab API Key |
| **Google AI** | https://aistudio.google.com/app/apikey | Free tier — grab API Key |

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt

# Download Silero VAD model files (needed once)
python voice_agent.py download-files
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

### 4. Run

**Option A — via Streamlit UI (recommended)**
```bash
streamlit run app.py
```
Then in the Streamlit sidebar:
1. Click **▶ Start** to launch the agent worker
2. Click **Generate Token** to get a LiveKit room token
3. Use the embedded mic widget or click **Open LiveKit Playground**
4. Start speaking — see the transcript update live

**Option B — run agent worker directly**
```bash
# Terminal 1 — Agent worker
python voice_agent.py dev

# Terminal 2 — Streamlit UI
streamlit run app.py
```

**Option C — console mode (no LiveKit server, mic on local machine)**
```bash
python voice_agent.py console
```

---

## Tools Available to the Agent

| Tool | Description |
|------|-------------|
| `get_current_datetime` | Current date/time in any timezone |
| `get_weather` | Weather for major cities (demo data) |
| `calculate` | Safe math expression evaluator |
| `convert_units` | Length, weight, temperature conversions |
| `get_fact` | Quick facts on common topics |

### Adding Your Own Tools

Edit `tools.py` — add a Python function with a clear docstring.
Then register it in `adk_agent/agent.py` under `tools=[...]`.
ADK uses the docstring to decide when to call the tool automatically.

---

## Customising

| What | Where | How |
|------|-------|-----|
| Gemini model | `adk_agent/agent.py` | Change `model="gemini-2.0-flash"` |
| STT model | `voice_agent.py` | Change `deepgram.STT(model=...)` |
| TTS voice | `voice_agent.py` | Change `deepgram.TTS(model=...)` |
| Agent personality | `adk_agent/agent.py` | Edit `SYSTEM_PROMPT` |
| Greeting | `voice_agent.py` | Edit `VoiceAssistant.on_enter()` |
| Room name | `app.py` | Change `ROOM_NAME` constant |

### Available Deepgram TTS Voices
- `aura-2-thalia-en` — natural female (default)
- `aura-2-orion-en` — natural male
- `aura-asteria-en` — expressive female
- `aura-zeus-en` — deep male

See all voices: https://developers.deepgram.com/docs/tts-models

---

## Troubleshooting

**Agent doesn't respond to speech**
- Check Deepgram API key is valid
- Ensure the LiveKit room name matches between agent and frontend
- Check the browser granted microphone permission

**`ImportError: google.adk`**
- Run `pip install google-adk` or `pip install -r requirements.txt`

**`LIVEKIT_URL` not set**
- Copy `.env.example` to `.env` and fill in the variables

**High latency**
- Switch to `aura-2-helios-en` for faster TTS
- Use `nova-2` instead of `nova-3` for faster STT
- Deepgram has Mumbai co-location for lower latency in India

---

## License
MIT
