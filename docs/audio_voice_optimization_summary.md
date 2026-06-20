# butler_audio 和 butler_voice 优化总结

## 优化概览

本次优化完成了 butler_audio 和 butler_voice 模块的全面升级，实现了类似小爱音箱的语音交互流程，并提供了完善的测试工具。

## 完成的功能

### 1. speaker_node.py 修复 ✓
- **问题**: 原实现只接收 TTS 文本日志，没有实际音频播放功能
- **修复**:
  - 添加 `AudioData` 消息订阅，支持原始音频播放
  - 支持多种采样位宽 (8/16/32 bit)
  - 支持多通道音频
  - 添加播放状态发布 (`/moss/audio/playback_state`)
  - 保持对 `String` 消息的向后兼容

### 2. VAD 算法改进 ✓
- **文件**: `butler_voice/webrtc_vad.py` (新增)
- **功能**:
  - `WebRTCVAD`: WebRTC VAD 封装，支持 0-3 级敏感度
  - `HybridVAD`: 混合 VAD，结合能量阈值和 WebRTC VAD
  - `create_vad()`: 工厂函数，简化创建
- **配置**:
  - `vad_mode`: `energy` | `webrtc` | `hybrid`
  - `webrtc_aggressiveness`: 0-3 (3 最严格)
- **集成**: `asr_client.py` 已更新，支持新的 VAD 模式

### 3. 提示音系统 ✓
- **文件**: `butler_audio/sound_effects.py` (新增)
- **功能**:
  - 10 种内置音效类型 (唤醒、监听、处理、成功、错误等)
  - 音效生成器 (正弦波、和弦、脉冲、叮声等)
  - 音量控制 (全局和单个音效)
  - 自定义音效支持 (WAV 文件加载)
  - 播放序列支持
- **全局管理器**: `get_sound_manager()` 单例访问

### 4. 状态机管理 ✓
- **文件**: `butler_voice/voice_state_machine.py` (新增)
- **状态**:
  - `IDLE`: 待机状态，等待唤醒词
  - `WAKING`: 唤醒词检测中
  - `LISTENING`: 监听用户语音
  - `PROCESSING`: 处理/识别语音
  - `SPEAKING`: 语音回复播放中
  - `ERROR`: 错误状态
  - `TIMEOUT`: 超时状态
- **特性**:
  - 状态转换回调
  - 超时管理
  - 上下文数据管理
  - ROS2 集成 (`VoiceStateMachineROS2`)

### 5. 唤醒词检测 ✓
- **文件**: `butler_voice/wake_word_node.py` (新增)
- **功能**:
  - `WakeWordDetector`: 基于 openWakeWord 的检测器
  - `SimpleWakeWordDetector`: 能量模式的简单检测器 (测试用)
  - `WakeWordNode`: ROS2 节点，订阅音频输入，发布唤醒事件
- **配置**:
  - `wake_word`: 唤醒词 (默认 "moss")
  - `threshold`: 检测阈值
  - `use_openwakeword`: 是否使用 openWakeWord

### 6. 配置和依赖更新 ✓
- **sim.yaml**:
  - 添加 `vad_mode` 和 `webrtc_aggressiveness` 配置
  - 添加 `wake_word` 配置部分
  - 启用唤醒词功能
- **setup.py**:
  - butler_voice: 添加 webrtcvad、openwakeword 依赖
  - butler_audio: 添加 soundfile、scipy 依赖
- **package.xml**: 更新依赖声明

### 7. 测试工具增强 ✓
- **ASR 测试 GUI** (`scripts/asr_test_gui_enhanced.py`):
  - WebRTC VAD 支持
  - 实时波形显示 (需要 matplotlib)
  - 状态机可视化
  - 统计信息 (识别次数、平均耗时)
  - VAD 模式切换
  - 配置重载
- **TTS 测试 GUI** (`scripts/tts_test_gui.py`):
  - 多 TTS Provider 支持 (Piper、Edge、OpenAI)
  - 文本输入和合成
  - 音频播放控制
  - 历史记录
  - 参数调整

### 8. 单元测试 ✓
- **butler_voice/tests**:
  - `test_webrtc_vad.py`: WebRTC VAD 和 HybridVAD 测试
  - `test_voice_state_machine.py`: 状态机完整测试
- **butler_audio/tests**:
  - `test_sound_effects.py`: 提示音系统测试

### 9. 集成测试 ✓
- **文件**: `scripts/integration_test.py`
- **覆盖**:
  - 音效系统集成
  - VAD 集成
  - 状态机集成
  - ASR 客户端集成 (mocked)
  - 完整工作流测试

## 文件结构

