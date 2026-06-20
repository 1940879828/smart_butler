"""
TTS API router.
Defines endpoints for speech synthesis (Phase 2).
"""

from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from voice_service.models.request import TTSRequest
from voice_service.models.response import TTSResponse, ErrorResponse
from voice_service.services.tts_service import get_tts_service, TTSService
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
    prefix="/tts",
    tags=["TTS"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        501: {"model": ErrorResponse, "description": "Not Implemented"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)


@router.post(
    "/synthesize",
    response_model=TTSResponse,
    summary="Synthesize speech from text",
    description="Convert text to speech using Piper TTS (Phase 2)"
)
async def synthesize_speech(
    request: TTSRequest,
    api_key: str = Depends(verify_api_key),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Synthesize speech from text.
    
    - **text**: Text to synthesize (max 1000 characters)
    - **voice**: Voice model identifier (default: zh_CN)
    - **sample_rate**: Output sample rate (default: 22050)
    - **format**: Output format (default: wav)
    - **speed**: Speech speed multiplier (0.5-2.0)
    """
    # Phase 2 implementation
    logger.warning("TTS synthesis endpoint called but not implemented yet")
    
    # Return placeholder response
    result = tts_service.synthesize(
        text=request.text,
        voice=request.voice,
        sample_rate=request.sample_rate,
        speed=request.speed
    )
    
    return TTSResponse(
        audio=result["audio"],
        sample_rate=result["sample_rate"],
        duration=result["duration"],
        format=result["format"]
    )


@router.get(
    "/health",
    summary="TTS service health check",
    description="Check TTS service health and status"
)
async def health_check(
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Check TTS service health.
    
    Returns service status and availability information.
    """
    try:
        health_status = tts_service.get_health_status()
        return health_status
    except Exception as e:
        logger.error(f"TTS health check failed: {e}")
        return {
            "available": False,
            "error": str(e)
        }


@router.get(
    "/info",
    summary="TTS service information",
    description="Get TTS service capabilities and supported features"
)
async def get_info(
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Get TTS service information.
    
    Returns supported voices, formats, and languages.
    """
    try:
        info = tts_service.get_info()
        return info
    except Exception as e:
        logger.error(f"Failed to get TTS info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get service info")