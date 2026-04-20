#!/usr/bin/env python3
"""
Launch file demo navigation: square_drive và turn_90_by_odom.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node


def generate_launch_description():

    demo_arg = DeclareLaunchArgument(
        'demo',
        default_value='square',
        description='Demo mode: square / turn90'
    )

    demo = LaunchConfiguration('demo')

    # Demo 1: Chạy hình vuông (time-based)
    square_node = Node(
        package='yahboom_nav',
        executable='square_drive',
        name='square_drive',
        output='screen',
        parameters=[{
            'linear_speed':  0.15,
            'angular_speed': 0.5,
            'side_length':   0.5,
            'num_loops':     1,
        }],
    )

    # Demo 2: Quay 90° (odom-based, closed-loop)
    turn90_node = Node(
        package='yahboom_nav',
        executable='turn_90_by_odom',
        name='turn_90_by_odom',
        output='screen',
        parameters=[{
            'turn_angle_deg':   90.0,
            'angular_speed_max': 0.4,
            'kp':               1.5,
            'tolerance_deg':    1.5,
            'turn_direction':   1,
        }],
    )

    return LaunchDescription([
        demo_arg,
        # Bỏ comment node bạn muốn chạy:
        square_node,
        # turn90_node,
    ])
