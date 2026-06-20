#!/usr/bin/env python3
"""TTS Test GUI – standalone tool for testing Text-to-Speech.

Features:
- Text input and synthesis
- Audio playback
- Parameter adjustment
- History tracking
- No ROS2 dependency. Reads config from config/sim.yaml.
"""

import io
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
import wave

import numpy as np
import requests
import sounddevice as sd
import yaml


# ---- Config loading -------------------------------------------------

def _find_ws_root():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(path, 'config')):
            return path
        path = os.path.dirname(path)
    return path


def _load_tts_config():
    ws = _find_ws_root()
    cfg_path = os.path.join(ws, 'config', 'sim.yaml')
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f'config not found: {cfg_path}')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    voice = raw.get('nodes', {}).get('voice', {})
    tts = voice.get('tts', {})
    asr = voice.get('asr', {})

    return {
        'provider': tts.get('provider', 'piper'),
        'voice': tts.get('voice', 'zh_CN'),
        'windows_endpoint': tts.get('windows_endpoint', ''),
        'api_base': asr.get('api_base', ''),
        'api_key': asr.get('api_key', ''),
        'sample_rate': int(asr.get('sample_rate', 16000)),
    }


# ---- TTS API calls --------------------------------------------------

def synthesize_piper(text: str, cfg: dict) -> tuple[np.ndarray, int, float]:
    """Synthesize speech using Piper TTS (via Windows endpoint)."""
    endpoint = cfg.get('windows_endpoint', '')
    if not endpoint:
        raise ValueError("Windows endpoint not configured for Piper TTS")

    url = f'{endpoint}/synthesize'
    payload = {
        'text': text,
        'voice': cfg.get('voice', 'zh_CN'),
    }

    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=30)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        raise ValueError(f'HTTP {resp.status_code}: {resp.text[:200]}')

    # Response should be WAV audio
    audio_data = resp.content
    with wave.open(io.BytesIO(audio_data), 'rb') as wf:
        sample_rate = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    return audio, sample_rate, elapsed


def synthesize_edge_tts(text: str, cfg: dict) -> tuple[np.ndarray, int, float]:
    """Synthesize speech using Edge TTS."""
    try:
        import edge_tts
        import asyncio
    except ImportError:
        raise ValueError("edge-tts not installed. Install with: pip install edge-tts")

    voice = cfg.get('voice', 'zh-CN-XiaoxiaoNeural')

    async def _synthesize():
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    t0 = time.time()
    audio_bytes = asyncio.run(_synthesize())
    elapsed = time.time() - t0

    # Convert to numpy array
    with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
        sample_rate = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    return audio, sample_rate, elapsed


def synthesize_openai_tts(text: str, cfg: dict) -> tuple[np.ndarray, int, float]:
    """Synthesize speech using OpenAI-compatible TTS API."""
    api_base = cfg.get('api_base', '')
    api_key = cfg.get('api_key', '')
    if not api_base or not api_key:
        raise ValueError("API base and key required for OpenAI TTS")

    url = f'{api_base}/audio/speech'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'tts-1',
        'input': text,
        'voice': 'alloy',
        'response_format': 'wav',
    }

    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        raise ValueError(f'HTTP {resp.status_code}: {resp.text[:200]}')

    with wave.open(io.BytesIO(resp.content), 'rb') as wf:
        sample_rate = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    return audio, sample_rate, elapsed


# ---- GUI Application ------------------------------------------------

