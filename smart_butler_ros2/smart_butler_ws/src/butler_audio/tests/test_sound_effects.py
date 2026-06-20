"""Unit tests for sound effects module."""

import numpy as np
import pytest

from butler_audio.butler_audio.sound_effects import (
    SoundEffectsManager,
    SoundEffectType,
    SoundEffect,
    get_sound_manager,
    play_sound,
)


class TestSoundEffect:
    """Tests for SoundEffect class."""

    def test_initialization(self):
        """Test SoundEffect initialization."""
        data = np.zeros(1000, dtype=np.float32)
        effect = SoundEffect("test", data, 22050, 0.8)

        assert effect.name == "test"
        assert len(effect.data) == 1000
        assert effect.sample_rate == 22050
        assert effect.volume == 0.8

    def test_get_playable(self):
        """Test getting playable audio data."""
        data = np.ones(1000, dtype=np.float32)
        effect = SoundEffect("test", data, 22050, 0.5)

        playable = effect.get_playable()
        assert len(playable) == 1000
        assert np.allclose(playable, 0.5)  # volume applied

    def test_volume_clamping(self):
        """Test volume is clamped to [0, 1]."""
        data = np.zeros(100, dtype=np.float32)

        effect1 = SoundEffect("test", data, 22050, 1.5)
        assert effect1.volume == 1.0

        effect2 = SoundEffect("test", data, 22050, -0.5)
        assert effect2.volume == 0.0


class TestSoundEffectsManager:
    """Tests for SoundEffectsManager class."""

    def test_initialization(self):
        """Test SoundEffectsManager initialization."""
        manager = SoundEffectsManager(sample_rate=22050, default_volume=0.8)

        # Should have default effects
        available = manager.get_available_effects()
        assert len(available) > 0
        assert SoundEffectType.WAKE_WORD in available
        assert SoundEffectType.ERROR in available

    def test_default_effects(self):
        """Test that all default effects are created."""
        manager = SoundEffectsManager()

        expected_effects = [
            SoundEffectType.WAKE_WORD,
            SoundEffectType.LISTENING_START,
            SoundEffectType.LISTENING_END,
            SoundEffectType.PROCESSING,
            SoundEffectType.SUCCESS,
            SoundEffectType.ERROR,
            SoundEffectType.TIMEOUT,
            SoundEffectType.CONFIRMATION,
            SoundEffectType.CANCEL,
            SoundEffectType.NOTIFICATION,
        ]

        for effect_type in expected_effects:
            assert effect_type in manager._effects

    def test_generate_sine(self):
        """Test sine wave generation."""
        manager = SoundEffectsManager()

        # Generate 1 second of 440Hz sine wave
        sine = manager._generate_sine(440, 1.0)
        assert len(sine) == 22050  # default sample rate
        assert sine.dtype == np.float32
        assert np.max(np.abs(sine)) <= 1.0

    def test_generate_tone(self):
        """Test tone generation."""
        manager = SoundEffectsManager()

        # Single frequency
        tone = manager._generate_tone([440], 0.5)
        assert len(tone) == int(22050 * 0.5)

        # Frequency sweep
        sweep = manager._generate_tone([440, 880], 0.5)
        assert len(sweep) == int(22050 * 0.5)

    def test_generate_ding(self):
        """Test ding sound generation."""
        manager = SoundEffectsManager()

        ding = manager._generate_ding(880, 0.3)
        assert len(ding) == int(22050 * 0.3)
        assert ding.dtype == np.float32

    def test_generate_chord(self):
        """Test chord generation."""
        manager = SoundEffectsManager()

        chord = manager._generate_chord([440, 550, 660], 0.4)
        assert len(chord) == int(22050 * 0.4)

    def test_generate_pulse(self):
        """Test pulse generation."""
        manager = SoundEffectsManager()

        pulse = manager._generate_pulse(600, 1.0, 2.0)
        assert len(pulse) == int(22050 * 1.0)

    def test_generate_double_beep(self):
        """Test double beep generation."""
        manager = SoundEffectsManager()

        beep = manager._generate_double_beep(800, 0.1, 0.05)
        expected_len = int(22050 * (0.1 + 0.05 + 0.1))
        assert len(beep) == expected_len

    def test_generate_chime(self):
        """Test chime generation."""
        manager = SoundEffectsManager()

        chime = manager._generate_chime([800, 1000], 0.3)
        assert len(chime) == int(22050 * 0.3)

    def test_add_custom_effect(self):
        """Test adding custom sound effect."""
        manager = SoundEffectsManager()

        data = np.zeros(1000, dtype=np.float32)
        manager.add_custom_effect("custom", data, 22050, 0.7)

        assert "custom" in manager.get_custom_effects()
        assert manager._custom_effects["custom"].volume == 0.7

    def test_set_volume(self):
        """Test setting volume for specific effect."""
        manager = SoundEffectsManager()

        manager.set_volume(SoundEffectType.WAKE_WORD, 0.5)
        assert manager._effects[SoundEffectType.WAKE_WORD].volume == 0.5

    def test_set_global_volume(self):
        """Test setting global volume."""
        manager = SoundEffectsManager()

        manager.set_global_volume(0.3)
        for effect in manager._effects.values():
            assert effect.volume == 0.3

    def test_set_global_volume_clamping(self):
        """Test global volume clamping."""
        manager = SoundEffectsManager()

        manager.set_global_volume(1.5)
        for effect in manager._effects.values():
            assert effect.volume == 1.0

        manager.set_global_volume(-0.5)
        for effect in manager._effects.values():
            assert effect.volume == 0.0

    def test_play_nonexistent_effect(self):
        """Test playing non-existent effect."""
        manager = SoundEffectsManager()

        # Should not raise exception
        manager.play(custom_name="nonexistent")

    def test_play_effect(self):
        """Test playing an effect (mocked)."""
        manager = SoundEffectsManager()

        # Mock sounddevice to avoid actual playback
        import unittest.mock
        with unittest.mock.patch('sounddevice.play'):
            manager.play(SoundEffectType.WAKE_WORD, blocking=True)

    def test_stop(self):
        """Test stopping playback."""
        manager = SoundEffectsManager()

        # Mock sounddevice
        import unittest.mock
        with unittest.mock.patch('sounddevice.stop'):
            manager.stop()

    def test_is_playing(self):
        """Test is_playing property."""
        manager = SoundEffectsManager()
        assert not manager.is_playing

    def test_global_manager(self):
        """Test global manager instance."""
        manager1 = get_sound_manager()
        manager2 = get_sound_manager()
        assert manager1 is manager2  # Same instance

    def test_play_sound_convenience(self):
        """Test convenience play_sound function."""
        import unittest.mock
        with unittest.mock.patch('sounddevice.play'):
            play_sound(SoundEffectType.WAKE_WORD, blocking=True)


class TestSoundEffectTypes:
    """Tests for SoundEffectType enum."""

    def test_all_types(self):
        """Test that all expected types exist."""
        expected = [
            'WAKE_WORD', 'LISTENING_START', 'LISTENING_END',
            'PROCESSING', 'SUCCESS', 'ERROR', 'TIMEOUT',
            'CONFIRMATION', 'CANCEL', 'NOTIFICATION',
        ]

        for name in expected:
            assert hasattr(SoundEffectType, name)

    def test_string_values(self):
        """Test string values of enum."""
        assert SoundEffectType.WAKE_WORD.value == "wake_word"
        assert SoundEffectType.ERROR.value == "error"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
