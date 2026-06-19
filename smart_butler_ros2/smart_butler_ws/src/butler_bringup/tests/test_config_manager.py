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
