# Evo11ve AI Skills Voice Assistant

A voice conversational assistant for the **Evo11ve AI Skills Program**. Visitors click **Start**, speak their questions, see live captions, and hear the answer in a natural voice. The assistant can also raise support tickets and send emails to the team.


---

## Features

- **Voice in, voice out:** speak a question and hear the reply.
- **Live captions:** words appear on screen while you are still speaking.
- **Streaming answers:** the reply types out word by word.
- **Grounded answers:** the assistant only uses the program information in its system prompt, and says so when it does not know (for example, it never invents seats, dates, refunds or discounts).
- **Tool calling:** the AI can decide on its own to
  - `raise_ticket`: log a complaint, payment or enrollment problem, or a request for a human
  - `send_email`: send a callback request, enrollment confirmation or escalation to the team
- **Conversation memory:** the last 16 messages are sent each turn, so follow-ups like "what can they build?" work.
- **Interruptible:** click the mic or the orb to stop the assistant while it is speaking.
- **English-only** replies, written in a spoken, phone-call style (short sentences, no markdown).
- **Latency logging:** every stage writes timing to `backend/logs/timing.log`.

---

## Tech stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + Vite | UI, mic recording, audio playback |
| Backend | Python, FastAPI, Uvicorn | API, WebSocket, streaming |
| Speech-to-text | Deepgram (`nova-3`) | Live transcription over WebSocket |
| LLM | Google Gemini (`google-genai`) | Answers and tool calling |
| Text-to-speech | ElevenLabs (`eleven_turbo_v2_5`) | Streaming MP3 voice |
| Email | Gmail SMTP | `send_email` tool |
| Storage | `tickets.json` | Local ticket store for `raise_ticket` |

---




## Project structure

```
evo11ve-ai/
├── backend/
│   ├── app.py                  
│   ├── models.py              
│   ├── requirements.txt
│   ├── .env                    
│   ├── data/
│   │   └── tickets.json        # tickets created by raise_ticket
│   ├── logs/
│   │   └── timing.log          # latency logs
│   ├── prompts/
│   │   └── system_prompt.py    # prompts
│   ├── services/
│   │   ├── chat_service.py     # Gemini + tool-calling 
│   │   └── speech_service.py   # Deepgram + ElevenLabs TTS 
│   └── tools/
│       ├── email_tool.py       # Gmail SMTP sender
│       └── ticket_tool.py      # local ticket writer
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── public/logo.png
    └── src/
        ├── App.jsx             # UI, recording, SSE parsing, audio playback
        ├── main.jsx
        └── styles.css
```

---

## API endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Health check, returns `{"status": "ok"}` |
| `/chat/stream` | POST | Body `{"messages": [{"role": "user", "content": "..."}]}`. Streams Server-Sent Events: `status`, `token`, `action`, `done`, `error` |
| `/speech/live` | WebSocket | Browser sends audio bytes (and `{"type": "stop"}`); server sends `partial`, `final` or `error` |
| `/speech/greeting` | GET | Streams the greeting as MP3 |
| `/speech/speak?text=...` | GET | Streams MP3 for the given text (max 3000 characters) |

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys for **Gemini**, **Deepgram** and **ElevenLabs**
- A Gmail account with an **app password** (only needed for the email tool)

### 1. Clone

```bash
git clone https://github.com/murali-D07/evo11ve-AI.git
cd evo11ve-AI
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env`:

```env
# Required AI providers
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=cgSgspJ2msm6clMCkdW9

GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
EMAIL_TO=
FRONTEND_ORIGIN=http://localhost:5173

GEMINI_CHAT_MODEL=gemini-3-flash-preview
GEMINI_API_KEY=

DEEPGRAM_API_KEY=
```

Run the server **from inside the `backend` folder**:

```bash
uvicorn app:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Start it:

```bash
npm run dev
```
Open `http://localhost:5173`, click **Start conversation**, allow the microphone, and start talking.

---