```
butler_audio/
├── butler_audio/
│   ├── __init__.py          # 更新：导出 sound_effects
│   ├── mic_node.py          # 保持不变
│   ├── speaker_node.py      # 修复：添加 AudioData 订阅
│   └── sound_effects.py     # 新增：提示音管理
├── tests/
│   ├── test_mic_node.py
│   ├── test_speaker_node.py
│   └── test_sound_effects.py # 新增
├── setup.py                 # 更新：添加依赖
└── package.xml              # 更新：添加依赖

butler_voice/
├── butler_voice/
│   ├── __init__.py          # 更新：导出新模块
│   ├── asr_client.py        # 改进：集成 WebRTC VAD
│   ├── tts_client.py        # 保持不变
│   ├── webrtc_vad.py        # 新增：WebRTC VAD
│   ├── voice_state_machine.py # 新增：状态机
│   └── wake_word_node.py    # 新增：唤醒词检测
├── tests/
│   ├── test_asr_client.py
│   ├── test_tts_client.py
│   ├── test_webrtc_vad.py   # 新增
│   └── test_voice_state_machine.py # 新增
├── setup.py                 # 更新：添加依赖
└── package.xml              # 更新：添加依赖

scripts/
├── asr_test_gui.py          # 保持不变
├── asr_test_gui_enhanced.py # 新增：增强版 ASR 测试
├── tts_test_gui.py          # 新增：TTS 测试
└── integration_test.py      # 新增：集成测试

config/
└── sim.yaml                 # 更新：添加新配置项
```

## 使用指南

### 运行测试

```bash
# 单元测试
cd smart_butler_ros2/smart_butler_ws
python -m pytest src/butler_voice/tests/ -v
python -m pytest src/butler_audio/tests/ -v

# 集成测试
python scripts/integration_test.py
```

### 启动测试 GUI

```bash
# ASR 测试 (增强版)
python scripts/asr_test_gui_enhanced.py

# TTS 测试
python scripts/tts_test_gui.py
```

### 安装可选依赖

```bash
# WebRTC VAD (更好的 VAD)
pip install webrtcvad

# 唤醒词检测
pip install openwakeword onnxruntime

# 波形显示 (ASR GUI)
pip install matplotlib

# Edge TTS
pip install edge-tts

# 音效文件支持
pip install soundfile scipy
```

### ROS2 节点启动

```bash
# 构建
colcon build --packages-select butler_audio butler_voice

# 启动节点
ros2 run butler_audio mic_node
ros2 run butler_audio speaker_node
ros2 run butler_voice asr_client
ros2 run butler_voice wake_word_node
```

## 语音交互流程

```
┌─────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│  IDLE   │────▶│ WAKING  │────▶│LISTENING │────▶│PROCESSING│────▶│SPEAKING │
│         │     │         │     │          │     │          │     │         │
│ 等待唤醒 │     │唤醒词检测│     │ 监听语音  │     │ 语音识别  │     │语音回复  │
└─────────┘     └─────────┘     └──────────┘     └──────────┘     └─────────┘
     ▲                                                              │
     └──────────────────────────────────────────────────────────────┘
```

1. **IDLE**: 等待唤醒词 "moss"
2. **WAKING**: 检测到唤醒词，播放提示音
3. **LISTENING**: 监听用户语音输入
4. **PROCESSING**: 发送音频到 ASR 服务识别
5. **SPEAKING**: 播放 TTS 语音回复
6. 返回 IDLE

## 后续工作

1. **唤醒词模型训练**: 训练自定义 "moss" 唤醒词模型
2. **性能优化**: 优化 VAD 参数，减少误触发
3. **更多音效**: 添加更多自定义音效
4. **UI 优化**: 改进测试 GUI 的用户体验
5. **文档完善**: 添加详细的 API 文档

## 依赖版本

### 必需依赖
- Python >= 3.8
- numpy >= 1.20
- sounddevice >= 0.4
- requests >= 2.25
- PyYAML >= 5.4

### 可选依赖
- webrtcvad >= 2.0.10 (WebRTC VAD)
- openwakeword >= 0.6.0 (唤醒词检测)
- onnxruntime >= 1.16.0 (唤醒词检测)
- matplotlib >= 3.5 (波形显示)
- soundfile >= 0.12 (音效文件)
- scipy >= 1.7 (信号处理)
- edge-tts >= 6.1 (Edge TTS)

## 总结

本次优化显著提升了 butler_audio 和 butler_voice 模块的功能和可测试性：

1. **VAD 准确率提升**: WebRTC VAD 比简单能量阈值更准确
2. **用户体验改善**: 唤醒词 + 提示音 + 状态机 = 类似小爱音箱的体验
3. **测试便利性**: GUI 测试工具让调试更简单
4. **代码质量**: 完整的单元测试和集成测试
5. **可扩展性**: 模块化设计，易于添加新功能
