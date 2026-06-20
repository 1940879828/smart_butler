---
name: voice-service-plan
overview: 在Windows环境下搭建Whisper ASR HTTP服务，后续扩展Piper TTS服务，为ROS2智能管家机器人提供语音识别和语音合成能力。
todos:
  - id: create-docs-plan
    content: 创建docs目录和语音服务实现计划文档
    status: completed
  - id: create-server-structure
    content: 创建smart_butler_server目录结构和基础文件
    status: completed
    dependencies:
      - create-docs-plan
  - id: implement-asr-config
    content: 实现ASR服务配置管理模块
    status: completed
    dependencies:
      - create-server-structure
  - id: implement-asr-models
    content: 实现ASR请求/响应数据模型
    status: completed
    dependencies:
      - implement-asr-config
  - id: implement-asr-service
    content: 实现ASR核心服务逻辑（faster-whisper集成）
    status: completed
    dependencies:
      - implement-asr-models
  - id: implement-asr-router
    content: 实现ASR API路由和FastAPI应用
    status: completed
    dependencies:
      - implement-asr-service
  - id: implement-audio-utils
    content: 实现音频处理工具函数
    status: completed
    dependencies:
      - implement-asr-router
  - id: implement-logging
    content: 实现日志配置和错误处理
    status: completed
    dependencies:
      - implement-audio-utils
  - id: create-requirements
    content: 创建requirements.txt和环境配置
    status: completed
    dependencies:
      - implement-logging
  - id: create-readme
    content: 创建README部署文档
    status: completed
    dependencies:
      - create-requirements
---

## 需求分析

用户需要在当前Windows环境下，使用5070Ti显卡，在`smart_butler_server/voice_service/`目录下搭建Whisper ASR HTTP服务，并将计划文档新建在项目根目录的`docs`目录下。

### 核心需求

1. **第一阶段**：实现ASR（语音识别）HTTP服务
2. **第二阶段**：实现TTS（语音合成）HTTP服务
3. **部署环境**：Windows + 5070Ti GPU
4. **服务位置**：`smart_butler_server/voice_service/`
5. **文档位置**：项目根目录的`docs`目录

### 现有接口规范

从`butler_voice`包中提取的现有接口设计：

**ASR服务**（端口8001）：

- 端点：POST /transcribe
- 请求：`{"audio": "base64编码", "language": "zh", "model": "base", "sample_rate": 16000, "encoding": "int16"}`
- 响应：`{"text": "识别出的文本"}`

**TTS服务**（端口8002）：

- 端点：POST /synthesize
- 请求：`{"text": "要合成的文本", "voice": "zh_CN", "sample_rate": 22050, "format": "wav"}`
- 响应：`{"audio": "base64编码的音频数据"}`

### 功能要求

- 支持中文语音识别
- 支持GPU加速
- 与现有ROS2系统兼容
- 可扩展架构，便于后续添加TTS

## 技术方案

### 技术栈选择

- **Web框架**：FastAPI（高性能、自动文档生成）
- **ASR引擎**：faster-whisper（GPU加速）
- **TTS引擎**：piper-tts（第二阶段）
- **音频处理**：numpy、soundfile
- **配置管理**：python-dotenv + pydantic-settings
- **日志**：loguru
- **部署**：uvicorn

### 目录结构设计

```
smart_butler_server/
├── voice_service/
│   ├── __init__.py
│   ├── main.py              # FastAPI应用入口
│   ├── config.py            # 配置管理
│   ├── models/              # 数据模型
│   │   ├── __init__.py
│   │   ├── request.py       # 请求模型
│   │   └── response.py      # 响应模型
│   ├── services/            # 业务逻辑
│   │   ├── __init__.py
│   │   ├── asr_service.py   # ASR服务
│   │   └── tts_service.py   # TTS服务（第二阶段）
│   ├── routers/             # API路由
│   │   ├── __init__.py
│   │   ├── asr_router.py    # ASR路由
│   │   └── tts_router.py    # TTS路由（第二阶段）
│   └── utils/               # 工具函数
│       ├── __init__.py
│       ├── audio_utils.py   # 音频处理
│       └── logger.py        # 日志配置
├── requirements.txt         # 依赖管理
├── .env.example            # 环境变量示例
└── README.md               # 服务说明
```

### API设计规范

#### ASR服务端点

```
POST /transcribe
Content-Type: application/json

请求体：
{
    "audio": "string (base64编码的int16音频数据)",
    "language": "string (可选，默认'zh')",
    "model": "string (可选，默认'base')",
    "sample_rate": "integer (可选，默认16000)",
    "encoding": "string (可选，默认'int16')"
}

响应体：
{
    "text": "string (识别出的文本)",
    "confidence": "float (置信度，可选)",
    "language": "string (检测到的语言，可选)"
}
```

#### 健康检查端点

```
GET /health

响应体：
{
    "status": "healthy",
    "service": "asr",
    "model": "base",
    "gpu_available": true
}
```

### GPU加速配置

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    model_size_or_path="base",
    device="cuda",
    compute_type="float16"
)
```

### 音频处理流程

1. 接收base64编码的音频数据
2. 解码为int16 numpy数组
3. 转换为float32并归一化
4. 调用faster-whisper转录
5. 返回识别结果

### 性能优化

- 模型预加载
- 异步处理
- 请求缓存
- 并发控制

### 依赖管理

```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
faster-whisper>=0.10.0
numpy>=1.24.0
soundfile>=0.12.0
python-dotenv>=1.0.0
loguru>=0.7.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
torch>=2.0.0
torchaudio>=2.0.0
```

### 部署方案

```
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn voice_service.main:app --host 0.0.0.0 --port 8001
```

### 与ROS2集成

更新`sim.yaml`配置：

```
voice:
  asr:
    windows_endpoint: "http://<Windows_IP>:8001"
  tts:
    windows_endpoint: "http://<Windows_IP>:8002"
```