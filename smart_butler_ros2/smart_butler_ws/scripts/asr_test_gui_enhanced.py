#!/usr/bin/env python3
"""Enhanced ASR Test GUI – standalone tool for testing the speech recognition pipeline.

Features:
- WebRTC VAD support (optional)
- Real-time waveform display
- State machine visualization
- Wake word testing
- No ROS2 dependency. Reads config from config/sim.yaml.
"""

import base64
import collections
import io
import os
import queue
import sys
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import ttk, scrolledtext
import wave

import numpy as np
import requests
import sounddevice as sd
import yaml

# scipy for band-pass filter
from scipy.signal import butter, sosfilt

# Optional: WebRTC VAD
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'butler_voice'))
    from butler_voice.webrtc_vad import HybridVAD, create_vad
    HAS_WEBRTC_VAD = True
except ImportError:
    HAS_WEBRTC_VAD = False

# Optional: matplotlib for waveform
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ---- Config loading -------------------------------------------------

def _find_ws_root():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(path, 'config')):
            return path
        path = os.path.dirname(path)
    return path


def _load_config():
    ws = _find_ws_root()
    cfg_path = os.path.join(ws, 'config', 'sim.yaml')
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f'config not found: {cfg_path}')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    voice = raw.get('nodes', {}).get('voice', {})
    asr = voice.get('asr', {})
    wake = voice.get('wake_word', {})

    return {
        'asr': {
            'api_base': asr.get('api_base', ''),
            'api_key': asr.get('api_key', ''),
            'model': asr.get('model', 'mimo-v2.5-asr'),
            'language': asr.get('language', 'zh'),
            'sample_rate': int(asr.get('sample_rate', 16000)),
            'buffer_duration': float(asr.get('buffer_duration', 2.0)),
            'silence_threshold': int(asr.get('silence_threshold', 3500)),
            'noise_reduction': asr.get('noise_reduction', True),
            'filter_lowcut': asr.get('filter_lowcut', 80),
            'filter_highcut': asr.get('filter_highcut', 4000),
            'vad_mode': asr.get('vad_mode', 'energy'),
            'webrtc_aggressiveness': int(asr.get('webrtc_aggressiveness', 2)),
        },
        'wake_word': {
            'enabled': wake.get('enabled', False),
            'word': wake.get('word', 'moss'),
            'threshold': float(wake.get('threshold', 0.5)),
            'energy_threshold': int(wake.get('energy_threshold', 3000)),
        },
    }


# ---- WAV encoding ---------------------------------------------------

def _encode_wav_b64(audio: np.ndarray, sample_rate: int) -> str:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f'data:audio/wav;base64,{b64}'


# ---- ASR API call ---------------------------------------------------

def transcribe_mimo(audio: np.ndarray, cfg: dict) -> tuple[str, float]:
    """Send WAV audio to MiMo and return recognized text and elapsed time."""
    url = f'{cfg["api_base"]}/chat/completions'
    data_url = _encode_wav_b64(audio, cfg['sample_rate'])
    payload = {
        'model': cfg['model'],
        'messages': [{
            'role': 'user',
            'content': [{
                'type': 'input_audio',
                'input_audio': {
                    'data': data_url,
                    'format': 'wav',
                },
            }],
        }],
        'asr_options': {
            'language': cfg.get('language', 'zh'),
        },
    }

    t0 = time.time()
    resp = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {cfg["api_key"]}',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=30,
    )
    elapsed = time.time() - t0

    if resp.status_code != 200:
        return f'[HTTP {resp.status_code}] {resp.text[:200]}', elapsed

    body = resp.json()
    choices = body.get('choices', [])
    if not choices:
        return '', elapsed
    text = choices[0].get('message', {}).get('content', '').strip()
    return text, elapsed


# ---- GUI Application ------------------------------------------------

