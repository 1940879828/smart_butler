# 语音服务实现计划

## 1. 项目概述

### 1.1 目标
在Windows环境下，使用5070Ti显卡，搭建Whisper ASR（语音识别）HTTP服务，并预留Piper TTS（语音合成）扩展接口。为ROS2智能管家机器人MOSS提供语音交互能力。

### 1.2 背景
MOSS机器人采用跨机架构：
- **Ubuntu（开发机）**：运行ROS2节点、Gazebo仿真
- **Windows（当前环境）**：运行AI服务，包括语音识别、语音合成、大模型推理

ROS2节点通过HTTP调用Windows上的语音服务，实现语音交互功能。

### 1.3 项目阶段
- **第一阶段**：实现Whisper ASR HTTP服务（端口8001）
- **第二阶段**：实现Piper TTS HTTP服务（端口8002）

## 2. 技术选型

### 2.1 核心技术栈

| 组件 | 技术选择 | 版本要求 | 说明 |
|------|---------|---------|------|
| Web框架 | FastAPI | ≥0.104.0 | 高性能、自动文档生成、异步支持 |
| ASR引擎 | faster-whisper | ≥0.10.0 | GPU加速的Whisper实现 |
| TTS引擎 | piper-tts | ≥1.2.0 | 第二阶段使用 |
| 音频处理 | numpy + soundfile | numpy≥1.24.0, soundfile≥0.12.0 | 音频数据转换 |
| 配置管理 | python-dotenv + pydantic-settings | dotenv≥1.0.0, pydantic-settings≥2.0.0 | 环境变量管理 |
| 日志系统 | loguru | ≥0.7.0 | 结构化日志 |
| 数据验证 | Pydantic | ≥2.0.0 | 请求/响应数据验证 |
| GPU支持 | PyTorch | ≥2.0.0 | CUDA加速 |
| 部署 | uvicorn | ≥0.24.0 | ASGI服务器 |

### 2.2 选择理由

1. **FastAPI**：
   - 自动生成OpenAPI文档
   - 原生异步支持，适合高并发场景
   - 类型提示和数据验证
   - 性能优异

2. **faster-whisper**：
   - 比原版Whisper快4倍
   - 支持GPU加速（CUDA）
   - 内存占用更低
   - 支持多种模型大小（tiny, base, small, medium, large）

3. **PyTorch + CUDA**：
   - 充分利用5070Ti GPU
   - 支持混合精度计算（float16）
   - 成熟的GPU加速生态

## 3. 系统架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Windows 主机 (5070Ti)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Voice Service (FastAPI)                │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │ ASR Router  │  │ TTS Router  │  │ Health      │ │   │
│  │  │ /transcribe │  │ /synthesize │  │ /health     │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │   │
│  │         │                │                │        │   │
│  │  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐ │   │
│  │  │ ASR Service │  │ TTS Service │  │ System      │ │   │
│  │  │ (Whisper)   │  │ (Piper)     │  │ Monitor     │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────┘ │   │
│  │         │                │                          │   │
│  │  ┌──────▼──────┐  ┌──────▼──────┐                   │   │
│  │  │ GPU (CUDA)  │  │ GPU (CUDA)  │                   │   │
│  │  │ 5070Ti      │  │ 5070Ti      │                   │   │
│  │  └─────────────┘  └─────────────┘                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (REST API)
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Ubuntu 主机 (ROS2)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ROS2 节点                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │ butler_voice│  │ butler_audio│  │ butler_ai   │ │   │
│  │  │ ASR/TTS     │  │ Mic/Speaker │  │ LLM         │ │   │
│  │  │ 客户端      │  │ 硬件层      │  │ 客户端      │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │   │
│  │         │                │                │        │   │
│  │  ┌──────▼─────────────────▼─────────────────▼──────┐ │   │
│  │  │              ROS2 Topics / Services            │ │   │
│  │  │  /moss/audio/raw  /moss/voice/recognized      │ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

1. **ASR流程**：
   ```
   麦克风 → butler_audio/mic_node → /moss/audio/raw → butler_voice/asr_client
   → HTTP POST /transcribe → Whisper ASR → 返回文本 → /moss/voice/recognized
   ```

2. **TTS流程**（第二阶段）：
   ```
   文本输入 → /moss/voice/speak → butler_voice/tts_client → HTTP POST /synthesize
   → Piper TTS → 返回音频 → /moss/audio/tts_output → butler_audio/speaker_node
   ```

## 4. 目录结构设计

