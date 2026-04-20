#!/usr/bin/env python3
"""
Launch file cho Gazebo + spawn robot.
Dùng độc lập hoặc được include từ sim_complete.launch.py.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    pkg_gazebo = get_package_share_directory('yahboom_gazebo')
    world_file = os.path.join(pkg_gazebo, 'worlds', 'empty_world.world')

    gazebo = ExecuteProcess(
        cmd=[
            'gazebo', '--verbose',
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
            world_file
        ],
        output='screen',
    )

    spawn_entity = TimerAction(
        period=5.0,
        actions=[
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                name='spawn_robot',
                arguments=[
                    '-topic', 'robot_description',
                    '-entity', 'yahboom_car',
                    '-x', '0.0',
                    '-y', '0.0',
                    '-z', '0.1',
                ],
                output='screen',
            )
        ]
    )

    return LaunchDescription([
        gazebo,
        spawn_entity,
    ])
