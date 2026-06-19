string text          # 识别出的文本
float32 confidence   # 置信度 0.0 ~ 1.0
bool is_final        # 是否是最终结果
byte[] audio_data    # 原始音频数据（可选，用于传递给ASR）
int32 sample_rate    # 采样率（如16000）
