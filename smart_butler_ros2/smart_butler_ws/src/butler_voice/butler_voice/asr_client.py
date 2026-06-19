"""ASR client node for MOSS robot.

Supports two backends:
- remote: sends audio to a Windows Whisper HTTP service
- local:  transcribes directly using local faster-whisper

Subscribes to /moss/audio/raw for VoiceCommand messages, performs VAD
on accumulated audio buffers, and publishes recognition results to
/moss/voice/recognized.
"""

import base64
from collections import deque
import hashlib
import logging
import os
import queue
import threading

import numpy as np
import rclpy
from rclpy.node import Node
import requests
from std_msgs.msg import String

from butler_msgs.msg import VoiceCommand


# ---------- local Whisper helpers ----------

_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()

# Suppress verbose CTranslate2 / faster-whisper logs
logging.getLogger('faster_whisper').setLevel(logging.WARNING)
logging.getLogger('ctranslate2').setLevel(logging.WARNING)


def _get_whisper_model(model_size: str, device: str, compute_type: str):
    """Load (or retrieve cached) faster-whisper model."""
    cache_key = (model_size, device, compute_type)
    with _MODEL_CACHE_LOCK:
        if cache_key not in _MODEL_CACHE:
            from faster_whisper import WhisperModel
            _MODEL_CACHE[cache_key] = WhisperModel(
                model_size, device=device, compute_type=compute_type)
    return _MODEL_CACHE[cache_key]


# ---------- ASR Client ----------

