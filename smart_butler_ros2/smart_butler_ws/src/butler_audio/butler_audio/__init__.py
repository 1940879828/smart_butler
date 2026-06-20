"""Butler Audio package for MOSS robot.

This package provides audio input/output capabilities:
- mic_node: Microphone capture node
- speaker_node: Audio playback node
- sound_effects: Sound effects manager
"""

from .sound_effects import (
    SoundEffectsManager,
    SoundEffectType,
    get_sound_manager,
    play_sound,
)

__all__ = [
    'SoundEffectsManager',
    'SoundEffectType',
    'get_sound_manager',
    'play_sound',
]