```
smart_butler_server/
├── voice_service/                    # 语音服务主目录
│   ├── __init__.py                   # 包初始化
│   ├── main.py                       # FastAPI应用入口
│   ├── config.py                     # 配置管理
│   ├── models/                       # 数据模型
│   │   ├── __init__.py
│   │   ├── request.py                # 请求模型
│   │   └── response.py               # 响应模型
│   ├── services/                     # 业务逻辑
│   │   ├── __init__.py
│   │   ├── asr_service.py            # ASR服务实现
│   │   └── tts_service.py            # TTS服务实现（第二阶段）
│   ├── routers/                      # API路由
│   │   ├── __init__.py
│   │   ├── asr_router.py             # ASR路由
│   │   └── tts_router.py             # TTS路由（第二阶段）
│   └── utils/                        # 工具函数
│       ├── __init__.py
│       ├── audio_utils.py            # 音频处理工具
│       └── logger.py                 # 日志配置
├── docs/                             # 文档目录
│   ├── voice-service-implementation-plan.md
│   └── api-spec.md                   # API规范文档
├── tests/                            # 测试目录
│   ├── test_asr.py                   # ASR测试
│   └── test_tts.py                   # TTS测试（第二阶段）
├── requirements.txt                  # Python依赖
├── .env.example                      # 环境变量示例
├── .env                              # 环境变量（不提交到git）
├── README.md                         # 项目说明
└── docker-compose.yml                # Docker部署（可选）
```

## 5. API设计规范

### 5.1 ASR服务端点

#### 5.1.1 语音识别

**端点**：`POST /transcribe`

**请求头**：
```http
Content-Type: application/json
```

**请求体**：
```json
{
    "audio": "string (base64编码的int16音频数据)",
    "language": "string (可选，默认'zh')",
    "model": "string (可选，默认'base')",
    "sample_rate": "integer (可选，默认16000)",
    "encoding": "string (可选，默认'int16')"
}
```

**参数说明**：
- `audio`：base64编码的音频数据，必须是16kHz采样率、单声道、int16格式
- `language`：语言代码，支持'zh'（中文）、'en'（英文）等
- `model`：Whisper模型大小，可选值：tiny, base, small, medium, large
- `sample_rate`：音频采样率，支持8000, 16000, 22050, 44100, 48000
- `encoding`：音频编码格式，目前支持'int16'

**响应体**：
```json
{
    "text": "string (识别出的文本)",
    "confidence": "float (置信度，0.0-1.0)",
    "language": "string (检测到的语言)",
    "duration": "float (音频时长，秒)"
}
```

**错误响应**：
```json
{
    "error": "string (错误信息)",
    "code": "string (错误代码)"
}
```

**示例**：
```python
import requests
import base64
import numpy as np

# 准备音频数据（16kHz, int16, 单声道）
audio_data = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)
audio_base64 = base64.b64encode(audio_data.tobytes()).decode('utf-8')

# 发送请求
response = requests.post(
    "http://localhost:8001/transcribe",
    json={
        "audio": audio_base64,
        "language": "zh",
        "model": "base",
        "sample_rate": 16000,
        "encoding": "int16"
    }
)

result = response.json()
print(f"识别结果: {result['text']}")
```

#### 5.1.2 健康检查

**端点**：`GET /health`

**响应体**：
```json
{
    "status": "healthy",
    "service": "asr",
    "model": "base",
    "gpu_available": true,
    "gpu_name": "NVIDIA GeForce RTX 5070 Ti",
    "version": "1.0.0",
    "uptime": 3600.5
}
```

### 5.2 TTS服务端点（第二阶段）

#### 5.2.1 语音合成

**端点**：`POST /synthesize`

**请求体**：
```json
{
    "text": "string (要合成的文本)",
    "voice": "string (可选，默认'zh_CN')",
    "sample_rate": "integer (可选，默认22050)",
    "format": "string (可选，默认'wav')",
    "speed": "float (可选，默认1.0)"
}
```

**响应体**：
```json
{
    "audio": "string (base64编码的音频数据)",
    "sample_rate": "integer (采样率)",
    "duration": "float (音频时长，秒)",
    "format": "string (音频格式)"
}
```

### 5.3 通用端点

#### 5.3.1 服务信息

**端点**：`GET /info`

**响应体**：
```json
{
    "service": "voice-service",
    "version": "1.0.0",
    "asr": {
        "available": true,
        "model": "base",
        "supported_languages": ["zh", "en"]
    },
    "tts": {
        "available": false,
        "reason": "第二阶段实现"
    }
}
```

## 6. 实现步骤

### 6.1 第一阶段：ASR服务实现

#### 6.1.1 环境准备

