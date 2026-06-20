#!/usr/bin/env python3
"""Integration test for butler_audio and butler_voice modules.

This script tests the integration of:
- Sound effects
- VAD (WebRTC and energy-based)
- State machine
- ASR client (mocked)

Run with: python integration_test.py
"""

import os
import sys
import time
import threading
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestSoundEffectsIntegration(unittest.TestCase):
    """Test sound effects integration."""

    def test_sound_effects_import(self):
        """Test importing sound effects module."""
        from butler_audio.sound_effects import (
            SoundEffectsManager,
            SoundEffectType,
            get_sound_manager,
        )

        manager = SoundEffectsManager()
        self.assertIsNotNone(manager)

        # Check all effect types
        for effect_type in SoundEffectType:
            self.assertIn(effect_type, manager.get_available_effects())

    def test_sound_generation(self):
        """Test sound generation functions."""
        from butler_audio.sound_effects import SoundEffectsManager

        manager = SoundEffectsManager()

        # Test all generation methods
        ding = manager._generate_ding(880, 0.1)
        self.assertGreater(len(ding), 0)
        self.assertEqual(ding.dtype, np.float32)

        tone = manager._generate_tone([440], 0.1)
        self.assertGreater(len(tone), 0)

        chord = manager._generate_chord([440, 550], 0.1)
        self.assertGreater(len(chord), 0)

        pulse = manager._generate_pulse(600, 0.1, 2.0)
        self.assertGreater(len(pulse), 0)

        beep = manager._generate_double_beep(800, 0.05, 0.02)
        self.assertGreater(len(beep), 0)

        chime = manager._generate_chime([800, 1000], 0.1)
        self.assertGreater(len(chime), 0)

    @patch('sounddevice.play')
    @patch('sounddevice.wait')
    def test_sound_playback(self, mock_wait, mock_play):
        """Test sound playback."""
        from butler_audio.sound_effects import SoundEffectsManager, SoundEffectType

        manager = SoundEffectsManager()
        manager.play(SoundEffectType.WAKE_WORD, blocking=True)

        mock_play.assert_called_once()
        mock_wait.assert_called_once()


class TestVADIntegration(unittest.TestCase):
    """Test VAD integration."""

    def test_energy_vad(self):
        """Test energy-based VAD."""
        from butler_voice.webrtc_vad import HybridVAD

        vad = HybridVAD(sample_rate=16000, energy_threshold=500, use_webrtc=False)

        # Test silence
        silence = np.zeros(1024, dtype=np.int16)
        is_speech, audio = vad.process(silence)
        self.assertFalse(is_speech)
        self.assertIsNone(audio)

        # Test speech
        speech = np.random.randint(-5000, 5000, 1024, dtype=np.int16)
        is_speech, audio = vad.process(speech)
        self.assertTrue(is_speech)
        self.assertIsNone(audio)  # Still speaking

        # Test speech end
        for _ in range(100):
            is_speech, audio = vad.process(silence)
            if audio is not None:
                break

        self.assertIsNotNone(audio)
        self.assertGreater(len(audio), 0)

    def test_webrtc_vad_import(self):
        """Test WebRTC VAD import."""
        try:
            from butler_voice.webrtc_vad import WebRTCVAD, create_vad

            # Try to create VAD
            vad = create_vad(sample_rate=16000, use_webrtc=True)
            self.assertIsNotNone(vad)
        except ImportError:
            print("WebRTC VAD not available, skipping test")

    def test_vad_reset(self):
        """Test VAD reset functionality."""
        from butler_voice.webrtc_vad import HybridVAD

        vad = HybridVAD(sample_rate=16000, energy_threshold=500, use_webrtc=False)

        # Process some audio
        speech = np.random.randint(-5000, 5000, 1024, dtype=np.int16)
        vad.process(speech)

        # Reset
        vad.reset()
        self.assertFalse(vad.is_speaking)


