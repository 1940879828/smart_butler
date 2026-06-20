# MOSS 语音服务 API 规范

## 概述

MOSS语音服务提供RESTful API接口，用于语音识别（ASR）和语音合成（TTS）。

**基础URL**: `http://<host>:<port>`

**默认端口**:
- ASR服务: 8001
- TTS服务: 8002 (第二阶段)

## 认证

### API密钥认证 (可选)

如果配置了API密钥，所有请求必须在Header中包含：

```
X-API-Key: <your-api-key>
```

**错误响应**:
```json
{
    "error": "Invalid API Key",
    "code": "INVALID_API_KEY"
}
```

## 通用响应格式

### 成功响应
```json
{
    "field1": "value1",
    "field2": "value2"
}
```

### 错误响应
```json
{
    "error": "错误描述",
    "code": "ERROR_CODE",
    "details": {
        "field": "具体错误信息"
    }
}
```

## 端点列表

### 1. 根端点

#### `GET /`

**描述**: 服务根端点，返回基本信息

**响应**:
```json
{
    "service": "voice-service",
    "version": "1.0.0",
    "status": "running",
    "docs": "/docs",
    "health": "/health"
}
```

### 2. 健康检查

#### `GET /health`

**描述**: 检查服务整体健康状态

**响应**:
```json
{
    "status": "healthy",
    "service": "voice-service",
    "version": "1.0.0",
    "uptime": 3600.5,
    "asr": {
        "status": "healthy",
        "service": "asr",
        "model": "base",
        "gpu_available": true,
        "gpu_name": "NVIDIA GeForce RTX 5070 Ti",
        "version": "1.0.0",
        "uptime": 3600.5,
        "request_count": 100,
        "average_latency": 0.5,
        "error_rate": 0.01
    },
    "tts": {
        "available": false,
        "reason": "Phase 2 implementation"
    }
}
```

**状态值**:
- `healthy`: 所有服务正常
- `degraded`: 部分服务异常
- `unhealthy`: 服务不可用

### 3. 服务信息

#### `GET /info`

**描述**: 获取服务详细信息和功能

**响应**:
```json
{
    "service": "voice-service",
    "version": "1.0.0",
    "asr": {
        "available": true,
        "model": "base",
        "supported_languages": ["zh", "en"],
        "supported_models": ["tiny", "base", "small", "medium", "large"]
    },
    "tts": {
        "available": false,
        "reason": "第二阶段实现",
        "model": "zh_CN",
        "supported_formats": ["wav", "mp3"],
        "supported_languages": ["zh_CN", "en_US"]
    }
}
```

### 4. 性能指标

#### `GET /metrics`

**描述**: 获取服务性能指标

**响应**:
```json
{
    "service": "voice-service",
    "uptime": 3600.5,
    "asr": {
        "request_count": 100,
        "average_latency": 0.5,
        "p95_latency": 0.6,
        "p99_latency": 0.75,
        "error_rate": 0.01,
        "gpu_utilization": 45.2,
        "memory_usage": 1024.5
    }
}
```

## ASR API

### 1. 语音识别

#### `POST /asr/transcribe`

**描述**: 将音频数据转换为文本

**请求头**:
```
Content-Type: application/json
X-API-Key: <api-key> (可选)
```

**请求体**:
```json
{
    "audio": "string (base64编码的音频数据)",
    "language": "string (可选，默认'zh')",
    "model": "string (可选，默认'base')",
    "sample_rate": "integer (可选，默认16000)",
    "encoding": "string (可选，默认'int16')"
}
```

**参数说明**:
- `audio`: base64编码的音频数据，必须是16kHz采样率、单声道、int16格式
- `language`: 语言代码，支持'zh'（中文）、'en'（英文）等
- `model`: Whisper模型大小，可选值：tiny, base, small, medium, large
- `sample_rate`: 音频采样率，支持8000, 16000, 22050, 44100, 48000
- `encoding`: 音频编码格式，支持'int16', 'float32'

**响应**:
```json
{
    "text": "string (识别出的文本)",
    "confidence": "float (置信度，0.0-1.0)",
    "language": "string (检测到的语言)",
    "duration": "float (音频时长，秒)",
    "words": [
        {
            "word": "string (单词)",
            "start": "float (开始时间，秒)",
            "end": "float (结束时间，秒)",
            "probability": "float (置信度)"
        }
    ]
}
```

**错误响应**:
```json
{
    "error": "Invalid audio data: ...",
    "code": "INVALID_AUDIO"
}
```

