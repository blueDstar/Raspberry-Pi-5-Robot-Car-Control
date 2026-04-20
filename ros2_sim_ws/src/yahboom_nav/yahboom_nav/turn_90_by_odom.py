#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      TURN 90 BY ODOM — Quay 90° dùng odometry feedback (closed-loop)      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  SO SÁNH VỚI square_drive.py (time-based):                                 ║
║                                                                              ║
║  Time-based (open-loop):                                                    ║
║    - Đặt angular.z = ω, chờ T = 90°/ω giây                                 ║
║    - ĐƠN GIẢN nhưng KHÔNG CHÍNH XÁC                                         ║
║    - Sai khi có trượt bánh, tải khác nhau, hoặc sensor delay                ║
║                                                                              ║
║  Odom-based (closed-loop):                                                  ║
║    - Subscribe /odom, lấy yaw hiện tại                                      ║
║    - So sánh yaw hiện tại với target_yaw (yaw_start + 90°)                  ║
║    - Điều chỉnh angular.z theo proportional controller                      ║
║    - CHÍNH XÁC hơn vì có feedback, nhưng phụ thuộc chất lượng /odom        ║
║                                                                              ║
║  THUẬT TOÁN:                                                                 ║
║    1. Ghi nhận yaw_start từ /odom                                            ║
║    2. target_yaw = yaw_start + π/2 (90°)                                    ║
║    3. Proportional control: ω = Kp * (target_yaw - yaw_current)             ║
║    4. Dừng khi |error| < tolerance (0.02 rad ≈ 1.1°)                       ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


def quat_to_yaw(orientation) -> float:
    """Chuyển quaternion sang yaw angle (rad)."""
    x = orientation.x
    y = orientation.y
    z = orientation.z
    w = orientation.w
    # Công thức từ quaternion → Euler yaw
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def normalize_angle(angle: float) -> float:
    """Normalize angle về khoảng [-π, π]."""
    while angle >  math.pi: angle -= 2 * math.pi
    while angle < -math.pi: angle += 2 * math.pi
    return angle


