# Voice-to-Voice GPT Chat – Technical Details

## Solution Overview
This project implements a real-time voice-to-voice chatbot using OpenAI APIs, WebSockets, and browser-based speech recognition.

- **Frontend (client_streamer.html)**  
  - Uses the browser’s **Web Speech API (SpeechRecognition)** for speech-to-text (STT).  
  - Captures recognized transcript and sends it to the backend over WebSocket.  
  - Decodes and plays **PCM audio chunks** streamed from backend.  
  - Implements an **audio queue + playhead scheduling** for smooth playback.  
  - Includes a **Replay** button to re-listen to the last full response.  

- **Backend (server.py)**  
  - Runs a WebSocket server on **port 8910**.  
  - Receives transcribed text from client.  
  - Calls **OpenAI Chat API** for generating responses.  
  - Streams the response through **OpenAI TTS (24kHz PCM)**.  
  - Encodes audio chunks as Base64 and sends them back to client.  

---

## Deployment Notes

### Local Deployment
- Works out of the box on `ws://localhost:8910`.  
- Recommended browser: **Chrome** (best STT support).  

### Server Deployment
- Host the backend on a cloud VM or container (AWS, GCP, Azure, Docker).  
- Ensure **port 8910** is open to clients.  
- Use **HTTPS + Secure WebSocket (wss://)** for production.  
- Store API keys securely (environment variable, secrets manager, or vault).  

### Frontend Hosting
- The `client_streamer.html` file can be served from any static hosting provider (GitHub Pages, Vercel, or Nginx).  
- Update WebSocket URL in the HTML to point to your server.  

---

## Execution Flow
1. User clicks **Start Talking** → browser captures speech.  
2. Browser converts **speech → text** using Web Speech API.  
3. Transcript is sent via **WebSocket** to backend.  
4. Backend queries **OpenAI Chat API** → generates response text.  
5. Response text is passed into **OpenAI TTS** → converted into PCM audio chunks.  
6. PCM audio chunks are **streamed back** to frontend over WebSocket.  
7. Browser decodes PCM → smooth audio playback.  
8. User can click **Replay** to re-listen to the last full answer.  

---

## Challenges & Solutions

### Audio Quality Issues
- **Problem**: Initial audio playback had clicks/pops due to wrong sample rate handling.  
- **Fix**: Forced **24kHz AudioContext** and synchronized playhead scheduling.  

### Replay Logic
- **Problem**: Replay feature only played the last audio chunk.  
- **Fix**: Accumulated all chunks in a single buffer before replay.  

### Browser Compatibility
- **Issue**: `SpeechRecognition` API works only in **Chrome/Edge**.  
- **Limitation**: Not supported in **Firefox/Safari**.  

### WebSocket Scaling
- **Current Design**: Single-server WebSocket setup.  
- **Production Requirement**: Needs scaling with **load balancers + sticky sessions**.  

---

## Unsolved / Future Improvements

- **Fallback STT**  
  No support if browser lacks Web Speech API. Could integrate server-side STT (e.g., OpenAI Whisper).  

- **Conversation History**  
  Current design is **stateless** (no chat memory). Could add persistent history for multi-turn conversations.  

- **Latency Optimization**  
  Dependent on **OpenAI API response speed** and **network conditions**. Possible improvements include **parallel streaming of LLM + TTS**.  
