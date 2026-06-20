#!/usr/bin/env python3
"""
Test script to verify voice service startup.
This script tests basic imports and configuration loading.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test basic module imports."""
    print("Testing imports...")
    
    try:
        import fastapi
        print(f"[OK] FastAPI version: {fastapi.__version__}")
    except ImportError as e:
        print(f"[FAIL] FastAPI import failed: {e}")
        return False
    
    try:
        import uvicorn
        print(f"[OK] Uvicorn version: {uvicorn.__version__}")
    except ImportError as e:
        print(f"[FAIL] Uvicorn import failed: {e}")
        return False
    
    try:
        import pydantic
        print(f"[OK] Pydantic version: {pydantic.__version__}")
    except ImportError as e:
        print(f"[FAIL] Pydantic import failed: {e}")
        return False
    
    try:
        import numpy
        print(f"[OK] NumPy version: {numpy.__version__}")
    except ImportError as e:
        print(f"[FAIL] NumPy import failed: {e}")
        return False
    
    return True


def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")
    
    try:
        from voice_service.config import settings
        print(f"[OK] Configuration loaded successfully")
        print(f"  - ASR Host: {settings.ASR_HOST}")
        print(f"  - ASR Port: {settings.ASR_PORT}")
        print(f"  - Whisper Model: {settings.WHISPER_MODEL}")
        print(f"  - Device: {settings.WHISPER_DEVICE}")
        return True
    except Exception as e:
        print(f"[FAIL] Configuration loading failed: {e}")
        return False


def test_audio_utils():
    """Test audio utility functions."""
    print("\nTesting audio utilities...")
    
    try:
        import numpy as np
        from voice_service.utils.audio_utils import decode_audio_base64, validate_audio_format
        
        # Test audio decoding
        import base64
        sample_rate = 16000
        duration = 1.0
        samples = int(sample_rate * duration)
        audio_data = np.random.randint(-32768, 32767, size=samples, dtype=np.int16)
        audio_base64 = base64.b64encode(audio_data.tobytes()).decode('utf-8')
        
        audio_array, sr = decode_audio_base64(audio_base64, sample_rate=16000, encoding="int16")
        print(f"[OK] Audio decoding works: {len(audio_array)} samples")
        
        # Test validation
        validate_audio_format(audio_array, 16000)
        print(f"[OK] Audio validation works")
        
        return True
    except Exception as e:
        print(f"[FAIL] Audio utilities test failed: {e}")
        return False


def test_gpu():
    """Test GPU availability."""
    print("\nTesting GPU availability...")
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[OK] CUDA available: {gpu_name} ({gpu_memory:.1f} GB)")
            return True
        else:
            print("[WARN] CUDA not available, will use CPU")
            return True
    except ImportError:
        print("[WARN] PyTorch not installed, cannot check GPU")
        return True
    except Exception as e:
        print(f"[FAIL] GPU test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("MOSS Voice Service Startup Test")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_config,
        test_audio_utils,
        test_gpu
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"[OK] All tests passed ({passed}/{total})")
        print("\nService is ready to start!")
        print("Run: python -m uvicorn voice_service.main:app --host 0.0.0.0 --port 8001 --reload")
        return 0
    else:
        print(f"[FAIL] Some tests failed ({passed}/{total})")
        print("\nPlease install missing dependencies:")
        print("pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())