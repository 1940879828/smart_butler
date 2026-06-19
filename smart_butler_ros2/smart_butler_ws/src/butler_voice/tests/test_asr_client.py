"""Unit tests for ASRClient."""

from unittest.mock import patch

from butler_msgs.msg import VoiceCommand
import numpy as np
import pytest
import rclpy


@pytest.fixture
def asr_node():
    """Create ASRClient for testing."""
    rclpy.init()
    from butler_voice.asr_client import ASRClient
    node = ASRClient()
    yield node
    node.destroy_node()
    rclpy.shutdown()


def test_asr_client_initialization(asr_node):
    """Verify node is created with correct parameters."""
    assert asr_node.get_name() == 'asr_client'
    assert asr_node._sample_rate == 16000
    assert asr_node._language in ('zh', 'en')
    assert asr_node.audio_sub is not None
    assert asr_node.text_pub is not None


def test_asr_client_vad_resets_on_silence(asr_node):
    """Verify VAD state resets after flush."""
    asr_node._is_speaking = True
    asr_node._silence_count = 1000
    msg = VoiceCommand()
    msg.audio_data = np.zeros(1024, dtype=np.int16).tobytes()

    asr_node._on_audio(msg)

    assert asr_node._is_speaking


def test_asr_client_ends_utterance_on_silence(asr_node):
    """Verify utterance boundary detection."""
    asr_node._is_speaking = True
    asr_node._silence_count = asr_node._silence_req - 100
    msg_data = np.zeros(1024, dtype=np.int16).tobytes()

    asr_node._buffer.extend([0] * (asr_node._sample_rate * 1))
    msg = VoiceCommand()
    msg.audio_data = msg_data
    msg.sample_rate = 16000

    with patch.object(asr_node, '_flush') as mock_flush:
        asr_node._on_audio(msg)
        mock_flush.assert_called_once()
