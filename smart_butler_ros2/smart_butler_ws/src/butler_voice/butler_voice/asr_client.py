"""ASR client node for MOSS robot.

Supports multiple backends, switchable via the `backend` parameter or sim.yaml:
- mimo         – MiMo v2.5 ASR via chat/completions multimodal API
- local        – local faster-whisper inference
- whisper_remote – (design) POST base64 to Windows Whisper HTTP service

Subscribes to /moss/audio/raw for VoiceCommand messages, performs VAD on
accumulated audio buffers, and publishes recognition results to
/moss/voice/recognized.

VAD modes:
- energy: Simple energy threshold (legacy, fast but less accurate)
- webrtc: WebRTC VAD (more accurate, requires webrtcvad package)
- hybrid: Combined energy + WebRTC (best accuracy)
"""

import base64
from collections import deque
import io
import logging
import os
import queue
import threading
import wave

import numpy as np
import rclpy
from rclpy.node import Node
import requests
from std_msgs.msg import String
import yaml

from butler_msgs.msg import VoiceCommand

# Import WebRTC VAD module
try:
    from .webrtc_vad import HybridVAD, create_vad
    HAS_WEBRTC_VAD = True
except ImportError:
    HAS_WEBRTC_VAD = False
    # Fallback: define dummy classes
    class HybridVAD:
        def __init__(self, *args, **kwargs):
            pass
        def process(self, audio):
            return False, None
        def reset(self):
            pass
    def create_vad(*args, **kwargs):
        return HybridVAD()


# ---- Voice band-pass filter (lazy init) -----------------------------

_bandpass_sos = None
_bandpass_lock = threading.Lock()


def _get_bandpass_filter(sample_rate, lowcut=80, highcut=4000, order=4):
    """Band-pass filter for human voice (80-4000Hz)."""
    global _bandpass_sos
    cache_key = (sample_rate, lowcut, highcut, order)
    with _bandpass_lock:
        if _bandpass_sos is None or _bandpass_sos.get('key') != cache_key:
            from scipy.signal import butter
            nyq = 0.5 * sample_rate
            low = lowcut / nyq
            high = highcut / nyq
            sos = butter(order, [low, high], btype='band', output='sos')
            _bandpass_sos = {'key': cache_key, 'sos': sos}
        return _bandpass_sos['sos']


# ---- config helpers ------------------------------------------------

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'config', 'sim.yaml')
_CONFIG_PATH = os.path.normpath(os.path.abspath(_CONFIG_PATH))

_LOG = logging.getLogger('asr_client')


def _find_workspace_root():
    """Walk up from this file to find the workspace root (contains config/)."""
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cfg_dir = os.path.join(path, 'config')
        if os.path.isdir(cfg_dir):
            return path
        path = os.path.dirname(path)
    return os.path.dirname(os.path.dirname(__file__))


def _load_yaml_config():
    """Load voice.asr section from sim.yaml, resolving ${ENV_VAR} placeholders."""
    ws_root = _find_workspace_root()
    cfg_path = os.path.join(ws_root, 'config', 'sim.yaml')
    if not os.path.isfile(cfg_path):
        _LOG.warning('sim.yaml not found at %s', cfg_path)
        return {}

    with open(cfg_path, 'r', encoding='utf-8') as fh:
        raw = yaml.safe_load(fh)

    asr = raw.get('nodes', {}).get('voice', {}).get('asr', {})
    if not isinstance(asr, dict):
        return {}

    # Expand environment variables in string values
    resolved = {}
    for key, value in asr.items():
        if isinstance(value, str):
            resolved[key] = os.path.expandvars(value)
        else:
            resolved[key] = value
    return resolved


# ---- local Whisper helpers -----------------------------------------

_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()

logging.getLogger('faster_whisper').setLevel(logging.WARNING)
logging.getLogger('ctranslate2').setLevel(logging.WARNING)


def _get_whisper_model(model_size: str, device: str, compute_type: str):
    cache_key = (model_size, device, compute_type)
    with _MODEL_CACHE_LOCK:
        if cache_key not in _MODEL_CACHE:
            from faster_whisper import WhisperModel
            _MODEL_CACHE[cache_key] = WhisperModel(
                model_size, device=device, compute_type=compute_type)
    return _MODEL_CACHE[cache_key]


