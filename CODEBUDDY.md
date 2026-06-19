# CODEBUDDY.md

本文件为 CodeBuddy Code 在本仓库中工作时提供指引。

## 项目概述

MOSS 是一款安装在天花板轨道上的智能管家机器人，基于 ROS2 Jazzy Jalisco 开发。项目采用仿真优先的开发策略（Gazebo Fortress），预留真机迁移接口。由三个 Git 仓库组成，配有详细的实现指南文档。

**技术栈**：ROS2 Jazzy (rclpy)、Gazebo Fortress (Ignition)、BehaviorTree.CPP v4.x、OpenAI 兼容 LLM API、faster-whisper、piper-tts、FastAPI、Vue3/React、PostgreSQL、Docker

## 仓库结构

```
~/文档/LeranRos/
├── ros2智能管家实现指南.md          # 主实现指南文档（117KB）
├── smart_butler_ros2/               # ROS2 机器人核心
│   ├── .github/workflows/test.yml   # CI：GitHub Actions 构建/测试
│   ├── docker/                      # （空 - Docker 配置待补充）
│   └── smart_butler_ws/
│       ├── config/
│       │   ├── sim.yaml             # 仿真环境配置
│       │   └── features.yaml        # 功能开关配置
│       ├── scripts/
│       │   └── check_network.sh     # 网络连通性检查脚本
│       └── src/                     # ROS2 包目录（在此创建）
├── smart_butler_server/             # AI 与语音服务（部署在 Windows）
│   ├── ai_service/                  # 大模型服务（空）
│   ├── voice_service/               # Whisper ASR / Piper TTS（空）
│   └── db/                          # PostgreSQL 数据库迁移（空）
└── smart_butler_web/                # Web Dashboard（PWA）
    ├── backend/                     # FastAPI 后端（空）
    └── frontend/                    # Vue3/React 前端（空）
```

## 常用命令

### ROS2 构建与测试

```bash
# 进入工作空间
cd smart_butler_ros2/smart_butler_ws

# 构建所有包
colcon build --symlink-install

# 加载工作空间环境（执行任何 ros2 命令前必须先执行）
source install/setup.bash

# 构建单个包
colcon build --packages-select <包名>

# 运行所有测试
colcon test --event-handlers console_direct+
colcon test-result --verbose

# 运行单个包的测试
colcon test --packages-select <包名>

# 直接运行 Python 单元测试
python3 -m pytest src/<包名>/tests/ -v

# 运行单个测试文件
python3 -m pytest src/<包名>/tests/test_specific.py -v
```

### ROS2 调试检查

```bash
# 列出所有可用的消息/服务定义
ros2 interface list | grep butler_msgs

# 查看消息定义
ros2 interface show butler_msgs/msg/GimbalCommand

# 列出活跃的话题
ros2 topic list

# 监控话题频率
ros2 topic hz /moss/camera/image

# 打印话题数据
ros2 topic echo /moss/devices/state --once

# 发布测试指令
ros2 topic pub --once /moss/gimbal/command butler_msgs/msg/GimbalCommand \
  "{pan: 0.5, tilt: 0.3, roll: 0.0}"

# 查看 launch 文件参数
ros2 launch butler_bringup moss_sim.launch.py --show-arguments
```

### 仿真环境

```bash
# 启动 Gazebo 智能家居世界
ros2 launch butler_gazebo sim_world.launch.py

# 验证 Gazebo 安装
gz sim --versions
```

### 网络验证

```bash
# 检查与 Windows 主机的连通性（PostgreSQL、Ollama）
./smart_butler_ros2/smart_butler_ws/scripts/check_network.sh
```

## 架构说明

### ROS2 包职责

| 包名 | 构建类型 | 职责 |
|------|---------|------|
| `butler_bringup` | ament_python | Launch 文件、配置管理器（模块级单例） |
| `butler_msgs` | ament_cmake | 自定义 .msg/.srv/.action 消息定义 |
| `butler_description` | ament_cmake | URDF/Xacro/SDF 机器人模型 |
| `butler_gazebo` | ament_cmake | Gazebo 世界文件、插件、设备模拟器 |
| `butler_camera` | ament_python | 摄像头节点（仿真 + 真实硬件抽象层） |
| `butler_gimbal` | ament_python | 3 轴云台控制器 |
| `butler_audio` | ament_python | 音频采集（麦克风）与播放（喇叭） |
| `butler_voice` | ament_python | ASR/TTS 服务客户端（远程调用 Windows 服务） |
| `butler_ai` | ament_python | OpenAI 兼容 LLM 客户端 |
| `butler_behavior` | ament_python | 行为树定义 |
| `butler_ha` | ament_python | Home Assistant REST API 客户端 |
| `butler_security` | ament_python | 安全模块、操作日志 |
| `butler_web` | ament_python | Web API 端点（ROS2 侧） |

### ROS2 话题数据流

```
/moss/camera/image_raw       <- Gazebo 摄像头插件发布
/moss/camera/image_processed <- sim_camera_node 添加时间戳水印
/moss/gimbal/command         <- GimbalCommand 消息 → 驱动 pan/tilt/roll 关节
/moss/audio/raw              <- MicNode 发布原始音频帧
/moss/voice/recognized       <- ASRClient 发布识别出的文本
/moss/voice/speak            <- TTSClient 接收待合成文本
/moss/devices/state          <- SmartDevicesSim 发布设备状态
/moss/devices/command        <- JSON 格式的设备控制指令
```

