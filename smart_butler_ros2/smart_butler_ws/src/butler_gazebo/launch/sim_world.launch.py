import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch_ros.actions import Node


def generate_launch_description():
    pkg_gazebo = get_package_share_directory('butler_gazebo')
    pkg_description = get_package_share_directory('butler_description')

    world_file = os.path.join(pkg_gazebo, 'worlds', 'smart_home.sdf')
    urdf_file = os.path.join(pkg_description, 'urdf', 'moss.urdf.xacro')

    # 直接启动 Gazebo 服务器
    gz_sim = ExecuteProcess(
        cmd=['gz', 'sim', '-s', '-r', world_file],
        name='gz_sim',
        output='screen'
    )

    # 生成机器人模型（等 Gazebo 就绪后）
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'moss',
            '-x', '0.0', '-y', '0.0', '-z', '2.45',
            '-file', urdf_file,
        ],
        output='screen'
    )

    # ROS-Gazebo 桥接 - 摄像头图像
    bridge_camera = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/moss/camera/image_raw@sensor_msgs/msg/Image@gz.msgs.Image',
        ],
        output='screen'
    )

    return LaunchDescription([
        gz_sim,
        TimerAction(
            period=8.0,
            actions=[spawn_robot]
        ),
        bridge_camera,
    ])