class ASRClient(Node):
    """Speech recognition client.

    Parameters
    ----------
    backend (str):
        'remote' (default) – POST audio to a Whisper HTTP service
        'local'           – transcribe directly with faster-whisper
    asr_endpoint (str):
        URL of the remote Whisper service (used only in remote mode).
    local_model (str):
        Whisper model size for local mode (tiny, base, small, medium, large).
    local_device (str):
        Device for local mode ('cpu' or 'cuda'). Defaults to 'cpu'.
    local_compute_type (str):
        Compute type for local mode. Defaults to 'int8' for cpu,
        'float16' for cuda.
    """

    def __init__(self):
        super().__init__('asr_client')

        # --- parameters ---
        self.declare_parameter('backend', 'remote')
        self.declare_parameter('asr_endpoint',
                               'http://192.168.2.xxx:8001/transcribe')
        self.declare_parameter('language', 'zh')
        self.declare_parameter('model', 'tiny')
        self.declare_parameter('buffer_duration', 2.0)
        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('silence_threshold', 500)
        self.declare_parameter('max_retries', 3)
        # local-only parameters
        self.declare_parameter('local_model', 'tiny')
        self.declare_parameter('local_device', 'cpu')
        self.declare_parameter('local_compute_type', 'int8')

        self._backend = self.get_parameter('backend').value
        self._endpoint = self.get_parameter('asr_endpoint').value
        self._language = self.get_parameter('language').value
        self._model_name = self.get_parameter('model').value
        self._buffer_dur = self.get_parameter('buffer_duration').value
        self._sample_rate = self.get_parameter('sample_rate').value
        self._silence_threshold = self.get_parameter('silence_threshold').value
        self._max_retries = self.get_parameter('max_retries').value

        self._local_model = self.get_parameter('local_model').value
        self._local_device = self.get_parameter('local_device').value
        self._local_compute_type = self.get_parameter(
            'local_compute_type').value

        # --- local Whisper model (loaded lazily on first use) ---
        self._whisper_model = None
        if self._backend == 'local':
            self._init_local_model()

        # --- VAD state ---
        buflen = int(self._sample_rate * self._buffer_dur)
        self._buffer = deque(maxlen=buflen)
        self._is_speaking = False
        self._silence_count = 0
        self._silence_req = int(self._sample_rate * 0.5)  # 0.5 s silence

        # --- ROS2 interface ---
        self.audio_sub = self.create_subscription(
            VoiceCommand, '/moss/audio/raw', self._on_audio, 10)
        self.text_pub = self.create_publisher(
            String, '/moss/voice/recognized', 10)

        self._result_queue = queue.Queue()
        self.create_timer(0.1, self._publish_results)

        self.get_logger().info(
            f'ASR client ready (backend={self._backend}, '
            f'lang={self._language}, model={self._model_name})')

    # ---- local model init ------------------------------------------------

    def _init_local_model(self):
        """Load the local faster-whisper model in a background thread."""
        self.get_logger().info(
            f'Loading local Whisper model "{self._local_model}" '
            f'on {self._local_device} (compute={self._local_compute_type}) ...')
        thread = threading.Thread(
            target=self._load_model, daemon=True, name='whisper-loader')
        thread.start()

    def _load_model(self):
        try:
            self._whisper_model = _get_whisper_model(
                self._local_model, self._local_device, self._local_compute_type)
            self.get_logger().info(
                f'Local Whisper model "{self._local_model}" loaded.')
        except Exception as e:
            self.get_logger().error(f'Failed to load local Whisper model: {e}')
            self._whisper_model = None

    # ---- VAD callback ------------------------------------------------

    def _on_audio(self, msg: VoiceCommand):
        """Receive audio data and run basic energy-based VAD."""
        if not msg.audio_data:
            return

        audio = np.frombuffer(msg.audio_data, dtype=np.int16)
        energy = np.abs(audio).mean()

        if energy > self._silence_threshold:
            self._is_speaking = True
            self._silence_count = 0
            self._buffer.extend(audio.tolist())
        elif self._is_speaking:
            self._silence_count += len(audio)
            self._buffer.extend(audio.tolist())
            if self._silence_count >= self._silence_req:
                self._flush()

    # ---- flush & dispatch ------------------------------------------------

    def _flush(self):
        """Send buffered audio for transcription."""
        min_samples = int(self._sample_rate * 0.5)
        if len(self._buffer) < min_samples:
            self._reset()
            return

        audio_data = np.array(list(self._buffer), dtype=np.int16)
        self._reset()

        if self._backend == 'local':
            thread = threading.Thread(
                target=self._transcribe_local,
                args=(audio_data,), daemon=True)
        else:
            thread = threading.Thread(
                target=self._transcribe_remote,
                args=(audio_data,), daemon=True)
        thread.start()

    def _reset(self):
        self._buffer.clear()
        self._is_speaking = False
        self._silence_count = 0

    # ---- remote transcription --------------------------------------------

    def _transcribe_remote(self, audio: np.ndarray):
        """Send audio to a remote Whisper HTTP service with retries."""
        audio_b64 = base64.b64encode(audio.tobytes()).decode('utf-8')
        payload = {
            'audio': audio_b64,
            'language': self._language,
            'model': self._model_name,
            'sample_rate': self._sample_rate,
            'encoding': 'int16',
        }

        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    self._endpoint, json=payload, timeout=10)
                if resp.status_code == 200:
                    text = resp.json().get('text', '')
                    if text and text.strip():
                        self._result_queue.put(text.strip())
                    return
                self.get_logger().warn(
                    f'ASR HTTP {resp.status_code}: {resp.text[:100]}')
            except requests.RequestException as e:
                self.get_logger().warn(
                    f'ASR attempt {attempt + 1}/{self._max_retries}: {e}')
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        self.get_logger().error('Remote ASR request failed after all retries')

    # ---- local transcription ---------------------------------------------

    def _transcribe_local(self, audio: np.ndarray):
        """Transcribe audio using the local faster-whisper model."""
        if self._whisper_model is None:
            self.get_logger().error(
                'Local Whisper model not ready. Is it still loading?',
                throttle_duration_sec=5.0)
            return

        try:
            # Convert int16 → float32 in [-1, 1]
            audio_f32 = audio.astype(np.float32) / 32768.0

            segments, _ = self._whisper_model.transcribe(
                audio_f32,
                language=self._language if self._language != 'auto' else None,
                beam_size=5,
            )

            text = ' '.join(seg.text.strip() for seg in segments).strip()
            if text:
                self._result_queue.put(text)
                self.get_logger().info(f'[local] Recognized: {text}')
        except Exception as e:
            self.get_logger().error(f'Local transcription failed: {e}')

    # ---- result publishing -----------------------------------------------

    def _publish_results(self):
        """Periodically publish queued recognition results."""
        while not self._result_queue.empty():
            try:
                text = self._result_queue.get_nowait()
                msg = String()
                msg.data = text
                self.text_pub.publish(msg)
                self.get_logger().info(f'Recognized: {text}')
            except queue.Empty:
                break


def main(args=None):
    rclpy.init(args=args)
    node = ASRClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
