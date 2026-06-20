"""Unit tests for VoiceStateMachine."""

import time
import threading
import numpy as np
import pytest

from butler_voice.butler_voice.voice_state_machine import VoiceStateMachine, VoiceState, create_state_machine


class TestVoiceStateMachine:
    """Tests for VoiceStateMachine class."""

    def test_initialization(self):
        """Test state machine initialization."""
        sm = create_state_machine()
        assert sm.state == VoiceState.IDLE
        assert sm.previous_state == VoiceState.IDLE
        assert sm.state_duration >= 0
        assert sm.time_since_activity >= 0

    def test_state_transitions(self):
        """Test basic state transitions."""
        sm = create_state_machine()

        # Test IDLE -> WAKING
        sm.to_waking("test")
        assert sm.state == VoiceState.WAKING
        assert sm.previous_state == VoiceState.IDLE

        # Test WAKING -> LISTENING
        sm.to_listening("test")
        assert sm.state == VoiceState.LISTENING

        # Test LISTENING -> PROCESSING
        sm.to_processing("test")
        assert sm.state == VoiceState.PROCESSING

        # Test PROCESSING -> SPEAKING
        sm.to_speaking("test")
        assert sm.state == VoiceState.SPEAKING

        # Test SPEAKING -> IDLE
        sm.to_idle("test")
        assert sm.state == VoiceState.IDLE

    def test_error_transition(self):
        """Test error state transition."""
        sm = create_state_machine()

        sm.to_error("test error")
        assert sm.state == VoiceState.ERROR
        assert sm.get_context('error_message') == "test error"

    def test_timeout_transition(self):
        """Test timeout state transition."""
        sm = create_state_machine()

        sm.to_timeout("test timeout")
        assert sm.state == VoiceState.TIMEOUT

    def test_state_change_callback(self):
        """Test state change callback."""
        sm = create_state_machine()

        callback_calls = []

        def on_change(old_state, new_state, context):
            callback_calls.append((old_state, new_state))

        sm.on_state_change(on_change)

        sm.to_waking("test")
        assert len(callback_calls) == 1
        assert callback_calls[0] == (VoiceState.IDLE, VoiceState.WAKING)

        sm.to_listening("test")
        assert len(callback_calls) == 2
        assert callback_calls[1] == (VoiceState.WAKING, VoiceState.LISTENING)

    def test_state_enter_callback(self):
        """Test state enter callback."""
        sm = create_state_machine()

        enter_calls = []

        def on_waking_enter(context):
            enter_calls.append('waking')

        sm.on_state_enter(VoiceState.WAKING, on_waking_enter)

        sm.to_waking("test")
        assert 'waking' in enter_calls

    def test_state_exit_callback(self):
        """Test state exit callback."""
        sm = create_state_machine()

        exit_calls = []

        def on_idle_exit(context):
            exit_calls.append('idle')

        sm.on_state_exit(VoiceState.IDLE, on_idle_exit)

        sm.to_waking("test")
        assert 'idle' in exit_calls

    def test_wake_word_callback(self):
        """Test wake word callback."""
        sm = create_state_machine()

        wake_calls = []

        def on_wake_word():
            wake_calls.append(True)

        sm.on_wake_word(on_wake_word)

        sm.on_wake_word_detected()
        assert len(wake_calls) == 1

    def test_speech_callbacks(self):
        """Test speech start/end callbacks."""
        sm = create_state_machine()

        speech_start_calls = []
        speech_end_calls = []

        def on_speech_start():
            speech_start_calls.append(True)

        def on_speech_end(audio):
            speech_end_calls.append(audio)

        sm.on_speech_start(on_speech_start)
        sm.on_speech_end(on_speech_end)

        # First need to be in LISTENING state
        sm.to_waking("test")
        sm.to_listening("test")

        sm.on_speech_detected()
        assert len(speech_start_calls) == 1

        test_audio = np.zeros(100, dtype=np.int16)
        sm.on_speech_ended(test_audio)
        assert len(speech_end_calls) == 1
        assert np.array_equal(speech_end_calls[0], test_audio)

    def test_recognition_callback(self):
        """Test recognition result callback."""
        sm = create_state_machine()

        recognition_calls = []

        def on_recognition(text, confidence):
            recognition_calls.append((text, confidence))

        sm.on_recognition_result(on_recognition)

        # Need to be in PROCESSING state
        sm.to_waking("test")
        sm.to_listening("test")
        sm.to_processing("test")

        sm.on_recognition_complete("test text", 0.95)
        assert len(recognition_calls) == 1
        assert recognition_calls[0] == ("test text", 0.95)
        assert sm.get_context('recognized_text') == "test text"
        assert sm.get_context('confidence') == 0.95

    def test_speaking_callbacks(self):
        """Test speaking start/end callbacks."""
        sm = create_state_machine()

        speaking_start_calls = []
        speaking_end_calls = []

        def on_speaking_start():
            speaking_start_calls.append(True)

        def on_speaking_end():
            speaking_end_calls.append(True)

        sm.on_speaking_start(on_speaking_start)
        sm.on_speaking_end(on_speaking_end)

        sm.to_speaking("test")
        assert len(speaking_start_calls) == 1

        sm.on_speaking_complete()
        assert len(speaking_end_calls) == 1
        assert sm.state == VoiceState.IDLE

    def test_error_callback(self):
        """Test error callback."""
        sm = create_state_machine()

        error_calls = []

        def on_error(message):
            error_calls.append(message)

        sm.on_error(on_error)

        sm.on_error_occurred("test error")
        assert len(error_calls) == 1
        assert error_calls[0] == "test error"

    def test_context_management(self):
        """Test context data management."""
        sm = create_state_machine()

        # Set context
        sm.set_context('key1', 'value1')
        sm.set_context('key2', 42)

        assert sm.get_context('key1') == 'value1'
        assert sm.get_context('key2') == 42
        assert sm.get_context('nonexistent', 'default') == 'default'

        # Clear context
        sm.clear_context()
        assert sm.get_context('key1') is None

    def test_state_info(self):
        """Test state info retrieval."""
        sm = create_state_machine()

        info = sm.get_state_info()
        assert info['state'] == 'idle'
        assert info['previous_state'] == 'idle'
        assert 'state_duration' in info
        assert 'time_since_activity' in info
        assert 'context' in info

    def test_state_helpers(self):
        """Test state helper methods."""
        sm = create_state_machine()

        assert sm.is_idle()
        assert not sm.is_listening()
        assert not sm.is_processing()
        assert not sm.is_speaking()
        assert not sm.is_active()

        sm.to_listening("test")
        assert not sm.is_idle()
        assert sm.is_listening()
        assert sm.is_active()

    def test_reset(self):
        """Test state machine reset."""
        sm = create_state_machine()

        # Change state and add context
        sm.to_waking("test")
        sm.set_context('key', 'value')

        # Reset
        sm.reset()
        assert sm.state == VoiceState.IDLE
        assert sm.get_context('key') is None

    def test_wake_word_detected_flow(self):
        """Test wake word detection flow."""
        sm = create_state_machine()

        # Should transition from IDLE to WAKING to LISTENING
        sm.on_wake_word_detected()
        assert sm.state == VoiceState.WAKING

        # Wait for auto-transition to LISTENING
        time.sleep(0.6)
        assert sm.state == VoiceState.LISTENING

    def test_speech_flow(self):
        """Test complete speech flow."""
        sm = create_state_machine()

        # Start from LISTENING
        sm.to_listening("test")

        # Speech detected
        sm.on_speech_detected()
        assert sm.time_since_activity < 1.0

        # Speech ended
        audio = np.zeros(100, dtype=np.int16)
        sm.on_speech_ended(audio)
        assert sm.state == VoiceState.PROCESSING

        # Recognition complete
        sm.on_recognition_complete("test", 0.9)
        assert sm.state == VoiceState.PROCESSING  # Still processing

        # Speaking complete
        sm.to_speaking("test")
        sm.on_speaking_complete()
        assert sm.state == VoiceState.IDLE

    def test_timeout_handling(self):
        """Test timeout handling."""
        # Use short timeouts for testing
        sm = create_state_machine(
            wake_word_timeout=0.1,
            listening_timeout=0.1,
        )

        sm.to_waking("test")
        time.sleep(0.2)

        # Should have timed out
        assert sm.state == VoiceState.TIMEOUT or sm.state == VoiceState.IDLE

    def test_thread_safety(self):
        """Test thread safety of state transitions."""
        sm = create_state_machine()
        errors = []

        def worker():
            try:
                for _ in range(100):
                    sm.to_waking("thread")
                    sm.to_listening("thread")
                    sm.to_processing("thread")
                    sm.to_speaking("thread")
                    sm.to_idle("thread")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert sm.state == VoiceState.IDLE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
