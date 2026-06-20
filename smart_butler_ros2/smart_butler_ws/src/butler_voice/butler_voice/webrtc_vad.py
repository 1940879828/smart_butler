"""WebRTC VAD wrapper for voice activity detection.

Provides a more robust VAD compared to simple energy thresholding.
WebRTC VAD uses machine learning to distinguish speech from noise.
"""

import collections
import threading
from typing import Optional, Callable

import numpy as np

# Lazy import webrtcvad to avoid hard dependency
_webrtcvad = None
_import_lock = threading.Lock()


def _get_webrtcvad():
    """Lazy import webrtcvad module."""
    global _webrtcvad
    if _webrtcvad is None:
        with _import_lock:
            if _webrtcvad is None:
                try:
                    import webrtcvad
                    _webrtcvad = webrtcvad
                except ImportError:
                    raise ImportError(
                        "webrtcvad is required for WebRTC VAD. "
                        "Install it with: pip install webrtcvad"
                    )
    return _webrtcvad


class WebRTCVAD:
    """WebRTC Voice Activity Detection wrapper.

    This class provides a more robust VAD implementation using WebRTC's
    voice activity detection algorithm, which is better at distinguishing
    speech from background noise compared to simple energy thresholding.

    Args:
        sample_rate: Audio sample rate in Hz (8000, 16000, 32000, or 48000)
        aggressiveness: VAD aggressiveness mode (0-3)
            0: Least aggressive (most permissive)
            3: Most aggressive (least permissive, good for noisy environments)
        frame_duration_ms: Frame duration in milliseconds (10, 20, or 30)
        padding_duration_ms: Padding duration for context (300ms recommended)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
        frame_duration_ms: int = 30,
        padding_duration_ms: int = 300,
    ):
        self._sample_rate = sample_rate
        self._aggressiveness = aggressiveness
        self._frame_duration_ms = frame_duration_ms
        self._padding_duration_ms = padding_duration_ms

        # Validate parameters
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError(
                f"Sample rate must be 8000, 16000, 32000, or 48000, got {sample_rate}"
            )
        if aggressiveness not in (0, 1, 2, 3):
            raise ValueError(
                f"Aggressiveness must be 0-3, got {aggressiveness}"
            )
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError(
                f"Frame duration must be 10, 20, or 30ms, got {frame_duration_ms}"
            )

        # Calculate frame size in samples
        self._frame_size = int(sample_rate * frame_duration_ms / 1000)

        # Calculate number of padding frames
        num_padding_frames = int(padding_duration_ms / frame_duration_ms)
        self._ring_buffer = collections.deque(maxlen=num_padding_frames)

        # State
        self._voiced_frames = []
        self._triggered = False

        # Initialize VAD
        vad = _get_webrtcvad()
        self._vad = vad.Vad(aggressiveness)

        # Callbacks
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
        self._on_vad_update: Optional[Callable] = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def aggressiveness(self) -> int:
        return self._aggressiveness

    @property
    def frame_size(self) -> int:
        return self._frame_size

    @property
    def is_speech(self) -> bool:
        """Whether speech is currently detected."""
        return self._triggered

    def set_callbacks(
        self,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable] = None,
        on_vad_update: Optional[Callable] = None,
    ):
        """Set callback functions for VAD events.

        Args:
            on_speech_start: Called when speech starts
            on_speech_end: Called when speech ends (with collected audio)
            on_vad_update: Called on each VAD update with (is_speech, probability)
        """
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_vad_update = on_vad_update

    def process_frame(self, frame: np.ndarray) -> bool:
        """Process a single audio frame and return whether speech is detected.

        Args:
            frame: Audio frame as numpy array (int16 or float32)
                  If float32, will be converted to int16

        Returns:
            True if speech is detected in this frame
        """
        # Convert to int16 if needed
        if frame.dtype == np.float32 or frame.dtype == np.float64:
            frame = (frame * 32767).astype(np.int16)
        elif frame.dtype != np.int16:
            frame = frame.astype(np.int16)

        # Ensure correct frame size
        if len(frame) != self._frame_size:
            # Resample or pad if needed
            if len(frame) < self._frame_size:
                frame = np.pad(frame, (0, self._frame_size - len(frame)))
            else:
                frame = frame[:self._frame_size]

        # Convert to bytes for WebRTC VAD
        frame_bytes = frame.tobytes()

        # Check if frame is speech
        try:
            is_speech = self._vad.is_speech(frame_bytes, self._sample_rate)
        except Exception:
            # If VAD fails, assume no speech
            return False

        # Update ring buffer
        self._ring_buffer.append((frame_bytes, is_speech))

        # Notify update
        if self._on_vad_update:
            self._on_vad_update(is_speech)

        # State machine for speech detection
        if not self._triggered:
            # Check if enough frames in ring buffer are speech
            num_voiced = sum(1 for _, speech in self._ring_buffer if speech)
            if num_voiced > 0.9 * self._ring_buffer.maxlen:
                self._triggered = True
                self._voiced_frames = [f for f, _ in self._ring_buffer]
                if self._on_speech_start:
                    self._on_speech_start()
        else:
            # Accumulate voiced frames
            self._voiced_frames.append(frame_bytes)

            # Check if speech has ended
            num_unvoiced = sum(1 for _, speech in self._ring_buffer if not speech)
            if num_unvoiced > 0.9 * self._ring_buffer.maxlen:
                self._triggered = False
                if self._on_speech_end:
                    # Concatenate all voiced frames
                    audio_bytes = b''.join(self._voiced_frames)
                    audio = np.frombuffer(audio_bytes, dtype=np.int16)
                    self._on_speech_end(audio)
                self._voiced_frames = []

        return self._triggered

    def process_audio(self, audio: np.ndarray) -> tuple[bool, Optional[np.ndarray]]:
        """Process a chunk of audio and return speech detection result.

        This is a convenience method that processes multiple frames.

        Args:
            audio: Audio data as numpy array (int16 or float32)

        Returns:
            Tuple of (is_speech, speech_audio)
            - is_speech: True if speech is currently detected
            - speech_audio: Collected speech audio when speech ends, None otherwise
        """
        # Convert to int16 if needed
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            audio = (audio * 32767).astype(np.int16)
        elif audio.dtype != np.int16:
            audio = audio.astype(np.int16)

        speech_audio = None
        is_speech = False

        # Process frame by frame
        for i in range(0, len(audio), self._frame_size):
            frame = audio[i:i + self._frame_size]
            if len(frame) < self._frame_size:
                # Pad last frame if needed
                frame = np.pad(frame, (0, self._frame_size - len(frame)))

            # Create a temporary callback to capture speech end
            captured_audio = None

            # Use default argument to capture current value
            def on_speech_end(audio_data, _captured=None):
                nonlocal captured_audio
                captured_audio = audio_data

            # Set temporary callback
            original_callback = self._on_speech_end
            self._on_speech_end = on_speech_end

            # Process frame
            is_speech = self.process_frame(frame)

            # Restore original callback
            self._on_speech_end = original_callback

            # If speech ended, call original callback
            if captured_audio is not None:
                speech_audio = captured_audio
                if original_callback:
                    original_callback(captured_audio)

        return is_speech, speech_audio

    def reset(self):
        """Reset the VAD state."""
        self._ring_buffer.clear()
        self._voiced_frames = []
        self._triggered = False


class HybridVAD:
    """Hybrid VAD combining energy threshold and WebRTC VAD.

    Uses both energy-based detection and WebRTC VAD for more robust
    voice activity detection.

    Args:
        sample_rate: Audio sample rate in Hz
        energy_threshold: Energy threshold for initial detection
        webrtc_aggressiveness: WebRTC VAD aggressiveness (0-3)
        use_webrtc: Whether to use WebRTC VAD (requires webrtcvad package)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: int = 500,
        webrtc_aggressiveness: int = 2,
        use_webrtc: bool = True,
    ):
        self._sample_rate = sample_rate
        self._energy_threshold = energy_threshold
        self._use_webrtc = use_webrtc

        # Energy-based state
        self._is_speaking_energy = False
        self._silence_count = 0
        self._silence_required = int(sample_rate * 0.5)  # 500ms silence

        # WebRTC VAD
        self._webrtc_vad = None
        if use_webrtc:
            try:
                self._webrtc_vad = WebRTCVAD(
                    sample_rate=sample_rate,
                    aggressiveness=webrtc_aggressiveness,
                )
            except ImportError:
                self._use_webrtc = False

        # Combined state
        self._is_speaking = False
        self._speech_buffer = []

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def energy_threshold(self) -> int:
        return self._energy_threshold

    @energy_threshold.setter
    def energy_threshold(self, value: int):
        self._energy_threshold = value

    def process(self, audio: np.ndarray) -> tuple[bool, Optional[np.ndarray]]:
        """Process audio and detect speech.

        Args:
            audio: Audio data as numpy array (int16)

        Returns:
            Tuple of (is_speech, speech_audio)
            - is_speech: True if speech is detected
            - speech_audio: Complete speech audio when speech ends
        """
        # Convert to int16 if needed
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            audio = (audio * 32767).astype(np.int16)

        # Energy-based detection
        energy = np.abs(audio.astype(np.float64)).mean()
        energy_speech = energy > self._energy_threshold

        # WebRTC VAD detection
        webrtc_speech = False
        if self._use_webrtc and self._webrtc_vad:
            webrtc_speech, webrtc_audio = self._webrtc_vad.process_audio(audio)
            if webrtc_audio is not None:
                # Speech ended from WebRTC
                return True, webrtc_audio

        # Combined decision
        if self._use_webrtc and self._webrtc_vad:
            # Use WebRTC as primary, energy as secondary
            is_speech = webrtc_speech or (energy_speech and self._is_speaking)
        else:
            # Energy-only detection
            is_speech = energy_speech

        # State machine for energy-based detection
        if is_speech:
            if not self._is_speaking:
                self._is_speaking = True
                self._speech_buffer = []
            self._silence_count = 0
            self._speech_buffer.append(audio)
        elif self._is_speaking:
            self._silence_count += len(audio)
            self._speech_buffer.append(audio)

            # Check for speech end
            if self._silence_count >= self._silence_required:
                self._is_speaking = False
                if self._speech_buffer:
                    speech_audio = np.concatenate(self._speech_buffer)
                    self._speech_buffer = []
                    return True, speech_audio
                self._speech_buffer = []

        return self._is_speaking, None

    def reset(self):
        """Reset the VAD state."""
        self._is_speaking = False
        self._is_speaking_energy = False
        self._silence_count = 0
        self._speech_buffer = []
        if self._webrtc_vad:
            self._webrtc_vad.reset()


def create_vad(
    sample_rate: int = 16000,
    energy_threshold: int = 500,
    use_webrtc: bool = True,
    webrtc_aggressiveness: int = 2,
) -> HybridVAD:
    """Create a VAD instance with the given parameters.

    Args:
        sample_rate: Audio sample rate in Hz
        energy_threshold: Energy threshold for detection
        use_webrtc: Whether to use WebRTC VAD
        webrtc_aggressiveness: WebRTC VAD aggressiveness (0-3)

    Returns:
        HybridVAD instance
    """
    return HybridVAD(
        sample_rate=sample_rate,
        energy_threshold=energy_threshold,
        use_webrtc=use_webrtc,
        webrtc_aggressiveness=webrtc_aggressiveness,
    )
