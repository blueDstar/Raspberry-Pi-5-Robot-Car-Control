from setuptools import setup
import os
from glob import glob

package_name = 'yahboom_nav'

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
    description='Navigation demo nodes cho Yahboom robot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Chạy hình vuông (time-based)
            'square_drive      = yahboom_nav.square_drive:main',
            # Quay 90° dùng odometry feedback (closed-loop)
            'turn_90_by_odom   = yahboom_nav.turn_90_by_odom:main',
        ],
    },
)
