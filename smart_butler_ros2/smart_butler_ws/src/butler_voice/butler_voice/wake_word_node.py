"""Wake word detection node for MOSS robot.

Detects the wake word "moss" using openWakeWord or energy-based detection.
Publishes wake word events on /moss/voice/wake_word.

Dependencies:
- openwakeword: pip install openwakeword
- onnxruntime: pip install onnxruntime (required by openwakeword)
"""

import logging
import threading
import time
from typing import Optional, Callable

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool

from butler_msgs.msg import VoiceCommand

# Lazy import openwakeword
_openwakeword = None
_oww_lock = threading.Lock()


def _get_openwakeword():
    """Lazy import openwakeword."""
    global _openwakeword
    if _openwakeword is None:
        with _oww_lock:
            if _openwakeword is None:
                try:
                    import openwakeword
                    _openwakeword = openwakeword
                except ImportError:
                    raise ImportError(
                        "openwakeword is required for wake word detection. "
                        "Install with: pip install openwakeword onnxruntime"
                    )
    return _openwakeword


class WakeWordDetector:
    """Wake word detector using openWakeWord.

    Args:
        wake_word: Wake word to detect (default: "moss")
        threshold: Detection threshold (0.0 to 1.0)
        sample_rate: Audio sample rate
        chunk_size: Audio chunk size for processing
    """

    def __init__(
        self,
        wake_word: str = "moss",
        threshold: float = 0.5,
        sample_rate: int = 16000,
        chunk_size: int = 1280,
    ):
        self._wake_word = wake_word
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size

        self._model = None
        self._model_loaded = False
        self._loading = False

        self._logger = logging.getLogger('wake_word_detector')

        # Callbacks
        self._on_detect: Optional[Callable] = None

    def set_callback(self, callback: Callable):
        """Set callback for wake word detection.

        Callback signature: callback(wake_word, confidence)
        """
        self._on_detect = callback

    def load_model(self):
        """Load the wake word model."""
        if self._model_loaded or self._loading:
            return

        self._loading = True
        try:
            oww = _get_openwakeword()

            # Initialize openWakeWord
            oww.utils.download_models()

            # Create model instance
            self._model = oww.Model()

            # Check if custom wake word model exists
            # For custom wake words, you may need to train or find a model
            # For now, we'll use the generic model and look for "hey jarvis" as a placeholder
            # In production, you'd train a custom model for "moss"

            self._model_loaded = True
            self._logger.info(
                f"Wake word model loaded. Looking for: {self._wake_word}")

        except Exception as e:
            self._logger.error(f"Failed to load wake word model: {e}")
            self._model_loaded = False
        finally:
            self._loading = False

    def process_audio(self, audio: np.ndarray) -> Optional[float]:
        """Process audio chunk and check for wake word.

        Args:
            audio: Audio data as numpy array (int16 or float32)

        Returns:
            Confidence score if wake word detected, None otherwise
        """
        if not self._model_loaded or self._model is None:
            return None

        # Convert to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure correct chunk size
        if len(audio) < self._chunk_size:
            audio = np.pad(audio, (0, self._chunk_size - len(audio)))
        elif len(audio) > self._chunk_size:
            audio = audio[:self._chunk_size]

        try:
            # Get prediction
            prediction = self._model.predict(audio)

            # Check for wake word
            # openWakeWord returns a dict with model names as keys
            for model_name, score in prediction.items():
                if score >= self._threshold:
                    self._logger.info(
                        f"Wake word detected! Model: {model_name}, "
                        f"Score: {score:.3f}")
                    if self._on_detect:
                        self._on_detect(self._wake_word, score)
                    return score

        except Exception as e:
            self._logger.error(f"Error processing audio: {e}")

        return None

    def set_threshold(self, threshold: float):
        """Set detection threshold."""
        self._threshold = min(1.0, max(0.0, threshold))

    def reset(self):
        """Reset the detector state."""
        if self._model:
            try:
                self._model.reset()
            except Exception:
                pass

    @property
    def is_loaded(self) -> bool:
        """Whether the model is loaded."""
        return self._model_loaded

    @property
    def is_loading(self) -> bool:
        """Whether the model is currently loading."""
        return self._loading


class SimpleWakeWordDetector:
    """Simple energy-based wake word detector (fallback).

    Uses energy patterns as a simple approximation when openWakeWord
    is not available. This is NOT accurate and should only be used
    for testing.

    Args:
        threshold: Energy threshold for detection
        min_duration: Minimum speech duration in seconds
        max_duration: Maximum speech duration in seconds
    """

    def __init__(
        self,
        threshold: int = 3000,
        min_duration: float = 0.2,
        max_duration: float = 1.0,
    ):
        self._threshold = threshold
        self._min_duration = min_duration
        self._max_duration = max_duration

        self._is_speaking = False
        self._speech_start = 0
        self._speech_buffer = []

        self._logger = logging.getLogger('simple_wake_word')

        self._on_detect: Optional[Callable] = None

    def set_callback(self, callback: Callable):
        """Set callback for wake word detection."""
        self._on_detect = callback

    def process_audio(self, audio: np.ndarray) -> Optional[float]:
        """Process audio and detect potential wake word.

        This is a very simple approximation based on speech patterns.
        """
        energy = np.abs(audio.astype(np.float64)).mean()

        if energy > self._threshold:
            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start = time.time()
                self._speech_buffer = []

            self._speech_buffer.append(audio)
        elif self._is_speaking:
            self._is_speaking = False
            duration = time.time() - self._speech_start

            # Check if duration is in wake word range
            if self._min_duration <= duration <= self._max_duration:
                # Simple heuristic: wake words are typically short
                confidence = 0.5  # Low confidence for simple detector
                self._logger.info(
                    f"Potential wake word detected (duration={duration:.2f}s)")
                if self._on_detect:
                    self._on_detect("moss", confidence)
                return confidence

            self._speech_buffer = []

        return None

    def reset(self):
        """Reset detector state."""
        self._is_speaking = False
        self._speech_buffer = []

    @property
    def is_loaded(self) -> bool:
        return True

    @property
    def is_loading(self) -> bool:
        return False


