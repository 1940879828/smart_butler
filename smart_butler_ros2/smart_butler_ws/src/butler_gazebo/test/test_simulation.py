"""
Gazebo simulation integration tests.

These tests require Gazebo, smart_devices_sim, and bridge nodes to be running.
Run manually during simulation verification.
"""

import time

from butler_msgs.msg import DeviceState, GimbalCommand
import pytest
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


class TestSimulation(Node):
    """Test helper node for simulation verification."""

    def __init__(self):
        super().__init__('test_simulation')
        self.received_images = []
        self.received_states = []

        self.image_sub = self.create_subscription(
            Image, '/moss/camera/image', self._on_image, 10
        )
        self.state_sub = self.create_subscription(
            DeviceState, '/moss/devices/state', self._on_state, 10
        )
        self.gimbal_pub = self.create_publisher(
            GimbalCommand, '/moss/gimbal/command', 10
        )

    def _on_image(self, msg):
        self.received_images.append(msg)

    def _on_state(self, msg):
        self.received_states.append(msg)


@pytest.fixture(scope='module')
def test_node():
    rclpy.init()
    node = TestSimulation()
    yield node
    node.destroy_node()
    rclpy.shutdown()


def test_camera_image_received(test_node):
    """Verify camera images are received from Gazebo."""
    time.sleep(2)
    rclpy.spin_once(test_node, timeout_sec=1.0)
    assert len(test_node.received_images) > 0, 'No camera images received'


def test_device_state_received(test_node):
    """Verify device states are published."""
    time.sleep(2)
    rclpy.spin_once(test_node, timeout_sec=1.0)
    assert len(test_node.received_states) > 0, 'No device states received'


def test_gimbal_command_sent(test_node):
    """Verify gimbal commands can be published without error."""
    cmd = GimbalCommand()
    cmd.pan = 0.5
    cmd.tilt = 0.3
    cmd.roll = 0.0
    test_node.gimbal_pub.publish(cmd)
    time.sleep(0.5)
    # Publishing without exception counts as pass
