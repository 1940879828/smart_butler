"""
生成测试音频文件
使用pyttsx3离线TTS或edge-tts在线TTS生成中文语音
"""

import subprocess
import sys

def check_package(pkg_name):
    try:
        __import__(pkg_name)
        return True
    except ImportError:
        return False

def generate_with_edge_tts(text, output_path):
    """使用edge-tts生成中文语音（推荐，音质好）"""
    import asyncio
    import edge_tts
    
    async def main():
        # 使用中文女声
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_path)
    
    asyncio.run(main())
    print(f"[OK] 已生成: {output_path}")

def generate_with_pyttsx3(text, output_path):
    """使用pyttsx3生成语音（离线，音质一般）"""
    import pyttsx3
    
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # 语速
    engine.save_to_file(text, output_path)
    engine.runAndWait()
    print(f"[OK] 已生成: {output_path}")

def generate_with_tts(text, output_path):
    """使用gTTS生成语音"""
    from gtts import gTTS
    
    tts = gTTS(text=text, lang='zh')
    tts.save(output_path)
    print(f"[OK] 已生成: {output_path}")

def convert_to_wav16k(input_path, output_path):
    """转换为16kHz单声道WAV（Whisper推荐格式）"""
    # 使用soundfile转换
    import soundfile as sf
    import numpy as np
    
    data, sr = sf.read(input_path)
    # 如果是立体声，转单声道
    if len(data.shape) > 1:
        data = data[:, 0]
    # 重采样到16kHz
    if sr != 16000:
        from scipy import signal
        data = signal.resample(data, int(len(data) * 16000 / sr))
    sf.write(output_path, data, 16000)
    print(f"[OK] 已转换为16kHz: {output_path}")


def main():
    # 测试文本
    test_texts = [
        "你好，我是MOSS智能管家，很高兴为您服务。",
        "今天天气怎么样？",
        "请帮我打开客厅的灯。",
        "播放一首轻松的音乐。"
    ]
    
    print("=" * 50)
    print("MOSS 语音服务 - 测试音频生成工具")
    print("=" * 50)
    
    # 检查可用的TTS引擎
    engines = []
    if check_package("edge_tts"):
        engines.append(("edge_tts", "Edge TTS (推荐，音质最好)"))
    if check_package("pyttsx3"):
        engines.append(("pyttsx3", "pyttsx3 (离线可用)"))
    if check_package("gtts"):
        engines.append(("gtts", "Google TTS"))
    
    if not engines:
        print("\n未检测到TTS引擎，请安装:")
        print("  pip install edge-tts  # 推荐，微软Edge TTS")
        print("  pip install pyttsx3   # 离线TTS")
        print("  pip install gtts      # Google TTS")
        return
    
    print("\n可用的TTS引擎:")
    for i, (name, desc) in enumerate(engines, 1):
        print(f"  {i}. {desc}")
    
    # 选择引擎
    choice = input(f"\n请选择引擎 (1-{len(engines)}): ").strip()
    try:
        idx = int(choice) - 1
        engine_name = engines[idx][0]
    except (ValueError, IndexError):
        engine_name = engines[0][0]
    
    print(f"\n使用引擎: {engine_name}")
    
    # 生成测试音频
    print("\n生成测试音频文件...")
    
    for i, text in enumerate(test_texts):
        output_path = f"test_audio_{i+1}.wav"
        
        if engine_name == "edge_tts":
            # edge-tts生成mp3，需要转换
            temp_path = f"test_audio_{i+1}.mp3"
            generate_with_edge_tts(text, temp_path)
            try:
                convert_to_wav16k(temp_path, output_path)
                import os
                os.remove(temp_path)  # 删除临时mp3
            except Exception as e:
                print(f"[WARN] 转换失败，保留mp3: {e}")
                output_path = temp_path
        elif engine_name == "pyttsx3":
            generate_with_pyttsx3(text, output_path)
        elif engine_name == "gtts":
            temp_path = f"test_audio_{i+1}.mp3"
            generate_with_tts(text, temp_path)
            try:
                convert_to_wav16k(temp_path, output_path)
                import os
                os.remove(temp_path)
            except Exception as e:
                print(f"[WARN] 转换失败，保留mp3: {e}")
                output_path = temp_path
    
    print("\n" + "=" * 50)
    print("生成完成! 文件列表:")
    print("  test_audio_1.wav - 问候语")
    print("  test_audio_2.wav - 天气查询")
    print("  test_audio_3.wav - 设备控制")
    print("  test_audio_4.wav - 音乐播放")
    print("\n可用test_gui.py加载这些文件测试ASR")


if __name__ == "__main__":
    main()