"""Microphone capture node for MOSS robot audio pipeline.

Captures audio from the system microphone and publishes VoiceCommand messages
on /moss/audio/raw for downstream ASR processing.
"""

import queue
import threading

from butler_msgs.msg import VoiceCommand
import numpy as np
import rclpy
from rclpy.node import Node
import sounddevice as sd


class MicNode(Node):
    """Microphone audio capture node using sounddevice."""

    def __init__(self):
        super().__init__('mic_node')

        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('channels', 1)
        self.declare_parameter('device', '')
        self.declare_parameter('blocksize', 1024)

        self._sample_rate = self.get_parameter('sample_rate').value
        self._channels = self.get_parameter('channels').value
        self._device = self.get_parameter('device').value or None
        self._blocksize = self.get_parameter('blocksize').value

        self.audio_pub = self.create_publisher(
            VoiceCommand, '/moss/audio/raw', 10)

        self._queue = queue.Queue(maxsize=200)
        self._running = False
        self._stream = None

        self._start()

    def _start(self):
        """Start audio stream and processing thread."""
        self._running = True
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                device=self._device,
                callback=self._audio_callback,
                blocksize=self._blocksize,
            )
            self._stream.start()
        except Exception as e:
            self.get_logger().error(f'Failed to open audio device: {e}')
            self.get_logger().info(
                'Available devices:\n' + str(sd.query_devices()))
            self._running = False
            return

        self._worker = threading.Thread(target=self._process, daemon=True)
        self._worker.start()

        self.get_logger().info(
            f'MicNode started (rate={self._sample_rate}, '
            f'channels={self._channels})')

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.get_logger().warn(str(status))
        if self._running and indata is not None:
            try:
                self._queue.put_nowait(indata.copy())
            except queue.Full:
                pass

    def _process(self):
        """Worker thread: dequeue and publish audio frames."""
        while self._running:
            try:
                audio = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            msg = VoiceCommand()
            msg.text = ''
            msg.confidence = 0.0
            msg.is_final = False
            msg.sample_rate = self._sample_rate

            int16_data = (audio.flatten() * 32767).astype(np.int16)
            msg.audio_data = int16_data.tobytes()

            self.audio_pub.publish(msg)

    def destroy_node(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MicNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