1. **创建虚拟环境**：
   ```bash
   cd smart_butler_server
   python -m venv venv
   venv\Scripts\activate
   ```

2. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**：
   ```bash
   cp .env.example .env
   # 编辑.env文件，配置GPU、模型等参数
   ```

#### 6.1.2 核心模块实现

1. **配置管理** (`config.py`)：
   - 使用pydantic-settings管理配置
   - 支持环境变量和.env文件
   - GPU配置、模型配置、端口配置

2. **数据模型** (`models/`)：
   - 请求模型：ASRRequest
   - 响应模型：ASRResponse, HealthResponse
   - 使用Pydantic进行数据验证

3. **ASR服务** (`services/asr_service.py`)：
   - faster-whisper模型加载
   - GPU加速配置
   - 音频预处理
   - 转录逻辑

4. **API路由** (`routers/asr_router.py`)：
   - FastAPI路由定义
   - 请求处理
   - 错误处理

5. **工具函数** (`utils/`)：
   - 音频格式转换
   - 日志配置
   - 性能监控

#### 6.1.3 集成测试

1. **单元测试**：
   - 测试音频处理函数
   - 测试模型加载
   - 测试API端点

2. **集成测试**：
   - 测试完整的ASR流程
   - 测试与ROS2节点的集成

### 6.2 第二阶段：TTS服务实现

#### 6.2.1 环境准备

1. **安装piper-tts**：
   ```bash
   pip install piper-tts
   ```

2. **下载中文语音模型**：
   ```bash
   # 下载中文语音模型
   piper --download-dir models/zh_CN
   ```

#### 6.2.2 核心模块实现

1. **TTS服务** (`services/tts_service.py`)：
   - piper-tts模型加载
   - 语音合成逻辑
   - 音频后处理

2. **TTS路由** (`routers/tts_router.py`)：
   - FastAPI路由定义
   - 请求处理

#### 6.2.3 集成测试

1. **单元测试**：
   - 测试TTS合成函数
   - 测试音频质量

2. **集成测试**：
   - 测试完整的TTS流程
   - 测试与ROS2节点的集成

## 7. 部署方案

### 7.1 本地开发部署

#### 7.1.1 启动服务

```bash
# 进入项目目录
cd smart_butler_server

# 激活虚拟环境
venv\Scripts\activate

# 启动ASR服务
python -m uvicorn voice_service.main:app --host 0.0.0.0 --port 8001 --reload

# 启动TTS服务（第二阶段）
python -m uvicorn voice_service.main:app --host 0.0.0.0 --port 8002 --reload
```

#### 7.1.2 访问服务

- **ASR服务**：http://localhost:8001
- **API文档**：http://localhost:8001/docs
- **健康检查**：http://localhost:8001/health

### 7.2 生产环境部署

#### 7.2.1 使用Gunicorn（推荐）

```bash
# 安装Gunicorn
pip install gunicorn

# 启动ASR服务
gunicorn voice_service.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8001

# 启动TTS服务（第二阶段）
gunicorn voice_service.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8002
```

#### 7.2.2 使用Docker（可选）

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8001 8002

