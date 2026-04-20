#!/usr/bin/env python3
"""
Launch file riêng cho mock_micro_ros package.
Test chỉ client + agent, không cần Gazebo.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    verbose_arg = DeclareLaunchArgument(
        'verbose', default_value='true',
        description='Bật verbose logging để thấy bridge messages'
    )

    mock_client = Node(
        package='mock_micro_ros',
        executable='mock_micro_ros_client',
        name='mock_micro_ros_client',
        output='screen',
        parameters=[{
            'wheel_radius':    0.033,
            'wheel_base':      0.150,
            'wheel_track':     0.190,
            'publish_rate':    50.0,
            'imu_noise_std':   0.01,
            'battery_voltage': 12.0,
        }],
    )

    mock_agent = Node(
        package='mock_micro_ros',
        executable='mock_micro_ros_agent',
        name='mock_micro_ros_agent',
        output='screen',
        parameters=[{
            'bridge_verbose': LaunchConfiguration('verbose'),
            'log_every_n': 10,  # Log nhiều hơn để học
        }],
    )

    return LaunchDescription([
        verbose_arg,
        mock_client,
        mock_agent,
    ])
