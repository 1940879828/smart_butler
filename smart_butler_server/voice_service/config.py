"""
Configuration management using pydantic-settings.
Supports environment variables and .env file.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ASR Service Configuration
    ASR_HOST: str = Field(default="0.0.0.0", description="ASR服务监听地址")
    ASR_PORT: int = Field(default=8001, description="ASR服务端口")
    WHISPER_MODEL: str = Field(default="base", description="Whisper模型大小")
    WHISPER_DEVICE: str = Field(default="cuda", description="计算设备 (cuda/cpu)")
    WHISPER_COMPUTE_TYPE: str = Field(default="float16", description="计算精度类型")
    
    # TTS Service Configuration (Phase 2)
    TTS_HOST: str = Field(default="0.0.0.0", description="TTS服务监听地址")
    TTS_PORT: int = Field(default=8002, description="TTS服务端口")
    PIPER_VOICE: str = Field(default="zh_CN", description="Piper TTS语音模型")
    
    # General Configuration
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    API_KEY: Optional[str] = Field(default=None, description="API密钥")
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS允许的源"
    )
    
    # GPU Configuration
    CUDA_VISIBLE_DEVICES: str = Field(default="0", description="可见的CUDA设备")
    
    # Service metadata
    SERVICE_NAME: str = "voice-service"
    SERVICE_VERSION: str = "1.0.0"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",  # Ignore extra environment variables
    }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings (dependency injection friendly)."""
    return settings


# Validate GPU availability on import
def validate_gpu():
    """Validate GPU availability and print device info."""
    import torch
    if not torch.cuda.is_available():
        print("Warning: CUDA is not available. Using CPU instead.")
        return False
    
    device_count = torch.cuda.device_count()
    for i in range(device_count):
        device_name = torch.cuda.get_device_name(i)
        device_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
        print(f"GPU {i}: {device_name} ({device_memory:.1f} GB)")
    
    return True


if __name__ == "__main__":
    # Test configuration loading
    print("Current configuration:")
    for field_name, field_value in settings.model_dump().items():
        print(f"  {field_name}: {field_value}")
    
    print("\nGPU validation:")
    validate_gpu()