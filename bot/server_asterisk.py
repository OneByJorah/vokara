"""
Vokara — Asterisk / FreePBX transport
JorahOne

Alternative to server.py for setups using Asterisk or FreePBX instead of
FreeSWITCH. Uses Asterisk's ARI (REST + WebSocket events) and the
externalMedia channel feature to get RTP audio into this process, rather
than FreeSWITCH's mod_audio_fork.

Same vokara_brain.py underneath (STT -> LLM -> TTS) — only the transport
differs.

--------------------------------------------------------------------------
Setup overview (see README.md for full walkthrough):

1. In Asterisk's ari.conf, enable ARI and create a user:
     [vokara]
     type = user
     password = changeme
     read_only = no

2. In http.conf, make sure the built-in HTTP server is enabled (ARI rides
   on it):
     [general]
     enabled = yes
     bindaddr = 0.0.0.0
     bindport = 8088

3. In extensions.conf (or FreePBX's Custom Destinations), route your bot
   extension into a Stasis app:
     exten => 8500,1,NoOp(Vokara)
      same => n,Answer()
      same => n,Stasis(vokara)
      same => n,Hangup()

4. This script connects to ARI's WebSocket event stream for the
   "vokara" Stasis app, and for each new channel:
      - creates an externalMedia channel (RTP, slin16 or ulaw)
      - bridges it to the caller's channel
      - reads/writes raw PCM over a local UDP socket to/from that bridge

This file provides the skeleton + working RTP I/O loop; the ARI channel/
bridge plumbing has a few moving parts that are genuinely
Asterisk-version-dependent (16 vs 18 vs 20 ARI behavior differs slightly),
so treat the ARI setup calls below as a strong starting point to adapt
against your specific Asterisk/FreePBX version's ARI docs.
--------------------------------------------------------------------------
"""

import asyncio
import json
import os
import socket

import requests
import vokara_brain as brain
import websockets
from vad import create_vad

ARI_HOST = os.environ.get("ARI_HOST", "http://127.0.0.1:8088")
ARI_USER = os.environ.get("ARI_USER", "vokara")
ARI_PASS = os.environ.get("ARI_PASS", "changeme")
ARI_APP = os.environ.get("ARI_APP", "vokara")

EXTERNAL_MEDIA_HOST = os.environ.get("EXTERNAL_MEDIA_HOST", "127.0.0.1")
EXTERNAL_MEDIA_PORT = int(os.environ.get("EXTERNAL_MEDIA_PORT", "40000"))
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", "16000"))  # slin16 default


def ari_post(path: str, **params):
    resp = requests.post(f"{ARI_HOST}/ari{path}", params=params,
                         auth=(ARI_USER, ARI_PASS), timeout=10)
    resp.raise_for_status()
    return resp.json() if resp.content else None


async def handle_channel(channel_id: str):
    """Bridges one caller channel through externalMedia and runs the brain loop."""
    print(f"[vokara-asterisk] handling channel {channel_id}")

    # Create a bridge, add the caller channel to it
    bridge = ari_post("/bridges", type="mixing")
    bridge_id = bridge["id"]
    ari_post(f"/bridges/{bridge_id}/addChannel", channel=channel_id)

    # Create the externalMedia channel pointing at our UDP listener
    ext = ari_post(
        "/channels/externalMedia",
        app=ARI_APP,
        external_host=f"{EXTERNAL_MEDIA_HOST}:{EXTERNAL_MEDIA_PORT}",
        format="slin16",
    )
    ari_post(f"/bridges/{bridge_id}/addChannel", channel=ext["id"])

    history = brain.new_history()
    buffer = bytearray()
    vad = create_vad(SAMPLE_RATE)
    speech_started = False

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((EXTERNAL_MEDIA_HOST, EXTERNAL_MEDIA_PORT))
    sock.setblocking(False)
    loop = asyncio.get_event_loop()

    try:
        while True:
            data, addr = await loop.sock_recv(sock, 4096)

            # Strip RTP header (12 bytes) to get raw PCM payload
            pcm = data[12:] if len(data) > 12 else b""
            if not pcm:
                continue

            buffer.extend(pcm)

            # Process through VAD
            for event in vad.process_stream(pcm):
                if event == "speech_start":
                    speech_started = True
                    buffer = bytearray()
                    print("[vokara-asterisk] speech started")

                elif event == "speech_end" and speech_started:
                    speech_started = False
                    pcm_full = bytes(buffer)
                    buffer = bytearray()
                    vad.reset()

                    text = brain.transcribe(pcm_full, SAMPLE_RATE)
                    if not text:
                        continue

                    print(f"[vokara-asterisk] caller said: {text}")
                    history.append({"role": "user", "content": text})
                    reply = brain.ask_llm(history)
                    history.append({"role": "assistant", "content": reply})
                    print(f"[vokara-asterisk] bot says: {reply}")

                    audio_out = brain.synthesize_piper(reply, SAMPLE_RATE)
                    # Send back as RTP-framed UDP packets to the caller's RTP
                    # source (simplified — a real implementation should track
                    # RTP seq/timestamp properly)
                    frame_size = 640  # 20ms @ 16kHz mono PCM16
                    for i in range(0, len(audio_out), frame_size):
                        sock.sendto(audio_out[i:i + frame_size], addr)

    finally:
        sock.close()


async def ari_event_loop():
    uri = f"{ARI_HOST.replace('http', 'ws')}/ari/events?app={ARI_APP}&api_key={ARI_USER}:{ARI_PASS}"
    async with websockets.connect(uri) as ws:
        print(f"[vokara-asterisk] connected to ARI events, app={ARI_APP}")
        async for message in ws:
            event = json.loads(message)
            if event.get("type") == "StasisStart":
                channel_id = event["channel"]["id"]
                asyncio.create_task(handle_channel(channel_id))


if __name__ == "__main__":
    asyncio.run(ari_event_loop())
