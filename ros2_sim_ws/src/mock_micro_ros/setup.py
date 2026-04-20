from setuptools import setup
import os
from glob import glob

package_name = 'mock_micro_ros'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Student',
    maintainer_email='student@example.com',
    description='Giả lập micro-ROS client và agent cho Yahboom robot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Node giả lập firmware ESP32/MCU
            'mock_micro_ros_client = mock_micro_ros.mock_client:main',
            # Node giả lập micro-ROS Agent (bridge)
            'mock_micro_ros_agent  = mock_micro_ros.mock_agent:main',
        ],
    },
)
