"""
Vokara — FreeSWITCH transport
JorahOne

Accepts a WebSocket audio stream from FreeSWITCH (mod_audio_fork) and runs
it through vokara_brain.py (STT -> LLM -> TTS), streaming synthesized audio
back into the same call.

Also serves a small HTTP surface on BOT_HTTP_PORT:
  GET /        — overview page (dashboard/index.html)
  GET /healthz — liveness probe

For Asterisk/FreePBX instead of FreeSWITCH, see server_asterisk.py — same
brain, different transport.
"""

import asyncio
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import vokara_brain as brain
import websockets
from vad import create_vad

BOT_WS_PORT = int(os.environ.get("BOT_WS_PORT", "8765"))
BOT_HTTP_PORT = int(os.environ.get("BOT_HTTP_PORT", "8766"))
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", "8000"))  # 8000=G.711, 16000=wideband

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")


class CallSession:
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.history = brain.new_history()
        self.buffer = bytearray()
        self.vad = create_vad(SAMPLE_RATE)
        self.speech_started = False

    def reset_buffer(self):
        self.buffer = bytearray()
        self.vad.reset()


async def handle_connection(websocket):
    call_id = "unknown"
    session = None
    print("[vokara] new call connected")

    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    meta = json.loads(message)
                    call_id = meta.get("call_id", "unknown")
                    session = CallSession(call_id)
                    print(f"[vokara] call_id={call_id} started")
                except json.JSONDecodeError:
                    pass
                continue

            if session is None:
                session = CallSession(call_id)

            session.buffer.extend(message)

            # Process through VAD
            for event in session.vad.process_stream(message):
                if event == "speech_start":
                    session.speech_started = True
                    session.buffer = bytearray()
                    print(f"[vokara] [{call_id}] speech started")

                elif event == "speech_end" and session.speech_started:
                    session.speech_started = False
                    pcm = bytes(session.buffer)
                    session.reset_buffer()

                    text = brain.transcribe(pcm, SAMPLE_RATE)
                    if not text:
                        continue

                    print(f"[vokara] [{call_id}] caller said: {text}")
                    session.history.append({"role": "user", "content": text})

                    reply = brain.ask_llm(session.history)
                    session.history.append({"role": "assistant", "content": reply})
                    print(f"[vokara] [{call_id}] bot says: {reply}")

                    audio_out = brain.synthesize_piper(reply, SAMPLE_RATE)

                    frame_size = 320  # 20ms @ 8kHz mono PCM16
                    for i in range(0, len(audio_out), frame_size):
                        await websocket.send(audio_out[i:i + frame_size])

    except websockets.exceptions.ConnectionClosed:
        print(f"[vokara] call_id={call_id} disconnected")


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves the overview page and /healthz. No directory listings."""

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            body = json.dumps({
                "status": "ok",
                "service": "vokara",
                "demo_mode": brain.DEMO_MODE,
                "ws_port": BOT_WS_PORT,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None

    def log_message(self, fmt, *args):
        print(f"[vokara-http] {fmt % args}")


def start_http_server():
    handler = partial(DashboardHandler, directory=os.path.abspath(DASHBOARD_DIR))
    httpd = ThreadingHTTPServer(("0.0.0.0", BOT_HTTP_PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"[vokara] HTTP dashboard + /healthz on 0.0.0.0:{BOT_HTTP_PORT}")
    return httpd


async def main():
    start_http_server()
    print(f"[vokara] call audio WebSocket listening on 0.0.0.0:{BOT_WS_PORT}")
    async with websockets.serve(handle_connection, "0.0.0.0", BOT_WS_PORT, max_size=None):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