# 启动服务
CMD ["python", "-m", "uvicorn", "voice_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  asr-service:
    build: .
    ports:
      - "8001:8001"
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - WHISPER_MODEL=base
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  tts-service:
    build: .
    ports:
      - "8002:8002"
    environment:
      - CUDA_VISIBLE_DEVICES=0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### 7.3 网络配置

#### 7.3.1 防火墙设置

```powershell
# Windows防火墙允许端口
New-NetFirewallRule -DisplayName "ASR Service" -Direction Inbound -Port 8001 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "TTS Service" -Direction Inbound -Port 8002 -Protocol TCP -Action Allow
```

#### 7.3.2 ROS2配置更新

更新`sim.yaml`中的端点配置：

```yaml
voice:
  asr:
    provider: "whisper"
    model: "base"
    windows_endpoint: "http://<Windows_IP>:8001"
  tts:
    provider: "piper"
    voice: "zh_CN"
    windows_endpoint: "http://<Windows_IP>:8002"
```

## 8. 测试策略

### 8.1 单元测试

#### 8.1.1 测试框架

- **pytest**：测试框架
- **pytest-asyncio**：异步测试
- **httpx**：HTTP客户端测试

#### 8.1.2 测试用例

```python
# tests/test_asr.py
import pytest
from httpx import AsyncClient
from voice_service.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_transcribe_endpoint(client):
    # 准备测试音频数据
    import base64
    import numpy as np
    audio_data = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)
    audio_base64 = base64.b64encode(audio_data.tobytes()).decode('utf-8')
    
    response = await client.post(
        "/transcribe",
        json={
            "audio": audio_base64,
            "language": "zh",
            "model": "base",
            "sample_rate": 16000,
            "encoding": "int16"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
```

### 8.2 集成测试

#### 8.2.1 ROS2集成测试

```python
# 测试与butler_voice的集成
import rclpy
from rclpy.node import Node
from butler_voice.asr_client import ASRClient

def test_asr_client_integration():
    rclpy.init()
    node = ASRClient()
    # 测试节点创建
    assert node.get_name() == 'asr_client'
    # 测试参数
    assert node._sample_rate == 16000
    rclpy.shutdown()
```

### 8.3 性能测试

#### 8.3.1 负载测试

```bash
# 使用locust进行负载测试
pip install locust

# locustfile.py
from locust import HttpUser, task, between

class ASRUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def transcribe(self):
        # 准备测试数据
        import base64
        import numpy as np
        audio_data = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)
        audio_base64 = base64.b64encode(audio_data.tobytes()).decode('utf-8')
        
        self.client.post(
            "/transcribe",
            json={
                "audio": audio_base64,
                "language": "zh",
                "model": "base",
                "sample_rate": 16000,
                "encoding": "int16"
            }
        )
```

```bash
# 启动负载测试
locust -f locustfile.py --host=http://localhost:8001
```

## 9. 监控与日志

### 9.1 日志配置

```python
# utils/logger.py
import sys
from loguru import logger

def setup_logger():
    """配置日志系统"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "logs/voice_service_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG"
    )
    return logger
```

### 9.2 性能监控

```python
# 性能监控中间件
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class PerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info(
            f"{request.method} {request.url.path} "
            f"completed in {process_time:.4f}s "
            f"status={response.status_code}"
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response
```

### 9.3 健康检查

```python
# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 检查GPU状态
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
        
        # 检查模型状态
        model_loaded = asr_service.model is not None
        
        return {
            "status": "healthy" if model_loaded else "degraded",
            "service": "asr",
            "model": config.whisper_model,
            "gpu_available": gpu_available,
            "gpu_name": gpu_name,
            "version": "1.0.0",
            "uptime": time.time() - start_time
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
```

## 10. 安全考虑

### 10.1 输入验证

- 验证音频数据格式和大小
- 限制请求频率（Rate Limiting）
- 验证语言和模型参数

### 10.2 访问控制

```python
# 简单的API密钥验证
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY", "your-secret-key")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key
```

### 10.3 数据安全

- 音频数据不持久化存储
- 请求日志中不记录完整音频数据
- 使用HTTPS（生产环境）

## 11. 未来扩展

### 11.1 功能扩展

1. **流式识别**：支持实时音频流识别
2. **多语言支持**：扩展更多语言模型
3. **说话人识别**：识别不同说话人
4. **情感分析**：分析语音情感

### 11.2 性能优化

1. **模型量化**：使用INT8量化减少内存占用
2. **批处理**：支持批量音频识别
3. **缓存机制**：缓存常用识别结果
4. **负载均衡**：多实例部署

### 11.3 集成扩展

1. **WebSocket支持**：实时音频流传输
2. **gRPC支持**：高性能RPC通信
3. **消息队列**：支持异步处理

## 12. 参考资料

1. **faster-whisper文档**：https://github.com/SYSTRAN/faster-whisper
2. **FastAPI文档**：https://fastapi.tiangolo.com/
3. **piper-tts文档**：https://github.com/rhasspy/piper
4. **ROS2集成指南**：`ros2智能管家实现指南.md` 第6章

## 13. 附录

### 13.1 环境变量示例

```bash
# .env.example
# ASR服务配置
ASR_HOST=0.0.0.0
ASR_PORT=8001
WHISPER_MODEL=base
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# TTS服务配置（第二阶段）
TTS_HOST=0.0.0.0
TTS_PORT=8002
PIPER_VOICE=zh_CN

# 通用配置
LOG_LEVEL=INFO
API_KEY=your-secret-key-here
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8080"]
```

### 13.2 依赖版本锁定

```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
faster-whisper==0.10.0
numpy==1.24.3
soundfile==0.12.1
python-dotenv==1.0.0
loguru==0.7.2
pydantic==2.5.0
pydantic-settings==2.1.0
torch==2.1.0
torchaudio==2.1.0
httpx==0.25.2
pytest==7.4.3
pytest-asyncio==0.21.1
```

---

**文档版本**：1.0.0  
**创建日期**：2026-06-20  
**最后更新**：2026-06-20  
**作者**：CodeBuddy