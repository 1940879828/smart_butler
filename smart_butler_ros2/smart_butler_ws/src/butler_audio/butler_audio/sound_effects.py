"""Sound effects manager for MOSS robot.

Provides various audio cues for different robot states:
- Wake word detection (ding sound)
- Error notifications
- Timeout warnings
- Processing indicators
- Success confirmations

Sound effects can be:
1. Generated programmatically (sine waves, beeps)
2. Loaded from WAV files
3. Synthesized using TTS
"""

import logging
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Callable

import numpy as np

# Lazy imports for audio playback
_sounddevice = None
_sd_lock = threading.Lock()


def _get_sounddevice():
    """Lazy import sounddevice."""
    global _sounddevice
    if _sounddevice is None:
        with _sd_lock:
            if _sounddevice is None:
                try:
                    import sounddevice as sd
                    _sounddevice = sd
                except ImportError:
                    raise ImportError(
                        "sounddevice is required for audio playback. "
                        "Install with: pip install sounddevice"
                    )
    return _sounddevice


class SoundEffectType(Enum):
    """Types of sound effects."""
    WAKE_WORD = "wake_word"          # 唤醒词检测成功
    LISTENING_START = "listening"    # 开始监听
    LISTENING_END = "listening_end"  # 停止监听
    PROCESSING = "processing"        # 处理中
    SUCCESS = "success"              # 操作成功
    ERROR = "error"                  # 错误
    TIMEOUT = "timeout"              # 超时
    CONFIRMATION = "confirmation"    # 确认
    CANCEL = "cancel"                # 取消
    NOTIFICATION = "notification"    # 通知


class SoundEffect:
    """Represents a single sound effect."""

    def __init__(
        self,
        name: str,
        data: np.ndarray,
        sample_rate: int = 22050,
        volume: float = 0.8,
    ):
        self.name = name
        self.data = data
        self.sample_rate = sample_rate
        self.volume = min(1.0, max(0.0, volume))

    def get_playable(self) -> np.ndarray:
        """Get audio data ready for playback with volume applied."""
        return self.data * self.volume


