"""
ASR (Automatic Speech Recognition) service using faster-whisper.
Handles model loading, audio preprocessing, and transcription.
"""

import time
import threading
import torch
import numpy as np
from typing import Optional, Dict, Any
from faster_whisper import WhisperModel
from voice_service.config import settings
from voice_service.utils.logger import get_logger
from voice_service.utils.audio_utils import (
    decode_audio_base64,
    validate_audio_format,
    resample_audio,
    get_audio_duration
)

logger = get_logger()


class ASRService:
    """ASR service using faster-whisper for speech recognition."""
    
    def __init__(self):
        """Initialize ASR service with model loading."""
        self.model: Optional[WhisperModel] = None
        self.model_name: str = settings.WHISPER_MODEL
        self.device: str = settings.WHISPER_DEVICE
        self.compute_type: str = settings.WHISPER_COMPUTE_TYPE
        self.is_loaded: bool = False
        self.load_time: float = 0.0
        
        # Performance tracking (thread-safe)
        self._lock = threading.Lock()
        self.request_count: int = 0
        self.total_latency: float = 0.0
        self.error_count: int = 0
        
        # Validate GPU availability
        self._validate_device()
        
        # Load model
        self._load_model()
    
    def _validate_device(self):
        """Validate and configure compute device."""
        if self.device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available. Falling back to CPU.")
            self.device = "cpu"
            self.compute_type = "float32"  # CPU doesn't support float16 well
        
        if self.device == "cuda":
            # Set CUDA device
            torch.cuda.set_device(0)
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"Using GPU: {gpu_name} ({gpu_memory:.1f} GB)")
        else:
            logger.info("Using CPU for inference")
    
    def _load_model(self):
        """Load faster-whisper model."""
        try:
            start_time = time.time()
            
            logger.info(f"Loading Whisper model: {self.model_name} on {self.device}")
            
            # Load model with appropriate settings
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )
            
            self.load_time = time.time() - start_time
            self.is_loaded = True
            
            logger.info(f"Model loaded successfully in {self.load_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.is_loaded = False
            raise RuntimeError(f"Model loading failed: {e}")
    
    def transcribe(self, audio_base64: str, language: str = "zh", 
                   sample_rate: int = 16000, encoding: str = "int16") -> Dict[str, Any]:
        """
        Transcribe audio from base64 encoded data.
        
        Args:
            audio_base64: Base64 encoded audio data
            language: Language code (zh, en, etc.)
            sample_rate: Audio sample rate in Hz
            encoding: Audio encoding format (int16, float32)
        
        Returns:
            Dictionary containing transcription results
        
        Raises:
            ValueError: If audio data is invalid
            RuntimeError: If transcription fails
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        
        start_time = time.time()
        with self._lock:
            self.request_count += 1
        
        try:
            # Decode audio
            audio_array, orig_sample_rate = decode_audio_base64(
                audio_base64, sample_rate, encoding
            )
            
            # Validate audio format
            validate_audio_format(audio_array, orig_sample_rate)
            
            # Resample if necessary (Whisper expects 16kHz)
            if orig_sample_rate != 16000:
                audio_array = resample_audio(audio_array, orig_sample_rate, 16000)
                logger.debug(f"Resampled audio from {orig_sample_rate}Hz to 16kHz")
            
            # Convert to float32 if needed
            if audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            
            # Perform transcription
            # initial_prompt引导模型输出简体中文
            initial_prompt = "以下是普通话的句子。" if language == "zh" else None
            
            segments, info = self.model.transcribe(
                audio_array,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200
                ),
                initial_prompt=initial_prompt
            )
            
            # Collect transcription results
            transcription_parts = []
            word_timestamps = []
            
            for segment in segments:
                transcription_parts.append(segment.text)
                
                # Collect word-level timestamps if available
                if hasattr(segment, 'words') and segment.words:
                    for word in segment.words:
                        word_timestamps.append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability
                        })
            
            # Combine transcription
            full_text = " ".join(transcription_parts).strip()
            
            # Calculate confidence from word probabilities (not language_probability)
            if word_timestamps:
                confidence = sum(w["probability"] for w in word_timestamps) / len(word_timestamps)
            else:
                confidence = 0.9 if full_text else 0.0
            
            # Calculate duration
            duration = get_audio_duration(audio_array, 16000)
            
            # Calculate latency (thread-safe)
            latency = time.time() - start_time
            with self._lock:
                self.total_latency += latency
            
            logger.info(f"Transcription completed in {latency:.3f}s: '{full_text[:50]}...'")
            
            return {
                "text": full_text,
                "confidence": confidence,
                "language": info.language if hasattr(info, 'language') else language,
                "duration": duration,
                "words": word_timestamps if word_timestamps else None
            }
            
        except Exception as e:
            with self._lock:
                self.error_count += 1
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get service health status.
        
        Returns:
            Dictionary containing health information
        """
        # Calculate uptime (assuming service started at import time)
        uptime = time.time() - self.load_time if self.load_time > 0 else 0
        
        # Calculate average latency
        avg_latency = (self.total_latency / self.request_count 
                      if self.request_count > 0 else 0.0)
        
        # Get GPU info
        gpu_available = torch.cuda.is_available()
        gpu_name = None
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
        
        return {
            "status": "healthy" if self.is_loaded else "unhealthy",
            "service": "asr",
            "model": self.model_name,
            "gpu_available": gpu_available,
            "gpu_name": gpu_name,
            "version": settings.SERVICE_VERSION,
            "uptime": uptime,
            "request_count": self.request_count,
            "average_latency": avg_latency,
            "error_rate": self.error_count / self.request_count if self.request_count > 0 else 0.0
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get detailed performance metrics.
        
        Returns:
            Dictionary containing performance metrics
        """
        avg_latency = (self.total_latency / self.request_count 
                      if self.request_count > 0 else 0.0)
        
        # Get GPU utilization if available
        gpu_utilization = None
        memory_usage = None
        
        if torch.cuda.is_available():
            try:
                # This is a simplified metric - in production, use nvidia-smi or similar
                gpu_utilization = torch.cuda.utilization()
                memory_usage = torch.cuda.memory_allocated() / 1024**2  # MB
            except Exception:
                pass
        
        return {
            "request_count": self.request_count,
            "average_latency": avg_latency,
            "p95_latency": avg_latency * 1.2,  # Simplified - in production, track actual percentiles
            "p99_latency": avg_latency * 1.5,
            "error_rate": self.error_count / self.request_count if self.request_count > 0 else 0.0,
            "gpu_utilization": gpu_utilization,
            "memory_usage": memory_usage
        }
    
    def reload_model(self, model_name: Optional[str] = None):
        """
        Reload the ASR model.
        
        Args:
            model_name: New model name (optional, uses current if not provided)
        """
        if model_name:
            self.model_name = model_name
        
        logger.info(f"Reloading model: {self.model_name}")
        self._load_model()
    
    def cleanup(self):
        """Cleanup resources."""
        if self.model:
            del self.model
            self.model = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("ASR service cleaned up")


# Global ASR service instance
asr_service = ASRService()


def get_asr_service() -> ASRService:
    """Get the global ASR service instance."""
    return asr_service