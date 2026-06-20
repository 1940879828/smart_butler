"""Unit tests for WebRTC VAD module."""

import numpy as np
import pytest

from butler_voice.butler_voice.webrtc_vad import WebRTCVAD, HybridVAD, create_vad


class TestWebRTCVAD:
    """Tests for WebRTCVAD class."""

    def test_initialization(self):
        """Test WebRTCVAD initialization with valid parameters."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)
            assert vad.sample_rate == 16000
            assert vad.aggressiveness == 2
            assert vad.frame_size == 480  # 30ms at 16kHz
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_invalid_sample_rate(self):
        """Test WebRTCVAD with invalid sample rate."""
        try:
            with pytest.raises(ValueError):
                WebRTCVAD(sample_rate=44100)
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_invalid_aggressiveness(self):
        """Test WebRTCVAD with invalid aggressiveness."""
        try:
            with pytest.raises(ValueError):
                WebRTCVAD(aggressiveness=5)
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_process_frame_silence(self):
        """Test processing a silent frame."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)
            # Create silent frame
            frame = np.zeros(480, dtype=np.int16)
            result = vad.process_frame(frame)
            assert isinstance(result, bool)
            assert not result  # Should not detect speech in silence
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_process_frame_speech(self):
        """Test processing a speech-like frame."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)
            # Create speech-like frame (sine wave)
            t = np.linspace(0, 0.03, 480, endpoint=False)
            frame = (np.sin(2 * np.pi * 300 * t) * 10000).astype(np.int16)
            result = vad.process_frame(frame)
            assert isinstance(result, bool)
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_process_audio(self):
        """Test processing a chunk of audio."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)
            # Create audio with some variation
            audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)
            is_speech, speech_audio = vad.process_audio(audio)
            assert isinstance(is_speech, bool)
            # speech_audio can be None or numpy array
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_reset(self):
        """Test resetting VAD state."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)
            # Process some audio first
            audio = np.random.randint(-1000, 1000, 480, dtype=np.int16)
            vad.process_frame(audio)

            # Reset
            vad.reset()
            assert not vad.is_speech
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_callbacks(self):
        """Test callback registration."""
        try:
            vad = WebRTCVAD(sample_rate=16000, aggressiveness=2)

            # Test callbacks
            speech_start_called = False
            speech_end_called = None
            vad_update_called = False

            def on_speech_start():
                nonlocal speech_start_called
                speech_start_called = True

            def on_speech_end(audio):
                nonlocal speech_end_called
                speech_end_called = audio

            def on_vad_update(is_speech):
                nonlocal vad_update_called
                vad_update_called = True

            vad.set_callbacks(
                on_speech_start=on_speech_start,
                on_speech_end=on_speech_end,
                on_vad_update=on_vad_update,
            )

            # Process a frame
            frame = np.zeros(480, dtype=np.int16)
            vad.process_frame(frame)

            assert vad_update_called
        except ImportError:
            pytest.skip("webrtcvad not installed")


class TestHybridVAD:
    """Tests for HybridVAD class."""

    def test_initialization_with_webrtc(self):
        """Test HybridVAD initialization with WebRTC enabled."""
        try:
            vad = HybridVAD(
                sample_rate=16000,
                energy_threshold=500,
                use_webrtc=True,
                webrtc_aggressiveness=2,
            )
            assert vad.is_speaking == False
            assert vad.energy_threshold == 500
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_initialization_without_webrtc(self):
        """Test HybridVAD initialization without WebRTC."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )
        assert vad.is_speaking == False
        assert vad.energy_threshold == 500

    def test_process_silence(self):
        """Test processing silence."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )

        # Silent audio
        audio = np.zeros(1024, dtype=np.int16)
        is_speech, speech_audio = vad.process(audio)

        assert not is_speech
        assert speech_audio is None

    def test_process_speech(self):
        """Test processing speech-like audio."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )

        # Speech-like audio (high energy)
        audio = np.random.randint(-5000, 5000, 1024, dtype=np.int16)
        is_speech, speech_audio = vad.process(audio)

        assert is_speech
        assert speech_audio is None  # Still speaking

    def test_process_speech_end(self):
        """Test detecting end of speech."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )

        # Start with speech
        speech_audio = np.random.randint(-5000, 5000, 1024, dtype=np.int16)
        vad.process(speech_audio)

        # Then silence
        silence_audio = np.zeros(1024, dtype=np.int16)

        # Process silence until speech ends
        for _ in range(100):  # More than enough for 500ms silence
            is_speech, ended_audio = vad.process(silence_audio)
            if ended_audio is not None:
                break

        # After enough silence, should detect end
        assert ended_audio is not None
        assert len(ended_audio) > 0

    def test_reset(self):
        """Test resetting HybridVAD."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )

        # Process some audio
        audio = np.random.randint(-5000, 5000, 1024, dtype=np.int16)
        vad.process(audio)

        # Reset
        vad.reset()
        assert not vad.is_speaking

    def test_energy_threshold_update(self):
        """Test updating energy threshold."""
        vad = HybridVAD(
            sample_rate=16000,
            energy_threshold=500,
            use_webrtc=False,
        )

        assert vad.energy_threshold == 500

        vad.energy_threshold = 1000
        assert vad.energy_threshold == 1000


class TestCreateVAD:
    """Tests for create_vad function."""

    def test_create_vad_default(self):
        """Test creating VAD with default parameters."""
        try:
            vad = create_vad()
            assert isinstance(vad, HybridVAD)
            assert vad.energy_threshold == 500
        except ImportError:
            pytest.skip("webrtcvad not installed")

    def test_create_vad_custom(self):
        """Test creating VAD with custom parameters."""
        vad = create_vad(
            sample_rate=16000,
            energy_threshold=1000,
            use_webrtc=False,
            webrtc_aggressiveness=3,
        )
        assert isinstance(vad, HybridVAD)
        assert vad.energy_threshold == 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
