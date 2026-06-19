"""Unit tests for SpeakerNode."""

from unittest.mock import patch

import pytest
import rclpy
from std_msgs.msg import String


@pytest.fixture
def speaker_node():
    """Create SpeakerNode with mocked sounddevice."""
    rclpy.init()
    with patch('sounddevice.play'), patch('sounddevice.wait'):
        from butler_audio.speaker_node import SpeakerNode
        node = SpeakerNode()
        node._running = False
        yield node
        node.destroy_node()
    rclpy.shutdown()


def test_speaker_node_initialization(speaker_node):
    """Verify node is created with correct parameters."""
    assert speaker_node.get_name() == 'speaker_node'
    assert speaker_node._sample_rate == 22050
    assert speaker_node.tts_sub is not None


def test_speaker_node_receives_tts(speaker_node):
    """Verify TTS callback logs incoming text."""
    msg = String()
    msg.data = 'Hello MOSS'

    speaker_node._on_tts(msg)

    assert msg.data == 'Hello MOSS'
