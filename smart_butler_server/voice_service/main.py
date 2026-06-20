"""
Main FastAPI application for voice service.
Entry point for the ASR/TTS HTTP service.
"""

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from voice_service.config import settings
from voice_service.utils.logger import get_logger
from voice_service.routers import asr_router, tts_router
from voice_service.services.asr_service import get_asr_service
from voice_service.services.tts_service import get_tts_service

logger = get_logger()

# Application startup time
_service_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")
    logger.info(f"ASR service: {settings.ASR_HOST}:{settings.ASR_PORT}")
    logger.info(f"TTS service: {settings.TTS_HOST}:{settings.TTS_PORT}")
    
    # Initialize services
    try:
        asr_svc = get_asr_service()
        tts_svc = get_tts_service()
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down voice service...")
    asr_svc.cleanup()
    logger.info("Voice service stopped")


# Create FastAPI application
app = FastAPI(
    title="MOSS Voice Service",
    description="""
    ## MOSS智能管家语音服务
    
    提供语音识别（ASR）和语音合成（TTS）功能，为ROS2智能管家机器人MOSS提供语音交互能力。
    
    ### 主要功能
    - **ASR**: 使用Whisper进行语音识别，支持中文和英文
    - **TTS**: 使用Piper进行语音合成（第二阶段）
    
    ### 技术栈
    - FastAPI + Uvicorn
    - faster-whisper (GPU加速)
    - piper-tts (第二阶段)
    - PyTorch + CUDA
    
    ### 跨机架构
    - **Windows主机**: 运行此语音服务
    - **Ubuntu主机**: 运行ROS2节点，通过HTTP调用语音服务
    """,
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Performance monitoring middleware
@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    """
    Monitor request performance.
    Logs request timing and adds performance headers.
    """
    req_start = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Calculate processing time
    process_time = time.time() - req_start
    
    # Add performance headers
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Service-Version"] = settings.SERVICE_VERSION
    
    # Log request (skip health checks to reduce noise)
    if request.url.path not in ["/health", "/docs", "/redoc", "/openapi.json"]:
        logger.info(
            f"{request.method} {request.url.path} "
            f"completed in {process_time:.4f}s "
            f"status={response.status_code}"
        )
    
    return response


# Include routers
app.include_router(asr_router.router)
app.include_router(tts_router.router)


@app.get(
    "/",
    summary="Service root",
    description="Basic service information"
)
async def root():
    """Root endpoint with basic service information."""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get(
    "/health",
    summary="Overall health check",
    description="Check overall service health"
)
async def health_check():
    """
    Overall health check endpoint.
    
    Returns combined health status of all services.
    """
    try:
        asr_service = get_asr_service()
        tts_service = get_tts_service()
        
        asr_health = asr_service.get_health_status()
        tts_health = tts_service.get_health_status()
        
        # Determine overall status
        overall_status = "healthy"
        if asr_health.get("status") != "healthy":
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "uptime": time.time() - _service_start_time,
            "asr": asr_health,
            "tts": tts_health
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get(
    "/info",
    summary="Service information",
    description="Get detailed service information and capabilities"
)
async def service_info():
    """
    Get service information.
    
    Returns detailed information about service capabilities.
    """
    asr_service = get_asr_service()
    tts_service = get_tts_service()
    
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "asr": {
            "available": asr_service.is_loaded,
            "model": asr_service.model_name,
            "supported_languages": ["zh", "en"],
            "supported_models": ["tiny", "base", "small", "medium", "large"]
        },
        "tts": tts_service.get_info()
    }


@app.get(
    "/metrics",
    summary="Performance metrics",
    description="Get detailed performance metrics"
)
async def get_metrics():
    """
    Get performance metrics.
    
    Returns request counts, latency statistics, and resource usage.
    """
    asr_service = get_asr_service()
    
    return {
        "service": settings.SERVICE_NAME,
        "uptime": time.time() - _service_start_time,
        "asr": asr_service.get_performance_metrics()
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run the application
    uvicorn.run(
        "voice_service.main:app",
        host=settings.ASR_HOST,
        port=settings.ASR_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )