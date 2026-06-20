"""
Audio processing utilities.
Handles audio format conversion, validation, and preprocessing.
"""

import base64
import numpy as np
from typing import Tuple
from voice_service.utils.logger import get_logger

logger = get_logger()


def decode_audio_base64(audio_base64: str, sample_rate: int = 16000, encoding: str = "int16") -> Tuple[np.ndarray, int]:
    """
    Decode base64 encoded audio data to numpy array.
    
    Args:
        audio_base64: Base64 encoded audio string
        sample_rate: Expected sample rate (for validation)
        encoding: Audio encoding format (int16, float32)
    
    Returns:
        Tuple of (audio_array, sample_rate)
    
    Raises:
        ValueError: If audio data is invalid
    """
    try:
        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_base64)
        
        # Convert to numpy array based on encoding
        if encoding == "int16":
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            # Normalize to float32 range [-1.0, 1.0] for Whisper
            audio_array = audio_array.astype(np.float32) / 32768.0
        elif encoding == "float32":
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")
        
        # Validate audio length
        if len(audio_array) == 0:
            raise ValueError("Empty audio data")
        
        logger.debug(f"Decoded audio: {len(audio_array)} samples, {len(audio_array)/sample_rate:.2f}s")
        return audio_array, sample_rate
        
    except Exception as e:
        logger.error(f"Failed to decode audio: {e}")
        raise ValueError(f"Invalid audio data: {e}")


def validate_audio_format(audio_array: np.ndarray, sample_rate: int) -> bool:
    """
    Validate audio format and properties.
    
    Args:
        audio_array: Audio data as numpy array
        sample_rate: Sample rate in Hz
    
    Returns:
        True if valid, raises ValueError if invalid
    """
    # Check sample rate
    valid_sample_rates = [8000, 16000, 22050, 44100, 48000]
    if sample_rate not in valid_sample_rates:
        raise ValueError(f"Invalid sample rate: {sample_rate}. Must be one of {valid_sample_rates}")
    
    # Check audio length (max 30 seconds for Whisper)
    max_duration = 30.0  # seconds
    duration = len(audio_array) / sample_rate
    if duration > max_duration:
        raise ValueError(f"Audio too long: {duration:.2f}s. Maximum allowed: {max_duration}s")
    
    # Check for silence or very low amplitude
    max_amplitude = np.max(np.abs(audio_array))
    if max_amplitude < 0.001:  # -60 dB
        logger.warning("Audio appears to be silent or very quiet")
    
    return True


def resample_audio(audio_array: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Resample audio to target sample rate.
    
    Args:
        audio_array: Input audio array
        orig_sr: Original sample rate
        target_sr: Target sample rate
    
    Returns:
        Resampled audio array
    """
    if orig_sr == target_sr:
        return audio_array
    
    try:
        # Use soundfile for high-quality resampling
        import soundfile as sf  # lazy import to avoid top-level dependency
        
        # Convert to float32 if needed
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)
        
        # Resample
        resampled = sf.resample(audio_array, orig_sr, target_sr)
        logger.debug(f"Resampled audio from {orig_sr}Hz to {target_sr}Hz")
        return resampled
        
    except Exception as e:
        logger.error(f"Resampling failed: {e}")
        # Fallback to simple linear interpolation
        logger.warning("Using simple interpolation for resampling")
        duration = len(audio_array) / orig_sr
        target_length = int(duration * target_sr)
        indices = np.linspace(0, len(audio_array) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)
        return resampled.astype(np.float32)


def get_audio_duration(audio_array: np.ndarray, sample_rate: int) -> float:
    """
    Calculate audio duration in seconds.
    
    Args:
        audio_array: Audio data array
        sample_rate: Sample rate in Hz
    
    Returns:
        Duration in seconds
    """
    return len(audio_array) / sample_rate


def normalize_audio(audio_array: np.ndarray) -> np.ndarray:
    """
    Normalize audio to [-1.0, 1.0] range.
    
    Args:
        audio_array: Input audio array
    
    Returns:
        Normalized audio array
    """
    max_val = np.max(np.abs(audio_array))
    if max_val > 0:
        return audio_array / max_val
    return audio_array


def audio_to_base64(audio_array: np.ndarray, sample_rate: int, encoding: str = "int16") -> str:
    """
    Convert audio array to base64 encoded string.
    
    Args:
        audio_array: Audio data as numpy array
        sample_rate: Sample rate (for metadata)
        encoding: Target encoding format
    
    Returns:
        Base64 encoded audio string
    """
    try:
        if encoding == "int16":
            # Convert float32 to int16
            if audio_array.dtype == np.float32:
                audio_int16 = (audio_array * 32767).astype(np.int16)
            else:
                audio_int16 = audio_array.astype(np.int16)
            audio_bytes = audio_int16.tobytes()
        elif encoding == "float32":
            audio_bytes = audio_array.astype(np.float32).tobytes()
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")
        
        return base64.b64encode(audio_bytes).decode("utf-8")
        
    except Exception as e:
        logger.error(f"Failed to encode audio: {e}")
        raise ValueError(f"Audio encoding failed: {e}")