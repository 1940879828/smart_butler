"""
Smart home device simulator for Gazebo.

Simulate smart home device states, publish sensor data, and handle commands.
"""

import json
import random

from butler_msgs.msg import DeviceState
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SmartDevicesSim(Node):
    """Simulate smart home devices and their response behavior."""

    def __init__(self):
        super().__init__('smart_devices_sim')

        self.devices = {
            'light_1': {
                'type': 'light',
                'state': {
                    'on': False, 'brightness': 100, 'color_temp': 4000,
                },
            },
            'thermostat_1': {
                'type': 'thermostat',
                'state': {
                    'temperature': 25.0, 'mode': 'cool', 'target': 24.0,
                },
            },
            'curtain_1': {'type': 'curtain', 'state': {'position': 0}},
            'temp_sensor_1': {
                'type': 'sensor',
                'state': {'temperature': 25.5, 'humidity': 60},
            },
        }

        # Publisher for device states
        self.state_pub = self.create_publisher(
            DeviceState, '/moss/devices/state', 10)

        # Subscriber for device commands
        self.command_sub = self.create_subscription(
            String,
            '/moss/devices/command',
            self.command_callback,
            10
        )

        # Timer to publish states periodically
        self.timer = self.create_timer(1.0, self.publish_states)

        self.get_logger().info('Smart device simulator started')
        self.get_logger().info(
            f'Simulated devices: {list(self.devices.keys())}')

    def publish_states(self):
        """Publish all device states periodically."""
        # Simulate temperature sensor fluctuations
        temp = self.devices['temp_sensor_1']['state']['temperature']
        self.devices['temp_sensor_1']['state']['temperature'] = (
            temp + random.uniform(-0.1, 0.1))

        now = self.get_clock().now().to_msg()
        for device_id, info in self.devices.items():
            msg = DeviceState()
            msg.device_id = device_id
            msg.device_type = info['type']
            msg.state = json.dumps(info['state'])
            msg.timestamp = now
            self.state_pub.publish(msg)

    def command_callback(self, msg: String):
        """Handle incoming device control commands."""
        try:
            command = json.loads(msg.data)
            device_id = command.get('device_id')
            params = command.get('params', {})

            if device_id in self.devices:
                old_state = self.devices[device_id]['state'].copy()
                self.devices[device_id]['state'].update(params)
                self.get_logger().info(
                    f'Device {device_id} state changed: '
                    f'{old_state} -> {self.devices[device_id]["state"]}'
                )
            else:
                self.get_logger().warn(f'Unknown device: {device_id}')
        except (json.JSONDecodeError, KeyError) as e:
            self.get_logger().error(f'Command parse error: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = SmartDevicesSim()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
