"""
仿真摄像头节点 - 从 Gazebo 话题读取图像并转发
作为硬件抽象层的 sim 版本实现
"""

import datetime
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import cv2
from cv_bridge import CvBridge


class SimCameraNode(Node):
    """仿真摄像头节点"""

    def __init__(self):
        super().__init__('sim_camera_node')

        # 声明参数
        self.declare_parameter('fps', 30)
        self.declare_parameter('resolution', [640, 480])
        self.declare_parameter('enable_display', False)

        self.bridge = CvBridge()

        # 订阅 Gazebo 摄像头话题
        self.subscription = self.create_subscription(
            Image,
            '/moss/camera/image_raw',
            self.image_callback,
            10
        )

        # 发布处理后的图像
        self.publisher = self.create_publisher(
            Image,
            '/moss/camera/image_processed',
            10
        )

        self.get_logger().info('仿真摄像头节点已启动')

    def image_callback(self, msg: Image):
        """接收 Gazebo 图像并转发"""
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

            # 添加时间戳水印
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(cv_image, timestamp, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # 发布处理后的图像
            processed_msg = self.bridge.cv2_to_imgmsg(cv_image, 'bgr8')
            processed_msg.header = msg.header
            self.publisher.publish(processed_msg)

        except Exception as e:
            self.get_logger().error(f'图像处理错误: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = SimCameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