class EnhancedASRGui:
    """Enhanced Tkinter GUI for testing the ASR pipeline."""

    def __init__(self):
        self.config = _load_config()
        self.cfg = self.config['asr']
        self.wake_cfg = self.config['wake_word']

        self._setup_state()
        self._build_ui()
        self._init_vad()
        self._update_timer = self.root.after(50, self._update)

    def _setup_state(self):
        self._running = False
        self._listening = False
        self._stream = None
        self._audio_queue = queue.Queue(maxsize=200)

        # VAD state
        self._vad_buffer = deque(maxlen=int(
            self.cfg['sample_rate'] * self.cfg['buffer_duration']))
        self._is_speaking = False
        self._silence_count = 0
        self._silence_req = int(self.cfg['sample_rate'] * 0.5)

        # Energy
        self._energy = 0
        self._energy_filtered = 0

        # Statistics
        self._record_count = 0
        self._total_time = 0
        self._avg_time = 0

        # State machine
        self._state = 'IDLE'  # IDLE, LISTENING, PROCESSING, SPEAKING
        self._state_time = time.time()

        # Waveform buffer
        self._waveform_buffer = deque(maxlen=500)

        # Filter
        self._filter_sos = self._build_bandpass()

    def _init_vad(self):
        """Initialize VAD based on configuration."""
        self._vad_mode = self.cfg.get('vad_mode', 'energy')
        self._hybrid_vad = None

        if self._vad_mode in ('webrtc', 'hybrid') and HAS_WEBRTC_VAD:
            try:
                self._hybrid_vad = create_vad(
                    sample_rate=self.cfg['sample_rate'],
                    energy_threshold=self.cfg['silence_threshold'],
                    use_webrtc=True,
                    webrtc_aggressiveness=self.cfg.get('webrtc_aggressiveness', 2),
                )
                self._log(f'WebRTC VAD initialized (mode={self._vad_mode})')
            except Exception as e:
                self._log(f'WebRTC VAD init failed: {e}')
                self._vad_mode = 'energy'
        elif self._vad_mode in ('webrtc', 'hybrid'):
            self._log('WebRTC VAD not available, using energy-based')
            self._vad_mode = 'energy'

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title('MOSS ASR 测试工具 - 增强版')
        self.root.geometry('900x700')
        self.root.resizable(True, True)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # ---- Menu bar ----
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="清除日志", command=self._clear_log)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)

        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="重新加载配置", command=self._reload_config)

        # ---- Service bar ----
        svc_frame = ttk.LabelFrame(self.root, text='服务控制', padding=5)
        svc_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(svc_frame, text='启动服务',
                   command=self._on_start_service).pack(side=tk.LEFT, padx=3)
        ttk.Button(svc_frame, text='停止服务',
                   command=self._on_stop_service).pack(side=tk.LEFT, padx=3)
        self._svc_label = ttk.Label(svc_frame, text='● 未启动',
                                    foreground='grey')
        self._svc_label.pack(side=tk.LEFT, padx=10)

        self._recording = False
        self._rec_btn = ttk.Button(svc_frame, text='开始收音',
                                   command=self._on_toggle_record)
        self._rec_btn.pack(side=tk.LEFT, padx=3)
        self._rec_label = ttk.Label(svc_frame, text='⏸ 已暂停',
                                    foreground='grey')
        self._rec_label.pack(side=tk.LEFT, padx=10)

        # ---- VAD mode selection ----
        vad_frame = ttk.LabelFrame(self.root, text='VAD 配置', padding=5)
        vad_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(vad_frame, text='VAD模式:').pack(side=tk.LEFT)
        self._vad_mode_var = tk.StringVar(value=self._vad_mode)
        vad_combo = ttk.Combobox(
            vad_frame, textvariable=self._vad_mode_var,
            values=['energy', 'webrtc', 'hybrid'], width=10, state='readonly')
        vad_combo.pack(side=tk.LEFT, padx=5)
        vad_combo.bind('<<ComboboxSelected>>', self._on_vad_mode_change)

        # Noise reduction toggle
        self._nr_var = tk.BooleanVar(value=self.cfg.get('noise_reduction', True))
        ttk.Checkbutton(
            vad_frame, text='降噪', variable=self._nr_var,
            command=self._on_noise_reduction_toggle).pack(side=tk.LEFT, padx=10)

        # State indicator
        ttk.Label(vad_frame, text='状态:').pack(side=tk.LEFT, padx=(20, 0))
        self._state_label = ttk.Label(vad_frame, text='IDLE', width=12,
                                      foreground='grey')
        self._state_label.pack(side=tk.LEFT, padx=5)

        # ---- Debug panel ----
        dbg_frame = ttk.LabelFrame(self.root, text='调试信息', padding=5)
        dbg_frame.pack(fill=tk.X, padx=5, pady=2)

        # Energy bar
        ttk.Label(dbg_frame, text='能量:').pack(side=tk.LEFT)
        self._energy_var = tk.IntVar(value=0)
        self._energy_bar = ttk.Progressbar(
            dbg_frame, variable=self._energy_var, maximum=20000, length=150)
        self._energy_bar.pack(side=tk.LEFT, padx=5)
        self._energy_label = ttk.Label(dbg_frame, text='0', width=8)
        self._energy_label.pack(side=tk.LEFT)

        # Threshold slider
        ttk.Label(dbg_frame, text='阈值:').pack(side=tk.LEFT, padx=(10, 0))
        self._threshold_scale = ttk.Scale(
            dbg_frame, from_=500, to=10000, length=120,
            command=self._on_threshold_change)
        self._threshold_scale.set(self.cfg['silence_threshold'])
        self._threshold_scale.pack(side=tk.LEFT, padx=5)
        self._threshold_label = ttk.Label(
            dbg_frame, text=str(self.cfg['silence_threshold']), width=6)
        self._threshold_label.pack(side=tk.LEFT)

        # VAD status
        ttk.Label(dbg_frame, text='VAD:').pack(side=tk.LEFT, padx=(10, 0))
        self._vad_label = ttk.Label(dbg_frame, text='--', width=10)
        self._vad_label.pack(side=tk.LEFT)

        # Buffer bar
        ttk.Label(dbg_frame, text='缓冲:').pack(side=tk.LEFT, padx=(10, 0))
        self._buf_var = tk.IntVar(value=0)
        self._buf_bar = ttk.Progressbar(
            dbg_frame, variable=self._buf_var, maximum=100, length=100)
        self._buf_bar.pack(side=tk.LEFT, padx=5)
        self._buf_label = ttk.Label(dbg_frame, text='0.0s', width=5)
        self._buf_label.pack(side=tk.LEFT)

        # ---- Waveform display ----
        if HAS_MATPLOTLIB:
            wave_frame = ttk.LabelFrame(self.root, text='波形显示', padding=5)
            wave_frame.pack(fill=tk.X, padx=5, pady=2)

            self._fig = Figure(figsize=(8, 1.5), dpi=80)
            self._ax = self._fig.add_subplot(111)
            self._ax.set_ylim(-10000, 10000)
            self._ax.set_xlim(0, 500)
            self._line, = self._ax.plot([], [], 'b-', linewidth=0.5)
            self._ax.set_facecolor('#f0f0f0')
            self._ax.grid(True, alpha=0.3)

            self._canvas = FigureCanvasTkAgg(self._fig, master=wave_frame)
            self._canvas.get_tk_widget().pack(fill=tk.X)

        # ---- Output panel ----
        out_frame = ttk.LabelFrame(self.root, text='识别结果', padding=5)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # Statistics bar
        stats_frame = ttk.Frame(out_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 5))

        self._count_label = ttk.Label(stats_frame, text='识别次数: 0')
        self._count_label.pack(side=tk.LEFT, padx=10)

        self._avg_time_label = ttk.Label(stats_frame, text='平均耗时: 0.0s')
        self._avg_time_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(stats_frame, text='清除', command=self._clear_log).pack(side=tk.RIGHT)

        # Output text
        self._output = scrolledtext.ScrolledText(
            out_frame, height=10, wrap=tk.WORD, font=('Consolas', 10),
            state=tk.DISABLED)
        self._output.pack(fill=tk.BOTH, expand=True)

        # ---- Status bar ----
        self._status = ttk.Label(
            self.root, text='就绪', relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(fill=tk.X, padx=5, pady=2)

    # ---- Button handlers --------------------------------------------

    def _on_start_service(self):
        if self._running:
            return
        try:
            self._stream = sd.InputStream(
                samplerate=self.cfg['sample_rate'],
                channels=1,
                callback=self._audio_callback,
                blocksize=1024,
                dtype='int16',
            )
            self._stream.start()
            self._running = True
            self._svc_label.config(text='● 运行中', foreground='green')
            self._status.config(text='服务已启动')
            self._log('服务已启动')
            self._set_state('IDLE')
        except Exception as e:
            self._status.config(text=f'启动失败: {e}')
            self._log(f'启动失败: {e}')

    def _on_stop_service(self):
        self._on_pause_listening()
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False
        self._recording = False
        self._listening = False
        self._svc_label.config(text='● 未启动', foreground='grey')
        self._rec_btn.config(text='开始收音')
        self._rec_label.config(text='⏸ 已暂停', foreground='grey')
        self._status.config(text='服务已停止')
        self._set_state('IDLE')

    def _on_toggle_record(self):
        if self._recording:
            self._on_pause_listening()
        else:
            self._on_start_listening()

    def _on_start_listening(self):
        if not self._running:
            self._status.config(text='请先启动服务')
            return
        self._recording = True
        self._listening = True
        self._rec_btn.config(text='停止收音')
        self._rec_label.config(text='● 录音中', foreground='red')
        self._status.config(text='正在收音...')
        self._set_state('LISTENING')

    def _on_pause_listening(self):
        self._recording = False
        self._listening = False
        self._rec_btn.config(text='开始收音')
        self._rec_label.config(text='⏸ 已暂停', foreground='grey')
        self._status.config(text='收音已暂停')
        self._set_state('IDLE')

    def _on_noise_reduction_toggle(self):
        enabled = self._nr_var.get()
        self._status.config(text=f'降噪: {"开" if enabled else "关"}')

    def _on_threshold_change(self, val):
        self.cfg['silence_threshold'] = int(float(val))
        self._threshold_label.config(text=str(self.cfg['silence_threshold']))
        if self._hybrid_vad:
            self._hybrid_vad.energy_threshold = self.cfg['silence_threshold']

    def _on_vad_mode_change(self, event=None):
        new_mode = self._vad_mode_var.get()
        if new_mode != self._vad_mode:
            self._vad_mode = new_mode
            self._init_vad()
            self._log(f'VAD模式已切换: {new_mode}')

    def _on_close(self):
        self._running = False
        self._listening = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.root.destroy()

    def _clear_log(self):
        self._output.config(state=tk.NORMAL)
        self._output.delete(1.0, tk.END)
        self._output.config(state=tk.DISABLED)
        self._record_count = 0
        self._total_time = 0
        self._avg_time = 0
        self._update_stats()

    def _reload_config(self):
        try:
            self.config = _load_config()
            self.cfg = self.config['asr']
            self.wake_cfg = self.config['wake_word']
            self._init_vad()
            self._log('配置已重新加载')
        except Exception as e:
            self._log(f'配置加载失败: {e}')

    def _build_bandpass(self):
        nyq = 0.5 * self.cfg['sample_rate']
        low = self.cfg.get('filter_lowcut', 80) / nyq
        high = self.cfg.get('filter_highcut', 4000) / nyq
        return butter(4, [low, high], btype='band', output='sos')

    def _apply_filter(self, audio: np.ndarray) -> np.ndarray:
        if not self._nr_var.get():
            return audio
        filtered = sosfilt(self._filter_sos, audio.astype(np.float32))
        return filtered.astype(np.int16)

    def _set_state(self, state: str):
        self._state = state
        self._state_time = time.time()

        colors = {
            'IDLE': 'grey',
            'LISTENING': 'blue',
            'PROCESSING': 'orange',
            'SPEAKING': 'green',
            'WAKING': 'purple',
        }
        self._state_label.config(text=state, foreground=colors.get(state, 'black'))

    # ---- audio callback ----------------------------------------------

    def _audio_callback(self, indata, frames, time_info, status):
        if not self._running:
            return
        if indata is None:
            return
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    # ---- main loop update (50ms) ------------------------------------

    def _update(self):
        # Process audio queue
        while not self._audio_queue.empty():
            try:
                audio = self._audio_queue.get_nowait()
                audio_i16 = audio.flatten().astype(np.int16)
                raw_energy = np.abs(audio_i16.astype(np.float64)).mean()

                # Apply voice band-pass filter for noise reduction
                audio_filtered = self._apply_filter(audio_i16)
                self._energy = int(raw_energy)
                self._energy_filtered = int(
                    np.abs(audio_filtered.astype(np.float64)).mean())

                # Update waveform buffer
                self._waveform_buffer.extend(audio_i16[-20:].tolist())

                if self._listening:
                    self._process_vad(audio_filtered)
            except queue.Empty:
                break

        # Update energy bar
        display_energy = self._energy_filtered if self._nr_var.get() else self._energy
        self._energy_var.set(display_energy)
        nr_tag = ' [降噪]' if self._nr_var.get() else ''
        self._energy_label.config(text=f'{display_energy}{nr_tag}')

        # Update buffer bar
        buf_fill = len(self._vad_buffer) / max(1, self._vad_buffer.maxlen)
        self._buf_var.set(int(buf_fill * 100))
        buf_sec = len(self._vad_buffer) / max(1, self.cfg['sample_rate'])
        self._buf_label.config(text=f'{buf_sec:.1f}s')

        # Update VAD status
        status_text = '正在说话' if self._is_speaking else '静音'
        self._vad_label.config(text=status_text)

        # Update waveform display
        if HAS_MATPLOTLIB and self._waveform_buffer:
            data = list(self._waveform_buffer)
            self._line.set_data(range(len(data)), data)
            self._canvas.draw_idle()

        self._update_timer = self.root.after(50, self._update)

    def _process_vad(self, audio: np.ndarray):
        if self._vad_mode in ('webrtc', 'hybrid') and self._hybrid_vad:
            # Use WebRTC/hybrid VAD
            is_speech, speech_audio = self._hybrid_vad.process(audio)
            if speech_audio is not None and len(speech_audio) > 0:
                self._on_speech_detected(speech_audio)
        else:
            # Energy-based VAD
            self._process_energy_vad(audio)

    def _process_energy_vad(self, audio: np.ndarray):
        threshold = self.cfg['silence_threshold']
        energy = np.abs(audio.astype(np.float64)).mean()

        if energy > threshold:
            self._is_speaking = True
            self._silence_count = 0
            self._vad_buffer.extend(audio.tolist())
        elif self._is_speaking:
            self._silence_count += len(audio)
            self._vad_buffer.extend(audio.tolist())
            if self._silence_count >= self._silence_req:
                self._flush_vad()

        # Auto-flush when buffer is full
        if len(self._vad_buffer) >= self._vad_buffer.maxlen:
            self._flush_vad()

    def _flush_vad(self):
        min_samples = int(self.cfg['sample_rate'] * 0.5)
        if len(self._vad_buffer) < min_samples:
            self._vad_buffer.clear()
            self._is_speaking = False
            self._silence_count = 0
            return

        audio = np.array(list(self._vad_buffer), dtype=np.int16)
        self._vad_buffer.clear()
        self._is_speaking = False
        self._silence_count = 0

        self._on_speech_detected(audio)

    def _on_speech_detected(self, audio: np.ndarray):
        self._set_state('PROCESSING')
        cfg_copy = dict(self.cfg)
        threading.Thread(
            target=self._transcribe_bg, args=(audio, cfg_copy),
            daemon=True).start()

    def _transcribe_bg(self, audio: np.ndarray, cfg: dict):
        t0 = time.time()
        self.root.after(0, lambda: self._status.config(text='识别中...'))
        try:
            text, elapsed = transcribe_mimo(audio, cfg)
        except Exception as e:
            text = f'[Error] {e}'
            elapsed = time.time() - t0

        self._record_count += 1
        self._total_time += elapsed
        self._avg_time = self._total_time / self._record_count

        ts = time.strftime('%H:%M:%S')
        self._log(f'{ts} ({elapsed:.1f}s) {text}')

        self.root.after(0, self._update_stats)
        self.root.after(0, lambda: self._set_state('LISTENING'))
        self.root.after(0, lambda: self._status.config(
            text=f'已识别 {self._record_count} 条'))

    def _update_stats(self):
        self._count_label.config(text=f'识别次数: {self._record_count}')
        self._avg_time_label.config(text=f'平均耗时: {self._avg_time:.1f}s')

    def _log(self, msg: str):
        def _append():
            self._output.config(state=tk.NORMAL)
            self._output.insert(tk.END, msg + '\n')
            self._output.see(tk.END)
            self._output.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def run(self):
        self.root.mainloop()
        # Cleanup on exit
        self._running = False
        self._listening = False
        if self._stream:
            self._stream.stop()
            self._stream.close()


def main():
    app = EnhancedASRGui()
    app.run()


if __name__ == '__main__':
    main()