# ---- WAV encoding --------------------------------------------------

def _encode_wav_b64(audio: np.ndarray, sample_rate: int) -> str:
    """Convert int16 PCM audio to a WAV data URL string."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f'data:audio/wav;base64,{b64}'


# ---- ASR Client ----------------------------------------------------

class ASRClient(Node):
    """Speech recognition client.

    Configuration is loaded from config/sim.yaml (voice.asr section).
    ROS2 parameters override YAML values at runtime.
    """

    def __init__(self):
        super().__init__('asr_client')

        # Load YAML config as base defaults
        self._cfg = _load_yaml_config()

        # --- parameters (YAML defaults + ROS2 param override) ---
        self.declare_parameter('backend', self._cfg.get('backend', 'mimo'))
        self.declare_parameter('language', self._cfg.get('language', 'zh'))
        self.declare_parameter('sample_rate',
                               self._cfg.get('sample_rate', 16000))
        self.declare_parameter('buffer_duration',
                               self._cfg.get('buffer_duration', 2.0))
        self.declare_parameter('silence_threshold',
                               self._cfg.get('silence_threshold', 500))
        self.declare_parameter('max_retries',
                               self._cfg.get('max_retries', 3))
        self.declare_parameter('noise_reduction',
                               self._cfg.get('noise_reduction', True))
        self.declare_parameter('filter_lowcut',
                               self._cfg.get('filter_lowcut', 80))
        self.declare_parameter('filter_highcut',
                               self._cfg.get('filter_highcut', 4000))

        # VAD configuration
        self.declare_parameter('vad_mode',
                               self._cfg.get('vad_mode', 'hybrid'))
        self.declare_parameter('webrtc_aggressiveness',
                               self._cfg.get('webrtc_aggressiveness', 2))

        # MiMo / remote params
        self.declare_parameter('api_base',
                               self._cfg.get('api_base', ''))
        self.declare_parameter('api_key',
                               self._cfg.get('api_key', ''))
        self.declare_parameter('model',
                               self._cfg.get('model', 'mimo-v2.5-asr'))

        # Design path: Windows Whisper remote params
        self.declare_parameter('whisper_endpoint',
                               self._cfg.get('whisper_endpoint', ''))
        self.declare_parameter('local_model',
                               self._cfg.get('local_model', 'tiny'))
        self.declare_parameter('local_device',
                               self._cfg.get('local_device', 'cpu'))
        self.declare_parameter('local_compute_type',
                               self._cfg.get('local_compute_type', 'int8'))

        # Read resolved values
        self._backend = self.get_parameter('backend').value
        self._language = self.get_parameter('language').value
        self._sample_rate = self.get_parameter('sample_rate').value
        self._buffer_dur = self.get_parameter('buffer_duration').value
        self._silence_threshold = self.get_parameter('silence_threshold').value
        self._max_retries = self.get_parameter('max_retries').value
        self._noise_reduction = self.get_parameter('noise_reduction').value
        self._filter_lowcut = self.get_parameter('filter_lowcut').value
        self._filter_highcut = self.get_parameter('filter_highcut').value

        self._api_base = self.get_parameter('api_base').value.rstrip('/')
        self._api_key = self.get_parameter('api_key').value
        self._model = self.get_parameter('model').value

        self._local_model = self.get_parameter('local_model').value
        self._local_device = self.get_parameter('local_device').value
        self._local_compute_type = self.get_parameter(
            'local_compute_type').value

        self._whisper_endpoint = self.get_parameter('whisper_endpoint').value

        # VAD configuration
        self._vad_mode = self.get_parameter('vad_mode').value
        self._webrtc_aggressiveness = self.get_parameter('webrtc_aggressiveness').value

        # --- local Whisper model (loaded lazily) ---
        self._whisper_model = None
        if self._backend == 'local':
            self._init_local_model()

        # --- noise reduction filter ---
        if self._noise_reduction:
            _get_bandpass_filter(
                self._sample_rate, self._filter_lowcut, self._filter_highcut)
            self.get_logger().info(
                f'Noise reduction enabled ({self._filter_lowcut}-'
                f'{self._filter_highcut}Hz band-pass)')

        # --- VAD initialization ---
        self._vad = None
        if self._vad_mode in ('webrtc', 'hybrid'):
            if HAS_WEBRTC_VAD:
                try:
                    self._vad = create_vad(
                        sample_rate=self._sample_rate,
                        energy_threshold=self._silence_threshold,
                        use_webrtc=True,
                        webrtc_aggressiveness=self._webrtc_aggressiveness,
                    )
                    self.get_logger().info(
                        f'WebRTC VAD enabled (mode={self._vad_mode}, '
                        f'aggressiveness={self._webrtc_aggressiveness})')
                except Exception as e:
                    self.get_logger().warn(
                        f'Failed to initialize WebRTC VAD: {e}. '
                        f'Falling back to energy-based VAD.')
                    self._vad_mode = 'energy'
                    self._vad = None
            else:
                self.get_logger().warn(
                    'WebRTC VAD requested but webrtcvad not installed. '
                    'Falling back to energy-based VAD. '
                    'Install with: pip install webrtcvad')
                self._vad_mode = 'energy'

        # --- VAD state (for energy-based fallback) ---
        buflen = int(self._sample_rate * self._buffer_dur)
        self._buffer = deque(maxlen=buflen)
        self._is_speaking = False
        self._silence_count = 0
        self._silence_req = int(self._sample_rate * 0.5)

        # --- ROS2 interface ---
        self.audio_sub = self.create_subscription(
            VoiceCommand, '/moss/audio/raw', self._on_audio, 10)
        self.text_pub = self.create_publisher(
            String, '/moss/voice/recognized', 10)

        self._result_queue = queue.Queue()
        self.create_timer(0.1, self._publish_results)

        backend_info = f'backend={self._backend}'
        if self._backend == 'mimo':
            backend_info += f', api_base={self._api_base}, model={self._model}'
        self.get_logger().info(
            f'ASR client ready ({backend_info}, lang={self._language})')

    # ---- local model init ------------------------------------------

    def _init_local_model(self):
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

    # ---- VAD callback ----------------------------------------------

    def _on_audio(self, msg: VoiceCommand):
        if not msg.audio_data:
            return

        # ROS2 Jazzy deserializes byte[] as list[int], list[bytes], bytearray, or bytes
        raw = msg.audio_data
        if isinstance(raw, list):
            try:
                raw = bytes(raw)
            except TypeError:
                # list[bytes] quirk in ROS2 Jazzy
                raw = bytes([b[0] for b in raw])
        elif isinstance(raw, bytearray):
            raw = bytes(raw)

        audio = np.frombuffer(raw, dtype=np.int16)

        # Voice band-pass filter (80-4000Hz) to reduce background noise
        if self._noise_reduction:
            from scipy.signal import sosfilt
            sos = _get_bandpass_filter(
                self._sample_rate, self._filter_lowcut, self._filter_highcut)
            audio_f32 = audio.astype(np.float32)
            audio_f32 = sosfilt(sos, audio_f32)
            audio = audio_f32.astype(np.int16)

        # Process audio through VAD
        if self._vad_mode in ('webrtc', 'hybrid') and self._vad is not None:
            # Use WebRTC/hybrid VAD
            is_speech, speech_audio = self._vad.process(audio)

            # If speech ended, we have complete audio to transcribe
            if speech_audio is not None and len(speech_audio) > 0:
                self._dispatch_transcription(speech_audio)
        else:
            # Fallback to energy-based VAD
            self._process_energy_vad(audio)

    def _process_energy_vad(self, audio: np.ndarray):
        """Process audio using simple energy-based VAD (fallback)."""
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

        # Auto-flush when buffer is full (safety: VAD may never detect silence
        # if ambient noise is above threshold)
        if len(self._buffer) >= self._buffer.maxlen:
            self._flush()

    # ---- flush & dispatch ------------------------------------------

    def _flush(self):
        """Flush energy-based VAD buffer and dispatch for transcription."""
        min_samples = int(self._sample_rate * 0.5)
        if len(self._buffer) < min_samples:
            self._reset()
            return

        audio_data = np.array(list(self._buffer), dtype=np.int16)
        self._reset()

        self._dispatch_transcription(audio_data)

    def _dispatch_transcription(self, audio_data: np.ndarray):
        """Dispatch audio for transcription in background thread."""
        if self._backend == 'local':
            target = self._transcribe_local
        elif self._backend == 'mimo':
            target = self._transcribe_mimo
        else:
            target = self._transcribe_remote         # design path

        thread = threading.Thread(
            target=target, args=(audio_data,), daemon=True)
        thread.start()

    def _reset(self):
        """Reset VAD state."""
        self._buffer.clear()
        self._is_speaking = False
        self._silence_count = 0
        if self._vad:
            self._vad.reset()

    # ---- MiMo chat-completions multimodal ASR ----------------------

    def _transcribe_mimo(self, audio: np.ndarray):
        """Send WAV audio to MiMo via /v1/chat/completions multimodal API."""
        if not self._api_key:
            self.get_logger().error(
                'MiMo API key not set.')
            return

        url = f'{self._api_base}/chat/completions'
        data_url = _encode_wav_b64(audio, self._sample_rate)

        payload = {
            'model': self._model,
            'messages': [{
                'role': 'user',
                'content': [{
                    'type': 'input_audio',
                    'input_audio': {
                        'data': data_url,
                        'format': 'wav',
                    },
                }],
            }],
            'asr_options': {
                'language': self._language,
            },
        }

        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    url,
                    headers={
                        'Authorization': f'Bearer {self._api_key}',
                        'Content-Type': 'application/json',
                    },
                    json=payload,
                    timeout=30,
                )

                if resp.status_code == 200:
                    body = resp.json()
                    choices = body.get('choices', [])
                    if choices:
                        text = choices[0].get('message', {}).get('content', '')
                        if text and text.strip():
                            self._result_queue.put(text.strip())
                            self.get_logger().info(
                                f'[mimo] Recognized: {text}')
                        else:
                            self.get_logger().info(
                                '[mimo] Recognition returned empty text')
                    return

                self.get_logger().warn(
                    f'MiMo HTTP {resp.status_code}: {resp.text[:200]}')

            except requests.RequestException as e:
                self.get_logger().warn(
                    f'MiMo attempt {attempt + 1}/{self._max_retries}: {e}')
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        self.get_logger().error('MiMo ASR request failed after all retries')

    # ---- remote Windows Whisper service (design) --------------------

    def _transcribe_remote(self, audio: np.ndarray):
        """Send base64 audio to the Windows Whisper HTTP service.

        Original design path: Ubuntu captures audio, Windows GPU transcribes.
        """
        if not self._whisper_endpoint:
            self.get_logger().error(
                'Whisper endpoint not configured.')
            return

        audio_b64 = base64.b64encode(audio.tobytes()).decode('utf-8')
        payload = {
            'audio': audio_b64,
            'language': self._language,
            'model': self._model,
            'sample_rate': self._sample_rate,
            'encoding': 'int16',
        }

        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    self._whisper_endpoint, json=payload, timeout=10)
                if resp.status_code == 200:
                    text = resp.json().get('text', '')
                    if text and text.strip():
                        self._result_queue.put(text.strip())
                        self.get_logger().info(
                            f'[whisper] Recognized: {text}')
                    return
                self.get_logger().warn(
                    f'Whisper HTTP {resp.status_code}: {resp.text[:100]}')
            except requests.RequestException as e:
                self.get_logger().warn(
                    f'Whisper attempt {attempt + 1}/{self._max_retries}: {e}')
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        self.get_logger().error('Whisper ASR request failed after all retries')

    # ---- local transcription ---------------------------------------

    def _transcribe_local(self, audio: np.ndarray):
        """Transcribe audio using local faster-whisper.

        CPU-only inference, used when the remote service is unavailable.
        """
        if self._whisper_model is None:
            self.get_logger().error(
                'Local Whisper model not ready. Is it still loading?',
                throttle_duration_sec=5.0)
            return

        try:
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

    # ---- result publishing -----------------------------------------

    def _publish_results(self):
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
