"""
语音服务测试GUI
基于tkinter的简单桌面测试工具
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import threading
import json
import base64
import numpy as np
import httpx
from datetime import datetime


class VoiceServiceTestGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MOSS 语音服务测试工具")
        self.root.geometry("800x600")
        
        # 服务地址
        self.base_url = "http://localhost:8001"
        
        self.create_widgets()
        
    def create_widgets(self):
        # 顶部连接状态
        status_frame = ttk.Frame(self.root, padding="5")
        status_frame.pack(fill=tk.X)
        
        ttk.Label(status_frame, text="服务地址:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar(value=self.base_url)
        url_entry = ttk.Entry(status_frame, textvariable=self.url_var, width=30)
        url_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(status_frame, text="连接测试", command=self.test_connection).pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(status_frame, text="● 未连接", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Notebook标签页
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: ASR测试
        asr_frame = ttk.Frame(notebook, padding="10")
        notebook.add(asr_frame, text="语音识别 (ASR)")
        self.create_asr_tab(asr_frame)
        
        # Tab 2: 健康检查
        health_frame = ttk.Frame(notebook, padding="10")
        notebook.add(health_frame, text="健康检查")
        self.create_health_tab(health_frame)
        
        # Tab 3: 服务信息
        info_frame = ttk.Frame(notebook, padding="10")
        notebook.add(info_frame, text="服务信息")
        self.create_info_tab(info_frame)
        
        # 底部日志
        log_frame = ttk.LabelFrame(self.root, text="请求日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def create_asr_tab(self, parent):
        # 音频输入方式
        input_frame = ttk.LabelFrame(parent, text="音频输入", padding="5")
        input_frame.pack(fill=tk.X, pady=5)
        
        self.audio_mode = tk.StringVar(value="generate")
        ttk.Radiobutton(input_frame, text="生成测试音频", variable=self.audio_mode, 
                        value="generate", command=self.on_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(input_frame, text="从文件加载", variable=self.audio_mode,
                        value="file", command=self.on_mode_change).pack(anchor=tk.W)
        
        file_frame = ttk.Frame(input_frame)
        file_frame.pack(fill=tk.X, pady=2)
        self.file_path = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_path, state=tk.DISABLED)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_btn = ttk.Button(file_frame, text="浏览", command=self.browse_file, state=tk.DISABLED)
        self.browse_btn.pack(side=tk.LEFT, padx=5)
        
        # 参数设置
        param_frame = ttk.LabelFrame(parent, text="参数", padding="5")
        param_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(param_frame, text="语言:").grid(row=0, column=0, sticky=tk.W)
        self.lang_var = tk.StringVar(value="zh")
        ttk.Combobox(param_frame, textvariable=self.lang_var, values=["zh", "en"], 
                     width=10, state="readonly").grid(row=0, column=1, padx=5)
        
        ttk.Label(param_frame, text="音频时长(秒):").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.duration_var = tk.StringVar(value="2")
        ttk.Spinbox(param_frame, from_=0.5, to=30, increment=0.5, 
                    textvariable=self.duration_var, width=5).grid(row=0, column=3, padx=5)
        
        ttk.Label(param_frame, text="采样率:").grid(row=1, column=0, sticky=tk.W)
        self.sr_var = tk.StringVar(value="16000")
        ttk.Combobox(param_frame, textvariable=self.sr_var, 
                     values=["8000", "16000", "22050", "44100"], width=10, state="readonly").grid(row=1, column=1, padx=5)
        
        # 发送按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="发送识别请求", command=self.send_asr_request).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="清空结果", command=lambda: self.result_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=10)
        
        # 结果显示
        result_frame = ttk.LabelFrame(parent, text="识别结果", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=6)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
    def create_health_tab(self, parent):
        ttk.Button(parent, text="刷新健康状态", command=self.check_health).pack(anchor=tk.W, pady=5)
        
        self.health_text = scrolledtext.ScrolledText(parent, height=15, state=tk.DISABLED)
        self.health_text.pack(fill=tk.BOTH, expand=True)
        
    def create_info_tab(self, parent):
        ttk.Button(parent, text="获取服务信息", command=self.get_service_info).pack(anchor=tk.W, pady=5)
        
        self.info_text = scrolledtext.ScrolledText(parent, height=15, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
    def on_mode_change(self):
        if self.audio_mode.get() == "file":
            self.file_entry.config(state=tk.NORMAL)
            self.browse_btn.config(state=tk.NORMAL)
        else:
            self.file_entry.config(state=tk.DISABLED)
            self.browse_btn.config(state=tk.DISABLED)
            
    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav"), ("All files", "*.*")])
        if path:
            self.file_path.set(path)
            
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def set_result(self, text_widget, content):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", content)
        text_widget.config(state=tk.DISABLED)
        
    def run_async(self, func, *args):
        thread = threading.Thread(target=func, args=args, daemon=True)
        thread.start()
        
    def test_connection(self):
        def _test():
            try:
                self.log(f"连接测试: {self.url_var.get()}")
                r = httpx.get(f"{self.url_var.get()}/health", timeout=5)
                if r.status_code == 200:
                    self.status_label.config(text="● 已连接", foreground="green")
                    self.log("连接成功!")
                else:
                    self.status_label.config(text="● 错误", foreground="red")
                    self.log(f"连接失败: {r.status_code}")
            except Exception as e:
                self.status_label.config(text="● 未连接", foreground="red")
                self.log(f"连接失败: {e}")
        self.run_async(_test)
        
    def send_asr_request(self):
        def _send():
            try:
                base_url = self.url_var.get()
                
                # 准备音频数据
                if self.audio_mode.get() == "generate":
                    sr = int(self.sr_var.get())
                    duration = float(self.duration_var.get())
                    samples = int(sr * duration)
                    # 生成带噪声的测试音频
                    t = np.linspace(0, duration, samples, dtype=np.float32)
                    audio = (np.sin(2 * np.pi * 440 * t) * 0.3 + 
                            np.random.randn(samples) * 0.01).astype(np.float32)
                    audio_int16 = (audio * 32767).astype(np.int16)
                    audio_b64 = base64.b64encode(audio_int16.tobytes()).decode()
                    self.log(f"生成测试音频: {duration}秒, {sr}Hz")
                else:
                    path = self.file_path.get()
                    if not path:
                        self.log("请选择音频文件")
                        return
                    import soundfile as sf
                    audio, sr = sf.read(path, dtype='int16')
                    if len(audio.shape) > 1:
                        audio = audio[:, 0]  # 取单声道
                    audio_b64 = base64.b64encode(audio.tobytes()).decode()
                    self.log(f"加载文件: {path}")
                
                # 发送请求
                self.log("发送ASR请求...")
                r = httpx.post(
                    f"{base_url}/asr/transcribe",
                    json={
                        "audio": audio_b64,
                        "language": self.lang_var.get(),
                        "sample_rate": int(self.sr_var.get()),
                        "encoding": "int16"
                    },
                    timeout=30
                )
                
                if r.status_code == 200:
                    result = r.json()
                    display = json.dumps(result, indent=2, ensure_ascii=False)
                    self.set_result(self.result_text, display)
                    self.log(f"识别完成: '{result['text']}' (耗时 {result['duration']:.2f}秒)")
                else:
                    self.set_result(self.result_text, f"错误: {r.status_code}\n{r.text}")
                    self.log(f"请求失败: {r.status_code}")
                    
            except Exception as e:
                self.set_result(self.result_text, f"异常: {e}")
                self.log(f"请求异常: {e}")
                
        self.run_async(_send)
        
    def check_health(self):
        def _check():
            try:
                self.log("获取健康状态...")
                r = httpx.get(f"{self.url_var.get()}/health", timeout=10)
                if r.status_code == 200:
                    display = json.dumps(r.json(), indent=2, ensure_ascii=False)
                    self.set_result(self.health_text, display)
                    self.log("健康检查完成")
                else:
                    self.set_result(self.health_text, f"错误: {r.status_code}")
            except Exception as e:
                self.set_result(self.health_text, f"异常: {e}")
                self.log(f"健康检查失败: {e}")
        self.run_async(_check)
        
    def get_service_info(self):
        def _get():
            try:
                self.log("获取服务信息...")
                r = httpx.get(f"{self.url_var.get()}/info", timeout=10)
                if r.status_code == 200:
                    display = json.dumps(r.json(), indent=2, ensure_ascii=False)
                    self.set_result(self.info_text, display)
                    self.log("获取信息完成")
                else:
                    self.set_result(self.info_text, f"错误: {r.status_code}")
            except Exception as e:
                self.set_result(self.info_text, f"异常: {e}")
                self.log(f"获取信息失败: {e}")
        self.run_async(_get)


def main():
    root = tk.Tk()
    app = VoiceServiceTestGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()