class TestStateMachineIntegration(unittest.TestCase):
    """Test state machine integration."""

    def test_state_machine_creation(self):
        """Test state machine creation."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState

        sm = create_state_machine()
        self.assertEqual(sm.state, VoiceState.IDLE)

    def test_state_transitions(self):
        """Test state transitions."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState

        sm = create_state_machine()

        # Test full flow
        sm.on_wake_word_detected()
        self.assertEqual(sm.state, VoiceState.WAKING)

        time.sleep(0.6)
        self.assertEqual(sm.state, VoiceState.LISTENING)

        sm.on_speech_detected()
        sm.on_speech_ended(np.zeros(100, dtype=np.int16))
        self.assertEqual(sm.state, VoiceState.PROCESSING)

        sm.on_recognition_complete("test", 0.9)
        sm.to_speaking("test")
        sm.on_speaking_complete()
        self.assertEqual(sm.state, VoiceState.IDLE)

    def test_state_callbacks(self):
        """Test state machine callbacks."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState

        sm = create_state_machine()

        callback_log = []

        def on_change(old, new, ctx):
            callback_log.append(('change', old, new))

        def on_wake():
            callback_log.append(('wake',))

        sm.on_state_change(on_change)
        sm.on_wake_word(on_wake)

        sm.on_wake_word_detected()

        self.assertTrue(any(c[0] == 'wake' for c in callback_log))
        self.assertTrue(any(c[0] == 'change' for c in callback_log))

    def test_state_context(self):
        """Test state machine context."""
        from butler_voice.voice_state_machine import create_state_machine

        sm = create_state_machine()

        sm.set_context('key1', 'value1')
        sm.set_context('key2', 42)

        self.assertEqual(sm.get_context('key1'), 'value1')
        self.assertEqual(sm.get_context('key2'), 42)

        sm.clear_context()
        self.assertIsNone(sm.get_context('key1'))


class TestASRClientIntegration(unittest.TestCase):
    """Test ASR client integration (mocked)."""

    @patch('requests.post')
    def test_asr_transcription(self, mock_post):
        """Test ASR transcription (mocked)."""
        from butler_voice.asr_client import transcribe_mimo

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '测试文本'
                }
            }]
        }
        mock_post.return_value = mock_response

        # Test transcription
        audio = np.zeros(16000, dtype=np.int16)  # 1 second of silence
        cfg = {
            'api_base': 'http://test.com/v1',
            'api_key': 'test_key',
            'model': 'test_model',
            'language': 'zh',
            'sample_rate': 16000,
        }

        try:
            from scripts.asr_test_gui import transcribe_mimo as gui_transcribe
            text, elapsed = gui_transcribe(audio, cfg)
            self.assertEqual(text, '测试文本')
            self.assertGreater(elapsed, 0)
        except ImportError:
            # Fallback to direct import
            pass


class TestFullIntegration(unittest.TestCase):
    """Test full integration of all components."""

    def test_full_workflow(self):
        """Test full workflow integration."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState
        from butler_voice.webrtc_vad import HybridVAD
        from butler_audio.sound_effects import SoundEffectsManager, SoundEffectType

        # Create components
        sm = create_state_machine()
        vad = HybridVAD(sample_rate=16000, energy_threshold=500, use_webrtc=False)
        sound = SoundEffectsManager()

        # Simulate workflow
        self.assertEqual(sm.state, VoiceState.IDLE)

        # Wake word detection
        sm.on_wake_word_detected()
        self.assertEqual(sm.state, VoiceState.WAKING)

        # Wait for auto-transition
        time.sleep(0.6)
        self.assertEqual(sm.state, VoiceState.LISTENING)

        # Speech detection
        speech_audio = np.random.randint(-5000, 5000, 16000, dtype=np.int16)
        is_speech, ended_audio = vad.process(speech_audio)
        self.assertTrue(is_speech)

        # Speech end
        sm.on_speech_ended(speech_audio)
        self.assertEqual(sm.state, VoiceState.PROCESSING)

        # Recognition
        sm.on_recognition_complete("打开客厅灯", 0.95)
        self.assertEqual(sm.get_context('recognized_text'), "打开客厅灯")

        # Speaking
        sm.to_speaking("test")
        self.assertEqual(sm.state, VoiceState.SPEAKING)

        # Complete
        sm.on_speaking_complete()
        self.assertEqual(sm.state, VoiceState.IDLE)

    def test_error_handling(self):
        """Test error handling in integration."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState

        sm = create_state_machine()

        # Simulate error
        sm.on_error_occurred("测试错误")
        self.assertEqual(sm.state, VoiceState.ERROR)
        self.assertEqual(sm.get_context('error_message'), "测试错误")

        # Recovery
        sm.to_idle("recovery")
        self.assertEqual(sm.state, VoiceState.IDLE)

    def test_timeout_handling(self):
        """Test timeout handling."""
        from butler_voice.voice_state_machine import create_state_machine, VoiceState

        # Create with short timeouts
        sm = create_state_machine(
            wake_word_timeout=0.1,
            listening_timeout=0.1,
        )

        sm.to_waking("test")
        time.sleep(0.2)

        # Should have timed out
        self.assertIn(sm.state, [VoiceState.TIMEOUT, VoiceState.IDLE])


def run_integration_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("Running Integration Tests")
    print("=" * 60)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestSoundEffectsIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestVADIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestStateMachineIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestASRClientIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestFullIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1)
