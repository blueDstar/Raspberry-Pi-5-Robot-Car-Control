#!/usr/bin/env python3
"""
Launch file tổng — Khởi động toàn bộ hệ thống mô phỏng Yahboom.

Thứ tự khởi động:
  1. Gazebo Classic (physics simulation)
  2. robot_state_publisher (URDF → TF static)
  3. mock_micro_ros_client (giả lập ESP32 firmware)
  4. mock_micro_ros_agent (giả lập micro-ROS Agent bridge)
  5. yahboom_driver_node (odom, TF dynamic)
  6. RViz2 (visualization)

Tùy chọn (comment out nếu không cần):
  - Gazebo spawn entity
  - rqt_graph

Usage:
  ros2 launch yahboom_bringup sim_complete.launch.py
  ros2 launch yahboom_bringup sim_complete.launch.py use_rviz:=false
  ros2 launch yahboom_bringup sim_complete.launch.py use_gazebo:=false
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    TimerAction,
    LogInfo,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():

    # ─────────────────────────────────────────────────────
    # PACKAGE PATHS
    # ─────────────────────────────────────────────────────
    pkg_desc    = get_package_share_directory('yahboom_description')
    pkg_gazebo  = get_package_share_directory('yahboom_gazebo')
    pkg_bringup = get_package_share_directory('yahboom_bringup')

    # ─────────────────────────────────────────────────────
    # LAUNCH ARGUMENTS
    # ─────────────────────────────────────────────────────
    use_gazebo_arg = DeclareLaunchArgument(
        'use_gazebo',
        default_value='true',
        description='Có chạy Gazebo không (false để test node-only)'
    )

    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Có mở RViz2 không'
    )

    use_rqt_arg = DeclareLaunchArgument(
        'use_rqt',
        default_value='false',
        description='Có mở rqt_graph không'
    )

    namespace_arg = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='ROS namespace (để trống = global)'
    )

    use_gazebo   = LaunchConfiguration('use_gazebo')
    use_rviz     = LaunchConfiguration('use_rviz')
    use_rqt      = LaunchConfiguration('use_rqt')

    # ─────────────────────────────────────────────────────
    # URDF từ XACRO
    # ─────────────────────────────────────────────────────
    xacro_file = os.path.join(pkg_desc, 'urdf', 'yahboom_car.urdf.xacro')
    robot_description = Command(['xacro ', xacro_file])

    # ─────────────────────────────────────────────────────
    # NODE 1: robot_state_publisher
    # Publish static TF từ URDF (base_link → wheel_*, imu_link, v.v.)
    # ─────────────────────────────────────────────────────
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
    )

    # ─────────────────────────────────────────────────────
    # NODE 2: mock_micro_ros_client (Giả lập ESP32/MCU firmware)
    # ─────────────────────────────────────────────────────
    mock_client = Node(
        package='mock_micro_ros',
        executable='mock_micro_ros_client',
        name='mock_micro_ros_client',
        output='screen',
        parameters=[{
            'car_type':        'yahboom_4wd',
            'wheel_radius':    0.033,
            'wheel_base':      0.150,
            'wheel_track':     0.190,
            'ticks_per_rev':   1320,
            'publish_rate':    50.0,
            'imu_noise_std':   0.01,
            'battery_voltage': 12.0,
            'use_sim_time':    True,
        }],
    )

    # ─────────────────────────────────────────────────────
    # NODE 3: mock_micro_ros_agent (Giả lập micro-ROS Agent)
    # ─────────────────────────────────────────────────────
    mock_agent = Node(
        package='mock_micro_ros',
        executable='mock_micro_ros_agent',
        name='mock_micro_ros_agent',
        output='screen',
        parameters=[{
            'bridge_verbose': True,
            'log_every_n':    50,
            'use_sim_time':   True,
        }],
    )

    # ─────────────────────────────────────────────────────
    # NODE 4: yahboom_driver (Tính odom, broadcast TF)
    # ─────────────────────────────────────────────────────
    yahboom_driver = Node(
        package='yahboom_driver',
        executable='yahboom_driver_node',
        name='yahboom_driver',
        output='screen',
        parameters=[{
            'wheel_radius': 0.033,
            'wheel_track':  0.190,
            'odom_frame':   'odom',
            'base_frame':   'base_footprint',
            'publish_tf':   True,
            'use_sim_time': True,
        }],
    )

    # ─────────────────────────────────────────────────────
    # GAZEBO: Khởi động Gazebo Classic
    # ─────────────────────────────────────────────────────
    world_file = os.path.join(pkg_gazebo, 'worlds', 'empty_world.world')

    gazebo = ExecuteProcess(
        condition=IfCondition(use_gazebo),
        cmd=[
            'gazebo', '--verbose',
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
            world_file
        ],
        output='screen',
    )

    # Spawn robot vào Gazebo (sau khi Gazebo đã khởi động)
    spawn_entity = TimerAction(
        period=5.0,  # Chờ 5s để Gazebo load xong
        actions=[
            Node(
                condition=IfCondition(use_gazebo),
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

    # ─────────────────────────────────────────────────────
    # RVIZ2
    # ─────────────────────────────────────────────────────
    rviz_config = os.path.join(pkg_desc, 'rviz', 'yahboom.rviz')

    rviz2 = TimerAction(
        period=3.0,  # Chờ 3s để robot_state_publisher đã có URDF
        actions=[
            Node(
                condition=IfCondition(use_rviz),
                package='rviz2',
                executable='rviz2',
                name='rviz2',
                arguments=['-d', rviz_config] if os.path.exists(rviz_config) else [],
                parameters=[{'use_sim_time': True}],
                output='screen',
            )
        ]
    )

    # ─────────────────────────────────────────────────────
    # RQT_GRAPH (tùy chọn)
    # ─────────────────────────────────────────────────────
    rqt_graph = TimerAction(
        period=5.0,
        actions=[
            ExecuteProcess(
                condition=IfCondition(use_rqt),
                cmd=['rqt_graph'],
                output='screen',
            )
        ]
    )

    # ─────────────────────────────────────────────────────
    # LOG INFO
    # ─────────────────────────────────────────────────────
    log_start = LogInfo(msg=[
        '\n',
        '╔══════════════════════════════════════════════════════╗\n',
        '║     Yahboom micro-ROS Simulation đang khởi động!    ║\n',
        '╠══════════════════════════════════════════════════════╣\n',
        '║  Sau khi launch xong, hãy thử:                      ║\n',
        '║  # Test di chuyển:                                  ║\n',
        '║  ros2 topic pub /cmd_vel geometry_msgs/Twist \\       ║\n',
        '║    "{linear: {x: 0.1}}" --once                      ║\n',
        '║                                                      ║\n',
        '║  # Xem nodes:                                        ║\n',
        '║  ros2 node list                                      ║\n',
        '║  rqt_graph                                           ║\n',
        '║                                                      ║\n',
        '║  # Echo topics:                                      ║\n',
        '║  ros2 topic echo /odom                              ║\n',
        '║  ros2 topic echo /micro_ros/encoder                  ║\n',
        '╚══════════════════════════════════════════════════════╝\n',
    ])

    return LaunchDescription([
        # Arguments
        use_gazebo_arg,
        use_rviz_arg,
        use_rqt_arg,
        namespace_arg,

        # Log
        log_start,

        # Gazebo simulation
        gazebo,
        spawn_entity,

        # Core ROS 2 nodes
        robot_state_publisher,
        mock_client,
        mock_agent,
        yahboom_driver,

        # Visualization
        rviz2,
        rqt_graph,
    ])
