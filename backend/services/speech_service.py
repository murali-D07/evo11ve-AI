import os
from collections.abc import Iterator

import httpx
import websockets
from fastapi import HTTPException

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3&language=en&interim_results=true&smart_format=true&endpointing=300"
)


def connect_deepgram():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    return websockets.connect(DEEPGRAM_URL, subprotocols=["token", api_key])


def stream_speech(text: str) -> Iterator[bytes]:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    text = text.strip()
    if not text:
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "language_code": "en",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    with httpx.stream(
        "POST",
        url,
        headers={
            "xi-api-key": api_key,
            "accept": "audio/mpeg",
        },
        json=payload,
        timeout=60,
    ) as response:
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="ElevenLabs could not generate speech.")

        yield from response.iter_bytes()
