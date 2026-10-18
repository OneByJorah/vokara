"""
Voice Activity Detection module for Vokara.

Provides Silero VAD (deep learning) with automatic fallback to
amplitude-threshold VAD when PyTorch is unavailable.

Usage:
    from vad import create_vad

    vad = create_vad(sample_rate=16000)
    is_speech = vad.is_speech(pcm_chunk_bytes)
    # or streaming:
    for event in vad.process_stream(pcm_chunk_bytes):
        if event == "speech_start":
            ...
        elif event == "speech_end":
            ...
"""

import logging
import os

import numpy as np

logger = logging.getLogger("vokara.vad")

SILENCE_THRESHOLD = int(os.environ.get("VAD_SILENCE_THRESHOLD", "500"))
SILENCE_MS = int(os.environ.get("VAD_SILENCE_MS", "700"))


# ─── Silero VAD (requires PyTorch) ─────────────────────────────────────────

def _silero_available() -> bool:
    try:
        import torch  # noqa: F401
        from silero_vad import load_silero_vad  # noqa: F401
        return True
    except ImportError:
        return False


class SileroVAD:
    """Deep-learning VAD via silero-vad (PyTorch backend)."""

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model = None
        self._iterator = None

    def _ensure_model(self):
        if self._model is not None:
            return
        import torch
        from silero_vad import load_silero_vad

        torch.set_num_threads(1)
        self._model = load_silero_vad()
        logger.info("Silero VAD model loaded")

    def _ensure_iterator(self):
        if self._iterator is not None:
            return
        self._ensure_model()
        from silero_vad import VADIterator

        self._iterator = VADIterator(
            self._model,
            sampling_rate=self.sample_rate,
            threshold=self.threshold,
        )

    def is_speech(self, pcm_bytes: bytes) -> bool:
        """Check if a single PCM16 chunk contains speech."""
        self._ensure_model()
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        import torch
        tensor = torch.from_numpy(audio)
        speech_prob = self._model(tensor, self.sample_rate).item()
        return speech_prob >= self.threshold

    def process_stream(self, pcm_bytes: bytes):
        """Streaming VAD: yields 'speech_start' / 'speech_end' events."""
        self._ensure_iterator()
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        import torch
        tensor = torch.from_numpy(audio)
        result = self._iterator(tensor)
        if result:
            if "start" in result:
                yield "speech_start"
            if "end" in result:
                yield "speech_end"

    def reset(self):
        """Reset VAD iterator state (call on new call session)."""
        self._iterator = None


# ─── Amplitude VAD (fallback, no deps) ────────────────────────────────────

class AmplitudeVAD:
    """Simple amplitude-threshold VAD — works well in quiet environments.

    Tracks state to yield both 'speech_start' and 'speech_end' events,
    matching the SileroVAD streaming interface.
    """

    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        self.silence_threshold = SILENCE_THRESHOLD
        self._silence_ms = 0
        self._speaking = False

    def is_speech(self, pcm_bytes: bytes) -> bool:
        chunk = np.frombuffer(pcm_bytes, dtype=np.int16)
        return bool(np.abs(chunk).mean() >= self.silence_threshold) if len(chunk) else False

    def process_stream(self, pcm_bytes: bytes):
        """Yields 'speech_start' / 'speech_end' events based on amplitude."""
        is_silent = not self.is_speech(pcm_bytes)
        frame_ms = (len(pcm_bytes) / 2) / self.sample_rate * 1000

        if not is_silent:
            # Speech detected — reset silence counter
            self._silence_ms = 0
            if not self._speaking:
                self._speaking = True
                yield "speech_start"
        else:
            # Silence detected — accumulate
            self._silence_ms += frame_ms
            if self._speaking and self._silence_ms >= SILENCE_MS:
                self._speaking = False
                self._silence_ms = 0
                yield "speech_end"

    def reset(self):
        self._silence_ms = 0
        self._speaking = False


# ─── Factory ───────────────────────────────────────────────────────────────

def create_vad(sample_rate: int = 8000) -> AmplitudeVAD | SileroVAD:
    """Create the best available VAD instance.

    Prefers Silero VAD when PyTorch is installed; falls back to
    amplitude-threshold VAD.
    """
    prefer_amplitude = os.environ.get("VAD_BACKEND", "").lower() == "amplitude"

    if not prefer_amplitude and _silero_available():
        logger.info("Using Silero VAD (deep learning)")
        return SileroVAD(sample_rate=sample_rate)

    logger.info("Using amplitude-threshold VAD (fallback)")
    return AmplitudeVAD(sample_rate=sample_rate)
