#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      YAHBOOM DRIVER NODE — Thay thế Rosmaster_Lib trong mô phỏng          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  TRONG HỆ THẬT:                                                              ║
║    - Driver Python dùng Rosmaster_Lib để giao tiếp với board control         ║
║    - Gọi: car.set_car_motion(vx, vy, angular)                                ║
║    - Nhận encoder data (qua Rosmaster_Lib protocol, không qua micro-ROS)     ║
║    - Tính odometry và publish /odom                                           ║
║    - Publish /joint_states, /vel_raw, /imu/data_raw, /voltage                ║
║                                                                              ║
║  TRONG MÔ PHỎNG NÀY:                                                         ║
║    - Subscribe /joint_states từ mock_agent (thay vì Rosmaster_Lib)           ║
║    - Tính wheel velocities từ JointState                                     ║
║    - Tính odometry (differential drive kinematics)                           ║
║    - Publish /odom + TF odom → base_footprint                                ║
║    - Broadcast TF tree                                                        ║
║                                                                              ║
║  TOPICS:                                                                     ║
║    Nhận: /joint_states  (từ mock_agent)                                      ║
║    Gửi:  /odom          (nav_msgs/Odometry)                                  ║
║          /tf            (odom → base_footprint)                              ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

ODOMETRY KINEMATICS (Differential Drive):
  v_left  = average(v_fl, v_rl)  [m/s]
  v_right = average(v_fr, v_rr)  [m/s]
  
  v     = (v_right + v_left) / 2          [linear velocity]
  omega = (v_right - v_left) / track_width [angular velocity]
  
  dx    = v * cos(theta) * dt
  dy    = v * sin(theta) * dt
  dtheta = omega * dt
