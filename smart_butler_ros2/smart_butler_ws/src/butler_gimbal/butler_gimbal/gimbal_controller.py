"""
云台控制器 - 接收目标角度并控制 3 轴关节
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from butler_msgs.msg import GimbalCommand


class GimbalController(Node):
    """3 轴云台控制器"""

    def __init__(self):
        super().__init__('gimbal_controller')

        # 订阅云台控制指令
        self.command_sub = self.create_subscription(
            GimbalCommand,
            '/moss/gimbal/command',
            self.command_callback,
            10
        )

        # 仿真环境下发布到 Gazebo joint 位置控制器
        # 注意：Gazebo Fortress 使用 /world/.../joint/.../cmd_pos 话题
        self.pan_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/pan_joint/0/cmd_pos',
            10
        )
        self.tilt_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/tilt_joint/0/cmd_pos',
            10
        )
        self.roll_pub = self.create_publisher(
            Float64MultiArray,
            '/world/smart_home/model/moss/joint/roll_joint/0/cmd_pos',
            10
        )

        self.get_logger().info('云台控制器已启动')

    def command_callback(self, msg: GimbalCommand):
        """接收控制指令并转发到各关节"""
        self.get_logger().debug(
            f'云台指令: pan={msg.pan:.2f}, tilt={msg.tilt:.2f}, roll={msg.roll:.2f}'
        )

        # 发布各轴目标位置
        for pub, value in [
            (self.pan_pub, msg.pan),
            (self.tilt_pub, msg.tilt),
            (self.roll_pub, msg.roll)
        ]:
            cmd = Float64MultiArray()
            cmd.data = [float(value)]
            pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = GimbalController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
