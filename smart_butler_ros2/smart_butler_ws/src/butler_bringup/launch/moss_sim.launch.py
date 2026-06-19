import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # 配置路径
    pkg_bringup = get_package_share_directory('butler_bringup')
    config_sim = os.path.join(pkg_bringup, '..', '..', 'config', 'sim.yaml')

    use_sim = LaunchConfiguration('use_sim', default='true')

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim',
            default_value='true',
            description='Run in simulation mode'
        ),
        DeclareLaunchArgument(
            'config_file',
            default_value=config_sim,
            description='Path to YAML config file'
        ),
        # Stage 2: Audio and Voice nodes (feature-gated)
        # Uncomment to auto-launch; otherwise start manually:
        #   ros2 run butler_audio mic_node
        #   ros2 run butler_audio speaker_node
        #   ros2 run butler_voice asr_client
        #   ros2 run butler_voice tts_client
        # Node(package='butler_audio', executable='mic_node', output='screen'),
        # Node(package='butler_audio', executable='speaker_node', output='screen'),
        # Node(package='butler_voice', executable='asr_client', output='screen'),
        # Node(package='butler_voice', executable='tts_client', output='screen'),
    ])
