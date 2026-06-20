"""
ASR API router.
Defines endpoints for speech recognition.
"""

from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from typing import Optional
from voice_service.models.request import ASRRequest
from voice_service.models.response import ASRResponse, ErrorResponse
from voice_service.services.asr_service import get_asr_service, ASRService
from voice_service.config import settings
from voice_service.utils.logger import get_logger

logger = get_logger()

# API key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key if configured."""
    if settings.API_KEY:
        if api_key is None:
            logger.warning("Missing API key")
            raise HTTPException(status_code=403, detail="API Key required")
        if api_key != settings.API_KEY:
            logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
            raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key


router = APIRouter(
    prefix="/asr",
    tags=["ASR"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)


@router.post(
    "/transcribe",
    response_model=ASRResponse,
    summary="Transcribe audio to text",
    description="Transcribe base64 encoded audio data to text using Whisper ASR"
)
async def transcribe_audio(
    request: ASRRequest,
    api_key: str = Depends(verify_api_key),
    asr_service: ASRService = Depends(get_asr_service)
):
    """
    Transcribe audio to text.
    
    - **audio**: Base64 encoded audio data (16kHz, mono, int16)
    - **language**: Language code (default: zh)
    - **model**: Whisper model size (default: base)
    - **sample_rate**: Audio sample rate (default: 16000)
    - **encoding**: Audio encoding format (default: int16)
    """
    try:
        logger.info(f"Transcription request: language={request.language}, model={request.whisper_model}")
        
        # Perform transcription
        result = asr_service.transcribe(
            audio_base64=request.audio,
            language=request.language,
            sample_rate=request.sample_rate,
            encoding=request.encoding
        )
        
        return ASRResponse(
            text=result["text"],
            confidence=result["confidence"],
            language=result["language"],
            duration=result["duration"],
            words=result.get("words")
        )
        
    except ValueError as e:
        logger.warning(f"Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/health",
    summary="ASR service health check",
    description="Check ASR service health and status"
)
async def health_check(
    asr_service: ASRService = Depends(get_asr_service)
):
    """
    Check ASR service health.
    
    Returns service status, model information, and GPU availability.
    """
    try:
        health_status = asr_service.get_health_status()
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get(
    "/metrics",
    summary="ASR performance metrics",
    description="Get detailed performance metrics for ASR service"
)
async def get_metrics(
    api_key: str = Depends(verify_api_key),
    asr_service: ASRService = Depends(get_asr_service)
):
    """
    Get performance metrics.
    
    Returns request counts, latency statistics, and resource usage.
    """
    try:
        metrics = asr_service.get_performance_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to collect metrics")


@router.post(
    "/reload",
    summary="Reload ASR model",
    description="Reload the Whisper model (optional: switch to different model)"
)
async def reload_model(
    model_name: Optional[str] = None,
    api_key: str = Depends(verify_api_key),
    asr_service: ASRService = Depends(get_asr_service)
):
    """
    Reload the ASR model.
    
    - **model_name**: Optional new model name (tiny, base, small, medium, large)
    """
    try:
        logger.info(f"Reloading model: {model_name or 'current'}")
        asr_service.reload_model(model_name)
        return {"status": "success", "model": asr_service.model_name}
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))