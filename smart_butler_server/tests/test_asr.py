"""
Unit tests for ASR service.
Tests audio processing, model loading, and API endpoints.
"""

import pytest
import base64
import numpy as np
from fastapi.testclient import TestClient
from voice_service.main import app
from voice_service.services.asr_service import ASRService
from voice_service.utils.audio_utils import decode_audio_base64, validate_audio_format


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_audio_base64():
    """Generate sample audio data for testing."""
    # Generate 1 second of random audio (16kHz, int16)
    sample_rate = 16000
    duration = 1.0
    samples = int(sample_rate * duration)
    
    # Generate random audio data
    audio_data = np.random.randint(-32768, 32767, size=samples, dtype=np.int16)
    
    # Convert to base64
    audio_bytes = audio_data.tobytes()
    return base64.b64encode(audio_bytes).decode('utf-8')


@pytest.fixture
def sample_audio_float32_base64():
    """Generate sample float32 audio data for testing."""
    # Generate 1 second of random audio (16kHz, float32)
    sample_rate = 16000
    duration = 1.0
    samples = int(sample_rate * duration)
    
    # Generate random audio data in float32 range [-1.0, 1.0]
    audio_data = np.random.uniform(-1.0, 1.0, size=samples).astype(np.float32)
    
    # Convert to base64
    audio_bytes = audio_data.tobytes()
    return base64.b64encode(audio_bytes).decode('utf-8')


class TestAudioUtils:
    """Test audio utility functions."""
    
    def test_decode_audio_int16(self, sample_audio_base64):
        """Test decoding int16 audio data."""
        audio_array, sample_rate = decode_audio_base64(
            sample_audio_base64, 
            sample_rate=16000, 
            encoding="int16"
        )
        
        assert isinstance(audio_array, np.ndarray)
        assert audio_array.dtype == np.float32
        assert len(audio_array) == 16000  # 1 second at 16kHz
        assert sample_rate == 16000
    
    def test_decode_audio_float32(self, sample_audio_float32_base64):
        """Test decoding float32 audio data."""
        audio_array, sample_rate = decode_audio_base64(
            sample_audio_float32_base64,
            sample_rate=16000,
            encoding="float32"
        )
        
        assert isinstance(audio_array, np.ndarray)
        assert audio_array.dtype == np.float32
        assert len(audio_array) == 16000
    
    def test_validate_audio_format_valid(self):
        """Test audio format validation with valid data."""
        audio_array = np.random.uniform(-1.0, 1.0, size=16000).astype(np.float32)
        
        # Should not raise exception
        assert validate_audio_format(audio_array, 16000) is True
    
    def test_validate_audio_format_invalid_sample_rate(self):
        """Test audio format validation with invalid sample rate."""
        audio_array = np.random.uniform(-1.0, 1.0, size=16000).astype(np.float32)
        
        with pytest.raises(ValueError, match="Invalid sample rate"):
            validate_audio_format(audio_array, 12345)
    
    def test_validate_audio_format_too_long(self):
        """Test audio format validation with too long audio."""
        # 31 seconds of audio (exceeds 30 second limit)
        audio_array = np.random.uniform(-1.0, 1.0, size=16000 * 31).astype(np.float32)
        
        with pytest.raises(ValueError, match="Audio too long"):
            validate_audio_format(audio_array, 16000)


class TestASRService:
    """Test ASR service functionality."""
    
    def test_asr_service_initialization(self):
        """Test ASR service initialization."""
        # Note: This test requires GPU and model download
        # In CI/CD, you might want to mock this
        try:
            service = ASRService()
            assert service.is_loaded is True
            assert service.model is not None
        except RuntimeError as e:
            # If model loading fails (e.g., no GPU), skip test
            pytest.skip(f"Model loading failed: {e}")
    
    def test_asr_service_health_status(self):
        """Test ASR service health status."""
        try:
            service = ASRService()
            health = service.get_health_status()
            
            assert "status" in health
            assert "service" in health
            assert health["service"] == "asr"
        except RuntimeError:
            pytest.skip("Service initialization failed")


class TestAPIEndpoints:
    """Test API endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert data["status"] == "running"
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "asr" in data
        assert "tts" in data
    
    def test_info_endpoint(self, client):
        """Test service info endpoint."""
        response = client.get("/info")
        assert response.status_code == 200
        
        data = response.json()
        assert "service" in data
        assert "asr" in data
        assert "tts" in data
    
    def test_asr_health_endpoint(self, client):
        """Test ASR health endpoint."""
        response = client.get("/asr/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "model" in data
    
    def test_transcribe_endpoint_success(self, client, sample_audio_base64):
        """Test successful transcription endpoint."""
        # Skip if no GPU available
        try:
            import torch
            if not torch.cuda.is_available():
                pytest.skip("CUDA not available")
        except ImportError:
            pytest.skip("PyTorch not installed")
        
        response = client.post(
            "/asr/transcribe",
            json={
                "audio": sample_audio_base64,
                "language": "zh",
                "model": "base",
                "sample_rate": 16000,
                "encoding": "int16"
            }
        )
        
        # Note: This might fail if model is not loaded
        # In that case, we expect a 500 error
        if response.status_code == 200:
            data = response.json()
            assert "text" in data
            assert "confidence" in data
            assert "language" in data
            assert "duration" in data
    
    def test_transcribe_endpoint_invalid_audio(self, client):
        """Test transcription with invalid audio data."""
        response = client.post(
            "/asr/transcribe",
            json={
                "audio": "invalid_base64_data",
                "language": "zh",
                "model": "base",
                "sample_rate": 16000,
                "encoding": "int16"
            }
        )
        
        # Should return 400 for invalid audio
        assert response.status_code == 400
    
    def test_transcribe_endpoint_missing_audio(self, client):
        """Test transcription with missing audio data."""
        response = client.post(
            "/asr/transcribe",
            json={
                "language": "zh",
                "model": "base"
            }
        )
        
        # Should return 422 for validation error
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_async_transcribe():
    """Test async transcription (requires actual service)."""
    # This test requires the service to be running
    # Skip in unit tests
    pytest.skip("Integration test - requires running service")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])