class SoundEffectsManager:
    """Manages and plays sound effects for the robot.

    Args:
        sample_rate: Default sample rate for generated sounds
        default_volume: Default volume level (0.0 to 1.0)
        sound_dir: Directory to load custom sound files from
    """

    def __init__(
        self,
        sample_rate: int = 22050,
        default_volume: float = 0.8,
        sound_dir: Optional[str] = None,
    ):
        self._sample_rate = sample_rate
        self._default_volume = default_volume
        self._sound_dir = Path(sound_dir) if sound_dir else None

        self._effects: Dict[SoundEffectType, SoundEffect] = {}
        self._custom_effects: Dict[str, SoundEffect] = {}

        self._playing = False
        self._play_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._logger = logging.getLogger('sound_effects')

        # Initialize default sound effects
        self._init_default_effects()

        # Load custom sounds if directory exists
        if self._sound_dir and self._sound_dir.exists():
            self._load_custom_sounds()

    def _init_default_effects(self):
        """Initialize default sound effects using generated tones."""
        sr = self._sample_rate

        # Wake word detection - pleasant ding sound
        wake_data = self._generate_ding(frequency=880, duration=0.3)
        self._effects[SoundEffectType.WAKE_WORD] = SoundEffect(
            "wake_word", wake_data, sr, 0.7)

        # Listening start - short rising tone
        listen_start = self._generate_tone(
            frequencies=[440, 550, 660],
            duration=0.2,
            fade_out=True,
        )
        self._effects[SoundEffectType.LISTENING_START] = SoundEffect(
            "listening_start", listen_start, sr, 0.6)

        # Listening end - short falling tone
        listen_end = self._generate_tone(
            frequencies=[660, 550, 440],
            duration=0.2,
            fade_out=True,
        )
        self._effects[SoundEffectType.LISTENING_END] = SoundEffect(
            "listening_end", listen_end, sr, 0.6)

        # Processing - soft pulsing tone
        processing = self._generate_pulse(
            frequency=600,
            duration=1.0,
            pulse_rate=2.0,
        )
        self._effects[SoundEffectType.PROCESSING] = SoundEffect(
            "processing", processing, sr, 0.5)

        # Success - ascending chord
        success = self._generate_chord(
            frequencies=[523, 659, 784],  # C, E, G
            duration=0.4,
        )
        self._effects[SoundEffectType.SUCCESS] = SoundEffect(
            "success", success, sr, 0.7)

        # Error - descending minor tone
        error = self._generate_tone(
            frequencies=[440, 349, 294],
            duration=0.4,
            fade_out=True,
        )
        self._effects[SoundEffectType.ERROR] = SoundEffect(
            "error", error, sr, 0.8)

        # Timeout - long fading tone
        timeout = self._generate_tone(
            frequencies=[330],
            duration=1.0,
            fade_in=True,
            fade_out=True,
        )
        self._effects[SoundEffectType.TIMEOUT] = SoundEffect(
            "timeout", timeout, sr, 0.6)

        # Confirmation - double beep
        confirmation = self._generate_double_beep(
            frequency=800,
            beep_duration=0.1,
            gap_duration=0.05,
        )
        self._effects[SoundEffectType.CONFIRMATION] = SoundEffect(
            "confirmation", confirmation, sr, 0.7)

        # Cancel - descending double beep
        cancel = self._generate_double_beep(
            frequency=400,
            beep_duration=0.15,
            gap_duration=0.05,
            descending=True,
        )
        self._effects[SoundEffectType.CANCEL] = SoundEffect(
            "cancel", cancel, sr, 0.7)

        # Notification - soft chime
        notification = self._generate_chime(
            frequencies=[800, 1000],
            duration=0.3,
        )
        self._effects[SoundEffectType.NOTIFICATION] = SoundEffect(
            "notification", notification, sr, 0.6)

    def _load_custom_sounds(self):
        """Load custom sound files from the sound directory."""
        if not self._sound_dir:
            return

        try:
            import soundfile as sf
        except ImportError:
            self._logger.warning(
                "soundfile not installed, cannot load custom sounds. "
                "Install with: pip install soundfile"
            )
            return

        for wav_file in self._sound_dir.glob("*.wav"):
            try:
                data, sr = sf.read(wav_file, dtype='float32')
                # Convert to mono if needed
                if len(data.shape) > 1:
                    data = data.mean(axis=1)

                # Resample if needed
                if sr != self._sample_rate:
                    from scipy import signal
                    data = signal.resample(data, int(len(data) * self._sample_rate / sr))

                effect = SoundEffect(
                    wav_file.stem,
                    data,
                    self._sample_rate,
                    self._default_volume,
                )
                self._custom_effects[wav_file.stem] = effect
                self._logger.debug(f"Loaded custom sound: {wav_file.name}")

            except Exception as e:
                self._logger.warning(f"Failed to load {wav_file}: {e}")

    def _generate_sine(
        self,
        frequency: float,
        duration: float,
        sample_rate: int = None,
    ) -> np.ndarray:
        """Generate a sine wave."""
        sr = sample_rate or self._sample_rate
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        return np.sin(2 * np.pi * frequency * t).astype(np.float32)

    def _generate_tone(
        self,
        frequencies: list,
        duration: float,
        fade_in: bool = False,
        fade_out: bool = False,
    ) -> np.ndarray:
        """Generate a tone with optional frequency sweep."""
        sr = self._sample_rate
        samples = int(sr * duration)
        t = np.linspace(0, duration, samples, endpoint=False)

        if len(frequencies) == 1:
            # Single frequency
            data = np.sin(2 * np.pi * frequencies[0] * t)
        else:
            # Frequency sweep
            data = np.zeros(samples)
            freq_per_sample = np.interp(
                t, [0, duration], [frequencies[0], frequencies[-1]])
            phase = 0
            for i in range(samples):
                data[i] = np.sin(phase)
                phase += 2 * np.pi * freq_per_sample[i] / sr

        # Apply fade
        if fade_in:
            fade_samples = int(sr * 0.05)  # 50ms fade
            fade_curve = np.linspace(0, 1, fade_samples)
            data[:fade_samples] *= fade_curve

        if fade_out:
            fade_samples = int(sr * 0.05)  # 50ms fade
            fade_curve = np.linspace(1, 0, fade_samples)
            data[-fade_samples:] *= fade_curve

        return data.astype(np.float32)

    def _generate_ding(
        self,
        frequency: float = 880,
        duration: float = 0.3,
    ) -> np.ndarray:
        """Generate a pleasant ding sound."""
        sr = self._sample_rate
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # Main tone with harmonics
        data = (
            0.6 * np.sin(2 * np.pi * frequency * t) +
            0.3 * np.sin(2 * np.pi * frequency * 2 * t) +
            0.1 * np.sin(2 * np.pi * frequency * 3 * t)
        )

        # Exponential decay
        decay = np.exp(-t * 8)
        data *= decay

        return data.astype(np.float32)

    def _generate_chord(
        self,
        frequencies: list,
        duration: float,
    ) -> np.ndarray:
        """Generate a chord (multiple frequencies)."""
        sr = self._sample_rate
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        data = np.zeros_like(t)
        for freq in frequencies:
            data += np.sin(2 * np.pi * freq * t) / len(frequencies)

        # Apply envelope
        envelope = np.exp(-t * 3)
        data *= envelope

        return data.astype(np.float32)

    def _generate_pulse(
        self,
        frequency: float,
        duration: float,
        pulse_rate: float = 2.0,
    ) -> np.ndarray:
        """Generate a pulsing tone."""
        sr = self._sample_rate
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # Carrier wave
        carrier = np.sin(2 * np.pi * frequency * t)

        # Pulse envelope
        pulse_env = 0.5 * (1 + np.sin(2 * np.pi * pulse_rate * t))

        return (carrier * pulse_env).astype(np.float32)

    def _generate_double_beep(
        self,
        frequency: float,
        beep_duration: float,
        gap_duration: float,
        descending: bool = False,
    ) -> np.ndarray:
        """Generate a double beep sound."""
        sr = self._sample_rate

        if descending:
            freq1 = frequency
            freq2 = frequency * 0.8
        else:
            freq1 = frequency
            freq2 = frequency

        # Generate two beeps
        beep1 = self._generate_sine(freq1, beep_duration)
        gap = np.zeros(int(sr * gap_duration))
        beep2 = self._generate_sine(freq2, beep_duration)

        return np.concatenate([beep1, gap, beep2])

    def _generate_chime(
        self,
        frequencies: list,
        duration: float,
    ) -> np.ndarray:
        """Generate a chime sound."""
        sr = self._sample_rate
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        data = np.zeros_like(t)
        for i, freq in enumerate(frequencies):
            # Stagger the start times
            start = int(sr * 0.05 * i)
            end = len(t)
            if start < end:
                segment_t = t[:end - start]
                decay = np.exp(-segment_t * 10)
                data[start:end] += np.sin(2 * np.pi * freq * segment_t) * decay

        # Normalize
        max_val = np.max(np.abs(data))
        if max_val > 0:
            data /= max_val

        return data.astype(np.float32)

    def play(
        self,
        effect_type: SoundEffectType = None,
        custom_name: str = None,
        volume: float = None,
        blocking: bool = False,
    ):
        """Play a sound effect.

        Args:
            effect_type: Type of built-in sound effect
            custom_name: Name of custom sound effect
            volume: Volume override (0.0 to 1.0)
            blocking: If True, wait for playback to complete
        """
        # Get the effect
        effect = None
        if effect_type and effect_type in self._effects:
            effect = self._effects[effect_type]
        elif custom_name and custom_name in self._custom_effects:
            effect = self._custom_effects[custom_name]

        if effect is None:
            self._logger.warning(f"Sound effect not found: {effect_type or custom_name}")
            return

        # Apply volume
        play_volume = volume if volume is not None else effect.volume
        audio_data = effect.data * play_volume

        # Play in background thread
        def _play():
            try:
                sd = _get_sounddevice()
                sd.play(audio_data, effect.sample_rate)
                sd.wait()
            except Exception as e:
                self._logger.error(f"Playback error: {e}")
            finally:
                self._playing = False

        self._playing = True
        self._play_thread = threading.Thread(target=_play, daemon=True)
        self._play_thread.start()

        if blocking:
            self._play_thread.join()

    def stop(self):
        """Stop current playback."""
        try:
            sd = _get_sounddevice()
            sd.stop()
        except Exception:
            pass
        self._playing = False

    def play_sequence(
        self,
        effects: list,
        interval: float = 0.1,
    ):
        """Play a sequence of sound effects.

        Args:
            effects: List of (effect_type, custom_name, volume) tuples
            interval: Time between effects in seconds
        """
        def _play_sequence():
            for effect_info in effects:
                if len(effect_info) == 3:
                    effect_type, custom_name, volume = effect_info
                elif len(effect_info) == 2:
                    effect_type, custom_name = effect_info
                    volume = None
                else:
                    effect_type = effect_info[0]
                    custom_name = None
                    volume = None

                self.play(effect_type, custom_name, volume, blocking=True)
                time.sleep(interval)

        threading.Thread(target=_play_sequence, daemon=True).start()

    def set_volume(self, effect_type: SoundEffectType, volume: float):
        """Set volume for a specific effect type."""
        if effect_type in self._effects:
            self._effects[effect_type].volume = min(1.0, max(0.0, volume))

    def set_global_volume(self, volume: float):
        """Set volume for all effects."""
        volume = min(1.0, max(0.0, volume))
        for effect in self._effects.values():
            effect.volume = volume
        for effect in self._custom_effects.values():
            effect.volume = volume

    def add_custom_effect(
        self,
        name: str,
        data: np.ndarray,
        sample_rate: int = None,
        volume: float = None,
    ):
        """Add a custom sound effect.

        Args:
            name: Name of the effect
            data: Audio data as numpy array
            sample_rate: Sample rate (uses default if None)
            volume: Volume level (uses default if None)
        """
        effect = SoundEffect(
            name,
            data,
            sample_rate or self._sample_rate,
            volume if volume is not None else self._default_volume,
        )
        self._custom_effects[name] = effect

    def load_wav(self, name: str, filepath: str):
        """Load a WAV file as a sound effect.

        Args:
            name: Name for the effect
            filepath: Path to WAV file
        """
        try:
            import soundfile as sf
            data, sr = sf.read(filepath, dtype='float32')
            if len(data.shape) > 1:
                data = data.mean(axis=1)

            # Resample if needed
            if sr != self._sample_rate:
                from scipy import signal
                data = signal.resample(
                    data, int(len(data) * self._sample_rate / sr))

            self.add_custom_effect(name, data, self._sample_rate)
            self._logger.info(f"Loaded sound effect: {name}")

        except Exception as e:
            self._logger.error(f"Failed to load WAV file {filepath}: {e}")

    @property
    def is_playing(self) -> bool:
        """Whether audio is currently playing."""
        return self._playing

    def get_available_effects(self) -> list:
        """Get list of available effect types."""
        return list(self._effects.keys())

    def get_custom_effects(self) -> list:
        """Get list of custom effect names."""
        return list(self._custom_effects.keys())


