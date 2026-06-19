"""Speaker node for MOSS robot audio output.

Subscribes to /moss/audio/tts_output and plays audio via sounddevice.
"""

import queue
import threading

import numpy as np
import rclpy
from rclpy.node import Node
import sounddevice as sd
from std_msgs.msg import String


class SpeakerNode(Node):
    """Audio playback node for TTS output."""

    def __init__(self):
        super().__init__('speaker_node')

        self.declare_parameter('sample_rate', 22050)
        self._sample_rate = self.get_parameter('sample_rate').value

        self._play_queue = queue.Queue()
        self._running = True

        self.tts_sub = self.create_subscription(
            String, '/moss/audio/tts_output', self._on_tts, 10)

        self._worker = threading.Thread(target=self._play_loop, daemon=True)
        self._worker.start()

        self.get_logger().info(
            f'SpeakerNode started (rate={self._sample_rate})')

    def _on_tts(self, msg: String):
        """Receive TTS text and log it."""
        text = msg.data.strip()
        if text:
            self.get_logger().info(f'TTS output: {text}')

    def _play_loop(self):
        """Background thread that processes play queue."""
        while self._running:
            try:
                data = self._play_queue.get(timeout=0.5)
                if isinstance(data, np.ndarray) and len(data) > 0:
                    sd.play(data.astype(np.float32), self._sample_rate)
                    sd.wait()
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f'Playback error: {e}')

    def destroy_node(self):
        self._running = False
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
