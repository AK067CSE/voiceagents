# 🚀 Streamlit Cloud Deployment Guide

## Quick Deploy to Streamlit Cloud

### 1. Prepare Your Repository
```bash
git init
git add .
git commit -m "Initial voice agent deployment"
```

### 2. Push to GitHub
- Create a new repository on GitHub
- Push your code:
```bash
git remote add origin https://github.com/yourusername/voice-agent.git
git branch -M main
git push -u origin main
```

### 3. Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Connect your GitHub account
4. Select your repository
5. Main file path: `app.py`
6. Click **"Deploy"**

### 4. Configure Secrets
In your Streamlit Cloud app dashboard:
1. Go to **"Secrets"** tab
2. Add your API keys:

```toml
LIVEKIT_URL = "wss://your-project.livekit.cloud"
LIVEKIT_API_KEY = "APIxxxxxxxxxxxxxxxxxx"
LIVEKIT_API_SECRET = "your_livekit_secret"
DEEPGRAM_API_KEY = "your_deepgram_api_key"
GOOGLE_API_KEY = "your_google_api_key"
TTS_PROVIDER = "deepgram"
USE_FLUX = "false"
```

### 5. Test Your Deployment
- Your app will be available at: `https://yourusername-voice-agent.streamlit.app`
- Test the voice agent functionality

## Required API Keys

### LiveKit (Required)
- Sign up: [cloud.livekit.io](https://cloud.livekit.io)
- Get: URL, API Key, Secret

### Deepgram (Required)
- Sign up: [console.deepgram.com](https://console.deepgram.com)
- Get: API Key

### Google Gemini (Required)
- Sign up: [aistudio.google.com](https://aistudio.google.com/app/apikey)
- Get: API Key

### Optional TTS Providers
- **Cartesia**: [cartesia.ai](https://cartesia.ai) - Fastest TTS
- **ElevenLabs**: [elevenlabs.io](https://elevenlabs.io) - Ultra-low latency

## Troubleshooting

### App Won't Start
- Check all required secrets are set
- Verify `requirements.txt` is complete
- Check Streamlit Cloud logs

### Voice Agent Issues
- Ensure LiveKit credentials are correct
- Check Deepgram API key validity
- Verify Google API key has Gemini access

### Performance Tips
- Use Deepgram for best reliability
- Consider Cartesia for lowest latency
- Monitor your API usage quotas

## Cost Optimization
- Streamlit Cloud: Free tier available
- LiveKit: Free tier with limits
- Deepgram: $200 free credit
- Google Gemini: Free tier with limits