class WakeWordNode(Node):
    """ROS2 node for wake word detection.

    Subscribes to audio input and publishes wake word detection events.

    Parameters:
        wake_word: Wake word to detect (default: "moss")
        threshold: Detection threshold (default: 0.5)
        sample_rate: Audio sample rate (default: 16000)
        use_openwakeword: Whether to use openWakeWord (default: True)
        energy_threshold: Energy threshold for simple detector (default: 3000)
    """

    def __init__(self):
        super().__init__('wake_word_node')

        # Parameters
        self.declare_parameter('wake_word', 'moss')
        self.declare_parameter('threshold', 0.5)
        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('use_openwakeword', True)
        self.declare_parameter('energy_threshold', 3000)

        self._wake_word = self.get_parameter('wake_word').value
        self._threshold = self.get_parameter('threshold').value
        self._sample_rate = self.get_parameter('sample_rate').value
        self._use_openwakeword = self.get_parameter('use_openwakeword').value
        self._energy_threshold = self.get_parameter('energy_threshold').value

        # Initialize detector
        self._detector = None
        self._init_detector()

        # Publishers
        self._wake_pub = self.create_publisher(
            Bool, '/moss/voice/wake_word', 10)
        self._wake_text_pub = self.create_publisher(
            String, '/moss/voice/wake_word_text', 10)

        # Subscriber
        self._audio_sub = self.create_subscription(
            VoiceCommand, '/moss/audio/raw', self._on_audio, 10)

        # State
        self._enabled = True
        self._last_detect_time = 0
        self._cooldown = 2.0  # Cooldown between detections

        self.get_logger().info(
            f"Wake word node started. "
            f"Word: '{self._wake_word}', "
            f"Detector: {'openWakeWord' if self._use_openwakeword else 'simple'}")

    def _init_detector(self):
        """Initialize the wake word detector."""
        if self._use_openwakeword:
            try:
                self._detector = WakeWordDetector(
                    wake_word=self._wake_word,
                    threshold=self._threshold,
                    sample_rate=self._sample_rate,
                )
                # Load model in background
                threading.Thread(
                    target=self._detector.load_model,
                    daemon=True,
                ).start()
                self.get_logger().info("Using openWakeWord detector")
            except ImportError:
                self.get_logger().warn(
                    "openWakeWord not available, falling back to simple detector")
                self._detector = SimpleWakeWordDetector(
                    threshold=self._energy_threshold,
                )
        else:
            self._detector = SimpleWakeWordDetector(
                threshold=self._energy_threshold,
            )
            self.get_logger().info("Using simple energy-based detector")

        # Set detection callback
        self._detector.set_callback(self._on_wake_word_detected)

    def _on_audio(self, msg: VoiceCommand):
        """Process incoming audio."""
        if not self._enabled or not msg.audio_data:
            return

        # Convert bytes to numpy array
        raw = msg.audio_data
        if isinstance(raw, list):
            try:
                raw = bytes(raw)
            except TypeError:
                raw = bytes([b[0] for b in raw])
        elif isinstance(raw, bytearray):
            raw = bytes(raw)

        audio = np.frombuffer(raw, dtype=np.int16)

        # Process audio
        self._detector.process_audio(audio)

    def _on_wake_word_detected(self, wake_word: str, confidence: float):
        """Handle wake word detection."""
        current_time = time.time()

        # Check cooldown
        if current_time - self._last_detect_time < self._cooldown:
            return

        self._last_detect_time = current_time

        # Publish wake word event
        wake_msg = Bool()
        wake_msg.data = True
        self._wake_pub.publish(wake_msg)

        # Publish wake word text
        text_msg = String()
        text_msg.data = wake_word
        self._wake_text_pub.publish(text_msg)

        self.get_logger().info(
            f"Wake word '{wake_word}' detected! "
            f"Confidence: {confidence:.3f}")

    def enable(self):
        """Enable wake word detection."""
        self._enabled = True
        self.get_logger().info("Wake word detection enabled")

    def disable(self):
        """Disable wake word detection."""
        self._enabled = False
        self.get_logger().info("Wake word detection disabled")

    def set_threshold(self, threshold: float):
        """Set detection threshold."""
        self._threshold = threshold
        if isinstance(self._detector, WakeWordDetector):
            self._detector.set_threshold(threshold)
        self.get_logger().info(f"Threshold set to {threshold}")

    def destroy_node(self):
        """Clean up on node destruction."""
        if self._detector:
            self._detector.reset()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WakeWordNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