class Turn90ByOdomNode(Node):
    """
    Quay robot đúng 90° dùng odometry feedback (closed-loop control).
    
    Đây là ví dụ đơn giản nhất về P-controller dùng /odom.
    Trong hệ thật, Yahboom driver dùng IMU_YAW_PID về cơ bản tương tự,
    nhưng dùng IMU thay vì odom.
    """

    def __init__(self):
        super().__init__('turn_90_by_odom')

        # ─────────────────────────────────────────────────
        # PARAMETERS
        # ─────────────────────────────────────────────────
        self.declare_parameter('turn_angle_deg', 90.0)    # Góc cần quay (độ)
        self.declare_parameter('angular_speed_max', 0.4)  # rad/s tối đa
        self.declare_parameter('angular_speed_min', 0.08) # rad/s tối thiểu (deadband)
        self.declare_parameter('kp', 1.5)                 # Proportional gain
        self.declare_parameter('tolerance_deg', 1.5)      # Dung sai góc (độ)
        self.declare_parameter('turn_direction', 1)       # 1=trái, -1=phải

        turn_deg  = self.get_parameter('turn_angle_deg').value
        self.turn_rad       = math.radians(turn_deg)
        self.speed_max      = self.get_parameter('angular_speed_max').value
        self.speed_min      = self.get_parameter('angular_speed_min').value
        self.kp             = self.get_parameter('kp').value
        self.tolerance      = math.radians(self.get_parameter('tolerance_deg').value)
        self.turn_direction = self.get_parameter('turn_direction').value

        # ─────────────────────────────────────────────────
        # STATE MACHINE
        # ─────────────────────────────────────────────────
        # States: WAIT_ODOM → TURNING → DONE
        self.state = 'WAIT_ODOM'
        self.yaw_start  = None
        self.yaw_target = None
        self.current_yaw = None

        # ─────────────────────────────────────────────────
        # PUB / SUB
        # ─────────────────────────────────────────────────
        self.pub_cmd = self.create_publisher(Twist, '/cmd_vel', 10)

        self.sub_odom = self.create_subscription(
            Odometry,
            '/odom',
            self._on_odom,
            10
        )

        # Control loop timer (20Hz)
        self.timer = self.create_timer(0.05, self._control_loop)

        self.get_logger().info(
            f'\n'
            f'┌─────────────────────────────────────┐\n'
            f'│  Turn90ByOdom — Closed-loop control │\n'
            f'├─────────────────────────────────────┤\n'
            f'│  turn_angle  : {turn_deg:.1f}°               │\n'
            f'│  turn_dir    : {"trái (CCW)" if self.turn_direction > 0 else "phải (CW)"}          │\n'
            f'│  Kp          : {self.kp:.2f}                │\n'
            f'│  tolerance   : {math.degrees(self.tolerance):.1f}°               │\n'
            f'│  speed_max   : {self.speed_max:.2f} rad/s        │\n'
            f'│  speed_min   : {self.speed_min:.2f} rad/s        │\n'
            f'├─────────────────────────────────────┤\n'
            f'│  Subscribe: /odom                   │\n'
            f'│  Publish  : /cmd_vel                │\n'
            f'└─────────────────────────────────────┘\n'
            f'Chờ /odom data...'
        )

    def _on_odom(self, msg: Odometry):
        """Nhận yaw từ odometry."""
        self.current_yaw = quat_to_yaw(msg.pose.pose.orientation)

        if self.state == 'WAIT_ODOM':
            self.yaw_start  = self.current_yaw
            self.yaw_target = normalize_angle(
                self.yaw_start + self.turn_direction * self.turn_rad
            )
            self.state = 'TURNING'
            self.get_logger().info(
                f'🎯 Bắt đầu quay!\n'
                f'   yaw_start  = {math.degrees(self.yaw_start):.2f}°\n'
                f'   yaw_target = {math.degrees(self.yaw_target):.2f}°\n'
                f'   Δ = {math.degrees(self.turn_rad):.1f}°'
            )

    def _control_loop(self):
        """
        Proportional Controller cho góc quay.
        
        P-Controller:
          error = target_yaw - current_yaw  (cần normalize!)
          u = Kp * error
          u = clamp(u, speed_min, speed_max)
        """
        if self.state == 'WAIT_ODOM':
            return

        if self.state == 'DONE':
            return

        if self.current_yaw is None:
            return

        # Tính error (với normalize để tránh wrap-around)
        error = normalize_angle(self.yaw_target - self.current_yaw)

        self.get_logger().debug(
            f'[TURN] yaw={math.degrees(self.current_yaw):.2f}° '
            f'target={math.degrees(self.yaw_target):.2f}° '
            f'error={math.degrees(error):.2f}°'
        )

        # Kiểm tra đã đến đích chưa
        if abs(error) < self.tolerance:
            self._stop()
            self.state = 'DONE'
            self.get_logger().info(
                f'✅ Đã quay xong!\n'
                f'   Yaw cuối  = {math.degrees(self.current_yaw):.2f}°\n'
                f'   Yaw target= {math.degrees(self.yaw_target):.2f}°\n'
                f'   Error     = {math.degrees(error):.2f}°\n'
                f'\n'
                f'💡 So sánh: time-based sẽ có error lớn hơn nếu có slip!'
            )
            return

        # Proportional control
        u = self.kp * error

        # Clamp: không được nhỏ hơn speed_min (tránh motor không quay)
        if abs(u) < self.speed_min:
            u = math.copysign(self.speed_min, u)

        # Clamp: không được lớn hơn speed_max
        u = max(-self.speed_max, min(self.speed_max, u))

        # Publish
        cmd = Twist()
        cmd.angular.z = u
        self.pub_cmd.publish(cmd)

    def _stop(self):
        """Dừng xe."""
        cmd = Twist()
        self.pub_cmd.publish(cmd)
        self.get_logger().info('🛑 Dừng xe')


def main(args=None):
    rclpy.init(args=args)
    node = Turn90ByOdomNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('turn_90_by_odom bị dừng')
    finally:
        stop_msg = Twist()
        try:
            node.pub_cmd.publish(stop_msg)
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
