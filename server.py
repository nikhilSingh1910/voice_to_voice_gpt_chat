import asyncio
import json
import base64
from io import BytesIO
from typing import Optional, AsyncGenerator

import websockets
from openai import OpenAI

#  Config 
WS_HOST = "0.0.0.0"
WS_PORT = 8910

TEXT_MODEL = "gpt-4o-mini"
TTS_MODEL  = "gpt-4o-mini-tts"
TTS_VOICE  = "alloy"
AUDIO_CHUNK_BYTES = 64_000
TTS_PARALLELISM = 2
MAX_TEXT_Q = 8
MAX_AUDIO_Q = 16
MAX_WS_Q = 64
FIRST_SENTENCE_MIN = 80


client = OpenAI()

#  Helpers: LLM streaming 

async def llm_stream(prompt: str) -> AsyncGenerator[str, None]:
    print(f"[LLM] Starting stream for prompt: {prompt[:80]}...")
    messages = [
        {"role": "system", "content": "You are a investment adviser, and will answer questions related to it. If someone enquires about Gold, nudge them solftly towards Digital Gold, if the user doesnot mention gold, no need to do this."},
        {"role": "user", "content": prompt},
    ]

    stream = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=messages,
        temperature=0.3,
        stream=True,
    )

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()

    def pump():
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    print(f"[LLM] Token received: {delta.content!r}")
                    asyncio.run_coroutine_threadsafe(queue.put(delta.content), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    import threading
    threading.Thread(target=pump, daemon=True).start()

    while True:
        piece = await queue.get()
        if piece is None:
            break
        yield piece


#  Helpers: sentence chunker 

def make_sentence_chunker(min_len: int = FIRST_SENTENCE_MIN):
    buf = ""

    async def feed(token: str) -> Optional[str]:
        nonlocal buf
        buf += token
        seps = [". ", "? ", "! ", "; ", ": ", ", "]
        while True:
            cut = None
            for sep in seps:
                idx = buf.find(sep)
                if idx >= min_len:
                    cut = idx + len(sep)
                    break
            if cut is None:
                if len(buf) >= (min_len * 2):
                    cut = len(buf)
                else:
                    return None
            chunk, buf = buf[:cut], buf[cut:]
            text = chunk.strip()
            if text:
                print(f"[CHUNKER] Sentence ready: {text!r}")
                return text

    async def flush() -> Optional[str]:
        nonlocal buf
        text = buf.strip()
        buf = ""
        if text:
            print(f"[CHUNKER] Flushing tail: {text!r}")
        return text or None

    return feed, flush

#  Helpers: OpenAI TTS 
from io import BytesIO

async def tts_bytes(text: str) -> bytes:
    print(f"[TTS] Synthesizing speech for: {text!r}")
    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        response_format="pcm"
    ) as resp:
        buf = BytesIO()
        for chunk in resp.iter_bytes():
            buf.write(chunk)
        audio_bytes = buf.getvalue()
        print(f"[TTS] Done, got {len(audio_bytes)} bytes")
        return audio_bytes

#  Workers 

async def tts_worker(text_q: asyncio.Queue, audio_q: asyncio.Queue, idx: int):
    print(f"[TTS-WORKER-{idx}] Started")
    try:
        while True:
            text = await text_q.get()
            if text is None:
                print(f"[TTS-WORKER-{idx}] Shutdown")
                text_q.task_done()
                break
            try:
                print(f"[TTS-WORKER-{idx}] Processing: {text!r}")
                audio = await tts_bytes(text)
                await audio_q.put((text, audio))
                print(f"[TTS-WORKER-{idx}] Enqueued audio ({len(audio)} bytes)")
            except Exception as e:
                print(f"[TTS-WORKER-{idx}] Error: {e}")
                await audio_q.put((f"__TTS_ERROR__:{text}", str(e).encode()))
            finally:
                text_q.task_done()
    except asyncio.CancelledError:
        print(f"[TTS-WORKER-{idx}] Cancelled")

async def audio_slicer(audio_q: asyncio.Queue, ws_q: asyncio.Queue):
    seq = 0
    print("[SLICER] Started")
    try:
        while True:
            item = await audio_q.get()
            if item is None:
                print("[SLICER] No more audio, finishing")
                audio_q.task_done()
                break
            _text, audio_bytes = item
            print(f"[SLICER] Slicing audio ({len(audio_bytes)} bytes)")
            for i in range(0, len(audio_bytes), AUDIO_CHUNK_BYTES):
                chunk = audio_bytes[i : i + AUDIO_CHUNK_BYTES]
                await ws_q.put({
                    "content": base64.b64encode(chunk).decode("utf-8"),
                    "seq": seq,
                    "end": False
                })
                print(f"[SLICER] Enqueued chunk seq={seq} size={len(chunk)}")
                seq += 1
            audio_q.task_done()
        await ws_q.put({"end": True})
        print("[SLICER] Sent end marker")
    except asyncio.CancelledError:
        await ws_q.put({"end": True})
        print("[SLICER] Cancelled, sent end marker")

async def ws_sender(websocket, ws_q: asyncio.Queue):
    print("[WS-SENDER] Started")
    while True:
        msg = await ws_q.get()
        await websocket.send(json.dumps(msg))
        print(f"[WS-SENDER] Sent message: keys={list(msg.keys())}")
        ws_q.task_done()
        if msg.get("end"):
            print("[WS-SENDER] End marker received, stopping")
            break

#  Session orchestration 

async def run_session(websocket, payload: dict):
    prompt = payload.get("message", "")
    print(f"[SESSION] New session with prompt: {prompt!r}")

    text_q  = asyncio.Queue(maxsize=MAX_TEXT_Q)
    audio_q = asyncio.Queue(maxsize=MAX_AUDIO_Q)
    ws_q    = asyncio.Queue(maxsize=MAX_WS_Q)

    tts_workers = [asyncio.create_task(tts_worker(text_q, audio_q, i)) for i in range(TTS_PARALLELISM)]
    slicer_task = asyncio.create_task(audio_slicer(audio_q, ws_q))
    sender_task = asyncio.create_task(ws_sender(websocket, ws_q))

    feed, flush = make_sentence_chunker()

    async for tok in llm_stream(prompt):
        chunk = await feed(tok)
        if chunk:
            await text_q.put(chunk)

    tail = await flush()
    if tail:
        await text_q.put(tail)

    print("[SESSION] Waiting for TTS workers to finish...")
    for _ in range(TTS_PARALLELISM):
        await text_q.put(None)
    await text_q.join()

    print("[SESSION] Waiting for slicer...")
    await audio_q.put(None)
    await audio_q.join()
    await ws_q.join()

    for t in tts_workers:
        await t
    await slicer_task
    await sender_task
    print("[SESSION] Completed")

#  WebSocket server 

async def ws_app(websocket):
    print("[WS] Client connected")
    try:
        async for raw in websocket:
            print(f"[WS] Received: {raw[:80]}...")
            try:
                payload = json.loads(raw)
            except Exception:
                print("[WS] Invalid JSON")
                await websocket.send(json.dumps({"error": "invalid JSON"}))
                continue
            await run_session(websocket, payload)
    except websockets.exceptions.ConnectionClosed:
        print("[WS] Connection closed")
        return

async def main():
    print(f"Listening on ws://{WS_HOST}:{WS_PORT}")
    async with websockets.serve(ws_app, WS_HOST, WS_PORT, max_size=8_000_000):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
