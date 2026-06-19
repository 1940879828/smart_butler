"""TTS client node for MOSS robot.

Subscribes to /moss/voice/speak for text, sends it to a Windows Piper TTS
service via HTTP POST, and publishes the resulting audio on
/moss/audio/tts_audio. Also forwards text to /moss/audio/tts_output for
logging and display.
"""

import base64
import io
import queue
import threading
import wave

from butler_msgs.msg import AudioData
import numpy as np
import rclpy
from rclpy.node import Node
import requests
import sounddevice as sd
from std_msgs.msg import String


class TTSClient(Node):
    """Text-to-speech client using remote Piper service."""

    def __init__(self):
        super().__init__('tts_client')

        self.declare_parameter('tts_endpoint',
                               'http://192.168.2.xxx:8002/synthesize')
        self.declare_parameter('voice', 'zh_CN')
        self.declare_parameter('sample_rate', 22050)
        self.declare_parameter('max_retries', 3)
        self.declare_parameter('auto_play', False)

        self._endpoint = self.get_parameter('tts_endpoint').value
        self._voice = self.get_parameter('voice').value
        self._sample_rate = self.get_parameter('sample_rate').value
        self._max_retries = self.get_parameter('max_retries').value
        self._auto_play = self.get_parameter('auto_play').value

        self.text_sub = self.create_subscription(
            String, '/moss/voice/speak', self._on_text, 10)
        self.tts_pub = self.create_publisher(
            String, '/moss/audio/tts_output', 10)
        self.audio_pub = self.create_publisher(
            AudioData, '/moss/audio/tts_audio', 10)

        self._play_queue = queue.Queue()
        self._running = True

        if self._auto_play:
            self._player = threading.Thread(
                target=self._play_loop, daemon=True)
            self._player.start()

        self.get_logger().info(
            f'TTS client ready (endpoint={self._endpoint}, '
            f'voice={self._voice})')

    def _on_text(self, msg: String):
        """Handle incoming text to be synthesized."""
        text = msg.data.strip()
        if not text:
            return

        self.get_logger().info(f'TTS request: {text}')

        tts_msg = String()
        tts_msg.data = text
        self.tts_pub.publish(tts_msg)

        thread = threading.Thread(
            target=self._synthesize_thread, args=(text,), daemon=True)
        thread.start()

    def _synthesize_thread(self, text: str):
        """Send text to TTS service with retries."""
        payload = {
            'text': text,
            'voice': self._voice,
            'sample_rate': self._sample_rate,
            'format': 'wav',
        }

        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    self._endpoint, json=payload, timeout=30)
                if resp.status_code == 200:
                    result = resp.json()
                    audio = self._parse_audio(result)
                    if audio is not None:
                        self._publish_audio(audio)
                        if self._auto_play:
                            self._play_queue.put(audio)
                    return
                else:
                    self.get_logger().warn(
                        f'TTS HTTP {resp.status_code}: {resp.text[:100]}')
            except requests.RequestException as e:
                self.get_logger().warn(
                    f'TTS attempt {attempt + 1}/{self._max_retries}: {e}')
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        self.get_logger().error(f'TTS failed for: {text}')

    def _parse_audio(self, result: dict):
        """Parse audio data from TTS service response."""
        if 'audio' in result:
            audio_base64 = result['audio']
            audio_bytes = base64.b64decode(audio_base64)
            return np.frombuffer(audio_bytes, dtype=np.int16)
        elif 'audio_url' in result:
            try:
                resp = requests.get(result['audio_url'], timeout=10)
                if resp.status_code == 200:
                    audio_bytes = resp.content
                    try:
                        with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
                            data = wf.readframes(wf.getnframes())
                            return np.frombuffer(data, dtype=np.int16)
                    except wave.Error:
                        return np.frombuffer(audio_bytes, dtype=np.int16)
            except requests.RequestException as e:
                self.get_logger().error(f'TTS audio download failed: {e}')
        return None

    def _publish_audio(self, audio: np.ndarray):
        """Publish synthesized audio as AudioData message."""
        msg = AudioData()
        msg.timestamp = self.get_clock().now().to_msg()
        msg.sample_rate = self._sample_rate
        msg.channels = 1
        msg.sample_width = 16
        msg.data = audio.tobytes()
        self.audio_pub.publish(msg)

    def _play_loop(self):
        """Playback loop for auto-play mode."""
        while self._running:
            try:
                audio = self._play_queue.get(timeout=0.5)
                if len(audio) > 0:
                    sd.play(audio.astype(np.float32) / 32767,
                            self._sample_rate)
                    sd.wait()
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f'Playback error: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = TTSClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._running = False
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