"""

import math
import rclpy
from rclpy.node import Node
from rclpy.time import Time

from geometry_msgs.msg import TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    """Chuyển Euler angles sang Quaternion."""
    cr = math.cos(roll  * 0.5)
    sr = math.sin(roll  * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw   * 0.5)
    sy = math.sin(yaw   * 0.5)

    q = Quaternion()
    q.w = cr * cp * cy + sr * sp * sy
    q.x = sr * cp * cy - cr * sp * sy
    q.y = cr * sp * cy + sr * cp * sy
    q.z = cr * cp * sy - sr * sp * cy
    return q


class YahboomDriverNode(Node):
    """
    Driver ROS 2 cho Yahboom robot.
    
    Đây là tương đương của script Python thật dùng Rosmaster_Lib,
    nhưng nhận dữ liệu từ mock_agent thay vì serial board.
    """

    def __init__(self):
        super().__init__('yahboom_driver')

        # ─────────────────────────────────────────────────
        # PARAMETERS
        # ─────────────────────────────────────────────────
        self.declare_parameter('wheel_radius', 0.033)
        self.declare_parameter('wheel_track', 0.190)
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_footprint')
        self.declare_parameter('publish_tf', True)

        self.wheel_radius = self.get_parameter('wheel_radius').value
        self.wheel_track  = self.get_parameter('wheel_track').value
        self.odom_frame   = self.get_parameter('odom_frame').value
        self.base_frame   = self.get_parameter('base_frame').value
        self.publish_tf   = self.get_parameter('publish_tf').value

        # ─────────────────────────────────────────────────
        # ODOMETRY STATE
        # ─────────────────────────────────────────────────
        self.x     = 0.0
        self.y     = 0.0
        self.theta = 0.0

        self.prev_time: Time | None = None

        # ─────────────────────────────────────────────────
        # TF BROADCASTER
        # ─────────────────────────────────────────────────
        self.tf_broadcaster = TransformBroadcaster(self)

        # ─────────────────────────────────────────────────
        # SUBSCRIBERS
        # ─────────────────────────────────────────────────
        # Joint states từ mock_agent (encoder data)
        self.sub_joint = self.create_subscription(
            JointState,
            '/joint_states',
            self._on_joint_states,
            10
        )

        # ─────────────────────────────────────────────────
        # PUBLISHERS
        # ─────────────────────────────────────────────────
        self.pub_odom = self.create_publisher(Odometry, '/odom', 10)

        self.get_logger().info(
            f'\n'
            f'╔════════════════════════════════════════╗\n'
            f'║  YahboomDriver đã khởi động!           ║\n'
            f'║  [Thay thế Rosmaster_Lib driver]       ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  wheel_radius : {self.wheel_radius:.3f} m             ║\n'
            f'║  wheel_track  : {self.wheel_track:.3f} m             ║\n'
            f'║  odom_frame   : {self.odom_frame}              ║\n'
            f'║  base_frame   : {self.base_frame}       ║\n'
            f'╠════════════════════════════════════════╣\n'
            f'║  Subscribe: /joint_states              ║\n'
            f'║  Publish  : /odom                      ║\n'
            f'║  Broadcast: /tf (odom→base_footprint)  ║\n'
            f'╚════════════════════════════════════════╝'
        )

    def _on_joint_states(self, msg: JointState):
        """
        Callback nhận JointState từ mock_agent.
        Tính odometry và publish.
        
        JointState.velocity = [vel_fl, vel_rl, vel_fr, vel_rr] (rad/s)
        """
        if len(msg.velocity) < 4:
            return

        now = Time.from_msg(msg.header.stamp)

        if self.prev_time is None:
            self.prev_time = now
            return

        dt = (now - self.prev_time).nanoseconds * 1e-9
        self.prev_time = now

        if dt <= 0 or dt > 1.0:
            return

        # Tốc độ tuyến tính từng bánh (m/s)
        v_fl = msg.velocity[0] * self.wheel_radius
        v_rl = msg.velocity[1] * self.wheel_radius
        v_fr = msg.velocity[2] * self.wheel_radius
        v_rr = msg.velocity[3] * self.wheel_radius

        # Average trái/phải (giống xe differential)
        v_left  = (v_fl + v_rl) / 2.0
        v_right = (v_fr + v_rr) / 2.0

        # Vận tốc robot (differential drive kinematics)
        v_robot = (v_right + v_left) / 2.0
        omega   = (v_right - v_left) / self.wheel_track

        # Tích phân pose (Euler integration)
        dx     = v_robot * math.cos(self.theta) * dt
        dy     = v_robot * math.sin(self.theta) * dt
        dtheta = omega * dt

        self.x     += dx
        self.y     += dy
        self.theta += dtheta

        # Normalize theta về [-π, π]
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))

        # Publish odometry
        self._publish_odom(now, v_robot, omega)

        # Broadcast TF
        if self.publish_tf:
            self._broadcast_tf(now)

    def _publish_odom(self, stamp: Time, v: float, omega: float):
        """Publish odometry message."""
        odom = Odometry()
        odom.header.stamp = stamp.to_msg()
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id  = self.base_frame

        # Pose
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation = euler_to_quaternion(0.0, 0.0, self.theta)

        # Covariance (diagonal, đơn giản hóa)
        # Các phần tử: [x, y, z, roll, pitch, yaw]
        cov = [0.0] * 36
        cov[0]  = 0.01   # x
        cov[7]  = 0.01   # y
        cov[14] = 1e6    # z (không di chuyển theo trục z)
        cov[21] = 1e6    # roll
        cov[28] = 1e6    # pitch
        cov[35] = 0.03   # yaw
        odom.pose.covariance = cov

        # Twist (vận tốc)
        odom.twist.twist.linear.x  = v
        odom.twist.twist.linear.y  = 0.0
        odom.twist.twist.angular.z = omega

        twist_cov = [0.0] * 36
        twist_cov[0]  = 0.01
        twist_cov[7]  = 0.01
        twist_cov[35] = 0.03
        odom.twist.covariance = twist_cov

        self.pub_odom.publish(odom)

    def _broadcast_tf(self, stamp: Time):
        """
        Broadcast transform: odom → base_footprint
        
        TF tree đầy đủ:
          map (tùy chọn, nếu có SLAM)
            └── odom           (driver broadcast)
                  └── base_footprint  (driver broadcast)
                        └── base_link      (robot_state_publisher từ URDF)
                              ├── wheel_fl_link
                              ├── wheel_rl_link
                              ├── wheel_fr_link
                              ├── wheel_rr_link
                              ├── imu_link
                              └── laser_link
        """
        t = TransformStamped()
        t.header.stamp    = stamp.to_msg()
        t.header.frame_id = self.odom_frame
        t.child_frame_id  = self.base_frame

        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0

        q = euler_to_quaternion(0.0, 0.0, self.theta)
        t.transform.rotation.x = q.x
        t.transform.rotation.y = q.y
        t.transform.rotation.z = q.z
        t.transform.rotation.w = q.w

        self.tf_broadcaster.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = YahboomDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
