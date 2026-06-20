# MOSS 智能管家语音服务

为ROS2智能管家机器人MOSS提供语音交互能力的HTTP服务。

## 功能特性

### 语音识别 (ASR)
- 基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 的语音识别
- 支持GPU加速 (CUDA)
- 支持多种Whisper模型 (tiny, base, small, medium, large)
- 支持中文和英文识别
- 自动语音活动检测 (VAD)

### 语音合成 (TTS) - 第二阶段
- 基于 [piper-tts](https://github.com/rhasspy/piper) 的语音合成
- 支持多种语音模型
- 可调节语速

### 其他特性
- FastAPI高性能Web框架
- 自动API文档生成
- 完整的健康检查和监控
- 结构化日志记录
- API密钥认证
- CORS支持

## 系统要求

### 硬件要求
- **GPU**: NVIDIA显卡，支持CUDA (推荐RTX 5070 Ti或更高)
- **内存**: 8GB RAM以上
- **存储**: 2GB可用空间 (用于模型文件)

### 软件要求
- **操作系统**: Windows 10/11 64位
- **Python**: 3.8或更高版本
- **CUDA**: 11.8或更高版本
- **cuDNN**: 8.0或更高版本

## 安装指南

### 1. 克隆项目
```bash
cd smart_butler_server
```

### 2. 创建虚拟环境
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置环境变量
```bash
cp .env.example .env
# 编辑.env文件，配置GPU、模型等参数
```

### 5. 验证GPU安装
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

## 使用方法

### 启动服务
```bash
# 开发模式 (自动重载)
python -m uvicorn voice_service.main:app --host 0.0.0.0 --port 8001 --reload

# 或者直接运行
python voice_service/main.py
```

### 访问服务
- **ASR服务**: http://localhost:8001
- **API文档**: http://localhost:8001/docs
- **ReDoc文档**: http://localhost:8001/redoc
- **健康检查**: http://localhost:8001/health

### API使用示例

#### 语音识别
```python
import requests
import base64
import numpy as np

# 准备音频数据 (16kHz, int16, 单声道)
sample_rate = 16000
duration = 2.0  # 2秒
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
print(f"置信度: {result['confidence']}")
print(f"时长: {result['duration']}秒")
```

#### 健康检查
```python
import requests

response = requests.get("http://localhost:8001/health")
health = response.json()
print(f"服务状态: {health['status']}")
print(f"GPU: {health['gpu_name']}")
```

## 项目结构

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
│   └── api-spec.md                   # API规范文档
├── tests/                            # 测试目录
│   └── test_asr.py                   # ASR测试
├── requirements.txt                  # Python依赖
├── .env.example                      # 环境变量示例
├── .env                              # 环境变量（不提交到git）
└── README.md                         # 项目说明
```

## 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ASR_HOST` | 0.0.0.0 | ASR服务监听地址 |
| `ASR_PORT` | 8001 | ASR服务端口 |
| `WHISPER_MODEL` | base | Whisper模型大小 |
| `WHISPER_DEVICE` | cuda | 计算设备 (cuda/cpu) |
| `WHISPER_COMPUTE_TYPE` | float16 | 计算精度类型 |
| `TTS_HOST` | 0.0.0.0 | TTS服务监听地址 |
| `TTS_PORT` | 8002 | TTS服务端口 |
| `PIPER_VOICE` | zh_CN | Piper TTS语音模型 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `API_KEY` | None | API密钥 (可选) |
| `CORS_ORIGINS` | [...] | CORS允许的源 |

### Whisper模型选择

| 模型 | 参数量 | 显存占用 | 速度 | 准确度 |
|------|--------|----------|------|--------|
| tiny | 39M | ~1GB | 最快 | 低 |
| base | 74M | ~1GB | 快 | 中 |
| small | 244M | ~2GB | 中 | 中高 |
| medium | 769M | ~5GB | 慢 | 高 |
| large | 1550M | ~10GB | 最慢 | 最高 |

**推荐**: 对于中文识别，建议使用 `base` 或 `small` 模型。

## 部署

### 生产环境部署

#### 使用Gunicorn (推荐)
```bash
pip install gunicorn
gunicorn voice_service.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8001
```

#### 使用Docker
```bash
# 构建镜像
docker build -t moss-voice-service .

# 运行容器
docker run -d --gpus all -p 8001:8001 --name voice-service moss-voice-service
```

### 网络配置

#### Windows防火墙
```powershell
New-NetFirewallRule -DisplayName "MOSS Voice Service" -Direction Inbound -Port 8001 -Protocol TCP -Action Allow
```

#### ROS2配置更新
更新 `sim.yaml` 中的端点配置：
```yaml
voice:
  asr:
    provider: "whisper"
    model: "base"
    windows_endpoint: "http://<Windows_IP>:8001"
```

## 测试

### 运行测试
```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_asr.py -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=voice_service --cov-report=html
```

### 性能测试
```bash
# 使用locust进行负载测试
pip install locust
locust -f tests/locustfile.py --host=http://localhost:8001
```

## 监控与日志

### 日志文件
- 控制台日志: 实时输出
- 文件日志: `logs/voice_service_YYYY-MM-DD.log`
- 错误日志: `logs/errors.log`

### 监控端点
- `/health`: 健康检查
- `/metrics`: 性能指标
- `/info`: 服务信息

## 故障排除

### 常见问题

#### 1. CUDA不可用
```
问题: RuntimeError: CUDA is not available
解决: 
1. 检查NVIDIA驱动是否安装
2. 验证CUDA安装: python -c "import torch; print(torch.cuda.is_available())"
3. 检查.env文件中的WHISPER_DEVICE设置
```

#### 2. 模型加载失败
```
问题: RuntimeError: Model loading failed
解决:
1. 检查网络连接 (首次使用需要下载模型)
2. 检查磁盘空间
3. 尝试使用更小的模型 (tiny/base)
```

#### 3. 内存不足
```
问题: CUDA out of memory
解决:
1. 使用更小的模型
2. 减少batch size
3. 使用float32而不是float16
```

## 开发指南

### 添加新功能
1. 在 `voice_service/models/` 中定义数据模型
2. 在 `voice_service/services/` 中实现业务逻辑
3. 在 `voice_service/routers/` 中定义API端点
4. 在 `tests/` 中添加测试

### 代码规范
- 使用类型注解
- 编写文档字符串
- 遵循PEP 8规范
- 编写单元测试

## 许可证

本项目为MOSS智能管家机器人项目的一部分。

## 联系方式

如有问题或建议，请联系项目维护者。