### 配置系统

- **`config/sim.yaml`**：主配置文件（机器人模式、摄像头、云台、AI 端点、语音、HA、安全、网络）
- **`config/features.yaml`**：功能开关（wake_word、asr、tts、object_detection 等）
- 配置使用 `${VAR_NAME}` 语法进行环境变量替换
- 通过 `butler_bringup.config_manager.config` 单例访问，支持点分隔路径（如 `config.get('nodes.camera.resolution')`）
- 功能开关检查：`config.is_feature_enabled('asr')`

### 开发阶段

| 阶段 | 重点 | 关键包 |
|------|------|--------|
| 0 | 基础设施（骨架、配置、自定义消息） | butler_msgs, butler_bringup |
| 1 | 仿真环境（Gazebo 世界、机器人模型、摄像头、云台） | butler_description, butler_gazebo, butler_camera, butler_gimbal |
| 2 | 感知能力（音频、语音、WebRTC） | butler_audio, butler_voice |
| 3 | AI 大脑（大模型接入、行为树） | butler_ai, butler_behavior |
| 4 | 智能家居（HA 集成、安全防护） | butler_ha, butler_security |
| 5 | Web Dashboard（完整集成） | butler_web, smart_butler_web |

### 跨机架构

- **Ubuntu（开发机）**：ROS2 节点、Gazebo 仿真
- **Windows（5070Ti GPU 机器）**：PostgreSQL、Ollama/vLLM（本地大模型）、Whisper（ASR）、Piper（TTS）、butler_server（API 服务）
- 通信方式：ROS2 节点通过 REST/gRPC 调用 Windows 服务；可选 DDS 跨机 ROS2 通信
- Windows 主机 IP 在 `sim.yaml` 中配置为 `192.168.2.xxx`

### 自定义消息（butler_msgs）

- `GimbalCommand.msg`：pan/tilt/roll 角度
- `DeviceState.msg`：设备 ID、类型、JSON 状态、时间戳
- `VoiceCommand.msg`：文本、置信度、是否最终结果、音频数据
- `DetectionResult.msg`：类别名、置信度、边界框
- `AudioData.msg`：时间戳、采样率、通道数、采样位宽、原始数据
- `GetConfig.srv`：键 → 值 + 成功标志

## 本机环境

### 系统信息

| 项目 | 值 |
|------|-----|
| 操作系统 | Ubuntu 24.04.4 LTS (noble), x86_64 |
| 主机名 | taro-WUJIE14XA |
| 用户名 | taro |
| Python | 3.12.3 |
| cmake | 3.28.3 |
| ROS 2 | Jazzy（通过 packages.ros.org APT 源安装） |
| 摄像头 | SunplusIT HD Webcam (USB: 2b7e:b663)，设备路径 /dev/video0~3 |
| 本机 IP | 192.168.2.14 |
| VPN 代理 | http://127.0.0.1:7897 |

### 代理与镜像配置

本机位于中国（深圳），包下载需要配置镜像或代理：

- **APT**：mirrors.aliyun.com（无需代理）
- **pip**：pypi.tuna.tsinghua.edu.cn（已在 `~/.config/pip/pip.conf` 中配置）
- **pip 编译型大包**（dlib 等）：必须使用 `--proxy=http://127.0.0.1:7897`
- **Git**：已全局配置代理（`~/.gitconfig`），地址 `127.0.0.1:7897`
- **curl**：访问受限站点时使用 `-x http://127.0.0.1:7897`
- **wget**：使用 `-e use_proxy=yes -e https_proxy=http://127.0.0.1:7897`

安装包时参考以下方式：

```bash
# 普通 pip 安装（自动使用清华镜像）
pip3 install <包名>

# sudo pip 安装（使用 root 的镜像配置 /root/.config/pip/pip.conf）
sudo pip3 install <包名>

# 需要代理的编译型大包
sudo pip3 install --proxy=http://127.0.0.1:7897 dlib

# APT 安装（使用阿里云镜像，无需代理）
sudo apt-get install <包名>

# 临时开启系统级代理
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
```

## 开发注意事项

- `ros2智能管家实现指南.md` 是权威实现指南——各阶段的详细代码示例和步骤请参考该文档
- 含自定义消息的 ROS2 包（`butler_msgs`）必须使用 `ament_cmake` 构建类型；纯 Python 包使用 `ament_python`
- 构建后执行任何 `ros2` 命令前必须先 `source install/setup.bash`
- Gazebo Fortress 的插件命名规则为 `libignition-gazebo-*.so`（不是 `libgz-`）
- Gazebo Fortress 中关节控制的话题路径为 `/world/<世界名>/model/<模型名>/joint/<关节名>/0/cmd_pos`
- `sudo pip3 install` 使用独立的 pip 配置 `/root/.config/pip/pip.conf`——需确保该文件也指向清华镜像
- 编译型大包（dlib、face_recognition）不加 `--proxy=http://127.0.0.1:7897` 会超时