**示例**:
```python
import requests
import base64
import numpy as np

# 准备音频数据
sample_rate = 16000
duration = 2.0
samples = int(sample_rate * duration)
audio_data = np.random.randint(-32768, 32767, size=samples, dtype=np.int16)
audio_base64 = base64.b64encode(audio_data.tobytes()).decode('utf-8')

# 发送请求
response = requests.post(
    "http://localhost:8001/asr/transcribe",
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

### 2. ASR健康检查

#### `GET /asr/health`

**描述**: 检查ASR服务健康状态

**响应**:
```json
{
    "status": "healthy",
    "service": "asr",
    "model": "base",
    "gpu_available": true,
    "gpu_name": "NVIDIA GeForce RTX 5070 Ti",
    "version": "1.0.0",
    "uptime": 3600.5,
    "request_count": 100,
    "average_latency": 0.5,
    "error_rate": 0.01
}
```

### 3. ASR性能指标

#### `GET /asr/metrics`

**描述**: 获取ASR服务性能指标

**响应**:
```json
{
    "request_count": 100,
    "average_latency": 0.5,
    "p95_latency": 0.6,
    "p99_latency": 0.75,
    "error_rate": 0.01,
    "gpu_utilization": 45.2,
    "memory_usage": 1024.5
}
```

### 4. 重新加载模型

#### `POST /asr/reload`

**描述**: 重新加载ASR模型

**请求参数**:
- `model_name` (查询参数，可选): 新的模型名称

**响应**:
```json
{
    "status": "success",
    "model": "base"
}
```

## TTS API (第二阶段)

### 1. 语音合成

#### `POST /tts/synthesize`

**描述**: 将文本转换为语音

**请求头**:
```
Content-Type: application/json
X-API-Key: <api-key> (可选)
```

**请求体**:
```json
{
    "text": "string (要合成的文本)",
    "voice": "string (可选，默认'zh_CN')",
    "sample_rate": "integer (可选，默认22050)",
    "format": "string (可选，默认'wav')",
    "speed": "float (可选，默认1.0)"
}
```

**参数说明**:
- `text`: 要合成的文本，最大1000字符
- `voice`: 语音模型标识符
- `sample_rate`: 输出音频采样率
- `format`: 输出音频格式 (wav, mp3等)
- `speed`: 语速倍数 (0.5-2.0)

**响应**:
```json
{
    "audio": "string (base64编码的音频数据)",
    "sample_rate": "integer (采样率)",
    "duration": "float (音频时长，秒)",
    "format": "string (音频格式)"
}
```

**示例**:
```python
import requests
import base64

# 发送请求
response = requests.post(
    "http://localhost:8002/tts/synthesize",
    json={
        "text": "你好，我是MOSS智能管家",
        "voice": "zh_CN",
        "sample_rate": 22050,
        "format": "wav",
        "speed": 1.0
    }
)

result = response.json()

# 保存音频文件
audio_data = base64.b64decode(result['audio'])
with open("output.wav", "wb") as f:
    f.write(audio_data)
```

### 2. TTS健康检查

#### `GET /tts/health`

**描述**: 检查TTS服务健康状态

**响应**:
```json
{
    "available": false,
    "reason": "Phase 2 implementation",
    "model": "zh_CN",
    "request_count": 0
}
```

### 3. TTS服务信息

#### `GET /tts/info`

**描述**: 获取TTS服务信息

**响应**:
```json
{
    "available": false,
    "reason": "第二阶段实现",
    "model": "zh_CN",
    "supported_formats": ["wav", "mp3"],
    "supported_languages": ["zh_CN", "en_US"]
}
```

## 错误代码

| 错误代码 | HTTP状态码 | 描述 |
|----------|------------|------|
| `INVALID_AUDIO` | 400 | 音频数据格式无效 |
| `INVALID_API_KEY` | 403 | API密钥无效 |
| `MODEL_NOT_LOADED` | 500 | 模型未加载 |
| `TRANSCRIPTION_FAILED` | 500 | 转录失败 |
| `SYNTHESIS_FAILED` | 500 | 合成失败 |
| `VALIDATION_ERROR` | 422 | 请求参数验证失败 |
| `INTERNAL_ERROR` | 500 | 内部服务器错误 |

## 限流

为了保护服务，API可能实施限流：

- **默认限制**: 100请求/分钟/IP
- **响应头**:
  - `X-RateLimit-Limit`: 限制数量
  - `X-RateLimit-Remaining`: 剩余数量
  - `X-RateLimit-Reset`: 重置时间

**限流响应**:
```json
{
    "error": "Rate limit exceeded",
    "code": "RATE_LIMIT_EXCEEDED"
}
```

## 最佳实践

### 1. 音频格式
- 使用16kHz采样率、单声道、int16格式
- 音频长度不超过30秒
- 确保音频质量清晰，避免背景噪音

### 2. 错误处理
- 始终检查响应状态码
- 实现重试机制（对于500错误）
- 记录错误日志用于调试

### 3. 性能优化
- 使用连接池
- 实现请求批处理
- 监控服务性能指标

### 4. 安全性
- 使用HTTPS（生产环境）
- 验证API密钥
- 限制请求来源（CORS）

## 版本历史

### v1.0.0 (2026-06-20)
- 初始版本
- 实现ASR语音识别功能
- 支持Whisper模型
- 基础健康检查和监控

### v2.0.0 (计划中)
- 实现TTS语音合成功能
- 支持Piper TTS模型
- 流式识别支持