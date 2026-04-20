#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           SQUARE DRIVE — Điều khiển xe chạy hình vuông (time-based)       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Node này là HIGH-LEVEL navigation — publish /cmd_vel.                      ║
║                                                                              ║
║  Chuỗi lệnh:                                                                 ║
║    1. Tiến thẳng trong T_forward giây với vận tốc LINEAR_SPEED              ║
║    2. Dừng 0.3s                                                              ║
║    3. Quay LEFT 90° bằng cách đặt angular.z trong T_turn giây               ║
║    4. Dừng 0.3s                                                              ║
║    5. Lặp lại 4 lần → hình vuông hoàn chỉnh                                 ║
║                                                                              ║
║  HẠN CHẾ của time-based:                                                    ║
║    - Không chính xác nếu có trượt bánh (slip)                                ║
║    - Không dùng feedback (open-loop control)                                 ║
║    - Phụ thuộc vào thông số T_turn phải được tính đúng                      ║
║    - So sánh với turn_90_by_odom.py: closed-loop, chính xác hơn             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time


class SquareDriveNode(Node):
    """
    Điều khiển xe chạy hình vuông bằng /cmd_vel.
    Dùng time-based control (open-loop).
    """

    def __init__(self):
        super().__init__('square_drive')

        # ─────────────────────────────────────────────────
        # PARAMETERS
        # ─────────────────────────────────────────────────
        self.declare_parameter('linear_speed', 0.15)    # m/s tiến
        self.declare_parameter('angular_speed', 0.5)    # rad/s quay
        self.declare_parameter('side_length', 0.5)      # m mỗi cạnh
        self.declare_parameter('num_loops', 1)          # Số lần lặp hình vuông
        self.declare_parameter('pause_between', 0.3)    # s dừng giữa các pha

        self.linear_speed  = self.get_parameter('linear_speed').value
        self.angular_speed = self.get_parameter('angular_speed').value
        self.side_length   = self.get_parameter('side_length').value
        self.num_loops     = self.get_parameter('num_loops').value
        self.pause_time    = self.get_parameter('pause_between').value

        # Tính thời gian cho mỗi pha
        self.T_forward = self.side_length / self.linear_speed
        self.T_turn    = (3.14159265 / 2.0) / self.angular_speed  # 90° / omega

        self.pub_cmd = self.create_publisher(Twist, '/cmd_vel', 10)

        self.get_logger().info(
            f'\n'
            f'┌─────────────────────────────────────┐\n'
            f'│  SquareDrive — Hình vuông (time)    │\n'
            f'├─────────────────────────────────────┤\n'
            f'│  linear_speed  : {self.linear_speed:.2f} m/s         │\n'
            f'│  angular_speed : {self.angular_speed:.2f} rad/s       │\n'
            f'│  side_length   : {self.side_length:.2f} m            │\n'
            f'│  T_forward     : {self.T_forward:.2f} s             │\n'
            f'│  T_turn (90°)  : {self.T_turn:.2f} s             │\n'
            f'│  num_loops     : {self.num_loops}                    │\n'
            f'└─────────────────────────────────────┘\n'
            f'Bắt đầu sau 2 giây...'
        )

        # Chờ các node khác khởi động
        self.create_timer(2.0, self._start_driving)
        self._started = False

    def _start_driving(self):
        """Timer callback - chỉ chạy một lần."""
        if self._started:
            return
        self._started = True
        self._run_square()

    def _publish_vel(self, linear: float, angular: float, duration: float):
        """Publish /cmd_vel trong duration giây."""
        msg = Twist()
        msg.linear.x  = linear
        msg.angular.z = angular

        rate_hz = 20.0  # 20Hz publish rate
        period = 1.0 / rate_hz
        start = time.time()

        while time.time() - start < duration:
            self.pub_cmd.publish(msg)
            time.sleep(period)
            rclpy.spin_once(self, timeout_sec=0.0)  # process callbacks

    def _stop(self, duration: float = 0.3):
        """Dừng xe."""
        self._publish_vel(0.0, 0.0, duration)

    def _run_square(self):
        """Chạy hình vuông."""
        self.get_logger().info('🚗 Bắt đầu chạy hình vuông!')

        for loop in range(self.num_loops):
            self.get_logger().info(f'--- Vòng {loop + 1}/{self.num_loops} ---')

            for side in range(4):
                # ── Cạnh: Tiến thẳng ──
                self.get_logger().info(
                    f'  Cạnh {side + 1}: Tiến {self.side_length}m '
                    f'({self.T_forward:.2f}s)'
                )
                self._publish_vel(self.linear_speed, 0.0, self.T_forward)
                self._stop(self.pause_time)

                # ── Góc: Quay 90° ──
                self.get_logger().info(
                    f'  Góc {side + 1}: Quay trái 90° ({self.T_turn:.2f}s)'
                )
                self._publish_vel(0.0, self.angular_speed, self.T_turn)
                self._stop(self.pause_time)

        self.get_logger().info('✅ Hoàn thành hình vuông!')
        self.get_logger().info(
            '💡 Tip: So sánh với turn_90_by_odom.py để thấy sự khác biệt!'
        )

        # Dừng hẳn
        self._stop(1.0)


def main(args=None):
    rclpy.init(args=args)
    node = SquareDriveNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('square_drive bị dừng bởi người dùng')
    finally:
        # Đảm bảo xe dừng
        stop_msg = Twist()
        try:
            node.pub_cmd.publish(stop_msg)
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
