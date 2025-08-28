# Voice Chatbot with OpenAI TTS + STT

This project is a **real-time voice chatbot** that:
- Uses browser **SpeechRecognition API** for speech-to-text (STT).
- Sends recognized text to a Python backend over **WebSockets**.
- Backend uses **OpenAI TTS** to synthesize speech.
- Streams audio chunks back to the frontend for playback.

---

## Setup

### 1. Clone Repo
```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set OpenAI API Key
```bash
export OPENAI_API_KEY="your_api_key_here"   # Linux/Mac
setx OPENAI_API_KEY "your_api_key_here"    # Windows (PowerShell)
```

### 5. Running
#### 1. Start Backend WebSocket Server
```bash
python server.py
```
This will start the WebSocket server on: ```ws://localhost:8910```

#### 2. Start Frontend
   
a. Simply open client_streamer.html in Google Chrome (recommended).

b. Click Start Talking → speak into your microphone.

c. Your speech is transcribed and sent to backend.

d. Backend replies with speech (OpenAI TTS), streamed back to your browser.

e. Click Replay Last Answer to hear the full answer again.
