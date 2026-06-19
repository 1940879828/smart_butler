#!/usr/bin/env python3
"""ASR Test GUI – standalone tool for testing the MiMo speech recognition pipeline.

No ROS2 dependency. Reads MiMo config from config/sim.yaml.
"""

import base64
import io
import os
import queue
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import ttk
import wave

import numpy as np
import requests
import sounddevice as sd
import yaml

# scipy for band-pass filter
from scipy.signal import butter, sosfilt


# ---- Config loading -------------------------------------------------

def _find_ws_root():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(path, 'config')):
            return path
        path = os.path.dirname(path)
    return path


def _load_asr_config():
    ws = _find_ws_root()
    cfg_path = os.path.join(ws, 'config', 'sim.yaml')
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f'config not found: {cfg_path}')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    asr = raw.get('nodes', {}).get('voice', {}).get('asr', {})
    return {
        'api_base': asr.get('api_base', ''),
        'api_key': asr.get('api_key', ''),
        'model': asr.get('model', 'mimo-v2.5-asr'),
        'language': asr.get('language', 'zh'),
        'sample_rate': int(asr.get('sample_rate', 16000)),
        'buffer_duration': float(asr.get('buffer_duration', 2.0)),
        'silence_threshold': int(asr.get('silence_threshold', 3500)),
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

def transcribe_mimo(audio: np.ndarray, cfg: dict) -> str:
    """Send WAV audio to MiMo and return recognized text."""
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
        return f'[HTTP {resp.status_code}] {resp.text[:200]}'

    body = resp.json()
    choices = body.get('choices', [])
    if not choices:
        return ''
    text = choices[0].get('message', {}).get('content', '').strip()
    return text


# ---- GUI Application ------------------------------------------------

class ASRGui:
    """Tkinter GUI for testing the ASR pipeline."""

    def __init__(self):
        self.cfg = _load_asr_config()
        self._setup_state()
        self._build_ui()
        self._update_timer = self.root.after(50, self._update)

    def _setup_state(self):
        self._running = False
        self._listening = False
        self._stream = None
        self._audio_queue = queue.Queue(maxsize=200)
        self._vad_buffer = deque(maxlen=int(
            self.cfg['sample_rate'] * self.cfg['buffer_duration']))
        self._is_speaking = False
        self._silence_count = 0
        self._silence_req = int(self.cfg['sample_rate'] * 0.5)
        self._energy = 0
        self._energy_filtered = 0
        self._record_count = 0
        self._vad_status = '--'
        self._filter_sos = self._build_bandpass()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title('MOSS ASR 测试工具')
        self.root.geometry('700x550')
        self.root.resizable(True, True)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # ---- service bar ----
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

        # ---- noise reduction toggle ----
        self._nr_var = tk.BooleanVar(value=self.cfg.get('noise_reduction', True))
        self._nr_check = ttk.Checkbutton(
            svc_frame, text='降噪', variable=self._nr_var,
            command=self._on_noise_reduction_toggle)
        self._nr_check.pack(side=tk.RIGHT, padx=5)

        # ---- debug panel ----
        dbg_frame = ttk.LabelFrame(self.root, text='调试信息', padding=5)
        dbg_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(dbg_frame, text='麦克风能量:').pack(side=tk.LEFT)
        self._energy_var = tk.IntVar(value=0)
        self._energy_bar = ttk.Progressbar(
            dbg_frame, variable=self._energy_var, maximum=20000, length=200)
        self._energy_bar.pack(side=tk.LEFT, padx=5)
        self._energy_label = ttk.Label(dbg_frame, text='0', width=6)
        self._energy_label.pack(side=tk.LEFT)

        ttk.Label(dbg_frame, text='  阈值:').pack(side=tk.LEFT)
        self._threshold_scale = ttk.Scale(
            dbg_frame, from_=500, to=10000, length=150,
            command=self._on_threshold_change)
        self._threshold_scale.set(self.cfg['silence_threshold'])
        self._threshold_scale.pack(side=tk.LEFT, padx=5)
        self._threshold_label = ttk.Label(
            dbg_frame, text=str(self.cfg['silence_threshold']), width=6)
        self._threshold_label.pack(side=tk.LEFT)

        ttk.Label(dbg_frame, text='  VAD:').pack(side=tk.LEFT, padx=(15, 0))
        self._vad_label = ttk.Label(dbg_frame, text='--', width=10)
        self._vad_label.pack(side=tk.LEFT)

        ttk.Label(dbg_frame, text='  缓冲:').pack(side=tk.LEFT, padx=(15, 0))
        self._buf_var = tk.IntVar(value=0)
        self._buf_bar = ttk.Progressbar(
            dbg_frame, variable=self._buf_var, maximum=100, length=120)
        self._buf_bar.pack(side=tk.LEFT, padx=5)
        self._buf_label = ttk.Label(dbg_frame, text='0.0s', width=5)
        self._buf_label.pack(side=tk.LEFT)

        # ---- output panel ----
        out_frame = ttk.LabelFrame(self.root, text='识别结果', padding=5)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        self._output = tk.Text(
            out_frame, height=12, wrap=tk.WORD, font=('monospace', 10),
            state=tk.DISABLED)
        self._output.pack(fill=tk.BOTH, expand=True)

        # ---- status bar ----
        self._status = ttk.Label(
            self.root, text='就绪', relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(fill=tk.X, padx=5, pady=2)

    # ---- button handlers --------------------------------------------

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
        except Exception as e:
            self._status.config(text=f'启动失败: {e}')

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

    def _on_toggle_record(self):
        """Toggle recording on/off."""
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

    def _on_pause_listening(self):
        self._recording = False
        self._listening = False
        self._rec_btn.config(text='开始收音')
        self._rec_label.config(text='⏸ 已暂停', foreground='grey')
        self._status.config(text='收音已暂停')

    def _on_noise_reduction_toggle(self):
        enabled = self._nr_var.get()
        self._status.config(text=f'降噪: {"开" if enabled else "关"}')

    def _on_threshold_change(self, val):
        self.cfg['silence_threshold'] = int(float(val))
        self._threshold_label.config(text=str(self.cfg['silence_threshold']))

    def _on_close(self):
        self._running = False
        self._listening = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.root.destroy()

    def _build_bandpass(self):
        """Build Butterworth band-pass filter (80-4000Hz)."""
        nyq = 0.5 * self.cfg['sample_rate']
        low = self.cfg.get('filter_lowcut', 80) / nyq
        high = self.cfg.get('filter_highcut', 4000) / nyq
        return butter(4, [low, high], btype='band', output='sos')

    def _apply_filter(self, audio: np.ndarray) -> np.ndarray:
        if not self._nr_var.get():
            return audio
        filtered = sosfilt(self._filter_sos, audio.astype(np.float32))
        return filtered.astype(np.int16)

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

                if self._listening:
                    self._process_vad(audio_filtered)
            except queue.Empty:
                break

        # Update energy bar (show filtered energy when NR is on)
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

        self._update_timer = self.root.after(50, self._update)

    def _process_vad(self, audio: np.ndarray):
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

        cfg_copy = dict(self.cfg)
        threading.Thread(
            target=self._transcribe_bg, args=(audio, cfg_copy),
            daemon=True).start()

    def _transcribe_bg(self, audio: np.ndarray, cfg: dict):
        t0 = time.time()
        self.root.after(0, lambda: self._status.config(text='识别中...'))
        try:
            text = transcribe_mimo(audio, cfg)
        except Exception as e:
            text = f'[Error] {e}'
        elapsed = time.time() - t0

        self._record_count += 1
        ts = time.strftime('%H:%M:%S')
        self._log(f'{ts} ({elapsed:.1f}s) {text}')

        status = f'已识别 {self._record_count} 条'
        self.root.after(0, lambda: self._status.config(text=status))

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
    app = ASRGui()
    app.run()


if __name__ == '__main__':
    main()
