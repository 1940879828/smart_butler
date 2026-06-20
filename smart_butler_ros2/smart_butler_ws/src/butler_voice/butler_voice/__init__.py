"""Butler Voice package for MOSS robot.

This package provides voice interaction capabilities:
- asr_client: Automatic Speech Recognition client
- tts_client: Text-to-Speech client
- webrtc_vad: WebRTC Voice Activity Detection
- voice_state_machine: Voice interaction state machine
"""

from .voice_state_machine import (
    VoiceStateMachine,
    VoiceState,
    create_state_machine,
)

from .webrtc_vad import (
    WebRTCVAD,
    HybridVAD,
    create_vad,
)

__all__ = [
    'VoiceStateMachine',
    'VoiceState',
    'create_state_machine',
    'WebRTCVAD',
    'HybridVAD',
    'create_vad',
]