class TTSGui:
    """Tkinter GUI for testing TTS."""

    def __init__(self):
        self.cfg = _load_tts_config()
        self._setup_state()
        self._build_ui()

    def _setup_state(self):
        self._audio_queue = queue.Queue()
        self._is_playing = False
        self._current_audio = None
        self._current_sample_rate = None
        self._history = []

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title('MOSS TTS 测试工具')
        self.root.geometry('700x600')
        self.root.resizable(True, True)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # ---- Provider selection ----
        provider_frame = ttk.LabelFrame(self.root, text='TTS 配置', padding=5)
        provider_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(provider_frame, text='Provider:').pack(side=tk.LEFT)
        self._provider_var = tk.StringVar(value=self.cfg['provider'])
        provider_combo = ttk.Combobox(
            provider_frame, textvariable=self._provider_var,
            values=['piper', 'edge', 'openai'], width=10, state='readonly')
        provider_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(provider_frame, text='Voice:').pack(side=tk.LEFT, padx=(10, 0))
        self._voice_var = tk.StringVar(value=self.cfg['voice'])
        voice_entry = ttk.Entry(
            provider_frame, textvariable=self._voice_var, width=20)
        voice_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(provider_frame, text='刷新配置',
                   command=self._reload_config).pack(side=tk.RIGHT, padx=5)

        # ---- Text input ----
        input_frame = ttk.LabelFrame(self.root, text='文本输入', padding=5)
        input_frame.pack(fill=tk.X, padx=5, pady=2)

        self._text_input = scrolledtext.ScrolledText(
            input_frame, height=6, wrap=tk.WORD, font=('Microsoft YaHei', 11))
        self._text_input.pack(fill=tk.X)
        self._text_input.insert(tk.END, '你好，我是MOSS智能管家，很高兴为您服务。')

        # ---- Control buttons ----
        ctrl_frame = ttk.Frame(self.root, padding=5)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=2)

        self._synth_btn = ttk.Button(
            ctrl_frame, text='合成语音', command=self._on_synthesize)
        self._synth_btn.pack(side=tk.LEFT, padx=3)

        self._play_btn = ttk.Button(
            ctrl_frame, text='播放', command=self._on_play, state=tk.DISABLED)
        self._play_btn.pack(side=tk.LEFT, padx=3)

        self._stop_btn = ttk.Button(
            ctrl_frame, text='停止', command=self._on_stop, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=3)

        ttk.Button(ctrl_frame, text='清除',
                   command=self._on_clear).pack(side=tk.LEFT, padx=3)

        # Status
        self._status_label = ttk.Label(ctrl_frame, text='就绪')
        self._status_label.pack(side=tk.RIGHT, padx=10)

        # ---- Audio info ----
        info_frame = ttk.LabelFrame(self.root, text='音频信息', padding=5)
        info_frame.pack(fill=tk.X, padx=5, pady=2)

        self._info_label = ttk.Label(info_frame, text='未合成')
        self._info_label.pack(fill=tk.X)

        # ---- History ----
        history_frame = ttk.LabelFrame(self.root, text='历史记录', padding=5)
        history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # History list with scrollbar
        history_container = ttk.Frame(history_frame)
        history_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(history_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._history_list = tk.Listbox(
            history_container, yscrollcommand=scrollbar.set,
            font=('Consolas', 10))
        self._history_list.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._history_list.yview)

        # History buttons
        history_btn_frame = ttk.Frame(history_frame)
        history_btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(history_btn_frame, text='重播选中',
                   command=self._on_replay_selected).pack(side=tk.LEFT, padx=3)
        ttk.Button(history_btn_frame, text='清除历史',
                   command=self._on_clear_history).pack(side=tk.LEFT, padx=3)

        # ---- Status bar ----
        self._status = ttk.Label(
            self.root, text='就绪', relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(fill=tk.X, padx=5, pady=2)

    # ---- Button handlers --------------------------------------------

    def _on_synthesize(self):
        text = self._text_input.get(1.0, tk.END).strip()
        if not text:
            self._status.config(text='请输入文本')
            return

        self._synth_btn.config(state=tk.DISABLED)
        self._status.config(text='合成中...')
        self._status_label.config(text='合成中...')

        threading.Thread(
            target=self._synthesize_thread, args=(text,), daemon=True).start()

    def _synthesize_thread(self, text: str):
        try:
            provider = self._provider_var.get()
            cfg = dict(self.cfg)
            cfg['provider'] = provider
            cfg['voice'] = self._voice_var.get()

            if provider == 'piper':
                audio, sample_rate, elapsed = synthesize_piper(text, cfg)
            elif provider == 'edge':
                audio, sample_rate, elapsed = synthesize_edge_tts(text, cfg)
            elif provider == 'openai':
                audio, sample_rate, elapsed = synthesize_openai_tts(text, cfg)
            else:
                raise ValueError(f'Unknown provider: {provider}')

            self._current_audio = audio
            self._current_sample_rate = sample_rate

            # Add to history
            duration = len(audio) / sample_rate
            history_entry = {
                'text': text[:50] + ('...' if len(text) > 50 else ''),
                'full_text': text,
                'provider': provider,
                'elapsed': elapsed,
                'duration': duration,
                'sample_rate': sample_rate,
                'audio': audio,
            }
            self._history.append(history_entry)

            # Update UI
            self.root.after(0, lambda: self._on_synthesize_complete(
                elapsed, duration, sample_rate, len(audio)))
            self.root.after(0, lambda: self._add_history_entry(history_entry))

        except Exception as e:
            self.root.after(0, lambda: self._on_synthesize_error(str(e)))

    def _on_synthesize_complete(self, elapsed, duration, sample_rate, samples):
        self._synth_btn.config(state=tk.NORMAL)
        self._play_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.NORMAL)

        info_text = (
            f'采样率: {sample_rate}Hz | '
            f'时长: {duration:.1f}s | '
            f'合成耗时: {elapsed:.1f}s | '
            f'样本数: {samples}'
        )
        self._info_label.config(text=info_text)
        self._status.config(text='合成完成')
        self._status_label.config(text='就绪')

    def _on_synthesize_error(self, error_msg):
        self._synth_btn.config(state=tk.NORMAL)
        self._status.config(text=f'合成失败: {error_msg}')
        self._status_label.config(text='错误')

    def _on_play(self):
        if self._current_audio is None:
            return

        self._is_playing = True
        self._play_btn.config(state=tk.DISABLED)
        self._status.config(text='播放中...')
        self._status_label.config(text='播放中')

        def _play():
            try:
                sd.play(self._current_audio, self._current_sample_rate)
                sd.wait()
            except Exception as e:
                self.root.after(0, lambda: self._status.config(
                    text=f'播放错误: {e}'))
            finally:
                self._is_playing = False
                self.root.after(0, lambda: self._play_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self._status.config(text='播放完成'))
                self.root.after(0, lambda: self._status_label.config(text='就绪'))

        threading.Thread(target=_play, daemon=True).start()

    def _on_stop(self):
        sd.stop()
        self._is_playing = False
        self._play_btn.config(state=tk.NORMAL)
        self._status.config(text='已停止')
        self._status_label.config(text='就绪')

    def _on_clear(self):
        self._text_input.delete(1.0, tk.END)
        self._current_audio = None
        self._current_sample_rate = None
        self._play_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.DISABLED)
        self._info_label.config(text='未合成')
        self._status.config(text='已清除')

    def _on_replay_selected(self):
        selection = self._history_list.curselection()
        if not selection:
            return

        index = selection[0]
        if index < len(self._history):
            entry = self._history[index]
            self._current_audio = entry['audio']
            self._current_sample_rate = entry['sample_rate']
            self._on_play()

    def _on_clear_history(self):
        self._history.clear()
        self._history_list.delete(0, tk.END)
        self._status.config(text='历史已清除')

    def _add_history_entry(self, entry):
        display_text = (
            f"[{entry['provider']}] {entry['text']} "
            f"({entry['elapsed']:.1f}s, {entry['duration']:.1f}s)"
        )
        self._history_list.insert(tk.END, display_text)
        self._history_list.see(tk.END)

    def _reload_config(self):
        try:
            self.cfg = _load_tts_config()
            self._provider_var.set(self.cfg['provider'])
            self._voice_var.set(self.cfg['voice'])
            self._status.config(text='配置已重新加载')
        except Exception as e:
            self._status.config(text=f'配置加载失败: {e}')

    def _on_close(self):
        sd.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = TTSGui()
    app.run()


if __name__ == '__main__':
    main()
