"""ASR client node for MOSS robot.

Subscribes to /moss/audio/raw for VoiceCommand messages, performs VAD
on accumulated audio buffers, and sends audio to a Windows Whisper service
via HTTP POST. Published recognition results to /moss/voice/recognized.
"""

import base64
from collections import deque
import queue
import threading

from butler_msgs.msg import VoiceCommand
import numpy as np
import rclpy
from rclpy.node import Node
import requests
from std_msgs.msg import String


class ASRClient(Node):
    """Speech recognition client using remote Whisper service."""

    def __init__(self):
        super().__init__('asr_client')

        self.declare_parameter('asr_endpoint',
                               'http://192.168.2.xxx:8001/transcribe')
        self.declare_parameter('language', 'zh')
        self.declare_parameter('model', 'base')
        self.declare_parameter('buffer_duration', 2.0)
        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('silence_threshold', 500)
        self.declare_parameter('max_retries', 3)

        self._endpoint = self.get_parameter('asr_endpoint').value
        self._language = self.get_parameter('language').value
        self._model = self.get_parameter('model').value
        self._buffer_dur = self.get_parameter('buffer_duration').value
        self._sample_rate = self.get_parameter('sample_rate').value
        self._silence_threshold = self.get_parameter('silence_threshold').value
        self._max_retries = self.get_parameter('max_retries').value

        self._buffer = deque(
            maxlen=int(self._sample_rate * self._buffer_dur))
        self._is_speaking = False
        self._silence_count = 0
        self._silence_req = int(self._sample_rate * 0.5)

        self.audio_sub = self.create_subscription(
            VoiceCommand, '/moss/audio/raw', self._on_audio, 10)
        self.text_pub = self.create_publisher(
            String, '/moss/voice/recognized', 10)

        self._result_queue = queue.Queue()
        self.create_timer(0.1, self._publish_results)

        self.get_logger().info(
            f'ASR client ready (endpoint={self._endpoint}, '
            f'lang={self._language}, model={self._model})')

    def _on_audio(self, msg: VoiceCommand):
        """Receive audio data and run basic VAD."""
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

    def _flush(self):
        """Send buffered audio to ASR service in a background thread."""
        if len(self._buffer) < self._sample_rate * 0.5:
            self._reset()
            return

        audio_data = np.array(list(self._buffer), dtype=np.int16)
        self._reset()

        thread = threading.Thread(
            target=self._transcribe_thread, args=(audio_data,), daemon=True)
        thread.start()

    def _reset(self):
        self._buffer.clear()
        self._is_speaking = False
        self._silence_count = 0

    def _transcribe_thread(self, audio: np.ndarray):
        """Send audio to Whisper service with retries."""
        audio_base64 = base64.b64encode(audio.tobytes()).decode('utf-8')
        payload = {
            'audio': audio_base64,
            'language': self._language,
            'model': self._model,
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
                else:
                    self.get_logger().warn(
                        f'ASR HTTP {resp.status_code}: {resp.text[:100]}')
            except requests.RequestException as e:
                self.get_logger().warn(
                    f'ASR attempt {attempt + 1}/{self._max_retries}: {e}')
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        self.get_logger().error('ASR request failed after all retries')

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
