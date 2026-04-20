#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           MOCK MICRO-ROS CLIENT — Giả lập Firmware ESP32/MCU              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  TRONG HỆ THẬT:                                                              ║
║    - Chạy trên ESP32 hoặc STM32 (MCU)                                        ║
║    - Firmware viết bằng C/C++ dùng micro-ROS API                             ║
║    - Giao tiếp với ROS 2 qua DDS-XRCE protocol (serial/UDP)                  ║
║    - Đọc encoder quadrature thật từ 4 motor                                  ║
║    - Đọc IMU MPU6050 qua I2C                                                  ║
║    - Gửi tín hiệu PWM đến motor driver IC                                    ║
║    - Chạy Motor PID loop ở tần số cao (kHz)                                  ║
║                                                                              ║
║  TRONG MÔ PHỎNG NÀY:                                                         ║
║    - Chạy như một ROS 2 Python node bình thường                               ║
║    - Subscribe /micro_ros/cmd_vel_in (giả lập nhận lệnh qua micro-ROS)        ║
║    - Tính kinematics 4 bánh → tốc độ từng bánh                               ║
║    - Tích phân → encoder giả lập                                              ║
║    - Publish /micro_ros/encoder, /micro_ros/imu, /micro_ros/battery           ║
║                                                                              ║
║  ĐIỂM KHÁC BIỆT SO VỚI PHẦN CỨNG THẬT:                                      ║
║    - Không có overhead DDS-XRCE, không có serial latency                     ║
║    - Không có Motor PID (dùng kinematics lý tưởng)                           ║
║    - Encoder = tích phân trực tiếp (không có slip, quantization noise)       ║
║    - IMU = Gaussian noise thuần túy (không có drift, temperature effect)     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

KINEMATICS 4 BÁNH (từ firmware thật Yahboom):
  A = khoảng cách nửa trục dọc (wheel_base / 2)
  B = khoảng cách nửa trục ngang (wheel_track / 2)

  Vx  = vận tốc tiến (m/s)
  Vz  = vận tốc quay (rad/s)

  Motor1 (FL trái trước)  = Vm1 = Vx - Vz * (A + B)
  Motor2 (RL trái sau)    = Vm2 = Vx - Vz * (A + B)
  Motor3 (FR phải trước)  = Vm3 = Vx + Vz * (A + B)
  Motor4 (RR phải sau)    = Vm4 = Vx + Vz * (A + B)

  => Xe 4 bánh thường (không mecanum): trái/phải cùng tốc độ trong từng bên.
