import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from services.chat_service import stream_assistant_reply
from services.speech_service import connect_deepgram, stream_speech

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "logs/timing.log")
os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
    force=True,
)
log = logging.getLogger("timing")


def timed_stream(label: str, stream):
    start = time.perf_counter()
    first = True
    for chunk in stream:
        if first:
            log.info("%s: first chunk after %.0f ms", label, (time.perf_counter() - start) * 1000)
            first = False
        yield chunk
    log.info("%s: total %.0f ms", label, (time.perf_counter() - start) * 1000)


app = FastAPI(title="Evo11ve AI Skills Assistant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat/stream")
def chat_stream(payload: dict) -> StreamingResponse:
    messages = payload.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="A non-empty messages list is required.")
    return StreamingResponse(
        timed_stream("chat", stream_assistant_reply(messages)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def safe_send(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        pass


@app.websocket("/speech/live")
async def live_transcription(websocket: WebSocket) -> None:
    await websocket.accept()
    finals: list[str] = []  
    interim = ""          
    started = time.perf_counter()
    try:
        async with connect_deepgram() as dg:

            async def browser_to_deepgram() -> None:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if audio := message.get("bytes"):
                        await dg.send(audio)  
                    elif raw := message.get("text"):
                        if json.loads(raw).get("type") == "stop":
                            await dg.send(json.dumps({"type": "CloseStream"}))
                            return
                await dg.close()  

            sender = asyncio.create_task(browser_to_deepgram())
            try:
                async for raw in dg:  
                    data = json.loads(raw)
                    if data.get("type") != "Results":
                        continue
                    text = data["channel"]["alternatives"][0]["transcript"].strip()
                    if data.get("is_final"):
                        if text:
                            finals.append(text)
                        interim = ""
                    else:
                        interim = text
                    full = " ".join(finals + ([interim] if interim else []))
                    await safe_send(websocket, {"type": "partial", "text": full})
            finally:
                sender.cancel()

        final_text = " ".join(finals)
        log.info("stt session: %.0f ms -> %r", (time.perf_counter() - started) * 1000, final_text)
        await safe_send(websocket, {"type": "final", "text": final_text})
    except WebSocketDisconnect:
        pass
    except Exception as error:
        log.info("stt error: %s", error)
        await safe_send(websocket, {"type": "error", "message": f"Live transcription failed: {error}"})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/speech/greeting")
def greeting() -> StreamingResponse:
    return audio_response("Hi, I am the Evolve AI Skills assistant. How may I help you?", "tts greeting")


@app.get("/speech/speak")
def speak(text: str) -> StreamingResponse:
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text is required.")
    return audio_response(clean_text[:3000], "tts speak")


def audio_response(text: str, label: str = "tts") -> StreamingResponse:
    return StreamingResponse(
        timed_stream(label, stream_speech(text)),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )