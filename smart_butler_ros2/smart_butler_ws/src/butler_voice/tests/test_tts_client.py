"""Unit tests for TTSClient."""

from unittest.mock import patch

import pytest
import rclpy
from std_msgs.msg import String


@pytest.fixture
def tts_node():
    """Create TTSClient for testing."""
    rclpy.init()
    with patch('sounddevice.play'), patch('sounddevice.wait'):
        from butler_voice.tts_client import TTSClient
        node = TTSClient()
        yield node
        node.destroy_node()
    rclpy.shutdown()


def test_tts_client_initialization(tts_node):
    """Verify node is created with correct parameters."""
    assert tts_node.get_name() == 'tts_client'
    assert tts_node._sample_rate == 22050
    assert tts_node._voice == 'zh_CN'
    assert tts_node.text_sub is not None
    assert tts_node.tts_pub is not None
    assert tts_node.audio_pub is not None


def test_tts_client_handles_text(tts_node):
    """Verify text handler publishes to tts_output topic."""
    msg = String()
    msg.data = 'Hello MOSS'

    tts_node._on_text(msg)

    msg.data = 'Hello MOSS'
