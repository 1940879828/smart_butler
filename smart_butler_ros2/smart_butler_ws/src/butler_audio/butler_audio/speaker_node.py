"""Speaker node for MOSS robot audio output.

Subscribes to:
- /moss/audio/audio_data (AudioData) for raw audio playback
- /moss/audio/tts_output (String) for TTS text logging
"""

import queue
import threading

from butler_msgs.msg import AudioData
import numpy as np
import rclpy
from rclpy.node import Node
import sounddevice as sd
from std_msgs.msg import String


class SpeakerNode(Node):
    """Audio playback node for TTS output and raw audio."""

    def __init__(self):
        super().__init__('speaker_node')

        self.declare_parameter('sample_rate', 22050)
        self.declare_parameter('channels', 1)
        self.declare_parameter('device', '')
        self._sample_rate = self.get_parameter('sample_rate').value
        self._channels = self.get_parameter('channels').value
        self._device = self.get_parameter('device').value or None

        self._play_queue = queue.Queue()
        self._running = True

        # Subscribe to raw audio data
        self.audio_sub = self.create_subscription(
            AudioData, '/moss/audio/audio_data', self._on_audio_data, 10)

        # Subscribe to TTS text (for logging/coordination)
        self.tts_sub = self.create_subscription(
            String, '/moss/audio/tts_output', self._on_tts, 10)

        # Publisher for playback state
        self.state_pub = self.create_publisher(
            String, '/moss/audio/playback_state', 10)

        self._worker = threading.Thread(target=self._play_loop, daemon=True)
        self._worker.start()

        self.get_logger().info(
            f'SpeakerNode started (rate={self._sample_rate}, '
            f'channels={self._channels})')

    def _on_audio_data(self, msg: AudioData):
        """Receive AudioData and queue for playback."""
        if not msg.data:
            return

        # Convert bytes to numpy array based on sample width
        if msg.sample_width == 16:
            audio = np.frombuffer(msg.data, dtype=np.int16).astype(np.float32) / 32768.0
        elif msg.sample_width == 32:
            audio = np.frombuffer(msg.data, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif msg.sample_width == 8:
            audio = np.frombuffer(msg.data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
        else:
            self.get_logger().warn(f'Unsupported sample width: {msg.sample_width}')
            return

        # Reshape for multi-channel if needed
        if msg.channels > 1:
            audio = audio.reshape(-1, msg.channels)

        # Use message sample rate or default
        sample_rate = msg.sample_rate if msg.sample_rate > 0 else self._sample_rate

        self._play_queue.put((audio, sample_rate))
        self.get_logger().debug(f'Queued audio: {len(audio)} samples, {sample_rate}Hz')

    def _on_tts(self, msg: String):
        """Receive TTS text and log it."""
        text = msg.data.strip()
        if text:
            self.get_logger().info(f'TTS output: {text}')

    def _play_loop(self):
        """Background thread that processes play queue."""
        while self._running:
            try:
                item = self._play_queue.get(timeout=0.5)
                if item is None:
                    continue

                audio, sample_rate = item
                if len(audio) == 0:
                    continue

                # Publish playback state
                state_msg = String()
                state_msg.data = 'playing'
                self.state_pub.publish(state_msg)

                try:
                    # Stop any current playback
                    sd.stop()

                    # Play audio
                    sd.play(audio, sample_rate, device=self._device)
                    sd.wait()
                except Exception as e:
                    self.get_logger().error(f'Playback error: {e}')
                finally:
                    # Publish playback finished state
                    state_msg = String()
                    state_msg.data = 'idle'
                    self.state_pub.publish(state_msg)

            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f'Play loop error: {e}')

    def destroy_node(self):
        self._running = False
        sd.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = SpeakerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
