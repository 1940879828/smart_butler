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