"""

import math
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState, Imu
from std_msgs.msg import Float32
import numpy as np


class MockMicroROSClient(Node):
    """
    Giả lập firmware micro-ROS trên MCU (ESP32/STM32).
    
    Node này đóng vai PHẦN CỨNG THẬT:
      - Board control Yahboom
      - 4 motor với encoder
      - IMU MPU6050
      - Pin/battery monitor
    """

    def __init__(self):
        super().__init__('mock_micro_ros_client')

        # ─────────────────────────────────────────────────
        # KHAI BÁO PARAMETERS (tương đương config firmware thật)
        # Trong hệ thật: cấu hình qua CAR_TYPE, MOTOR_PID, v.v.
        # ─────────────────────────────────────────────────
        self.declare_parameter('car_type', 'yahboom_4wd')
        self.declare_parameter('wheel_radius', 0.033)       # m - bán kính bánh
        self.declare_parameter('wheel_base', 0.150)         # m - khoảng cách trục dọc
        self.declare_parameter('wheel_track', 0.190)        # m - khoảng cách trục ngang
        self.declare_parameter('ticks_per_rev', 1320)       # ticks/vòng (encoder thật 11 ticks * 30 ratio * 4)
        self.declare_parameter('publish_rate', 50.0)        # Hz
        self.declare_parameter('imu_noise_std', 0.01)       # rad/s^2 Gaussian noise
        self.declare_parameter('battery_voltage', 12.0)     # V giả lập
        self.declare_parameter('battery_noise_std', 0.05)   # V noise
        self.declare_parameter('ros_namespace', 'robot1')
        self.declare_parameter('domain_id', 20)             # ROS_DOMAIN_ID như hệ thật

        # Đọc parameters
        self.wheel_radius   = self.get_parameter('wheel_radius').value
        self.wheel_base     = self.get_parameter('wheel_base').value
        self.wheel_track    = self.get_parameter('wheel_track').value
        self.ticks_per_rev  = self.get_parameter('ticks_per_rev').value
        self.publish_rate   = self.get_parameter('publish_rate').value
        self.imu_noise_std  = self.get_parameter('imu_noise_std').value
        self.battery_voltage= self.get_parameter('battery_voltage').value
        self.batt_noise_std = self.get_parameter('battery_noise_std').value

        # A và B trong công thức kinematics Yahboom
        # (A+B) = half_track = khoảng cách từ tâm đến bánh theo phương ngang
        self.A = self.wheel_base  / 2.0   # nửa trục dọc
        self.B = self.wheel_track / 2.0   # nửa trục ngang

        # ─────────────────────────────────────────────────
        # TRẠNG THÁI NỘI BỘ (tương đương biến toàn cục trong firmware)
        # ─────────────────────────────────────────────────
        # Tốc độ bánh hiện tại (rad/s)
        self.wheel_vel = {
            'fl': 0.0,  # Motor1 - trái trước
            'rl': 0.0,  # Motor2 - trái sau
            'fr': 0.0,  # Motor3 - phải trước
            'rr': 0.0,  # Motor4 - phải sau
        }
        # Vị trí góc tích lũy (rad) → encoder ticks
        self.wheel_pos = {k: 0.0 for k in self.wheel_vel}

        # Yaw tích phân từ angular velocity
        self.yaw = 0.0

        # Thời điểm nhận cmd cuối (để timeout)
        self.last_cmd_time = self.get_clock().now()
        self.cmd_timeout_sec = 0.5  # Nếu 0.5s không có lệnh → dừng

        # ─────────────────────────────────────────────────
        # SUBSCRIBERS
        # Topic /micro_ros/cmd_vel_in: nhận từ mock_agent
        # Trong hệ thật: micro-ROS nhận publish từ Agent qua XRCE
        # ─────────────────────────────────────────────────
        self.sub_cmd = self.create_subscription(
            Twist,
            '/micro_ros/cmd_vel_in',
            self._on_cmd_vel,
            10
        )

        # ─────────────────────────────────────────────────
        # PUBLISHERS
        # Trong hệ thật: micro-ROS publish lên Agent qua XRCE serial
        # ─────────────────────────────────────────────────
        
        # Encoder 4 bánh → dùng JointState (position=rad, velocity=rad/s)
        self.pub_encoder = self.create_publisher(
            JointState,
            '/micro_ros/encoder',
            10
        )

        # IMU data thô (tương đương MPU6050 output)
        self.pub_imu = self.create_publisher(
            Imu,
            '/micro_ros/imu',
            10
        )

        # Battery voltage
        self.pub_battery = self.create_publisher(
            Float32,
            '/micro_ros/battery',
            10
        )

        # ─────────────────────────────────────────────────
        # TIMER: Publish định kỳ (tương đương main loop của firmware)
        # Firmware thật chạy ở tần số cao hơn (~1kHz cho PID)
        # nhưng publish micro-ROS ở ~50Hz
        # ─────────────────────────────────────────────────
        self.dt = 1.0 / self.publish_rate
        self.timer = self.create_timer(self.dt, self._publish_sensor_data)

        self.get_logger().info(
            f'\n'
            f'╔════════════════════════════════════════╗\n'
            f'║  MockMicroROSClient đã khởi động!      ║\n'
            f'║  [Giả lập firmware ESP32/MCU]          ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  wheel_radius : {self.wheel_radius:.3f} m             ║\n'
            f'║  wheel_base   : {self.wheel_base:.3f} m             ║\n'
            f'║  wheel_track  : {self.wheel_track:.3f} m             ║\n'
            f'║  A+B          : {self.A + self.B:.3f} m             ║\n'
            f'║  ticks/rev    : {self.ticks_per_rev}              ║\n'
            f'║  publish_rate : {self.publish_rate:.0f} Hz              ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  Subscribe: /micro_ros/cmd_vel_in      ║\n'
            f'║  Publish  : /micro_ros/encoder         ║\n'
            f'║  Publish  : /micro_ros/imu             ║\n'
            f'║  Publish  : /micro_ros/battery         ║\n'
            f'╚════════════════════════════════════════╝'
        )

    # ─────────────────────────────────────────────────────
    # CALLBACK: Nhận lệnh điều khiển từ mock_agent
    # ─────────────────────────────────────────────────────
    def _on_cmd_vel(self, msg: Twist):
        """
        Xử lý lệnh /cmd_vel.
        
        KINEMATICS 4 BÁNH YAHBOOM:
        ─────────────────────────
        Vx  = linear.x  (m/s, tiến/lùi)
        Vz  = angular.z (rad/s, quay trái/phải)
        Vy  = linear.y  → KHÔNG DÙNG (xe không phải mecanum)

        Công thức từ firmware Yahboom thật:
          Vm_left  = Vx - Vz * (A + B)
          Vm_right = Vx + Vz * (A + B)

        Tất cả bánh trái có cùng tốc độ, tất cả bánh phải có cùng tốc độ.
        Đây là đặc điểm của differential/skid-steer drive 4 bánh.
        """
        vx = msg.linear.x       # m/s
        vz = msg.angular.z      # rad/s
        # Vy = msg.linear.y     # Bỏ qua!

        # Tốc độ tuyến tính tại bề mặt bánh (m/s)
        v_left  = vx - vz * (self.A + self.B)   # Motor1(FL) & Motor2(RL)
        v_right = vx + vz * (self.A + self.B)   # Motor3(FR) & Motor4(RR)

        # Chuyển sang rad/s (để ra đơn vị encoder)
        w_left  = v_left  / self.wheel_radius
        w_right = v_right / self.wheel_radius

        # Gán cho từng bánh
        self.wheel_vel['fl'] = w_left   # Motor1: trái trước
        self.wheel_vel['rl'] = w_left   # Motor2: trái sau
        self.wheel_vel['fr'] = w_right  # Motor3: phải trước
        self.wheel_vel['rr'] = w_right  # Motor4: phải sau

        self.last_cmd_time = self.get_clock().now()

        self.get_logger().debug(
            f'[CLIENT] cmd_vel: vx={vx:.3f} vz={vz:.3f} → '
            f'w_L={w_left:.3f} rad/s  w_R={w_right:.3f} rad/s'
        )

    # ─────────────────────────────────────────────────────
    # TIMER CALLBACK: Publish sensor data
    # Tương đương main loop của firmware ESP32
    # ─────────────────────────────────────────────────────
    def _publish_sensor_data(self):
        """Publish encoder, IMU, battery định kỳ."""
        now = self.get_clock().now()

        # Kiểm tra timeout lệnh (safety feature)
        elapsed = (now - self.last_cmd_time).nanoseconds * 1e-9
        if elapsed > self.cmd_timeout_sec:
            # Dừng bánh nếu không có lệnh mới
            for k in self.wheel_vel:
                self.wheel_vel[k] = 0.0

        # Tích phân vị trí bánh (kinematics lý tưởng)
        for k in self.wheel_vel:
            self.wheel_pos[k] += self.wheel_vel[k] * self.dt

        # Tích phân yaw từ angular velocity
        # (angular velocity của robot = (v_right - v_left) / wheel_track)
        w_left  = self.wheel_vel['fl']  # hoặc rl, cùng giá trị
        w_right = self.wheel_vel['fr']  # hoặc rr, cùng giá trị
        omega = (w_right - w_left) * self.wheel_radius / self.wheel_track
        self.yaw += omega * self.dt

        # Publish encoder
        self._publish_encoder(now)

        # Publish IMU
        self._publish_imu(now, omega)

        # Publish battery
        self._publish_battery()

    def _publish_encoder(self, stamp):
        """
        Publish trạng thái 4 bánh dưới dạng JointState.
        
        Trong hệ thật: encoder quadrature gửi xung A/B,
        firmware đếm xung và publish ticks hoặc vị trí góc.
        
        Topics trong hệ thật Yahboom:
          /joint_states (sau khi qua driver)
        """
        msg = JointState()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = ''

        # 4 bánh theo thứ tự Motor1,2,3,4
        msg.name = ['wheel_fl_joint', 'wheel_rl_joint',
                    'wheel_fr_joint', 'wheel_rr_joint']

        # Position (rad) - tích phân encoder ticks
        msg.position = [
            self.wheel_pos['fl'],
            self.wheel_pos['rl'],
            self.wheel_pos['fr'],
            self.wheel_pos['rr'],
        ]

        # Velocity (rad/s) - từ kinematics
        msg.velocity = [
            self.wheel_vel['fl'],
            self.wheel_vel['rl'],
            self.wheel_vel['fr'],
            self.wheel_vel['rr'],
        ]

        # Effort (Nm) - 0.0 trong mô phỏng (không có PID)
        msg.effort = [0.0, 0.0, 0.0, 0.0]

        self.pub_encoder.publish(msg)

    def _publish_imu(self, stamp, omega: float):
        """
        Publish IMU data giả lập.
        
        Trong hệ thật: MPU6050 qua I2C, firmware đọc và publish.
        Topics:
          /imu/data_raw (sau Agent bridge)
        
        Noise model:
          - Angular velocity: Gaussian(mean=omega, std=imu_noise_std)
          - Linear acceleration: trọng lực + Gaussian noise
          - Orientation: tính từ yaw tích phân (không có drift model)
        """
        msg = Imu()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = 'imu_link'

        # Angular velocity (rad/s) với Gaussian noise
        noise = np.random.normal(0, self.imu_noise_std)
        msg.angular_velocity.x = float(np.random.normal(0, self.imu_noise_std * 0.1))
        msg.angular_velocity.y = float(np.random.normal(0, self.imu_noise_std * 0.1))
        msg.angular_velocity.z = float(omega + noise)

        # Covariance matrix (diagonal)
        std2 = self.imu_noise_std ** 2
        msg.angular_velocity_covariance = [
            std2, 0, 0,
            0, std2, 0,
            0, 0, std2
        ]

        # Linear acceleration (m/s^2) - giả lập robot trên mặt phẳng
        msg.linear_acceleration.x = float(np.random.normal(0, self.imu_noise_std))
        msg.linear_acceleration.y = float(np.random.normal(0, self.imu_noise_std))
        msg.linear_acceleration.z = float(9.81 + np.random.normal(0, self.imu_noise_std * 0.1))

        acc_std2 = (self.imu_noise_std * 0.5) ** 2
        msg.linear_acceleration_covariance = [
            acc_std2, 0, 0,
            0, acc_std2, 0,
            0, 0, acc_std2
        ]

        # Orientation từ yaw tích phân (quaternion)
        cy = math.cos(self.yaw * 0.5)
        sy = math.sin(self.yaw * 0.5)
        msg.orientation.w = cy
        msg.orientation.x = 0.0
        msg.orientation.y = 0.0
        msg.orientation.z = sy

        # Orientation covariance (-1 = không có)
        # MCU thật cung cấp raw data, không compute orientation
        msg.orientation_covariance[0] = -1.0

        self.pub_imu.publish(msg)

    def _publish_battery(self):
        """
        Publish điện áp pin giả lập.
        
        Trong hệ thật: ADC đọc điện áp qua voltage divider.
        Topic: /voltage
        """
        msg = Float32()
        noise = float(np.random.normal(0, self.batt_noise_std))
        msg.data = float(self.battery_voltage + noise)
        self.pub_battery.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MockMicroROSClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