# Global instance for easy access
_manager_instance: Optional[SoundEffectsManager] = None
_manager_lock = threading.Lock()


def get_sound_manager(
    sample_rate: int = 22050,
    default_volume: float = 0.8,
    sound_dir: Optional[str] = None,
) -> SoundEffectsManager:
    """Get or create the global sound effects manager.

    Args:
        sample_rate: Sample rate for audio
        default_volume: Default volume level
        sound_dir: Directory for custom sounds

    Returns:
        SoundEffectsManager instance
    """
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = SoundEffectsManager(
                    sample_rate, default_volume, sound_dir)
    return _manager_instance


def play_sound(
    effect_type: SoundEffectType = None,
    custom_name: str = None,
    volume: float = None,
    blocking: bool = False,
):
    """Convenience function to play a sound effect.

    Args:
        effect_type: Type of built-in sound effect
        custom_name: Name of custom sound effect
        volume: Volume override
        blocking: If True, wait for playback to complete
    """
    manager = get_sound_manager()
    manager.play(effect_type, custom_name, volume, blocking)


# Predefined sound sequences
def play_wake_sequence():
    """Play the wake word detection sequence."""
    manager = get_sound_manager()
    manager.play(SoundEffectType.WAKE_WORD)


def play_listening_sequence():
    """Play the start listening sequence."""
    manager = get_sound_manager()
    manager.play(SoundEffectType.LISTENING_START)


def play_success_sequence():
    """Play the success sequence."""
    manager = get_sound_manager()
    manager.play(SoundEffectType.SUCCESS)


def play_error_sequence():
    """Play the error sequence."""
    manager = get_sound_manager()
    manager.play(SoundEffectType.ERROR)


if __name__ == "__main__":
    # Test the sound effects
    logging.basicConfig(level=logging.INFO)

    print("Testing sound effects...")
    manager = get_sound_manager()

    for effect_type in SoundEffectType:
        print(f"Playing {effect_type.value}...")
        manager.play(effect_type, blocking=True)
        time.sleep(0.5)

    print("Done!")
