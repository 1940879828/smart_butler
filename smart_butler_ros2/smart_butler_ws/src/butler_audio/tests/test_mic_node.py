"""Unit tests for MicNode."""

from unittest.mock import patch

import pytest
import rclpy


@pytest.fixture
def mic_node():
    """Create MicNode with mocked sounddevice."""
    rclpy.init()
    with patch('sounddevice.InputStream'), \
         patch('sounddevice.query_devices', return_value='mock device'):
        from butler_audio.mic_node import MicNode
        node = MicNode()
        node._running = False  # stop worker thread during test
        yield node
        node.destroy_node()
    rclpy.shutdown()


def test_mic_node_initialization(mic_node):
    """Verify node is created with correct parameters."""
    assert mic_node.get_name() == 'mic_node'
    assert mic_node._sample_rate == 16000
    assert mic_node._channels == 1
    assert mic_node.audio_pub is not None


def test_mic_node_parameters():
    """Verify parameters can be overridden."""
    import rclpy
    from butler_audio.mic_node import MicNode

    rclpy.init()
    try:
        node = MicNode()
        assert node.get_parameter('sample_rate').value == 16000
        assert node.get_parameter('channels').value == 1
    finally:
        rclpy.shutdown()
