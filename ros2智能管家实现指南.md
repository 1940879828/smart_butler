# ROS2 智能管家机器人 MOSS 实现指南

> **创建日期**：2026-06-14  
> **ROS2 版本**：Jazzy Jalisco  
> **Python 版本**：3.12  
> **仿真平台**：Gazebo Fortress (Ignition)  
> **机器人名称**：MOSS  
> **目标**：在仿真环境中开发智能管家机器人，脱离硬件先行开发，预留真机迁移接口

---

## 目录

1. [项目概述](#1-项目概述)
2. [开发前准备](#2-开发前准备)
3. [项目结构](#3-项目结构)
4. [阶段 0：基础设施搭建](#4-阶段-0基础设施搭建)
5. [阶段 1：仿真环境搭建](#5-阶段-1仿真环境搭建)
6. [阶段 2：基础感知能力](#6-阶段-2基础感知能力)
7. [阶段 3：AI 大脑](#7-阶段-3ai-大脑)
8. [阶段 4：智能家居集成](#8-阶段-4智能家居集成)
9. [阶段 5：Web Dashboard 与完整集成](#9-阶段-5web-dashboard-与完整集成)
10. [硬件抽象层设计](#10-硬件抽象层设计)
11. [安全方案详解](#11-安全方案详解)
12. [扩展预留接口](#12-扩展预留接口)
13. [配置管理方案](#13-配置管理方案)
14. [附录：常见问题与排错](#14-附录常见问题与排错)

---

## 1. 项目概述

### 1.1 机器人介绍

MOSS 是一款部署在天花板轨道上的智能管家机器人，具备以下能力：

| 能力域 | 描述 | 优先级 |
|--------|------|--------|
| 移动能力 | 天花轨道滑行（Gazebo 仿真预留，真机后实现） | 低 |
| 摄像头感知 | 自动变焦摄像头，3 轴云台转动控制 | 高 |
| 画面识别 | 人物检测、宠物检测、画面追踪 | 中 |
| 音频交互 | 语音识别（ASR）、文本转语音（TTS）、唤醒词、喇叭输出 | 高 |
| AI 大模型 | 通过 OpenAI 兼容 API 连接云端或本地大模型 | 高 |
| 智能家居控制 | 通过 Home Assistant REST API 操控智能设备 | 高 |
| App 控制 | Web Dashboard (PWA) 远程查看视频、控制云台 | 高 |
| 安全防护 | 四层安全机制保护智能家居操作 | 高 |

### 1.2 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                     Web Dashboard (PWA)                           │
│               JWT Auth / WebRTC / REST API                        │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────┼──────────────────────────────────────┐
│   Ubuntu (本机 - ROS2)     │        Windows (5070Ti)              │
│                            │                                       │
│  ┌─────────────────────┐  │  ┌──────────────────────────────────┐│
│  │ Gazebo Fortress     │  │  │ PostgreSQL (数据持久化)          ││
│  │ ┌─────────────────┐ │  │  ├──────────────────────────────────┤│
│  │ │ 机器人模型       │ │  │  │ Ollama/vLLM (本地大模型)        ││
│  │ │ - 天花板轨道     │ │  │  ├──────────────────────────────────┤│
│  │ │ - 3轴云台        │ │  │  │ Whisper (语音识别)              ││
│  │ │ - 摄像头         │ │  │  ├──────────────────────────────────┤│
│  │ └─────────────────┘ │  │  │ Piper/eSpeak (TTS)               ││
│  │ ┌─────────────────┐ │  │  ├──────────────────────────────────┤│
│  │ │ 房间环境         │  │  │  │ butler_server (API服务)         ││
│  │ │ - 灯/空调/窗帘   │  │  │  └──────────────────────────────────┘│
│  │ │ - 温度传感器     │  │  │                                       │
│  │ └─────────────────┘ │  │                                        │
│  └─────────────────────┘  │                                        │
│                            │                                        │
│  ┌─────────────────────┐  │                                        │
│  │ ROS2 节点            │  │                                        │
│  │ butler_camera ───────┼──┼→ REST/gRPC ──→ Windows AI 服务       │
│  │ butler_gimbal        │  │                                        │
│  │ butler_audio         │  │  ◄── DDS (ROS2 跨机) ──→ (可选)      │
│  │ butler_voice         │  │                                        │
│  │ butler_ai            │  │  ┌──────────────────────────────────┐│
│  │ butler_behavior      │  │  │ Home Assistant (局域网)          ││
│  │ butler_ha ───────────┼──┼──┼ REST API / HTTPS                 ││
│  │ butler_security      │  │  └──────────────────────────────────┘│
│  └─────────────────────┘  │                                        │
└────────────────────────────┴──────────────────────────────────────┘
```

### 1.3 技术栈一览

| 层级 | 技术 | 用途 |
|------|------|------|
| 机器人框架 | ROS2 Jazzy (rclpy) | 核心通信、节点管理 |
| 仿真器 | Gazebo Fortress (Ignition) | 3D 物理仿真 |
| 行为逻辑 | BehaviorTree.CPP v4.x | 机器人行为状态机 |
| AI 接入 | openai Python SDK | 大模型对话（兼容 OpenAI API） |
| 语音识别 | faster-whisper / whisper.cpp | 语音转文本 |
| 语音合成 | piper-tts / edge-tts | 文本转语音 |
| 视频流 | WebRTC (aiortc) | 低延迟视频传输 |
| 后端框架 | FastAPI / Flask | Web Dashboard 后端 |
| 前端框架 | Vue3 / React | Web Dashboard 前端 |
| 数据库 | PostgreSQL + asyncpg | 数据持久化 |
| 容器化 | Docker + docker-compose | 部署管理 |
| CI/CD | GitHub Actions | 自动化测试 |
| 硬件仿真 | ros_gz (ros_gz_bridge) | ROS2-Gazebo 桥接 |

---

## 2. 开发前准备

### 2.1 GitHub 仓库创建

在 GitHub 上创建以下 3 个仓库（建议用一个 Organization 或统一前缀管理）：

```bash
# 仓库 1：机器人核心（ROS2 包）
github.com/<你的用户名>/smart_butler_ros2

# 仓库 2：Web Dashboard（前端 + 后端 API）
github.com/<你的用户名>/smart_butler_web

# 仓库 3：AI 与语音服务（部署在 Windows）
github.com/<你的用户名>/smart_butler_server
```

**创建步骤：**

```bash
# 1. 在 GitHub 网页创建以上 3 个空仓库（不要勾选 README）

# 2. 克隆到本地
cd ~/文档/LeranRos/smart_butler_ws/src

# 3. 基础 .gitignore（三个仓库通用）
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/

# ROS2
log/
install/
build/
*.log

# IDE
.vscode/
.idea/
*.swp

# Env
.env
.env.local

# Docker
docker-compose.override.yml

# OS
.DS_Store
Thumbs.db
EOF
```

### 2.2 环境要求

| 软件 | 版本要求 | 已验证版本 | 安装命令 |
|------|---------|-----------|---------|
| Ubuntu | 24.04 LTS | 24.04.4 | - |
| ROS 2 | Jazzy | Jazzy | 已安装 |
| Python | 3.12 | 3.12.3 | 已安装 |
| Gazebo | Fortress (Ignition) | - | `sudo apt install ignition-fortress` |
| CMake | 3.22+ | 3.28.3 | 已安装 |
| colcon | latest | - | `sudo apt install python3-colcon-common-extensions` |
| Git | 2.x | - | 已安装 |

### 2.3 依赖安装脚本

```bash
#!/bin/bash
# setup_deps.sh - 一次性安装所有开发依赖
set -e

echo "=== 安装 Gazebo Fortress ==="
sudo apt-get update
sudo apt-get install -y ignition-fortress

echo "=== 安装 ROS-Gazebo 桥接 ==="
sudo apt-get install -y ros-jazzy-ros-gz-bridge ros-jazzy-ros-gz-image
sudo apt-get install -y ros-jazzy-ros-gz-sim ros-jazzy-ros-gz-interfaces

echo "=== 安装 ROS2 常用工具 ==="
sudo apt-get install -y ros-jazzy-ros2-control ros-jazzy-ros2-controllers
sudo apt-get install -y ros-jazzy-xacro ros-jazzy-joint-state-publisher
sudo apt-get install -y ros-jazzy-robot-state-publisher ros-jazzy-rviz2

echo "=== 安装 BehaviorTree.CPP ==="
sudo apt-get install -y ros-jazzy-behaviortree-cpp

echo "=== Python 依赖 ==="
pip install --user \
    openai \
    faster-whisper \
    sounddevice soundfile \
    piper-tts \
    fastapi uvicorn[standard] \
    python-jose[cryptography] passlib[bcrypt] \
    asyncpg sqlalchemy[asyncio] \
    aiohttp jinja2 \
    websockets pyyaml \
    pydantic python-dotenv \
    opencv-python-headless \
    pytest pytest-asyncio

echo "=== 完成 ==="
echo "请执行: source /opt/ros/jazzy/setup.bash"
```

---

## 3. 项目结构

### 3.1 工作空间布局

```
~/文档/LeranRos/
├── ros2智能管家实现指南.md          # 本文档
│
├── smart_butler_ros2/               # Git 仓库 1
│   ├── .gitignore
│   ├── .github/workflows/           # CI/CD 配置
│   │   └── test.yml
│   ├── README.md
│   ├── docker/                      # Docker 部署配置
│   │   └── docker-compose.yml
│   └── smart_butler_ws/
│       ├── src/
│       │   ├── butler_bringup/      # 启动配置（launch 文件）
│       │   ├── butler_msgs/         # 自定义 ROS2 消息和服务
│       │   ├── butler_description/  # URDF/SDF 机器人模型
│       │   ├── butler_gazebo/       # Gazebo 世界和插件
│       │   ├── butler_camera/       # 摄像头节点（sim + real）
│       │   ├── butler_gimbal/       # 3轴云台控制
│       │   ├── butler_audio/        # 音频采集与播放
│       │   ├── butler_voice/        # 语音识别/合成
│       │   ├── butler_ai/           # AI 大模型客户端
│       │   ├── butler_behavior/     # 行为树定义
│       │   ├── butler_ha/           # Home Assistant 集成
│       │   ├── butler_security/     # 安全模块
│       │   └── butler_web/          # Web Dashboard 后端
│       ├── config/                  # 全局 YAML 配置
│       │   ├── sim.yaml             # 仿真环境配置
│       │   ├── real.yaml            # 真机环境配置
│       │   └── features.yaml        # 功能开关配置
│       └── scripts/                 # 工具脚本
│
├── smart_butler_web/                # Git 仓库 2
│   ├── .gitignore
│   ├── .github/workflows/test.yml
│   ├── README.md
│   ├── backend/                     # FastAPI 后端
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── auth/
│   │   └── tests/
│   └── frontend/                    # Vue3/React 前端
│       ├── package.json
│       ├── src/
│       └── public/
│
└── smart_butler_server/             # Git 仓库 3（部署在 Windows）
    ├── .gitignore
    ├── README.md
    ├── requirements.txt
    ├── ai_service/                  # 大模型服务
    ├── voice_service/               # 语音服务
    ├── db/                          # 数据库迁移
    └── docker-compose.yml
```

### 3.2 包职责速查表

| 包名 | 职责 | 主要依赖 | 开发阶段 |
|------|------|---------|---------|
| `butler_bringup` | launch 文件、全局启动配置 | 所有包 | 阶段 0 |
| `butler_msgs` | 自定义 .msg/.srv/.action | - | 阶段 0 |
| `butler_description` | URDF/Xacro/SDF 模型文件 | xacro | 阶段 1 |
| `butler_gazebo` | Gazebo 世界文件、插件 | ros_gz_bridge | 阶段 1 |
| `butler_camera` | 模拟/真实摄像头驱动 | sensor_msgs, cv_bridge | 阶段 1 |
| `butler_gimbal` | 3 轴云台控制 | trajectory_msgs | 阶段 1 |
| `butler_audio` | 音频硬件接口 | sounddevice | 阶段 2 |
| `butler_voice` | ASR/TTS 服务客户端 | faster-whisper, piper-tts | 阶段 2 |
| `butler_ai` | OpenAI 兼容 API 客户端 | openai | 阶段 3 |
| `butler_behavior` | BehaviorTree 行为定义 | behaviortree_cpp, py_trees | 阶段 3 |
| `butler_ha` | Home Assistant 客户端 | aiohttp | 阶段 4 |
| `butler_security` | 安全防护、操作日志 | - | 阶段 4 |
| `butler_web` | Web API 端点（ROS2 侧） | fastapi | 阶段 5 |

---

## 4. 阶段 0：基础设施搭建

> **目标**：搭建项目骨架，ROS2 workspace 可编译运行，配置系统就绪，Hello World 验证通过

### 4.1 目标与产出

| 产物 | 描述 |
|------|------|
| 3 个 GitHub 仓库 | 已初始化，含 .gitignore 和 CI 配置 |
| ROS2 workspace | `colcon build` 成功 |
| 配置系统 | `config/sim.yaml`, `config/features.yaml` 可正常读取 |
| butler_msgs 包 | 已定义基本消息类型 |
| 跨机通信验证 | Ubuntu ↔ Windows 网络可达性确认 |

### 4.2 详细步骤

#### 步骤 0.1：初始化 ROS2 Workspace

```bash
# 创建 workspace
mkdir -p ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws

# 初始化 Git（关联到 smart_butler_ros2 仓库）
cd ..
git init
git remote add origin git@github.com:<用户名>/smart_butler_ros2.git

# 创建 .gitignore（见 2.1 节）
```

#### 步骤 0.2：创建 butler_msgs 包

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src

# 创建 ROS2 包（ament_cmake，因为需要定义消息）
ros2 pkg create butler_msgs \
  --build-type ament_cmake \
  --dependencies builtin_interfaces rosidl_default_generators \
  --license Apache-2.0

# 创建自定义消息
mkdir -p butler_msgs/msg butler_msgs/srv butler_msgs/action
```

**butler_msgs/msg/GimbalCommand.msg**（云台控制指令）:
```
float32 pan       # 水平角度 (-180 ~ 180)
float32 tilt      # 俯仰角度 (-90 ~ 90)
float32 roll      # 旋转角度 (-180 ~ 180)
```

**butler_msgs/msg/DeviceState.msg**（智能设备状态）:
```
string device_id
string device_type   # light, thermostat, curtain, sensor
string state         # JSON 格式的状态详情
builtin_interfaces/Time timestamp
```

**butler_msgs/msg/VoiceCommand.msg**（语音指令）:
```
string text          # 识别出的文本
float32 confidence   # 置信度 0.0 ~ 1.0
bool is_final        # 是否是最终结果
byte[] audio_data    # 原始音频数据（可选，用于传递给ASR）
int32 sample_rate    # 采样率（如16000）
```

**butler_msgs/srv/GetConfig.srv**（获取配置）:
```
string key
---
string value
bool success
```

**butler_msgs/msg/DetectionResult.msg**（检测结果）:
```
string class_name    # person, pet, vehicle ...
float32 confidence
int32 x_min
int32 y_min
int32 x_max
int32 y_max
builtin_interfaces/Time timestamp
```

**butler_msgs/msg/AudioData.msg**（音频帧数据）:
```
builtin_interfaces/Time timestamp
int32 sample_rate      # 采样率 (如16000)
int32 channels         # 通道数 (如1)
int32 sample_width     # 采样位宽 (如16)
byte[] data            # 原始音频数据
```

更新 `butler_msgs/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.8)
project(butler_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GimbalCommand.msg"
  "msg/DeviceState.msg"
  "msg/VoiceCommand.msg"
  "msg/DetectionResult.msg"
  "msg/AudioData.msg"
  "srv/GetConfig.srv"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
```

更新 `butler_msgs/package.xml`，确认包含：
```xml
<depend>builtin_interfaces</depend>
<depend>rosidl_default_generators</depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

#### 步骤 0.3：创建 butler_bringup 包

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src

ros2 pkg create butler_bringup \
  --build-type ament_python \
  --dependencies rclpy launch launch_ros \
  --license Apache-2.0

mkdir -p butler_bringup/launch butler_bringup/config
```

**butler_bringup/launch/moss_sim.launch.py**（仿真启动文件骨架）:

```python
import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # 配置路径
    pkg_bringup = get_package_share_directory('butler_bringup')
    config_sim = os.path.join(pkg_bringup, '..', '..', 'config', 'sim.yaml')

    use_sim = LaunchConfiguration('use_sim', default='true')

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim',
            default_value='true',
            description='Run in simulation mode'
        ),
        DeclareLaunchArgument(
            'config_file',
            default_value=config_sim,
            description='Path to YAML config file'
        ),
        # 后续阶段逐步添加节点
    ])
```

#### 步骤 0.4：创建配置系统

**config/sim.yaml**（仿真环境配置）:

```yaml
# MOSS 机器人仿真环境配置
robot:
  name: "moss"
  mode: "simulation"  # simulation | real

# 功能开关
features:
  wake_word_enabled: false     # 唤醒词 "moss"，开发阶段关闭
  face_recognition_enabled: false
  smart_home_enabled: true
  voice_interaction_enabled: true
  video_streaming_enabled: true
  notifications_enabled: false  # 通知推送（预留）

# 节点配置
nodes:
  camera:
    sim_source: "video_file"    # video_file | gazebo_plugin
    video_path: "/home/taro/文档/LeranRos/assets/test_video.mp4"
    resolution: [640, 480]
    fps: 30

  gimbal:
    default_pan: 0.0
    default_tilt: 0.0
    default_roll: 0.0
    max_pan_speed: 60.0         # 度/秒

  ai:
    api_base: "https://api.openai.com/v1"   # 或 "http://192.168.2.xxx:11434/v1" (Ollama)
    model: "gpt-4o-mini"                     # 或 "qwen2.5:7b" (本地模型)
    max_tokens: 2048
    temperature: 0.7

  voice:
    asr:
      provider: "whisper"       # whisper | azure | local
      model: "base"             # tiny, base, small, medium, large
      windows_endpoint: "http://192.168.2.xxx:8001"  # Windows 服务地址
    tts:
      provider: "piper"         # piper | edge | local
      voice: "zh_CN"
      windows_endpoint: "http://192.168.2.xxx:8002"

  ha:
    base_url: "http://192.168.2.xxx:8123"
    token: "${HA_TOKEN}"        # 从环境变量读取

# 安全配置
security:
  jwt_secret: "${JWT_SECRET}"
  operation_log_dir: "/home/taro/文档/LeranRos/logs/operations"

# 跨机通信
network:
  windows_host: "192.168.2.xxx"  # Windows 机器 IP
  dds_domain: 0
  api_timeout: 30                # 秒
```

**config/features.yaml**（功能开关集中管理）:

```yaml
# MOSS 功能开关统一配置
# 用法: 节点启动时读取此文件，决定启用哪些功能模块

features:
  # 音频相关
  wake_word: false        # 唤醒词 "moss" 检测
  asr: true               # 语音识别
  tts: true               # 文本转语音

  # 视觉相关
  object_detection: true  # 物体检测
  person_tracking: false  # 人物追踪（留待后续）
  face_recognition: false # 人脸识别（留待后续）

  # 智能家居
  smart_home: true        # HA 操控
  auto_routine: false     # 自动场景（如离家模式）

  # 通知
  notifications: false    # 异常推送通知（留待后续）

  # 屏幕
  onboard_display: false  # 机载屏幕（先不做）

  # 移动
  track_movement: false   # 轨道移动（后期硬件）
```

#### 步骤 0.5：配置管理器实现

在 `butler_bringup` 包中添加配置加载模块：

**butler_bringup/butler_bringup/config_manager.py**:

```python
"""
MOSS 配置管理器
统一管理所有 YAML 配置和功能开关

注意：使用模块级单例模式，确保在ROS2多进程环境中正常工作
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
import threading


class ConfigManager:
    """配置管理器（使用模块级单例）"""

    def __init__(self):
        """初始化配置管理器"""
        self._config: Dict[str, Any] = {}
        self._features: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def load(self, config_path: str, features_path: Optional[str] = None):
        """
        加载配置文件

        Args:
            config_path: 主配置文件路径
            features_path: 功能开关配置文件路径（可选）
        """
        with self._lock:
            # 加载主配置
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}

            # 加载功能开关
            if features_path and Path(features_path).exists():
                with open(features_path, 'r', encoding='utf-8') as f:
                    feat_data = yaml.safe_load(f) or {}
                    self._features = feat_data.get('features', {})

            # 环境变量替换
            self._resolve_env_vars(self._config)
            self._loaded = True

    def _resolve_env_vars(self, data: Any) -> Any:
        """递归替换 ${VAR_NAME} 为环境变量值"""
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str) and v.startswith('${') and v.endswith('}'):
                    env_var = v[2:-1]
                    data[k] = os.environ.get(env_var, '')
                elif isinstance(v, (dict, list)):
                    self._resolve_env_vars(v)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str) and item.startswith('${') and item.endswith('}'):
                    env_var = item[2:-1]
                    data[i] = os.environ.get(env_var, '')
                elif isinstance(item, (dict, list)):
                    self._resolve_env_vars(item)
        return data

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        通过点分隔路径获取配置值

        Args:
            key_path: 配置路径，如 'nodes.camera.resolution'
            default: 默认值

        Returns:
            配置值或默认值
        """
        if not self._loaded:
            return default

        keys = key_path.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def is_feature_enabled(self, feature: str) -> bool:
        """
        检查功能开关是否启用

        Args:
            feature: 功能名称

        Returns:
            功能是否启用
        """
        return self._features.get(feature, False)

    def reload(self, config_path: str, features_path: Optional[str] = None):
        """
        重新加载配置（支持热重载）

        Args:
            config_path: 主配置文件路径
            features_path: 功能开关配置文件路径（可选）
        """
        self.load(config_path, features_path)

    @property
    def config(self) -> Dict[str, Any]:
        """获取完整配置字典"""
        return self._config.copy()

    @property
    def features(self) -> Dict[str, bool]:
        """获取功能开关字典"""
        return self._features.copy()


# 模块级单例（在ROS2多进程中更安全）
config = ConfigManager()
```

#### 步骤 0.6：跨机通信验证脚本

**scripts/check_network.sh**:

```bash
#!/bin/bash
# 验证 Ubuntu 与 Windows 机器的网络连通性

WINDOWS_IP="192.168.2.xxx"  # 替换为实际 IP

echo "=== 网络连通性检查 ==="

# ICMP 测试
echo -n "Ping 测试: "
if ping -c 1 -W 2 $WINDOWS_IP &>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达，请检查网络和防火墙"
fi

# 数据库端口测试 (PostgreSQL 默认 5432)
echo -n "PostgreSQL (5432): "
if timeout 2 bash -c "echo > /dev/tcp/$WINDOWS_IP/5432" 2>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达，请检查 Windows 上 PostgreSQL 是否运行且允许外部连接"
fi

# Ollama 端口测试 (默认 11434)
echo -n "Ollama (11434): "
if timeout 2 bash -c "echo > /dev/tcp/$WINDOWS_IP/11434" 2>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达"
fi
```

#### 步骤 0.7：首次编译验证

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws

# 编译
colcon build --symlink-install

# 加载环境
source install/setup.bash

# 验证消息定义
ros2 interface list | grep butler_msgs

# 验证 launch 文件
ros2 launch butler_bringup moss_sim.launch.py --show-arguments
```

#### 步骤 0.8：GitHub Actions CI 配置

**.github/workflows/test.yml**:

```yaml
name: Test

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-24.04
    container:
      image: osrf/ros:jazzy-desktop

    steps:
      - uses: actions/checkout@v4
        with:
          path: src/smart_butler_ros2

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y python3-pip python3-colcon-common-extensions
          pip install pytest pyyaml

      - name: Build
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --symlink-install

      - name: Test
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          colcon test --event-handlers console_direct+
          colcon test-result --verbose
```

### 4.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-0.1 | `colcon build` 无错误 | 运行 `colcon build --symlink-install` |
| AC-0.2 | 自定义消息可用 | `ros2 interface show butler_msgs/msg/GimbalCommand` 显示消息定义 |
| AC-0.3 | launch 文件可解析 | `ros2 launch butler_bringup moss_sim.launch.py --show-arguments` 无报错 |
| AC-0.4 | 配置系统工作 | 运行 Python 测试读取 config/sim.yaml 并获得正确值 |
| AC-0.5 | 网络连通 | `check_network.sh` 返回 Windows 可达 |
| AC-0.6 | GitHub CI 通过 | push 代码后 GitHub Actions 绿色 |

### 4.4 测试方案

**单元测试**（`butler_bringup/tests/test_config_manager.py`）:

```python
import pytest
import os
import tempfile
import yaml
from butler_bringup.config_manager import ConfigManager

@pytest.fixture
def temp_config():
    """创建临时配置文件"""
    config_data = {
        'robot': {'name': 'moss', 'mode': 'simulation'},
        'nodes': {
            'camera': {'resolution': [640, 480], 'fps': 30}
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

@pytest.fixture
def temp_features():
    """创建临时功能开关文件"""
    features_data = {
        'features': {
            'wake_word': False,
            'asr': True,
            'tts': True,
            'object_detection': True,
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(features_data, f)
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

def test_config_load(temp_config):
    """测试配置加载"""
    mgr = ConfigManager()
    mgr.load(temp_config)
    assert mgr.get('robot.name') == 'moss'
    assert mgr.get('nodes.camera.resolution') == [640, 480]

def test_config_default_value(temp_config):
    """测试默认值返回"""
    mgr = ConfigManager()
    mgr.load(temp_config)
    assert mgr.get('nonexistent.key', 'default') == 'default'

def test_config_not_loaded():
    """测试未加载时返回默认值"""
    mgr = ConfigManager()
    assert mgr.get('any.key', 'default') == 'default'

def test_features_load(temp_config, temp_features):
    """测试功能开关加载"""
    mgr = ConfigManager()
    mgr.load(temp_config, temp_features)
    assert mgr.is_feature_enabled('asr') is True
    assert mgr.is_feature_enabled('wake_word') is False
    assert mgr.is_feature_enabled('nonexistent') is False

def test_env_var_resolution():
    """测试环境变量替换"""
    os.environ['TEST_VAR'] = 'hello_world'
    config_data = {'test_key': '${TEST_VAR}'}
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name
    mgr = ConfigManager()
    mgr.load(temp_path)
    assert mgr.get('test_key') == 'hello_world'
    os.unlink(temp_path)
    del os.environ['TEST_VAR']

def test_config_reload(temp_config):
    """测试配置重载"""
    mgr = ConfigManager()
    mgr.load(temp_config)
    assert mgr.get('robot.name') == 'moss'

    # 修改配置文件
    new_config = {'robot': {'name': 'new_moss', 'mode': 'real'}}
    with open(temp_config, 'w') as f:
        yaml.dump(new_config, f)

    # 重载配置
    mgr.reload(temp_config)
    assert mgr.get('robot.name') == 'new_moss'
```

**运行测试**:
```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash
python3 -m pytest src/butler_bringup/tests/ -v
```

---

## 5. 阶段 1：仿真环境搭建

> **目标**：在 Gazebo Fortress 中创建完整仿真环境，包括 MOSS 机器人模型、房间环境和智能家居设备

### 5.1 目标与产出

| 产物 | 描述 |
|------|------|
| 机器人 URDF/SDF 模型 | 天花板安装底座 + 3 轴云台 + 摄像头 |
| Gazebo 世界文件 | 房间（带家具）+ 天花板轨道 + 智能设备模型 |
| ROS-Gazebo 桥接 | 摄像头话题、joint 状态正常收发 |
| 摄像头仿真 | Gazebo Camera Plugin 发布 sensor_msgs/Image |
| 云台控制仿真 | 可接受 joint 指令转动摄像头视角 |
| 智能设备模型 | 可调光灯、温度传感器、空调、窗帘模型及 ROS 接口 |

### 5.2 详细步骤

#### 步骤 1.1：安装 Gazebo Fortress

```bash
# 安装 Gazebo Fortress
sudo apt-get update
sudo apt-get install -y ignition-fortress

# 安装 ROS-Gazebo 桥接
sudo apt-get install -y ros-jazzy-ros-gz-bridge ros-jazzy-ros-gz-image
sudo apt-get install -y ros-jazzy-ros-gz-sim ros-jazzy-ros-gz-interfaces

# 验证安装
gz sim --versions
# 应输出: Gazebo Sim 8.x.x
```

#### 步骤 1.2：创建机器人描述包

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src

ros2 pkg create butler_description \
  --build-type ament_cmake \
  --dependencies xacro urdf \
  --license Apache-2.0

mkdir -p butler_description/urdf
mkdir -p butler_description/sdf
mkdir -p butler_description/meshes
mkdir -p butler_description/launch
```

**butler_description/urdf/moss.urdf.xacro**（机器人模型）:

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="moss">

  <!-- 材料定义 -->
  <material name="black">
    <color rgba="0.1 0.1 0.1 1.0"/>
  </material>
  <material name="gray">
    <color rgba="0.5 0.5 0.5 1.0"/>
  </material>
  <material name="white">
    <color rgba="0.9 0.9 0.9 1.0"/>
  </material>

  <!-- 世界参考帧（Gazebo 转换时必须显式定义） -->
  <link name="world"/>

  <!-- 底座 - 安装在天花板上 -->
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.15 0.15 0.05"/>
      </geometry>
      <material name="gray"/>
    </visual>
    <collision>
      <geometry>
        <box size="0.15 0.15 0.05"/>
      </geometry>
    </collision>
    <inertial>
      <mass value="0.5"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/>
    </inertial>
  </link>

  <!-- 固定底座到世界（天花板） -->
  <joint name="base_to_world" type="fixed">
    <parent link="world"/>
    <child link="base_link"/>
    <origin xyz="0 0 2.5" rpy="0 0 0"/> <!-- 天花板高度 2.5m -->
  </joint>

  <!-- Pan 轴（水平旋转） -->
  <joint name="pan_joint" type="revolute">
    <parent link="base_link"/>
    <child link="pan_link"/>
    <origin xyz="0 0 -0.05" rpy="0 0 0"/>
    <axis xyz="0 0 1"/>
    <limit lower="-3.1416" upper="3.1416" effort="1.0" velocity="1.0"/>
  </joint>

  <link name="pan_link">
    <visual>
      <geometry>
        <cylinder radius="0.04" length="0.03"/>
      </geometry>
      <material name="black"/>
    </visual>
    <inertial>
      <mass value="0.2"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
  </link>

  <!-- Tilt 轴（俯仰） -->
  <joint name="tilt_joint" type="revolute">
    <parent link="pan_link"/>
    <child link="tilt_link"/>
    <origin xyz="0 0 -0.02" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.57" upper="1.57" effort="0.5" velocity="0.5"/>
  </joint>

  <link name="tilt_link">
    <visual>
      <geometry>
        <box size="0.06 0.04 0.04"/>
      </geometry>
      <material name="white"/>
    </visual>
    <inertial>
      <mass value="0.15"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
  </link>

  <!-- Roll 轴（旋转） -->
  <joint name="roll_joint" type="revolute">
    <parent link="tilt_link"/>
    <child link="camera_link"/>
    <origin xyz="0.05 0 0" rpy="0 0 0"/>
    <axis xyz="1 0 0"/>
    <limit lower="-3.1416" upper="3.1416" effort="0.5" velocity="0.5"/>
  </joint>

  <!-- 摄像头 -->
  <link name="camera_link">
    <visual>
      <geometry>
        <cylinder radius="0.025" length="0.05"/>
      </geometry>
      <material name="black"/>
    </visual>
    <inertial>
      <mass value="0.1"/>
      <inertia ixx="0.00005" ixy="0" ixz="0" iyy="0.00005" iyz="0" izz="0.00005"/>
    </inertial>
  </link>

  <!-- 摄像头传感器 -->
  <gazebo reference="camera_link">
    <sensor type="camera" name="moss_camera">
      <update_rate>30.0</update_rate>
      <camera>
        <horizontal_fov>1.047</horizontal_fov>
        <image>
          <width>640</width>
          <height>480</height>
          <format>R8G8B8</format>
        </image>
        <clip>
          <near>0.1</near>
          <far>100</far>
        </clip>
      </camera>
    </sensor>
  </gazebo>

</robot>
```

> **注意**：Gazebo Fortress 8 中 `libignition-gazebo-camera-system.so` 已废弃。相机传感器由内置 Sensors 系统自动处理，不需要在 URDF 中显式声明 `<plugin>`。通过 `ros_gz_bridge` 桥接 Gazebo 相机话题到 ROS2 即可。
> 
> **已知限制**：当前 AMD GPU/Mesa 环境下，OGRE2 在 headless 模式不产出图像帧；GUI 模式下相机需要 SDF 中加载 Sensors 系统（可能挂起仿真）。可暂时跳过相机验证，改用设备状态话题验证仿真链路。

#### 步骤 1.3：创建 Gazebo 世界文件

```bash
mkdir -p butler_gazebo/worlds butler_gazebo/models butler_gazebo/launch

ros2 pkg create butler_gazebo \
  --build-type ament_cmake \
  --dependencies ros_gz_sim ros_gz_bridge \
  --license Apache-2.0
```

**butler_gazebo/worlds/smart_home.sdf**（房间世界）:

```xml
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="moss_smart_home">

    <!-- 物理引擎 -->
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- 光照 -->
    <light type="directional" name="sun">
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
    </light>

    <!-- 地面 -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry>
          <material><ambient>0.8 0.8 0.8</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 四面墙 -->
    <model name="wall_north">
      <static>true</static>
      <pose>0 2.5 1.25 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
          <material><ambient>0.9 0.9 0.85</ambient></material>
        </visual>
        <collision name="collision">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
        </collision>
      </link>
    </model>

    <model name="wall_south">
      <static>true</static>
      <pose>0 -2.5 1.25 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
          <material><ambient>0.9 0.9 0.85</ambient></material>
        </visual>
        <collision name="collision">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
        </collision>
      </link>
    </model>

    <model name="wall_east">
      <static>true</static>
      <pose>2.5 0 1.25 0 0 1.5708</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
          <material><ambient>0.9 0.9 0.85</ambient></material>
        </visual>
        <collision name="collision">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
        </collision>
      </link>
    </model>

    <model name="wall_west">
      <static>true</static>
      <pose>-2.5 0 1.25 0 0 1.5708</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
          <material><ambient>0.9 0.9 0.85</ambient></material>
        </visual>
        <collision name="collision">
          <geometry><box><size>5 0.1 2.5</size></box></geometry>
        </collision>
      </link>
    </model>

    <!-- 天花板 -->
    <model name="ceiling">
      <static>true</static>
      <pose>0 0 2.5 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>5 5 0.05</size></box></geometry>
          <material><ambient>0.95 0.95 0.9</ambient></material>
        </visual>
        <collision name="collision">
          <geometry><box><size>5 5 0.05</size></box></geometry>
        </collision>
      </link>
    </model>

    <!-- 天花板轨道 - 模拟轨道走线 -->
    <model name="ceiling_track">
      <static>true</static>
      <pose>0 0 2.45 0 0 0</pose>
      <link name="track">
        <visual name="visual">
          <geometry><box><size>3.0 0.02 0.01</size></box></geometry>
          <material><ambient>0.3 0.3 0.3</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 简单家具 - 沙发 -->
    <model name="sofa">
      <static>true</static>
      <pose>-1.5 -1.5 0.4 0 0 0</pose>
      <link name="sofa_body">
        <visual name="visual">
          <geometry><box><size>1.5 0.6 0.8</size></box></geometry>
          <material><ambient>0.4 0.3 0.2</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 简单家具 - 桌子 -->
    <model name="table">
      <static>true</static>
      <pose>1.0 1.0 0.4 0 0 0</pose>
      <link name="table_top">
        <visual name="visual">
          <geometry><box><size>1.0 0.6 0.05</size></box></geometry>
          <material><ambient>0.6 0.4 0.2</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 可调光灯模型（智能设备） -->
    <model name="smart_light">
      <static>true</static>
      <pose>0 0 2.3 0 0 0</pose>
      <link name="light_body">
        <visual name="visual">
          <geometry><sphere><radius>0.1</radius></sphere></geometry>
          <material>
            <ambient>1.0 1.0 0.8 1.0</ambient>
            <emissive>1.0 0.9 0.7 1.0</emissive>
          </material>
        </visual>
      </link>
    </model>

    <!-- 温度传感器模型 -->
    <model name="temp_sensor">
      <static>true</static>
      <pose>1.5 1.5 1.5 0 0 0</pose>
      <link name="sensor_body">
        <visual name="visual">
          <geometry><box><size>0.05 0.05 0.02</size></box></geometry>
          <material><ambient>0.8 0.8 0.8</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 窗帘模型 -->
    <model name="curtain">
      <static>true</static>
      <pose>0 -2.4 1.5 0 0 0</pose>
      <link name="curtain_body">
        <visual name="visual">
          <geometry><box><size>1.0 0.02 1.5</size></box></geometry>
          <material><ambient>0.7 0.8 0.9</ambient></material>
        </visual>
      </link>
    </model>

    <!-- 空调模型 -->
    <model name="ac_unit">
      <static>true</static>
      <pose>2.4 0 2.0 0 0 0</pose>
      <link name="ac_body">
        <visual name="visual">
          <geometry><box><size>0.4 0.15 0.3</size></box></geometry>
          <material><ambient>0.9 0.9 0.9</ambient></material>
        </visual>
      </link>
    </model>

  </world>
</sdf>
```

#### 步骤 1.4：创建仿真启动文件

**butler_gazebo/launch/sim_world.launch.py**:

```python
import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_gazebo = get_package_share_directory('butler_gazebo')
    pkg_description = get_package_share_directory('butler_description')

    world_file = os.path.join(pkg_gazebo, 'worlds', 'smart_home.sdf')
    urdf_file = os.path.join(pkg_description, 'urdf', 'moss.urdf.xacro')

    # 启动 Gazebo
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('ros_gz_sim'),
                         'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r {world_file}'}.items()
    )

    # URDF -> SDF 转换并生成到 Gazebo
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'moss',
            '-x', '0.0', '-y', '0.0', '-z', '2.45',  # 天花板位置
            '-file', urdf_file,
        ],
        output='screen'
    )

    # ROS-Gazebo 桥接 - 摄像头图像
    bridge_camera = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/moss/camera/image@sensor_msgs/msg/Image@gz.msgs.Image',
        ],
        output='screen'
    )

    # ROS-Gazebo 桥接 - 云台关节状态
    bridge_joints = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/world/smart_home/model/moss/joint/pan_joint/0/state@sensor_msgs/msg/JointState@gz.msgs.Model',
            '/world/smart_home/model/moss/joint/tilt_joint/0/state@sensor_msgs/msg/JointState@gz.msgs.Model',
            '/world/smart_home/model/moss/joint/roll_joint/0/state@sensor_msgs/msg/JointState@gz.msgs.Model',
        ],
        output='screen'
    )

    # 使用 TimerAction 确保 Gazebo 启动后再生成
    return LaunchDescription([
        gz_sim,
        TimerAction(
            period=3.0,
            actions=[spawn_robot]
        ),
        bridge_camera,
        bridge_joints,
    ])
```

#### 步骤 1.5：摄像头模拟节点

**butler_camera/butler_camera/sim_camera_node.py**:

```python
"""
仿真摄像头节点 - 从 Gazebo 话题读取图像并转发
作为硬件抽象层的 sim 版本实现
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import cv2
from cv_bridge import CvBridge


class SimCameraNode(Node):
    """仿真摄像头节点"""

    def __init__(self):
        super().__init__('sim_camera_node')

        # 声明参数
        self.declare_parameter('fps', 30)
        self.declare_parameter('resolution', [640, 480])
        self.declare_parameter('enable_display', False)

        self.bridge = CvBridge()

        # 订阅 Gazebo 摄像头话题
        self.subscription = self.create_subscription(
            Image,
            '/moss/camera/image',
            self.image_callback,
            10
        )

        # 发布处理后的图像
        self.publisher = self.create_publisher(
            Image,
            '/moss/camera/image_processed',
            10
        )

        # 发布检测结果
        self.detection_pub = self.create_publisher(
            Image,  # 画了边界框的图像
            '/moss/camera/detection_overlay',
            10
        )

        self.get_logger().info('仿真摄像头节点已启动')

    def image_callback(self, msg: Image):
        """接收 Gazebo 图像并转发"""
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

            # 添加时间戳水印
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(cv_image, timestamp, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # 发布处理后的图像
            processed_msg = self.bridge.cv2_to_imgmsg(cv_image, 'bgr8')
            processed_msg.header = msg.header
            self.publisher.publish(processed_msg)

        except Exception as e:
            self.get_logger().error(f'图像处理错误: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = SimCameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

#### 步骤 1.6：云台控制节点

**butler_gimbal/butler_gimbal/gimbal_controller.py**:

```python
"""
云台控制器 - 接收目标角度并控制 3 轴关节
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from butler_msgs.msg import GimbalCommand


class GimbalController(Node):
    """3 轴云台控制器"""

    def __init__(self):
        super().__init__('gimbal_controller')

        # 订阅云台控制指令
        self.command_sub = self.create_subscription(
            GimbalCommand,
            '/moss/gimbal/command',
            self.command_callback,
            10
        )

        # 仿真环境下发布到 Gazebo joint 位置控制器
        # 注意：Gazebo Fortress 使用 /world/.../joint/.../cmd_pos 话题
        self.pan_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/pan_joint/0/cmd_pos',
            10
        )
        self.tilt_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/tilt_joint/0/cmd_pos',
            10
        )
        self.roll_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/roll_joint/0/cmd_pos',
            10
        )

        self.get_logger().info('云台控制器已启动')

    def command_callback(self, msg: GimbalCommand):
        """接收控制指令并转发到各关节"""
        self.get_logger().debug(
            f'云台指令: pan={msg.pan:.2f}, tilt={msg.tilt:.2f}, roll={msg.roll:.2f}'
        )

        # 发布各轴目标位置
        for pub, value in [
            (self.pan_pub, msg.pan),
            (self.tilt_pub, msg.tilt),
            (self.roll_pub, msg.roll)
        ]:
            cmd = Float64MultiArray()
            cmd.data = [float(value)]
            pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = GimbalController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

#### 步骤 1.7：智能设备模拟节点

**butler_gazebo/butler_gazebo/smart_devices_sim.py**:

```python
"""
智能设备模拟器 - 在 Gazebo 仿真中模拟智能家居设备状态
发布传感器数据，接收控制指令
"""

import json
import random
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from butler_msgs.msg import DeviceState
from builtin_interfaces.msg import Time


class SmartDevicesSim(Node):
    """模拟智能家居设备"""

    def __init__(self):
        super().__init__('smart_devices_sim')

        # 设备状态存储
        self.devices = {
            'light_1': {'type': 'light', 'state': {'on': False, 'brightness': 100, 'color_temp': 4000}},
            'thermostat_1': {'type': 'thermostat', 'state': {'temperature': 25.0, 'mode': 'cool', 'target': 24.0}},
            'curtain_1': {'type': 'curtain', 'state': {'position': 0}},
            'temp_sensor_1': {'type': 'sensor', 'state': {'temperature': 25.5, 'humidity': 60}},
        }

        # 设备状态发布器
        self.state_pub = self.create_publisher(DeviceState, '/moss/devices/state', 10)

        # 设备控制订阅器
        self.command_sub = self.create_subscription(
            String,
            '/moss/devices/command',
            self.command_callback,
            10
        )

        # 定时发布状态（每秒）
        self.timer = self.create_timer(1.0, self.publish_states)

        self.get_logger().info('智能设备模拟器已启动')
        self.get_logger().info(f'模拟设备: {list(self.devices.keys())}')

    def publish_states(self):
        """定时发布所有设备状态"""
        # 模拟温度传感器波动
        temp = self.devices['temp_sensor_1']['state']['temperature']
        self.devices['temp_sensor_1']['state']['temperature'] = temp + random.uniform(-0.1, 0.1)

        now = self.get_clock().now().to_msg()
        for device_id, info in self.devices.items():
            msg = DeviceState()
            msg.device_id = device_id
            msg.device_type = info['type']
            msg.state = json.dumps(info['state'])
            msg.timestamp = now
            self.state_pub.publish(msg)

    def command_callback(self, msg: String):
        """接收设备控制指令"""
        try:
            command = json.loads(msg.data)
            device_id = command.get('device_id')
            action = command.get('action')
            params = command.get('params', {})

            if device_id in self.devices:
                old_state = self.devices[device_id]['state'].copy()
                self.devices[device_id]['state'].update(params)
                self.get_logger().info(
                    f'设备 {device_id} 状态变更: {old_state} -> {self.devices[device_id]["state"]}'
                )
            else:
                self.get_logger().warn(f'未知设备: {device_id}')
        except (json.JSONDecodeError, KeyError) as e:
            self.get_logger().error(f'指令解析错误: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = SmartDevicesSim()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

### 5.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-1.1 | Gazebo 正常启动并加载房间世界 | `gz sim smart_home.sdf` 看到 3D 房间 |
| AC-1.2 | 机器人模型可见且位置正确 | Gazebo 中看到天花板上的黑色圆柱体 |
| AC-1.3 | 摄像头话题有数据 | `ros2 topic hz /moss/camera/image` 显示约 30Hz |
| AC-1.4 | 云台可转动 | 发布 GimbalCommand 后，Gazebo 中摄像头角度改变 |
| AC-1.5 | 智能设备状态话题发布 | `ros2 topic echo /moss/devices/state` 有数据输出 |
| AC-1.6 | 智能设备可控制 | 发布控制指令后，设备状态相应改变 |

### 5.4 测试方案

**集成测试**（`butler_gazebo/test/test_simulation.py`）:

```python
"""
Gazebo 仿真集成测试
需要 Gazebo 运行中执行
"""

import pytest
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from butler_msgs.msg import GimbalCommand, DeviceState
import time


class TestSimulation(Node):
    """仿真测试辅助节点"""

    def __init__(self):
        super().__init__('test_simulation')
        self.received_images = []
        self.received_states = []

        self.image_sub = self.create_subscription(
            Image, '/moss/camera/image', self._on_image, 10
        )
        self.state_sub = self.create_subscription(
            DeviceState, '/moss/devices/state', self._on_state, 10
        )
        self.gimbal_pub = self.create_publisher(
            GimbalCommand, '/moss/gimbal/command', 10
        )

    def _on_image(self, msg):
        self.received_images.append(msg)

    def _on_state(self, msg):
        self.received_states.append(msg)


@pytest.fixture(scope="module")
def test_node():
    rclpy.init()
    node = TestSimulation()
    yield node
    node.destroy_node()
    rclpy.shutdown()


def test_camera_image_received(test_node):
    """验证摄像头图像可达"""
    time.sleep(2)
    rclpy.spin_once(test_node, timeout_sec=1.0)
    assert len(test_node.received_images) > 0, "未收到摄像头图像"


def test_device_state_received(test_node):
    """验证设备状态可达"""
    time.sleep(2)
    rclpy.spin_once(test_node, timeout_sec=1.0)
    assert len(test_node.received_states) > 0, "未收到设备状态"


def test_gimbal_command_sent(test_node):
    """验证云台指令可发送"""
    cmd = GimbalCommand()
    cmd.pan = 0.5
    cmd.tilt = 0.3
    cmd.roll = 0.0
    test_node.gimbal_pub.publish(cmd)
    time.sleep(0.5)
    # 验证发布成功（无异常即为通过）
```

**仿真验收操作流程**:

> **前提**：每个终端都需要先 `source install/setup.bash`。Gazebo gz-transport 需设置 `GZ_IP=127.0.0.1` 避免多播发现失败。

```bash
# === 终端 1：启动 Gazebo 仿真（GUI 模式）===
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash
GZ_IP=127.0.0.1 gz sim -r src/butler_gazebo/worlds/smart_home.sdf

# === 终端 2：生成 MOSS 机器人（等 Gazebo 启动后）===
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash
xacro src/butler_description/urdf/moss.urdf.xacro > /tmp/moss.urdf
GZ_IP=127.0.0.1 ros2 run ros_gz_sim create -name moss -x 0 -y 0 -z 2.45 -file /tmp/moss.urdf

# === 终端 3：启动智能设备模拟器 ===
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash
python3 -m butler_gazebo.smart_devices_sim

# === 终端 4：验证 ===
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash

# 查看所有话题
ros2 topic list | grep moss

# 验证设备状态
ros2 topic echo /moss/devices/state --once

# 发布云台控制指令（话题存在，无 subscriber 时会等待，可 Ctrl+C）
ros2 topic pub --once /moss/gimbal/command butler_msgs/msg/GimbalCommand \
  "{pan: 0.5, tilt: 0.3, roll: 0.0}"
```

**验收结果**:

| 话题 | 预期 | 状态 |
|------|------|------|
| `/moss/devices/state` | 每秒 4 条 DeviceState 消息 | 通过 |
| `/moss/devices/command` | 话题存在，等待订阅 | 通过 |
| `/moss/gimbal/command` | 话题存在，可 pub | 通过 |
| `/moss/camera/image_raw` | 需 Sensors + OGRE2 渲染 | 待解决（AMD GPU） |

---

## 6. 阶段 2：基础感知能力

> **目标**：实现音频采集/播放、语音识别（ASR）、文本转语音（TTS）、摄像头视频流通过 WebRTC 传输

### 6.1 目标与产出

| 产物 | 描述 |
|------|------|
| 音频采集节点 | 从本机麦克风录音，发布到 ROS2 话题 |
| 音频播放节点 | 订阅 ROS2 话题，通过喇叭播放 |
| 语音识别客户端 | 调用 Windows 5070Ti 上的 Whisper 服务 |
| TTS 客户端 | 调用 Windows 上的 Piper TTS 服务 |
| WebRTC 视频流 | 摄像头画面低延迟传输到浏览器 |
| 唤醒词检测 | "moss" 检测 + 功能开关 |

### 6.2 详细步骤

#### 步骤 6.1：创建音频采集节点

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src
ros2 pkg create butler_audio \
  --build-type ament_python \
  --dependencies rclpy std_msgs butler_msgs \
  --license Apache-2.0
```

**butler_audio/butler_audio/mic_node.py**:

```python
"""
麦克风采集节点 - 旁路模拟，直接读取本机麦克风
"""

import rclpy
from rclpy.node import Node
import numpy as np
import sounddevice as sd
from butler_msgs.msg import VoiceCommand
import threading
import queue


class MicNode(Node):
    """麦克风音频采集节点"""

    def __init__(self):
        super().__init__('mic_node')

        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('channels', 1)
        self.declare_parameter('device', None)  # None = 默认设备

        self.sample_rate = self.get_parameter('sample_rate').value
        self.channels = self.get_parameter('channels').value
        self.device = self.get_parameter('device').value

        # 音频帧发布器
        self.audio_pub = self.create_publisher(
            VoiceCommand,
            '/moss/audio/raw',
            10
        )

        # 音频队列（生产-消费模式）
        self.audio_queue = queue.Queue(maxsize=100)
        self._running = False
        self._stream = None

        # 启动采集线程
        self.start_listening()

        self.get_logger().info(f'麦克风节点已启动 (采样率: {self.sample_rate}Hz)')

    def start_listening(self):
        """开始采集音频"""
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            device=self.device,
            callback=self._audio_callback,
            blocksize=1024
        )
        self._stream.start()

        # 启动处理线程
        self._process_thread = threading.Thread(target=self._process_audio, daemon=True)
        self._process_thread.start()

    def _audio_callback(self, indata, frames, time, status):
        """音频回调函数"""
        if status:
            self.get_logger().warn(f'音频采集状态: {status}')
        if self._running:
            try:
                self.audio_queue.put_nowait(indata.copy())
            except queue.Full:
                pass  # 丢弃旧帧

    def _process_audio(self):
        """处理音频数据并发布"""
        while self._running:
            try:
                audio_data = self.audio_queue.get(timeout=0.1)
                msg = VoiceCommand()
                msg.text = ''  # 原始音频不含文本
                msg.confidence = 0.0
                msg.is_final = False
                # 可以后续添加音频数据字段
                self.audio_pub.publish(msg)
            except queue.Empty:
                continue

    def destroy_node(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MicNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

**butler_audio/butler_audio/speaker_node.py**:

```python
"""
喇叭播放节点
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import sounddevice as sd
import numpy as np
import io
import wave
import threading
import queue


class SpeakerNode(Node):
    """TTS 音频播放节点"""

    def __init__(self):
        super().__init__('speaker_node')

        self.declare_parameter('sample_rate', 22050)
        self.sample_rate = self.get_parameter('sample_rate').value

        # 订阅 TTS 输出文本
        self.tts_sub = self.create_subscription(
            String,
            '/moss/audio/tts_output',
            self.tts_callback,
            10
        )

        self.play_queue = queue.Queue()

        self.get_logger().info('喇叭播放节点已启动')

    def tts_callback(self, msg: String):
        """接收 TTS 文本并播放"""
        self.get_logger().info(f'TTS 输出: {msg.data}')
        # 实际上 TTS 节点会将文本转换为音频
        # 这里简化为打印
        # 真实实现时会通过 piper 或其他引擎生成音频文件然后播放
        self.play_queue.put(msg.data)

    def play_audio(self, audio_data: np.ndarray):
        """播放音频数据"""
        sd.play(audio_data, self.sample_rate)
        sd.wait()


def main(args=None):
    rclpy.init(args=args)
    node = SpeakerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

#### 步骤 6.2：创建语音服务客户端

```bash
ros2 pkg create butler_voice \
  --build-type ament_python \
  --dependencies rclpy std_msgs butler_msgs \
  --license Apache-2.0
```

**butler_voice/butler_voice/asr_client.py**:

```python
"""
语音识别 (ASR) 客户端
连接 Windows 上的 Whisper 服务
支持音频缓冲和批量发送
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from butler_msgs.msg import VoiceCommand
import aiohttp
import asyncio
import threading
import queue
import time
import base64
import struct
import numpy as np
from collections import deque


class ASRClient(Node):
    """语音识别客户端"""

    def __init__(self):
        super().__init__('asr_client')

        # 参数声明
        self.declare_parameter('asr_endpoint', 'http://192.168.2.xxx:8001/transcribe')
        self.declare_parameter('language', 'zh')
        self.declare_parameter('model', 'base')
        self.declare_parameter('buffer_duration', 2.0)  # 音频缓冲时长（秒）
        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('silence_threshold', 500)  # 静音阈值
        self.declare_parameter('max_retries', 3)  # 最大重试次数

        # 获取参数
        self.endpoint = self.get_parameter('asr_endpoint').value
        self.language = self.get_parameter('language').value
        self.model = self.get_parameter('model').value
        self.buffer_duration = self.get_parameter('buffer_duration').value
        self.sample_rate = self.get_parameter('sample_rate').value
        self.silence_threshold = self.get_parameter('silence_threshold').value
        self.max_retries = self.get_parameter('max_retries').value

        # 音频缓冲区
        self.audio_buffer = deque(maxlen=int(self.sample_rate * self.buffer_duration))
        self.is_speaking = False
        self.silence_count = 0
        self.silence_frames_required = int(self.sample_rate * 0.5)  # 0.5秒静音判定

        # 输入：原始音频
        self.audio_sub = self.create_subscription(
            VoiceCommand,
            '/moss/audio/raw',
            self.audio_callback,
            10
        )

        # 输出：识别文本
        self.text_pub = self.create_publisher(
            String,
            '/moss/voice/recognized',
            10
        )

        # 异步事件循环
        self.async_loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # 识别结果队列
        self.result_queue = queue.Queue()

        # 启动结果发布定时器
        self.create_timer(0.1, self._publish_results)

        self.get_logger().info(f'ASR 客户端已启动 (端点: {self.endpoint})')
        self.get_logger().info(f'缓冲时长: {self.buffer_duration}s, 语言: {self.language}')

    def _run_loop(self):
        """运行异步事件循环"""
        asyncio.set_event_loop(self.async_loop)
        self.async_loop.run_forever()

    def audio_callback(self, msg: VoiceCommand):
        """
        接收音频数据

        Args:
            msg: VoiceCommand消息，包含音频数据
        """
        # 如果消息包含音频数据
        if msg.audio_data:
            audio_array = np.frombuffer(msg.audio_data, dtype=np.int16)
        else:
            # 如果没有音频数据，跳过（实际应用中应该从AudioData话题获取）
            return

        # 计算音频能量
        energy = np.abs(audio_array).mean()

        # 语音活动检测 (VAD)
        if energy > self.silence_threshold:
            self.is_speaking = True
            self.silence_count = 0
            self.audio_buffer.extend(audio_array.tolist())
        elif self.is_speaking:
            self.silence_count += len(audio_array)
            self.audio_buffer.extend(audio_array.tolist())

            # 静音超过阈值，认为语音结束
            if self.silence_count >= self.silence_frames_required:
                self._process_buffer()

    def _process_buffer(self):
        """处理音频缓冲区，发送到ASR服务"""
        if len(self.audio_buffer) < self.sample_rate * 0.5:
            # 音频太短，丢弃
            self.audio_buffer.clear()
            self.is_speaking = False
            self.silence_count = 0
            return

        # 获取缓冲区音频
        audio_data = list(self.audio_buffer)
        self.audio_buffer.clear()
        self.is_speaking = False
        self.silence_count = 0

        # 转换为int16数组
        audio_array = np.array(audio_data, dtype=np.int16)

        # 异步发送到ASR服务
        asyncio.run_coroutine_threadsafe(
            self._transcribe_with_retry(audio_array),
            self.async_loop
        )

    async def _transcribe_with_retry(self, audio_array: np.ndarray):
        """
        带重试的语音识别

        Args:
            audio_array: 音频数据数组
        """
        for attempt in range(self.max_retries):
            try:
                text = await self.transcribe(audio_array)
                if text and text.strip():
                    self.result_queue.put(text.strip())
                    return
            except Exception as e:
                self.get_logger().warn(f'ASR请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}')
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避

        self.get_logger().error('ASR请求最终失败')

    async def transcribe(self, audio_array: np.ndarray) -> str:
        """
        调用远程 Whisper API

        Args:
            audio_array: int16音频数据

        Returns:
            识别的文本
        """
        # 将音频数据编码为base64
        audio_bytes = audio_array.tobytes()
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        # 构建请求数据
        request_data = {
            'audio': audio_base64,
            'language': self.language,
            'model': self.model,
            'sample_rate': self.sample_rate,
            'encoding': 'int16'
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get('text', '')
                else:
                    error_text = await resp.text()
                    raise Exception(f'ASR服务返回错误 {resp.status}: {error_text}')

    def _publish_results(self):
        """定时发布识别结果"""
        while not self.result_queue.empty():
            try:
                text = self.result_queue.get_nowait()
                msg = String()
                msg.data = text
                self.text_pub.publish(msg)
                self.get_logger().info(f'识别结果: {text}')
            except queue.Empty:
                break

    def destroy_node(self):
        """清理资源"""
        self.async_loop.call_soon_threadsafe(self.async_loop.stop)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ASRClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

**butler_voice/butler_voice/tts_client.py**:

```python
"""
文本转语音 (TTS) 客户端
连接 Windows 上的 TTS 服务
支持音频接收、格式转换和播放
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from butler_msgs.msg import AudioData
import aiohttp
import asyncio
import threading
import queue
import base64
import numpy as np
import sounddevice as sd
import io
import wave
from builtin_interfaces.msg import Time


class TTSClient(Node):
    """TTS 客户端"""

    def __init__(self):
        super().__init__('tts_client')

        # 参数声明
        self.declare_parameter('tts_endpoint', 'http://192.168.2.xxx:8002/synthesize')
        self.declare_parameter('voice', 'zh_CN')
        self.declare_parameter('sample_rate', 22050)
        self.declare_parameter('max_retries', 3)
        self.declare_parameter('auto_play', True)  # 自动播放合成的音频

        # 获取参数
        self.endpoint = self.get_parameter('tts_endpoint').value
        self.voice = self.get_parameter('voice').value
        self.sample_rate = self.get_parameter('sample_rate').value
        self.max_retries = self.get_parameter('max_retries').value
        self.auto_play = self.get_parameter('auto_play').value

        # 输入：合成文本
        self.text_sub = self.create_subscription(
            String,
            '/moss/voice/speak',
            self.text_callback,
            10
        )

        # 输出：TTS 文本（用于日志和显示）
        self.tts_pub = self.create_publisher(
            String,
            '/moss/audio/tts_output',
            10
        )

        # 输出：合成的音频数据
        self.audio_pub = self.create_publisher(
            AudioData,
            '/moss/audio/tts_audio',
            10
        )

        # 异步事件循环
        self.async_loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # 音频播放队列
        self.play_queue = queue.Queue()

        # 启动播放线程
        self._play_thread = threading.Thread(target=self._play_audio_loop, daemon=True)
        self._play_thread.start()

        self.get_logger().info(f'TTS 客户端已启动 (端点: {self.endpoint})')
        self.get_logger().info(f'语音: {self.voice}, 采样率: {self.sample_rate}Hz')

    def _run_loop(self):
        """运行异步事件循环"""
        asyncio.set_event_loop(self.async_loop)
        self.async_loop.run_forever()

    def text_callback(self, msg: String):
        """
        接收文本并调用 TTS 服务

        Args:
            msg: 包含待合成文本的消息
        """
        text = msg.data
        if not text or not text.strip():
            return

        self.get_logger().info(f'TTS 请求: {text}')

        # 发布TTS输出文本
        tts_msg = String()
        tts_msg.data = text
        self.tts_pub.publish(tts_msg)

        # 异步调用TTS服务
        asyncio.run_coroutine_threadsafe(
            self._synthesize_with_retry(text),
            self.async_loop
        )

    async def _synthesize_with_retry(self, text: str):
        """
        带重试的语音合成

        Args:
            text: 待合成的文本
        """
        for attempt in range(self.max_retries):
            try:
                audio_data = await self.synthesize(text)
                if audio_data is not None:
                    # 添加到播放队列
                    if self.auto_play:
                        self.play_queue.put(audio_data)

                    # 发布音频数据到ROS2话题
                    self._publish_audio(audio_data)
                    return
            except Exception as e:
                self.get_logger().warn(f'TTS请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}')
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避

        self.get_logger().error(f'TTS请求最终失败: {text}')

    async def synthesize(self, text: str) -> np.ndarray:
        """
        调用远程 TTS API

        Args:
            text: 待合成的文本

        Returns:
            int16音频数据数组
        """
        request_data = {
            'text': text,
            'voice': self.voice,
            'sample_rate': self.sample_rate,
            'format': 'wav'  # 请求WAV格式返回
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()

                    # 解析返回的音频数据
                    if 'audio' in result:
                        # Base64编码的音频数据
                        audio_base64 = result['audio']
                        audio_bytes = base64.b64decode(audio_base64)
                        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                        return audio_array
                    elif 'audio_url' in result:
                        # 音频文件URL，需要下载
                        audio_url = result['audio_url']
                        return await self._download_audio(audio_url)
                    else:
                        raise Exception('TTS服务返回格式错误：缺少audio或audio_url字段')
                else:
                    error_text = await resp.text()
                    raise Exception(f'TTS服务返回错误 {resp.status}: {error_text}')

    async def _download_audio(self, url: str) -> np.ndarray:
        """
        下载音频文件

        Args:
            url: 音频文件URL

        Returns:
            int16音频数据数组
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    audio_bytes = await resp.read()

                    # 尝试解析WAV格式
                    try:
                        with wave.open(io.BytesIO(audio_bytes), 'rb') as wav_file:
                            sample_width = wav_file.getsampwidth()
                            sample_rate = wav_file.getframerate()
                            n_frames = wav_file.getnframes()
                            audio_data = wav_file.readframes(n_frames)

                            # 转换为int16
                            if sample_width == 2:
                                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                            elif sample_width == 4:
                                audio_array = np.frombuffer(audio_data, dtype=np.int32)
                                audio_array = (audio_array / 65536).astype(np.int16)
                            else:
                                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                            return audio_array
                    except wave.Error:
                        # 如果不是WAV格式，尝试直接解析为原始PCM
                        return np.frombuffer(audio_bytes, dtype=np.int16)
                else:
                    raise Exception(f'下载音频失败: {resp.status}')

    def _publish_audio(self, audio_array: np.ndarray):
        """
        发布音频数据到ROS2话题

        Args:
            audio_array: int16音频数据
        """
        msg = AudioData()
        msg.timestamp = self.get_clock().now().to_msg()
        msg.sample_rate = self.sample_rate
        msg.channels = 1
        msg.sample_width = 16
        msg.data = audio_array.tobytes()
        self.audio_pub.publish(msg)

    def _play_audio_loop(self):
        """音频播放线程"""
        while True:
            try:
                audio_data = self.play_queue.get(timeout=1.0)
                if audio_data is not None and len(audio_data) > 0:
                    # 播放音频
                    sd.play(audio_data, self.sample_rate)
                    sd.wait()
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f'音频播放错误: {e}')

    def destroy_node(self):
        """清理资源"""
        self.async_loop.call_soon_threadsafe(self.async_loop.stop)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TTSClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

### 6.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-2.1 | 麦克风采集节点运行正常 | 查看日志确认 sounddevice 设备列表 |
| AC-2.2 | 喇叭节点可订阅 TTS 输出 | `ros2 topic pub /moss/voice/speak std_msgs/String "data: '测试'"` 后日志有输出 |
| AC-2.3 | ASR 客户端可连接 Windows | 手动调用 `/transcribe` 端点验证 |
| AC-2.4 | TTS 客户端可生成语音 | 发布文本后 Windows 端有响应 |
| AC-2.5 | 摄像头图像持续发布 | `ros2 topic hz /moss/camera/image` |

### 6.4 测试方案

```bash
# 音频采集测试
ros2 run butler_audio mic_node
# 观察日志，确认设备列表

# 喇叭测试
# 终端 1：启动喇叭节点
ros2 run butler_audio speaker_node
# 终端 2：发布测试文本
ros2 topic pub --once /moss/voice/speak std_msgs/String "data: '你好，我是MOSS'"

# 语音识别测试（需要 Windows 端服务运行）
# 终端 1：启动 ASR 客户端
ros2 run butler_voice asr_client
# 终端 2：启动麦克风节点
ros2 run butler_audio mic_node
```

---

## 7. 阶段 3：AI 大脑

> **目标**：集成大模型对话、唤醒词检测、BehaviorTree 行为逻辑

### 7.1 目标与产出

| 产物 | 描述 |
|------|------|
| OpenAI 兼容 API 客户端 | 可切换云端/本地模型 |
| 唤醒词检测节点 | "moss" 检测 + 功能开关 |
| 对话管理节点 | 多轮对话上下文 |
| BehaviorTree 定义 | 机器人行为树 XML 配置 |
| 行为树执行节点 | 加载并运行行为树 |

### 7.2 详细步骤

#### 步骤 7.1：创建 AI 客户端包

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src

ros2 pkg create butler_ai \
  --build-type ament_python \
  --dependencies rclpy std_msgs butler_msgs \
  --license Apache-2.0

mkdir -p butler_ai/butler_ai
```

**butler_ai/butler_ai/llm_client.py**:

```python
"""
大模型客户端 - 支持 OpenAI 兼容 API
可切换云端 API 和本地 Ollama
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from openai import OpenAI
import json


class LLMClient(Node):
    """大模型对话客户端"""

    def __init__(self):
        super().__init__('llm_client')

        # 从配置读取参数
        self.declare_parameter('api_base', 'https://api.openai.com/v1')
        self.declare_parameter('api_key', '')
        self.declare_parameter('model', 'gpt-4o-mini')
        self.declare_parameter('max_tokens', 2048)
        self.declare_parameter('temperature', 0.7)
        self.declare_parameter('system_prompt',
            '你是 MOSS，一个智能管家机器人。你的职责是协助管理智能家居、'
            '回答用户问题、提供信息。请用中文回答，语气友好专业。'
            '你可以控制灯光、空调、窗帘等智能设备。')

        self.client = OpenAI(
            base_url=self.get_parameter('api_base').value,
            api_key=self.get_parameter('api_key').value or 'sk-no-key'
        )

        # 对话上下文（最多保留 20 轮）
        self.conversation_history = [
            {'role': 'system', 'content': self.get_parameter('system_prompt').value}
        ]
        self.max_history = 20

        # 输入：用户语音识别结果
        self.speech_sub = self.create_subscription(
            String,
            '/moss/voice/recognized',
            self.speech_callback,
            10
        )

        # 输入：用户文本输入（Web Dashboard）
        self.text_sub = self.create_subscription(
            String,
            '/moss/ai/text_input',
            self.text_callback,
            10
        )

        # 输出：AI 回复
        self.reply_pub = self.create_publisher(
            String,
            '/moss/ai/reply',
            10
        )

        # 输出：发送给 TTS 的回复
        self.speak_pub = self.create_publisher(
            String,
            '/moss/voice/speak',
            10
        )

        # 输出：智能家居控制意图
        self.intent_pub = self.create_publisher(
            String,
            '/moss/ai/intent',
            10
        )

        self.get_logger().info('LLM 客户端已启动')
        self.get_logger().info(f'模型: {self.get_parameter("model").value}')
        self.get_logger().info(f'API: {self.get_parameter("api_base").value}')

    def speech_callback(self, msg: String):
        """处理语音识别结果"""
        if msg.data.strip():
            self.get_logger().info(f'用户: {msg.data}')
            self.chat(msg.data)

    def text_callback(self, msg: String):
        """处理文本输入"""
        if msg.data.strip():
            self.get_logger().info(f'用户 (文本): {msg.data}')
            self.chat(msg.data)

    def chat(self, user_input: str):
        """与 LLM 对话"""
        # 添加用户消息到历史
        self.conversation_history.append(
            {'role': 'user', 'content': user_input}
        )

        # 限制历史长度
        if len(self.conversation_history) > self.max_history + 1:
            # 保留系统提示词和最近的消息
            self.conversation_history = [
                self.conversation_history[0]
            ] + self.conversation_history[-(self.max_history):]

        try:
            response = self.client.chat.completions.create(
                model=self.get_parameter('model').value,
                messages=self.conversation_history,
                max_tokens=self.get_parameter('max_tokens').value,
                temperature=self.get_parameter('temperature').value
            )

            reply = response.choices[0].message.content

            # 添加到历史
            self.conversation_history.append(
                {'role': 'assistant', 'content': reply}
            )

            # 发布回复
            reply_msg = String()
            reply_msg.data = reply
            self.reply_pub.publish(reply_msg)
            self.speak_pub.publish(reply_msg)
            self.get_logger().info(f'MOSS: {reply}')

        except Exception as e:
            self.get_logger().error(f'LLM 调用失败: {e}')
            error_msg = String()
            error_msg.data = f'抱歉，我暂时无法思考。错误: {str(e)}'
            self.reply_pub.publish(error_msg)

    def clear_history(self):
        """清除对话历史（保留系统提示词）"""
        self.conversation_history = [
            self.conversation_history[0]
        ]
        self.get_logger().info('对话历史已清除')


def main(args=None):
    rclpy.init(args=args)
    node = LLMClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

#### 步骤 7.2：唤醒词检测节点

**butler_voice/butler_voice/wake_word_detector.py**:

```python
"""
唤醒词检测节点
检测 "moss" 以激活语音交互
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from butler_bringup.config_manager import config
import json


class WakeWordDetector(Node):
    """唤醒词检测节点"""

    def __init__(self):
        super().__init__('wake_word_detector')

        # 检查功能开关
        if not config.is_feature_enabled('wake_word'):
            self.get_logger().info('唤醒词功能已关闭（features.yaml）')
            # 直接设为始终唤醒状态
            self.set_always_active()
            return

        self.wake_word = 'moss'

        # 输入：语音识别结果
        self.speech_sub = self.create_subscription(
            String,
            '/moss/voice/recognized',
            self.speech_callback,
            10
        )

        # 输出：唤醒状态
        self.wake_pub = self.create_publisher(
            Bool,
            '/moss/wake_word/active',
            10
        )

        self.is_active = False
        self.get_logger().info(f'唤醒词检测已启动 (唤醒词: "{self.wake_word}")')

    def set_always_active(self):
        """当唤醒词关闭时，始终激活"""
        self.create_timer(1.0, lambda: None)  # 让节点保持运行

    def speech_callback(self, msg: String):
        """检测唤醒词"""
        text = msg.data.strip().lower()
        if self.wake_word in text and not self.is_active:
            self.is_active = True
            active_msg = Bool()
            active_msg.data = True
            self.wake_pub.publish(active_msg)
            self.get_logger().info(f'唤醒词检测到: "{text}"')
            # 5 秒后自动休眠
            self.create_timer(5.0, self._deactivate)

    def _deactivate(self):
        self.is_active = False
        active_msg = Bool()
        active_msg.data = False
        self.wake_pub.publish(active_msg)
        self.get_logger().debug('唤醒状态超时，进入休眠')


def main(args=None):
    rclpy.init(args=args)
    node = WakeWordDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

#### 步骤 7.3：行为树定义

**参考行为树 XML**（`butler_behavior/trees/main_behavior.xml`）:

```xml
<?xml version="1.0"?>
<root main_tree_to_execute="MainBehavior">
  <!-- MOSS 主行为树 -->

  <BehaviorTree ID="MainBehavior">
    <Sequence name="MainLoop">

      <!-- 检查是否唤醒 -->
      <Condition ID="IsWakeWordActive" name="唤醒检查"/>

      <!-- 等待用户语音或文本输入 -->
      <ReactiveSequence name="ProcessInput">

        <!-- 收到语音指令 -->
        <Fallback name="InputSource">
          <Condition ID="HasVoiceCommand" name="语音指令?"/>
          <Condition ID="HasTextCommand" name="文本指令?"/>
        </Fallback>

        <!-- 解析用户意图 -->
        <Action ID="ParseIntent" name="意图解析"/>

        <!-- 根据意图执行 -->
        <Fallback name="IntentDispatch">
          <!-- 智能家居控制 -->
          <Sequence name="SmartHome">
            <Condition ID="IsSmartHomeIntent" name="家居意图?"/>
            <Action ID="ControlSmartDevice" name="控制设备"/>
            <Action ID="LogOperation" name="记录操作"/>
          </Sequence>

          <!-- 大模型对话 -->
          <Sequence name="Chat">
            <Condition ID="IsChatIntent" name="对话意图?"/>
            <Action ID="ChatWithLLM" name="大模型对话"/>
            <Action ID="SpeakResponse" name="语音回复"/>
          </Sequence>

          <!-- 云台控制 -->
          <Sequence name="Camera">
            <Condition ID="IsCameraIntent" name="摄像头意图?"/>
            <Action ID="ControlGimbal" name="控制云台"/>
          </Sequence>

          <!-- 默认回复 -->
          <Action ID="DefaultReply" name="默认回复"/>
        </Fallback>

      </ReactiveSequence>

    </Sequence>
  </BehaviorTree>

  <!-- 行为树节点实现（在 Python 中注册） -->
</root>
```

### 7.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-3.1 | LLM 客户端可调用 API | 发布文本后获得有效回复 |
| AC-3.2 | 对话上下文保持 | 连续 2 轮对话，AI 记住前文 |
| AC-3.3 | 唤醒词触发 | 说 "moss" 后 `/moss/wake_word/active` 变为 True |
| AC-3.4 | 唤醒词可关闭 | 通过 features.yaml 关闭后始终激活 |
| AC-3.5 | 行为树可加载 | XML 文件被正确解析 |

### 7.4 测试方案

```bash
# LLM 客户端测试
# 终端 1：启动 LLM 客户端（确保 API key 在环境变量中）
export OPENAI_API_KEY="sk-your-key"
ros2 run butler_ai llm_client

# 终端 2：发送测试文本
ros2 topic pub --once /moss/ai/text_input std_msgs/String "data: '你好MOSS'"

# 终端 3：监听回复
ros2 topic echo /moss/ai/reply

# 多轮对话测试
ros2 topic pub --once /moss/ai/text_input std_msgs/String "data: '我叫小明'"
# 等待回复后
ros2 topic pub --once /moss/ai/text_input std_msgs/String "data: '我叫什么名字'"
# 验证 AI 是否记住名字
```

---

## 8. 阶段 4：智能家居集成

> **目标**：集成 Home Assistant REST API，实现安全四层防护，操作日志记录

### 8.1 目标与产出

| 产物 | 描述 |
|------|------|
| HA REST 客户端 | 调用 Home Assistant API 控制设备 |
| 设备状态同步 | 定期拉取或订阅 HA 设备状态变化 |
| 安全模块 | 四层安全实现 |
| 操作日志系统 | 记录所有智能家居操作，支持告警 |
| 安全配置 | 令牌管理、权限分级配置 |

### 8.2 详细步骤

#### 步骤 8.1：创建 HA 集成包

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws/src

ros2 pkg create butler_ha \
  --build-type ament_python \
  --dependencies rclpy std_msgs butler_msgs \
  --license Apache-2.0
```

**butler_ha/butler_ha/ha_client.py**:

```python
"""
Home Assistant REST API 客户端
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from butler_msgs.msg import DeviceState
import aiohttp
import asyncio
import threading
from butler_bringup.config_manager import config


class HAClient(Node):
    """Home Assistant 集成客户端"""

    def __init__(self):
        super().__init__('ha_client')

        # 从配置加载 HA 连接信息
        self.base_url = config.get('nodes.ha.base_url', 'http://localhost:8123')
        self.token = config.get('nodes.ha.token', '')
        self.api_timeout = config.get('network.api_timeout', 30)

        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

        # 设备状态缓存
        self.device_states = {}

        # ROS2 接口
        self.device_state_pub = self.create_publisher(
            DeviceState,
            '/moss/devices/state',
            10
        )

        self.control_sub = self.create_subscription(
            String,
            '/moss/devices/command',
            self.control_callback,
            10
        )

        # 异步事件循环（在独立线程中运行）
        self.async_loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

        # 定期同步状态（5 秒）
        self.timer = self.create_timer(5.0, self.sync_timer_callback)

        self.get_logger().info(f'HA 客户端已启动 (URL: {self.base_url})')

    def _run_async_loop(self):
        asyncio.set_event_loop(self.async_loop)
        self.async_loop.run_forever()

    def sync_timer_callback(self):
        """定时同步状态"""
        asyncio.run_coroutine_threadsafe(
            self.fetch_device_states(), self.async_loop
        )

    async def fetch_device_states(self):
        """获取 HA 中所有设备状态"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    f'{self.base_url}/api/states',
                    timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        for entity in states:
                            entity_id = entity.get('entity_id', '')
                            state = entity.get('state', '')
                            self.device_states[entity_id] = state
        except Exception as e:
            self.get_logger().warn(f'获取 HA 状态失败: {e}')

    def control_callback(self, msg: String):
        """接收设备控制指令"""
        try:
            command = json.loads(msg.data)
            entity_id = command.get('entity_id')
            service = command.get('service')  # e.g., 'light/turn_on'
            service_data = command.get('data', {})

            if entity_id and service:
                asyncio.run_coroutine_threadsafe(
                    self.call_service(service, entity_id, service_data),
                    self.async_loop
                )
        except json.JSONDecodeError as e:
            self.get_logger().error(f'控制指令解析失败: {e}')

    async def call_service(self, service: str, entity_id: str, data: dict = None):
        """调用 HA 服务"""
        domain, service_name = service.split('/')
        url = f'{self.base_url}/api/services/{domain}/{service_name}'

        payload = {'entity_id': entity_id}
        if data:
            payload.update(data)

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as resp:
                    if resp.status == 200:
                        self.get_logger().info(f'HA 服务调用成功: {service} -> {entity_id}')
                    else:
                        self.get_logger().error(
                            f'HA 服务调用失败: {resp.status} {await resp.text()}'
                        )
        except Exception as e:
            self.get_logger().error(f'HA 调用异常: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = HAClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

#### 步骤 8.2：安全模块

```bash
ros2 pkg create butler_security \
  --build-type ament_python \
  --dependencies rclpy std_msgs \
  --license Apache-2.0
```

**butler_security/butler_security/security_manager.py**:

```python
"""
MOSS 安全管理器
实现四层安全防护：
1. API Token 认证
2. 操作权限分级
3. 防火墙/代理隔离（通过网络配置实现）
4. 操作日志与告警
"""

import json
import os
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class OperationRisk(Enum):
    """操作风险等级"""
    READ_ONLY = 0      # 只读（查询状态）
    NORMAL = 1          # 常规操作（开关灯、调温度）
    SENSITIVE = 2       # 敏感操作（开锁、开窗）
    CRITICAL = 3        # 危险操作（关闭安防、修改配置）


class SecurityManager(Node):
    """安全管理器"""

    # 设备操作风险等级映射
    RISK_LEVELS = {
        'light.turn_on': OperationRisk.NORMAL,
        'light.turn_off': OperationRisk.NORMAL,
        'light.toggle': OperationRisk.NORMAL,
        'climate.set_temperature': OperationRisk.NORMAL,
        'cover.open_cover': OperationRisk.SENSITIVE,
        'cover.close_cover': OperationRisk.SENSITIVE,
        'lock.unlock': OperationRisk.CRITICAL,
        'lock.lock': OperationRisk.SENSITIVE,
        'alarm_control_panel.disarm': OperationRisk.CRITICAL,
        'alarm_control_panel.arm_home': OperationRisk.SENSITIVE,
    }

    def __init__(self):
        super().__init__('security_manager')

        # 操作日志目录
        self.log_dir = Path(config.get(
            'security.operation_log_dir',
            str(Path.home() / '文档/LeranRos/logs/operations')
        ))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 操作日志文件
        self.operation_log_file = self.log_dir / 'operations.log'

        # 设置日志记录器
        self.op_logger = logging.getLogger('moss_operations')
        self.op_logger.setLevel(logging.INFO)
        handler = logging.FileHandler(self.operation_log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.op_logger.addHandler(handler)

        # 订阅请求审计
        self.audit_sub = self.create_subscription(
            String,
            '/moss/security/audit_request',
            self.audit_callback,
            10
        )

        self.get_logger().info('安全管理器已启动')

    def audit_callback(self, msg: String):
        """审计操作请求"""
        try:
            request = json.loads(msg.data)
            action = request.get('action', 'unknown')
            operator = request.get('operator', 'unknown')
            risk = self._get_risk_level(action)

            self._log_operation(action, operator, risk)

            if risk == OperationRisk.CRITICAL:
                self._trigger_alert(action, operator)

        except json.JSONDecodeError:
            self.get_logger().error('审计请求解析失败')

    def _get_risk_level(self, action: str) -> OperationRisk:
        """获取操作的风险等级"""
        return self.RISK_LEVELS.get(action, OperationRisk.NORMAL)

    def _log_operation(self, action: str, operator: str, risk: OperationRisk):
        """记录操作日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'operator': operator,
            'risk_level': risk.name,
            'risk_value': risk.value
        }
        self.op_logger.info(json.dumps(log_entry, ensure_ascii=False))

    def _trigger_alert(self, action: str, operator: str):
        """触发告警 - 预留扩展"""
        # 后续扩展：发送 Telegram 通知、推送 App 通知、邮件告警
        self.get_logger().warn(f'⚠ 高风险操作告警: {action} by {operator}')

        # 预留通知接口
        alert_msg = String()
        alert_msg.data = json.dumps({
            'type': 'security_alert',
            'action': action,
            'operator': operator,
            'timestamp': datetime.now().isoformat()
        })
        # self.alert_pub.publish(alert_msg)  # 后续添加通知推送节点


def main(args=None):
    rclpy.init(args=args)
    node = SecurityManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

**butler_security/butler_security/notifications.py**（预留扩展）:

```python
"""
通知推送模块 - 预留扩展接口
当前仅定义接口和数据结构，功能待后续实现
"""

from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class NotifyLevel(Enum):
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


@dataclass
class Notification:
    """通知数据结构"""
    level: NotifyLevel
    title: str
    message: str
    timestamp: datetime
    source: str                 # 来源节点
    metadata: Optional[Dict[str, Any]] = None


def send_notification(notification: Notification) -> bool:
    """
    发送通知 - 预留接口

    Args:
        notification: 通知对象

    Returns:
        True if sent successfully, False otherwise

    后续扩展方向:
        - Telegram Bot 推送
        - Bark App 推送
        - Web Dashboard 实时通知
        - 邮件通知
        - 短信通知（严重告警）
    """
    # TODO: 实现 Telegram Bot 通知
    # https://core.telegram.org/bots/api

    # TODO: 实现 Bark App 通知
    # https://github.com/Finb/Bark

    # TODO: 实现 Web Dashboard WebSocket 推送
    # 通过 FastAPI WebSocket 推送到前端

    # TODO: 实现邮件通知
    # 通过 SMTP 发送告警邮件

    print(f"[通知-预留] {notification.level.value}: {notification.title} - {notification.message}")
    return False  # 暂未实现


def send_alert(
    title: str,
    message: str,
    level: NotifyLevel = NotifyLevel.WARNING,
    source: str = "moss_security"
) -> None:
    """
    便捷告警函数 - 预留接口

    后续扩展: 当检测到陌生人进入、烟雾报警、异常操作时调用
    """
    notification = Notification(
        level=level,
        title=title,
        message=message,
        timestamp=datetime.now(),
        source=source,
    )
    send_notification(notification)
```

### 8.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-4.1 | HA 客户端可连接 | 日志显示成功获取设备状态 |
| AC-4.2 | 设备状态同步 | `ros2 topic echo /moss/devices/state` 有数据 |
| AC-4.3 | 可控制设备 | 发布控制指令后 HA 设备状态改变 |
| AC-4.4 | 操作日志记录 | 检查 `logs/operations/operations.log` 有记录 |
| AC-4.5 | 风险分级生效 | 触发 CRITICAL 操作时日志有告警标记 |

### 8.4 测试方案

```bash
# 单元测试（不需要 HA 运行）
python3 -m pytest src/butler_security/tests/ -v

# 集成测试（需要 HA 运行）
# 1. 确保 Home Assistant 在 Windows 上运行
# 2. 设置 HA_TOKEN 环境变量
export HA_TOKEN="your-long-lived-token"

# 3. 启动 HA 客户端
ros2 run butler_ha ha_client

# 4. 发布控制指令
ros2 topic pub --once /moss/devices/command std_msgs/String \
  '{"entity_id": "light.living_room", "service": "light/toggle"}'

# 5. 检查操作日志
cat ~/文档/LeranRos/logs/operations/operations.log
```

---

## 9. 阶段 5：Web Dashboard 与完整集成

> **目标**：实现 Web Dashboard (PWA)，集成 JWT 认证、WebRTC 视频流、云台控制、设备控制、AI 对话面板，PostgreSQL 数据存储

### 9.1 目标与产出

| 产物 | 描述 |
|------|------|
| FastAPI 后端 | REST API + WebSocket + JWT 认证 |
| Vue3 前端 | PWA 界面，含视频查看、云台操纵杆、设备面板、对话界面 |
| WebRTC 信令 | 浏览器与机器人之间的 WebRTC 连接建立 |
| PostgreSQL 集成 | 用户数据、操作日志、事件记录持久化 |
| Docker 部署 | docker-compose 一键部署 |

### 9.2 详细步骤

#### 步骤 9.1：后端 API 服务

**smart_butler_web/backend/main.py**:

```python
"""
MOSS Web Dashboard 后端 API
FastAPI + JWT 认证 + WebSocket + WebRTC 信令
"""

from fastapi import FastAPI, HTTPException, Depends, WebSocket
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from datetime import datetime, timedelta
import asyncpg
import json

app = FastAPI(title="MOSS Dashboard API", version="1.0.0")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT 配置
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 数据库连接池
db_pool = None


@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host="192.168.2.xxx",  # Windows 机器 IP
        port=5432,
        user="moss",
        password="moss_password",
        database="moss_db"
    )


# === 认证模块 ===

def create_access_token(username: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": username, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/api/auth/login")
async def login(username: str, password: str):
    """用户登录"""
    # 生产环境需要验证密码哈希
    token = create_access_token(username)
    return {"access_token": token, "token_type": "bearer"}


# === 机器人控制 API ===

@app.get("/api/status")
async def get_status():
    """获取机器人状态"""
    return {
        "robot_name": "MOSS",
        "status": "online",
        "mode": "simulation",
        "camera": {"resolution": "640x480", "fps": 30},
        "gimbal": {"pan": 45.0, "tilt": -10.0, "roll": 0.0}
    }


@app.post("/api/gimbal/control")
async def control_gimbal(pan: float = 0, tilt: float = 0, roll: float = 0):
    """控制云台转动"""
    # 通过 ROS2 bridge 发布控制指令
    return {"status": "ok", "pan": pan, "tilt": tilt, "roll": roll}


@app.get("/api/devices")
async def list_devices():
    """获取智能设备列表和状态"""
    # 从 PostgreSQL 或内存缓存读取
    return {
        "devices": [
            {"id": "light_1", "type": "light", "state": {"on": True, "brightness": 80}},
            {"id": "thermostat_1", "type": "thermostat", "state": {"temperature": 24.0}},
            {"id": "curtain_1", "type": "curtain", "state": {"position": 50}},
        ]
    }


@app.post("/api/devices/control")
async def control_device(device_id: str, action: str, params: dict = {}):
    """控制智能设备"""
    return {"status": "ok", "device_id": device_id, "action": action}


@app.post("/api/ai/chat")
async def chat_with_moss(message: str):
    """发送消息给 MOSS AI"""
    return {"reply": f"MOSS: 收到消息'{message}'，这是回复"}


# === WebSocket ===

@app.websocket("/ws/video")
async def video_stream(websocket: WebSocket):
    """WebRTC 视频流信令"""
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"echo: {data}")


# === 健康检查 ===
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
```

#### 步骤 9.2：前端 PWA 骨架

**smart_butler_web/frontend/src/App.vue** (Vue3 示例):

```vue
<template>
  <div id="app">
    <header class="app-header">
      <h1>MOSS Dashboard</h1>
      <span class="status">{{ robotStatus }}</span>
    </header>

    <main class="dashboard">
      <!-- 视频面板 -->
      <section class="panel video-panel">
        <h2>实时画面</h2>
        <div class="video-container">
          <video ref="videoPlayer" autoplay playsinline></video>
        </div>
      </section>

      <!-- 云台控制 -->
      <section class="panel gimbal-panel">
        <h2>云台控制</h2>
        <div class="joystick">
          <button @mousedown="moveGimbal('up')" @mouseup="stopGimbal">↑</button>
          <button @mousedown="moveGimbal('left')" @mouseup="stopGimbal">←</button>
          <button @mousedown="moveGimbal('right')" @mouseup="stopGimbal">→</button>
          <button @mousedown="moveGimbal('down')" @mouseup="stopGimbal">↓</button>
        </div>
      </section>

      <!-- 智能设备 -->
      <section class="panel devices-panel">
        <h2>智能设备</h2>
        <div v-for="device in devices" :key="device.id" class="device-card">
          <span class="device-name">{{ device.id }}</span>
          <button @click="toggleDevice(device)">开关</button>
        </div>
      </section>

      <!-- 对话面板 -->
      <section class="panel chat-panel">
        <h2>与 MOSS 对话</h2>
        <div class="chat-messages">
          <div v-for="msg in messages" :key="msg.id" :class="['message', msg.role]">
            {{ msg.content }}
          </div>
        </div>
        <input v-model="chatInput" @keyup.enter="sendMessage" placeholder="输入消息..."/>
      </section>
    </main>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      robotStatus: '在线',
      devices: [],
      messages: [],
      chatInput: ''
    }
  },
  methods: {
    async moveGimbal(direction) {
      // 调用 /api/gimbal/control
    },
    stopGimbal() {},
    toggleDevice(device) {},
    async sendMessage() {
      if (this.chatInput.trim()) {
        this.messages.push({ id: Date.now(), role: 'user', content: this.chatInput })
        // 调用 /api/ai/chat
        this.chatInput = ''
      }
    }
  }
}
</script>
```

### 9.3 验收标准

| 编号 | 标准 | 验证方法 |
|------|------|---------|
| AC-5.1 | 后端 API 启动 | `uvicorn main:app` 后 `http://localhost:8000/health` 返回 healthy |
| AC-5.2 | JWT 登录可用 | POST /api/auth/login 获得 token |
| AC-5.3 | 前端页面可访问 | 浏览器打开 Dashboard，看到四大面板 |
| AC-5.4 | PostgreSQL 连接 | 后端写入数据后数据库可查询 |
| AC-5.5 | PWA 安装 | 浏览器地址栏显示"安装"按钮 |

---

## 10. 硬件抽象层设计

### 10.1 设计原则

采用**插件式独立节点**方案（方案 A）：
- 每个硬件外设定义统一的 ROS2 接口（话题/服务/动作）
- 模拟版本和真实版本是两个独立节点
- launch 文件根据场景选择启动对应节点

### 10.2 接口规范

| 硬件 | ROS2 接口 | Sim 节点 | Real 节点 |
|------|-----------|---------|----------|
| 摄像头 | `sensor_msgs/Image` on `~/image_raw` | `sim_camera_node` (读 Gazebo) | `real_camera_node` (读 /dev/video0) |
| 云台 Pan | `std_msgs/Float64` on `~/pan/command` | Gazebo joint controller | 舵机/PWM 驱动 |
| 云台 Tilt | `std_msgs/Float64` on `~/tilt/command` | Gazebo joint controller | 舵机/PWM 驱动 |
| 云台 Roll | `std_msgs/Float64` on `~/roll/command` | Gazebo joint controller | 舵机/PWM 驱动 |
| 麦克风 | 自定义 AudioData | `mic_node` (读 sounddevice) | 相同（都是本机） |
| 喇叭 | 自定义 AudioData | `speaker_node` (sounddevice) | 相同（都是本机） |

### 10.3 Launch 文件切换

**butler_bringup/launch/moss.launch.py**:

```python
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node


def generate_launch_description():
    use_sim = LaunchConfiguration('use_sim', default='true')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim', default_value='true'),

        # 模拟摄像头
        Node(
            package='butler_camera',
            executable='sim_camera_node',
            name='sim_camera_node',
            condition=IfCondition(use_sim)
        ),
        # 真实摄像头
        Node(
            package='butler_camera',
            executable='real_camera_node',
            name='real_camera_node',
            condition=IfCondition(use_sim)  # 条件取反
        ),
        # ... 其他节点
    ])
```

---

## 11. 安全方案详解

### 11.1 四层安全架构

```
┌──────────────────────────────────────────────┐
│              Layer 1: Token 认证               │
│  - Home Assistant Long-Lived Access Token    │
│  - JWT for Web Dashboard                     │
│  - HTTPS 传输                                │
├──────────────────────────────────────────────┤
│              Layer 2: 权限分级                │
│  - READ_ONLY:  查询设备状态                   │
│  - NORMAL:     开关灯、调温度                  │
│  - SENSITIVE:  开窗、开窗帘                    │
│  - CRITICAL:   开锁、关闭安防                  │
├──────────────────────────────────────────────┤
│              Layer 3: 网络隔离                │
│  - 机器人不直接暴露到公网                      │
│  - HA 仅在局域网访问                          │
│  - 外网通过 VPN/WireGuard 接入                │
├──────────────────────────────────────────────┤
│              Layer 4: 审计日志                │
│  - 所有操作记录到 PostgreSQL                   │
│  - CRITICAL 操作实时告警                      │
│  - 日志保留 90 天，方便追溯                    │
└──────────────────────────────────────────────┘
```

### 11.2 环境变量安全配置

```bash
# .env 文件（不提交 Git）
HA_TOKEN=eyJhbGciOiJIUzI1NiIs...
JWT_SECRET=your-256-bit-secret
OPENAI_API_KEY=sk-your-openai-key
DB_PASSWORD=moss_db_password
```

---

## 12. 扩展预留接口

### 12.1 已预留的扩展点

| 扩展点 | 位置 | 当前状态 |
|--------|------|---------|
| 人脸识别 | `features.yaml: face_recognition: false` | 接口已定义，节点待实现 |
| 人物追踪 | `features.yaml: person_tracking: false` | 接口已定义 |
| 轨道移动 | `features.yaml: track_movement: false` | Gazebo 世界已预留轨道模型 |
| 通知推送 | `butler_security/notifications.py` | 接口已定义，函数体为空 |
| 机载屏幕 | `features.yaml: onboard_display: false` | 不做处理 |
| 自动场景 | `features.yaml: auto_routine: false` | 后续添加 |

### 12.2 添加新功能的流程

1. 在 `config/features.yaml` 添加功能开关
2. 在对应包中创建新节点
3. 在 `butler_bringup/launch` 中添加条件启动
4. 实现 Sim 版本和 Real 版本的硬件抽象
5. 添加测试

---

## 13. 配置管理方案

### 13.1 配置层次

```
优先级（高 → 低）:
  CLI 参数 > 环境变量 > YAML 配置文件 > 代码默认值
```

### 13.2 配置文件清单

| 文件 | 用途 | 提交 Git |
|------|------|---------|
| `config/sim.yaml` | 仿真环境全量配置 | 是 |
| `config/real.yaml` | 真机环境全量配置 | 是 |
| `config/features.yaml` | 功能开关集中管理 | 是 |
| `.env` | 敏感信息（Token、密码） | 否 |
| `config/defaults.yaml` | 代码默认值（文档参考用） | 是 |

### 13.3 节点使用配置的规范

```python
# 推荐做法：通过 ConfigManager 读取，结合 ROS2 参数
from butler_bringup.config_manager import config

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        # 从 YAML 配置读取
        value = config.get('nodes.my_node.setting', 'default')
        # 或声明 ROS2 参数（允许 CLI 覆盖）
        self.declare_parameter('setting', value)
```

---

## 14. 附录：常见问题与排错

### 14.1 Gazebo Fortress 常见问题

| 问题 | 解决方案 |
|------|---------|
| `gz sim` 启动黑屏 | `sudo apt install mesa-utils` 检查 GPU 驱动 |
| 找不到 `ros_gz_bridge` | `sudo apt install ros-jazzy-ros-gz-bridge` |
| 模型不显示 | 检查 SDF 文件路径，Gazebo 资源路径 `GZ_SIM_RESOURCE_PATH` |
| ros_gz_sim create 卡在 "Waiting" | 设置 `GZ_IP=127.0.0.1`，确保 Gazebo 已启动且 world 名称匹配 |
| gz-transport 多播发现失败 | 所有终端统一设置 `export GZ_IP=127.0.0.1` 禁用多播 |
| 关节话题名无效 | ROS2 不允许 `/0/state` 类 token（数字开头），须在桥接时用别名 |
| Xacro 未被 Gazebo 解析 | 先用 `xacro` 命令生成 `.urdf`，再传给 `ros_gz_sim create -file` |
| URDF 中 `world` link 未定义 | 在 Xacro 中添加 `<link name="world"/>` |
| Camera 插件名失效 | Gazebo Fortress 8 无 `libignition-gazebo-camera-system.so`，改为 Sensors 系统 |
| Sensor 插件导致仿真挂起 | 移除 SDF 中的 Sensors 插件，相机验证可暂跳过 |
| 摄像头话题无数据 | OGRE2 + AMD/Mesa headless 渲染不产出帧，需 GPU 驱动修复 |

### 14.2 ROS2 常见问题

| 问题 | 解决方案 |
|------|---------|
| `colcon build` 失败 | `source /opt/ros/jazzy/setup.bash` 后重试 |
| 话题无数据 | 检查 topic 名称和命名空间是否正确 |
| 节点找不到 | 确认 `install/setup.bash` 已 source |
| `file(STRINGS)` 中文路径报错 | CMake 无法处理 UTF-8 多字节字符，patch 改用 `file(READ)` |
| pytest 9.x 与 ROS2 插件冲突 | 降级为系统自带 pytest 7.4.4：`pip3 install "pytest<8" --user` |
| numpy 2.x 与 cv_bridge 不兼容 | 降级 numpy 到 1.26.4 + opencv-python-headless 4.10.0.84 |

### 14.3 跨机通信问题

| 问题 | 解决方案 |
|------|---------|
| Ubuntu 无法访问 Windows | 关闭 Windows 防火墙或添加规则 |
| API 调用超时 | 检查 Windows 服务是否启动，端口是否监听 |
| PostgreSQL 连接拒绝 | 修改 `pg_hba.conf` 允许外部 IP |

### 14.4 第5章实测总结

**构建修复记录**:
1. **CMake + UTF-8 路径 bug**：Patch `/opt/ros/jazzy/share/rosidl_adapter/cmake/rosidl_adapt_interfaces.cmake`，将 `file(STRINGS "${idl_output}" idl_tuples)` 替换为 `file(READ "${idl_output}" idl_content); string(REGEX REPLACE "\n$" "" idl_content "${idl_content}"); string(REPLACE "\n" ";" idl_tuples "${idl_content}")`
2. **pytest 版本冲突**：`pip3 uninstall pytest pytest-asyncio`，使用系统 `pytest-3` (v7.4.4)
3. **numpy/cv_bridge 兼容**：`pip3 install "numpy<2" "opencv-python-headless==4.10.0.84"`
4. **代码风格修复**：smart_devices_sim.py 的 flake8/pep257 问题已修复（英文 docstring、导入顺序、行长、未使用变量）
5. **URDF 修复**：添加 `<link name="world"/>`，移除废弃的 camera 插件
6. **SDF 修复**：移除导致挂起的 Sensors 插件
7. **launch 文件修复**：移除关节状态桥接（ROS2 话题名非法），修正摄像头桥接话题名（`image` → `image_raw`）

**阶段 1 验收状态**:

| 编号 | 标准 | 状态 |
|------|------|------|
| AC-0.1 | `colcon build` 0 错误 | ✓ |
| AC-0.2 | 6 个自定义 msg/srv 可用 | ✓ |
| AC-0.3 | launch 文件可解析 | ✓ |
| AC-0.4 | 配置系统测试通过 | ✓ 6/6 |
| AC-1.1 | Gazebo 世界加载 | ✓ |
| AC-1.2 | 机器人生成 | ✓ |
| AC-1.3 | 摄像头话题有数据 | ✗ OGRE2/AMD 限制 |
| AC-1.4 | 云台话题可 pub | ✓ |
| AC-1.5 | 设备状态话题正常 | ✓ |

### 14.5 参考命令速查

```bash
# ROS2 常用命令
ros2 topic list                    # 列出所有话题
ros2 topic echo <topic>            # 监听话题
ros2 topic echo <topic> --once     # 监听一次
ros2 topic hz <topic>              # 话题频率
ros2 node list                     # 列出节点
ros2 run <package> <executable>    # 运行节点
ros2 launch <package> <launch>     # 启动 launch 文件
ros2 topic pub --once <topic> <type> "<data>"  # 发布一次

# Gazebo 常用命令
gz sim <world.sdf>                 # 启动 Gazebo（GUI）
gz sim -s <world.sdf>              # 启动 Gazebo（无 GUI 服务端）
GZ_IP=127.0.0.1 gz sim ...         # 绕过 gz-transport 多播
gz topic -l                        # 列出 Gazebo 话题
gz service -l                      # 列出 Gazebo 服务
ros2 run ros_gz_sim create ...    # 生成模型到运行中的 Gazebo

# colcon 常用命令
colcon build --symlink-install     # 编译（符号链接方式，改代码即时生效）
colcon build --packages-select <pkg>  # 只编译特定包
colcon test                        # 运行测试（会用系统 pytest）
colcon test-result --verbose       # 查看测试结果
/usr/bin/pytest-3 src/<pkg>/test/ -v  # 直接运行测试（pytest 7.x）

# 网络调试
export GZ_IP=127.0.0.1             # 强制 Gazebo 使用本地回环
```

### 14.6 第5章测试命令（可直接复制使用）

以下命令均经过实测验证。**关键是理解哪些命令会阻塞终端（必须单独开窗口），哪些可以合并成一行**。

#### 必须分布在不同终端的命令（4 个终端，各占一个窗口）

> **核心原则**：会持续运行的命令（服务器、模拟器、桥接）必须独占终端；一次性操作（xacro 转换、ros2 create、验证）可以合并在同一个终端。

| 终端 | 命令 | 说明 | 可合并？ |
|------|------|------|----------|
| 终端1 | `GZ_IP=127.0.0.1 gz sim -r src/butler_gazebo/worlds/smart_home.sdf` | Gazebo 服务器（持续运行） | **不可合并**，需独占终端 |
| 终端2 | `xacro ... > /tmp/moss.urdf && GZ_IP=127.0.0.1 ros2 run ros_gz_sim create ... -file /tmp/moss.urdf` | 生成机器人（一次性） | **可合并**成一行（见下方） |
| 终端3 | `python3 -m butler_gazebo.smart_devices_sim` | 设备模拟器（持续运行） | **不可合并**，需独占终端 |
| 终端4 | `ros2 topic echo /moss/devices/state --once` 等 | 验证命令（一次性） | **可合并**成一行 |

#### 终端1：启动 Gazebo（独占，不可合并）

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws && source install/setup.bash && GZ_IP=127.0.0.1 gz sim -r src/butler_gazebo/worlds/smart_home.sdf
```
> 启动后保持运行不关闭。Gazebo GUI 窗口会显示智能家居房间。等 GUI 窗口出现后方可执行终端2。

#### 终端2：生成 MOSS 机器人（可合并成一行）

> **千万注意**：不要用 `&&` 连接 `cd` 和长命令，会被 shell 换行截断。必须分两步执行。

**第一步**（当前目录为 ws）：
```bash
xacro src/butler_description/urdf/moss.urdf.xacro > /tmp/moss.urdf
```

**第二步**：
```bash
GZ_IP=127.0.0.1 ros2 run ros_gz_sim create -name moss -x 0 -y 0 -z 2.45 -file /tmp/moss.urdf
```
> 看到 `Entity creation successful` 即成功。Gazebo GUI 中将出现天花板上的黑色立方体（MOSS）。

#### 终端3：启动智能设备模拟器（独占，不可合并）

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws && source install/setup.bash && python3 -m butler_gazebo.smart_devices_sim
```
> 看到 `Smart device simulator started` 和 4 个设备列表即成功。保持运行。

#### 终端4：验证话题（多条命令，可逐行执行）

```bash
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws && source install/setup.bash && ros2 topic echo /moss/devices/state --once
```
> 应看到 `device_id: light_1` 等设备状态 JSON 数据。Ctrl+C 退出后继续执行：

```bash
ros2 topic pub --once /moss/gimbal/command butler_msgs/msg/GimbalCommand "{pan: 0.5, tilt: 0.3, roll: 0.0}"
```
> 无 subscriber 时会 `Waiting for at least 1 matching subscription`，这是正常的（云台控制器未启动），直接 Ctrl+C 跳过。

```bash
ros2 topic list | grep moss
```
> 应看到 `/moss/devices/command`、`/moss/devices/state`、`/moss/gimbal/command` 三个话题。

---

#### 常见调试失败模式及原因

| 现象 | 原因 | 解决 |
|------|------|------|
| `ros2 run` 找不到命令 | 没有 `source install/setup.bash` | 每条命令前后加上 `source` |
| `xacro` 报 `No such file` | 不在 ws 目录 | 先 `cd ~/文档/.../smart_butler_ws` |
| `python3 -m butler_gazebo` 报 `ModuleNotFoundError` | 同上，没 source | 先 `source install/setup.bash` |
| `ros_gz_sim create` 卡在 `Waiting` | Gazebo 没启动或 world 名不匹配 | 确认终端1 Gazebo 已运行 |
| `ros_gz_sim create` 卡在 `Requesting list` | gz-transport 多播不通 | 所有终端加 `GZ_IP=127.0.0.1` |
| 话题 echo 无输出 | 生产者未启动或桥接未建立 | 确认终端3 设备模拟器在运行 |
| `Waiting for subscription` | 话题无 subscriber（正常） | 直接 Ctrl+C，不影响验证 |

---

## 15. 快速启动流程总结

完成所有阶段后，完整启动顺序：

```bash
# === Windows 端（5070Ti 机器）===
# 1. 启动 PostgreSQL
# 2. 启动 Home Assistant
# 3. 启动 AI/Voice 服务
docker-compose -f smart_butler_server/docker-compose.yml up -d

# === Ubuntu 端（ROS2 机器）===
cd ~/文档/LeranRos/smart_butler_ros2/smart_butler_ws
source install/setup.bash

# 终端 1: 启动 Gazebo 仿真
ros2 launch butler_bringup moss_sim.launch.py

# 终端 2: 启动机器人核心节点
ros2 launch butler_bringup moss_core.launch.py

# 终端 3: 启动 Web Dashboard 后端
cd ~/文档/LeranRos/smart_butler_web
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 终端 4: 启动前端开发服务器
cd ~/文档/LeranRos/smart_butler_web/frontend
npm run dev

# 浏览器打开 http://localhost:5173
```

---

*本文档随项目开发持续更新。如有疑问，参考 `~/经验/本系统和环境信息.md`。*
