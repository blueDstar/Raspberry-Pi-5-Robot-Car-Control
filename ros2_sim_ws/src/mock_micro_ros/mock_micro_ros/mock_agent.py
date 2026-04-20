#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         MOCK MICRO-ROS AGENT — Giả lập micro-ROS Agent Bridge             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  TRONG HỆ THẬT:                                                              ║
║    - micro-ros-agent là một binary C++ chạy trên host (Raspberry Pi)         ║
║    - Kết nối với ESP32 qua serial /dev/ttyUSB0 tại baudrate 921600           ║
║    - Hoạt động như một proxy: chuyển DDS-XRCE ↔ DDS (ROS 2 native)          ║
║    - Topics ESP32 publish xuất hiện trực tiếp trên ROS 2 graph              ║
║    - Topics host publish có thể subscribe được từ ESP32                      ║
║    - Không cần code thêm: Agent tự động bridge tất cả topics                ║
║                                                                              ║
║    Lệnh thật:                                                                ║
║      micro_ros_agent serial --dev /dev/ttyUSB0 -b 921600                    ║
║      hoặc: micro_ros_agent udp4 --port 8888 -b 921600                       ║
║                                                                              ║
║  TRONG MÔ PHỎNG NÀY:                                                         ║
║    - Node Python đóng vai Agent                                               ║
║    - Hướng XUỐNG (→ Client): bridge /cmd_vel → /micro_ros/cmd_vel_in         ║
║    - Hướng LÊN (→ ROS 2): bridge /micro_ros/* → các topics ROS 2 chuẩn      ║
║    - Log rõ ràng mỗi message để học luồng dữ liệu                            ║
║                                                                              ║
║  TẠI SAO CẦN NODE NÀY?                                                       ║
║    Trong hệ thật, Agent TRONG SUỐT (transparent) với người dùng.             ║
║    Node này làm Agent HỮU HÌNH để bạn thấy rõ dữ liệu chạy qua đâu.        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

LUỒNG DỮ LIỆU QUA AGENT:

  ROS 2 Graph        Agent (this node)       micro-ROS Client (ESP32)
  ──────────         ─────────────────       ────────────────────────
  /cmd_vel      →→→  [bridge down]      →→→  /micro_ros/cmd_vel_in
                                             
  /micro_ros/encoder ←←←  [bridge up]  ←←←  /micro_ros/encoder
  /joint_states ←←←  [bridge up]       ←←←  /micro_ros/encoder
  /vel_raw      ←←←  [bridge up]       ←←←  /micro_ros/encoder
  /imu/data_raw ←←←  [bridge up]       ←←←  /micro_ros/imu
  /voltage      ←←←  [bridge up]       ←←←  /micro_ros/battery
"""

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState, Imu
from std_msgs.msg import Float32, Float32MultiArray


class MockMicroROSAgent(Node):
    """
    Giả lập micro-ROS Agent bridge.
    
    Node này là LAYER TRUNG GIAN giữa:
      - ROS 2 high-level graph (cmd_vel, joint_states, odom...)
      - micro-ROS client (mock_client.py giả lập ESP32)
    
    Trong hệ thật: Binary micro-ros-agent làm việc này tự động.
    Ở đây ta viết tường minh để học rõ cách bridge hoạt động.
    """

    def __init__(self):
        super().__init__('mock_micro_ros_agent')

        self.declare_parameter('bridge_verbose', True)
        self.declare_parameter('log_every_n', 50)  # Log mỗi n messages (tránh spam)

        self.verbose = self.get_parameter('bridge_verbose').value
        self.log_every_n = self.get_parameter('log_every_n').value

        # Counters để throttle logging
        self._cnt = {'cmd': 0, 'enc': 0, 'imu': 0, 'bat': 0}

        # ─────────────────────────────────────────────────────
        # HƯỚNG XUỐNG: ROS 2 → micro-ROS Client
        # ─────────────────────────────────────────────────────
        
        # Subscribe /cmd_vel từ ROS 2 graph (teleop, nav, square_drive...)
        self.sub_cmd_vel = self.create_subscription(
            Twist,
            '/cmd_vel',
            self._bridge_cmd_vel_down,
            10
        )

        # Publish /micro_ros/cmd_vel_in → Client (giả lập qua XRCE serial)
        self.pub_cmd_to_client = self.create_publisher(
            Twist,
            '/micro_ros/cmd_vel_in',
            10
        )

        # ─────────────────────────────────────────────────────
        # HƯỚNG LÊN: micro-ROS Client → ROS 2 Graph
        # ─────────────────────────────────────────────────────

        # Subscribe encoder từ client
        self.sub_encoder = self.create_subscription(
            JointState,
            '/micro_ros/encoder',
            self._bridge_encoder_up,
            10
        )

        # Subscribe IMU từ client
        self.sub_imu = self.create_subscription(
            Imu,
            '/micro_ros/imu',
            self._bridge_imu_up,
            10
        )

        # Subscribe battery từ client
        self.sub_battery = self.create_subscription(
            Float32,
            '/micro_ros/battery',
            self._bridge_battery_up,
            10
        )

        # Publish ra ROS 2 graph (tương đương topics mà driver thật Yahboom dùng)
        
        # /joint_states: robot_state_publisher dùng để publish TF
        self.pub_joint_states = self.create_publisher(
            JointState,
            '/joint_states',
            10
        )

        # /vel_raw: tốc độ 4 bánh dạng raw (Float32MultiArray [vFL, vRL, vFR, vRR])
        # Trong hệ thật: Rosmaster_Lib publish topic này
        self.pub_vel_raw = self.create_publisher(
            Float32MultiArray,
            '/vel_raw',
            10
        )

        # /imu/data_raw: IMU data sau khi qua Agent
        # Đây chính là topic mà IMU driver thật publish
        self.pub_imu = self.create_publisher(
            Imu,
            '/imu/data_raw',
            10
        )

        # /voltage: điện áp pin
        self.pub_voltage = self.create_publisher(
            Float32,
            '/voltage',
            10
        )

        self.get_logger().info(
            f'\n'
            f'╔════════════════════════════════════════╗\n'
            f'║  MockMicroROSAgent đã khởi động!       ║\n'
            f'║  [Giả lập micro-ros-agent binary]      ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  TRONG HỆ THẬT:                        ║\n'
            f'║  micro_ros_agent serial                ║\n'
            f'║    --dev /dev/ttyUSB0 -b 921600        ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  BRIDGE XUỐNG (→ Client):              ║\n'
            f'║  /cmd_vel → /micro_ros/cmd_vel_in      ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  BRIDGE LÊN (→ ROS 2):                 ║\n'
            f'║  /micro_ros/encoder → /joint_states    ║\n'
            f'║  /micro_ros/encoder → /vel_raw         ║\n'
            f'║  /micro_ros/imu     → /imu/data_raw    ║\n'
            f'║  /micro_ros/battery → /voltage         ║\n'
            f'╚════════════════════════════════════════╝'
        )

    # ─────────────────────────────────────────────────────
    # BRIDGE XUỐNG: /cmd_vel → /micro_ros/cmd_vel_in
    # ─────────────────────────────────────────────────────
    def _bridge_cmd_vel_down(self, msg: Twist):
        """
        Bridge lệnh điều khiển từ ROS 2 xuống micro-ROS client.
        
        TRONG HỆ THẬT:
          - Agent nhận /cmd_vel từ ROS 2 DDS graph
          - Serialize thành DDS-XRCE message
          - Gửi qua serial UART đến ESP32
          - ESP32 firmware deserialize và xử lý
        
        TRONG MÔ PHỎNG:
          - Đơn giản republish Twist message
          - Log để thấy rõ dữ liệu đi qua Agent
        """
        # Forward xuống client
        self.pub_cmd_to_client.publish(msg)

        # Throttled logging
        self._cnt['cmd'] += 1
        if self.verbose and (self._cnt['cmd'] % self.log_every_n == 1):
            self.get_logger().info(
                f'[AGENT→CLIENT] cmd_vel: '
                f'vx={msg.linear.x:.3f} m/s, '
                f'vz={msg.angular.z:.3f} rad/s'
            )

    # ─────────────────────────────────────────────────────
    # BRIDGE LÊN: Encoder → /joint_states + /vel_raw
    # ─────────────────────────────────────────────────────
    def _bridge_encoder_up(self, msg: JointState):
        """
        Bridge encoder data từ client lên ROS 2 graph.
        
        TRONG HỆ THẬT:
          - ESP32 firmware đọc encoder quadrature
          - Publish qua micro-ROS lên Agent
          - Agent forward vào ROS 2 DDS graph
          - Driver (dùng Rosmaster_Lib) nhận và tính odom
        
        Ở đây ta bridge thành 2 topics:
        1. /joint_states: để robot_state_publisher tính TF bánh
        2. /vel_raw: tốc độ 4 bánh raw (m/s), dùng cho odom
        """
        # 1. Forward joint states (robot_state_publisher cần)
        self.pub_joint_states.publish(msg)

        # 2. Tính vel_raw (m/s) từ velocity trong JointState (rad/s)
        # wheel_radius giả định 0.033m (khớp với mock_client)
        WHEEL_RADIUS = 0.033
        vel_raw_msg = Float32MultiArray()
        if len(msg.velocity) >= 4:
            vel_raw_msg.data = [
                float(msg.velocity[0] * WHEEL_RADIUS),  # FL m/s
                float(msg.velocity[1] * WHEEL_RADIUS),  # RL m/s
                float(msg.velocity[2] * WHEEL_RADIUS),  # FR m/s
                float(msg.velocity[3] * WHEEL_RADIUS),  # RR m/s
            ]
        self.pub_vel_raw.publish(vel_raw_msg)

        # Throttled logging
        self._cnt['enc'] += 1
        if self.verbose and (self._cnt['enc'] % self.log_every_n == 1):
            if len(msg.velocity) >= 4:
                self.get_logger().info(
                    f'[CLIENT→AGENT→ROS2] encoder: '
                    f'FL={msg.velocity[0]:.2f} '
                    f'RL={msg.velocity[1]:.2f} '
                    f'FR={msg.velocity[2]:.2f} '
                    f'RR={msg.velocity[3]:.2f} rad/s'
                )

    # ─────────────────────────────────────────────────────
    # BRIDGE LÊN: IMU → /imu/data_raw
    # ─────────────────────────────────────────────────────
    def _bridge_imu_up(self, msg: Imu):
        """
        Bridge IMU data từ client lên ROS 2 graph.
        
        TRONG HỆ THẬT:
          - MPU6050 → I2C → ESP32 → micro-ROS → Agent → /imu/data_raw
          - Driver thật Yahboom đọc /imu/data_raw để tính IMU yaw PID
        """
        self.pub_imu.publish(msg)

        self._cnt['imu'] += 1
        if self.verbose and (self._cnt['imu'] % self.log_every_n == 1):
            self.get_logger().debug(
                f'[CLIENT→AGENT→ROS2] imu: '
                f'gz={msg.angular_velocity.z:.4f} rad/s'
            )

    # ─────────────────────────────────────────────────────
    # BRIDGE LÊN: Battery → /voltage
    # ─────────────────────────────────────────────────────
    def _bridge_battery_up(self, msg: Float32):
        """Bridge điện áp pin lên ROS 2 graph."""
        self.pub_voltage.publish(msg)

        self._cnt['bat'] += 1
        if self.verbose and (self._cnt['bat'] % self.log_every_n == 1):
            self.get_logger().info(
                f'[CLIENT→AGENT→ROS2] battery: {msg.data:.2f} V'
            )


def main(args=None):
    rclpy.init(args=args)
    node = MockMicroROSAgent()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
