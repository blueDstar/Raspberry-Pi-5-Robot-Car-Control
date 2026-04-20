# 🤖 Yahboom Robot Car — ROS 2 micro-ROS Simulation Workspace

> **Mục đích:** Học kiến trúc hệ thống xe robot Yahboom 4 bánh dùng micro-ROS\
> **Platform:** Ubuntu 22.04 + ROS 2 Humble + Gazebo Classic 11\
> **Không cần:** Raspberry Pi, ESP32, phần cứng thật

---

## 📐 Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LUỒNG DỮ LIỆU TOÀN HỆ THỐNG                        │
│                                                                          │
│   [ROS 2 Level]          [Agent]           [MCU/ESP32 Level]           │
│                                                                          │
│   /cmd_vel  ────────→  mock_agent  ──→  /micro_ros/cmd_vel_in          │
│   (teleop/nav)         (bridge)         mock_client                     │
│                            │            ┌─────────────────┐             │
│                            │            │ Kinematics:     │             │
│                            │            │ Vm1=Vx-Vz(A+B) │             │
│                            │            │ Vm2=Vx-Vz(A+B) │             │
│                            │            │ Vm3=Vx+Vz(A+B) │             │
│                            │            │ Vm4=Vx+Vz(A+B) │             │
│                            │            └─────────────────┘             │
│                            │                    ↓                       │
│   /joint_states  ←──── mock_agent ←── /micro_ros/encoder               │
│   /imu/data_raw  ←──── mock_agent ←── /micro_ros/imu                  │
│   /voltage       ←──── mock_agent ←── /micro_ros/battery               │
│                                                                          │
│   yahboom_driver ←── /joint_states                                      │
│        ↓                                                                 │
│   /odom + /tf                                                            │
│        ↓                                                                 │
│   RViz2 (visualization)                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Mapping: Mô phỏng ↔ Hệ thật

| Thành phần mô phỏng | Tương ứng hệ thật |
|---|---|
| `mock_micro_ros_client.py` | Firmware C++ trên ESP32/STM32 |
| `mock_micro_ros_agent.py` | Binary `micro-ros-agent` chạy trên Pi |
| `yahboom_driver.py` | Driver Python dùng `Rosmaster_Lib` |
| Gazebo + URDF physics | Phần cứng xe vật lý |
| RViz2 + rqt_graph | Công cụ debug/monitor |

---

## 📁 Cấu trúc thư mục

```
ros2_sim_ws/
├── src/
│   ├── yahboom_description/      # URDF/Xacro + RViz config
│   │   ├── urdf/yahboom_car.urdf.xacro
│   │   └── rviz/yahboom.rviz
│   │
│   ├── yahboom_gazebo/           # World Gazebo
│   │   ├── worlds/empty_world.world
│   │   └── launch/gazebo.launch.py
│   │
│   ├── mock_micro_ros/           # ⭐ Trái tim mô phỏng
│   │   ├── mock_micro_ros/
│   │   │   ├── mock_client.py    # Giả lập ESP32 firmware
│   │   │   └── mock_agent.py     # Giả lập micro-ROS Agent
│   │   └── launch/mock_micro_ros.launch.py
│   │
│   ├── yahboom_driver/           # Driver ROS 2 (odom, TF)
│   │   ├── yahboom_driver/driver_node.py
│   │   └── config/driver_params.yaml
│   │
│   ├── yahboom_nav/              # Navigation demos
│   │   ├── yahboom_nav/
│   │   │   ├── square_drive.py       # Hình vuông (time-based)
│   │   │   └── turn_90_by_odom.py    # Quay 90° (odom-based)
│   │   └── launch/nav_demo.launch.py
│   │
│   └── yahboom_bringup/          # Launch tổng
│       ├── launch/sim_complete.launch.py
│       └── config/sim_params.yaml
└── README.md
```

---

## 🛠️ Cài đặt

### 1. Cài ROS 2 Humble (nếu chưa có)

```bash
# Theo hướng dẫn chính thức:
# https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html

sudo apt install ros-humble-desktop
source /opt/ros/humble/setup.bash
```

### 2. Cài Gazebo Classic và các dependencies

```bash
sudo apt update
sudo apt install -y \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-gazebo-ros \
    ros-humble-gazebo-plugins \
    ros-humble-robot-state-publisher \
    ros-humble-joint-state-publisher \
    ros-humble-joint-state-publisher-gui \
    ros-humble-xacro \
    ros-humble-tf2-ros \
    ros-humble-tf2-tools \
    ros-humble-tf2-geometry-msgs \
    ros-humble-rviz2 \
    ros-humble-rqt \
    ros-humble-rqt-graph \
    ros-humble-teleop-twist-keyboard \
    python3-colcon-common-extensions \
    python3-numpy
```

### 3. Build workspace

```bash
# Di chuyển vào thư mục chứa ros2_sim_ws
cd ~/path/to/Raspberry-Pi-5-Robot-Car-Control

# Build
cd ros2_sim_ws
colcon build --symlink-install

# Source
source install/setup.bash
# Hoặc thêm vào ~/.bashrc:
echo "source ~/path/to/ros2_sim_ws/install/setup.bash" >> ~/.bashrc
```

### 4. Kiểm tra build thành công

```bash
ros2 pkg list | grep -E "yahboom|mock_micro"
# Kết quả mong đợi:
# mock_micro_ros
# yahboom_bringup
# yahboom_description
# yahboom_driver
# yahboom_gazebo
# yahboom_nav
```

---

## 🚀 Chạy Simulation

### Option A: Chạy toàn bộ (Gazebo + RViz2 + tất cả nodes)

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_sim_ws/install/setup.bash

ros2 launch yahboom_bringup sim_complete.launch.py
```

### Option B: Chạy không có Gazebo (test nodes nhanh)

```bash
ros2 launch yahboom_bringup sim_complete.launch.py use_gazebo:=false
```

### Option C: Chỉ test mock micro-ROS layer

```bash
ros2 launch mock_micro_ros mock_micro_ros.launch.py
```

---

## 🧪 Test từng bước

### Bước 1: Kiểm tra các node đang chạy

```bash
# Trong terminal mới (sau khi đã launch)
ros2 node list
# Kết quả mong đợi:
# /mock_micro_ros_client
# /mock_micro_ros_agent
# /yahboom_driver
# /robot_state_publisher
```

### Bước 2: Xem graph nodes/topics

```bash
rqt_graph
# Hoặc trong launch file: dùng argument use_rqt:=true
ros2 launch yahboom_bringup sim_complete.launch.py use_rqt:=true
```

### Bước 3: Echo các topics để học luồng dữ liệu

```bash
# Terminal 1: Xem encoder output của mock client
ros2 topic echo /micro_ros/encoder

# Terminal 2: Xem IMU sau khi qua agent
ros2 topic echo /imu/data_raw

# Terminal 3: Xem odometry
ros2 topic echo /odom

# Terminal 4: Xem điện áp pin
ros2 topic echo /voltage

# Bandwidth của từng topic
ros2 topic bw /micro_ros/encoder
ros2 topic bw /odom
```

### Bước 4: Test điều khiển thủ công

```bash
# Tiến thẳng
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Quay trái
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.5}}"

# Dừng
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{}"

# Teleop keyboard interactif
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

### Bước 5: Xem TF tree

```bash
# Xem TF dạng ASCII tree
ros2 run tf2_tools view_frames

# Kết quả lưu vào frames.pdf (xem bằng evince)
evince frames.pdf

# Hoặc monitor TF realtime:
ros2 topic echo /tf
ros2 topic echo /tf_static

# Check transform cụ thể giữa 2 frames:
ros2 run tf2_ros tf2_echo odom base_footprint
```

### Bước 6: Chạy xe tiến thẳng (kiểm tra không drift)

```bash
# Trong terminal riêng:
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.15}}" \
  --rate 10 \
  &

# Theo dõi x,y trong odom (phải tăng theo đường thẳng)
ros2 topic echo /odom --field pose.pose.position

# Dừng sau 5s:
sleep 5 && ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{}"
```

### Bước 7: Cho xe chạy hình vuông (time-based)

```bash
ros2 run yahboom_nav square_drive
# Robot sẽ:
# → Tiến 0.5m
# → Quay trái 90°
# → Tiến 0.5m
# → Quay trái 90°
# → ... (4 lần = 1 hình vuông)
```

### Bước 8: Quay 90° dùng odom (closed-loop)

```bash
# Terminal 1: Theo dõi odom yaw
ros2 topic echo /odom --field pose.pose.orientation

# Terminal 2: Chạy node
ros2 run yahboom_nav turn_90_by_odom
# Robot sẽ quay cho đến khi yaw tăng đúng 90° theo odom feedback
```

### Bước 9: So sánh time-based vs odom-based

```bash
# 1. Chạy square_drive và nhìn RViz2: có drift không?
ros2 run yahboom_nav square_drive

# 2. Sau đó reset odom:
ros2 topic pub --once /odom nav_msgs/msg/Odometry "{}"

# 3. Chạy 4 lần turn_90_by_odom + tiến thẳng thủ công:
# (xem sự khác biệt về độ chính xác)
```

---

## 📊 Bảng Topics đầy đủ

| Topic | Type | Hz | Mô tả |
|---|---|---|---|
| `/cmd_vel` | Twist | on_demand | Lệnh điều khiển từ telop/nav |
| `/micro_ros/cmd_vel_in` | Twist | on_demand | Sau khi qua Agent → Client |
| `/micro_ros/encoder` | JointState | 50 Hz | Encoder 4 bánh (từ mock_client) |
| `/micro_ros/imu` | Imu | 50 Hz | IMU data thô (từ mock_client) |
| `/micro_ros/battery` | Float32 | 50 Hz | Điện áp pin (từ mock_client) |
| `/joint_states` | JointState | 50 Hz | Bridge từ mock_agent |
| `/vel_raw` | Float32MA | 50 Hz | Tốc độ 4 bánh m/s (bridge) |
| `/imu/data_raw` | Imu | 50 Hz | IMU sau Agent |
| `/voltage` | Float32 | 50 Hz | Pin sau Agent |
| `/odom` | Odometry | 50 Hz | Odometry tích phân (driver) |
| `/tf` | TFMessage | 50 Hz | Dynamic TF tree |
| `/tf_static` | TFMessage | latched | Static TF from URDF |
| `/robot_description` | String | latched | URDF text |
| `/gazebo/odom` | Odometry | 50 Hz | Ground truth từ Gazebo |

---

## 🎓 Giải thích kiến trúc (Mini Course)

### 1. micro-ROS Client (ESP32)

```
[ESP32 Firmware - C/C++]
┌─────────────────────────────────────────────┐
│  // Khởi tạo micro-ROS (trong hệ thật)     │
│  rcl_init();                                 │
│  rclc_executor_init();                       │
│                                              │
│  // Subscribe nhận lệnh từ Agent            │
│  rclc_subscription_init(cmd_vel_sub);        │
│                                              │
│  // Callback xử lý lệnh:                    │
│  void cmd_vel_cb(const Twist* msg) {         │
│    float vx = msg->linear.x;                 │
│    float vz = msg->angular.z;                │
│    Vm1 = Vm2 = vx - vz * (A + B);           │
│    Vm3 = Vm4 = vx + vz * (A + B);           │
│    set_motor_pwm(Vm1, Vm2, Vm3, Vm4);       │
│  }                                           │
│                                              │
│  // Publish encoder + IMU → Agent           │
│  rcl_publish(encoder_pub, &encoder_msg);    │
│  rcl_publish(imu_pub, &imu_msg);            │
└─────────────────────────────────────────────┘
```

**Trong mô phỏng:** `mock_client.py` làm y hệt, nhưng bằng Python.
- Không có serial, không có PWM thật
- Encoder = tích phân toán học (không có slip)
- IMU = Gaussian noise

### 2. micro-ROS Agent

```
[Binary chạy trên Raspberry Pi]
micro_ros_agent serial --dev /dev/ttyUSB0 -b 921600

     DDS native (ROS 2)          |  DDS-XRCE (micro-ROS)
     ─────────────────           |  ──────────────────────
     /cmd_vel (Twist)    ──────→ |  XRCE_WRITE → ESP32
                                 |
     /joint_states       ←────── |  XRCE_READ ← ESP32
     /imu/data_raw       ←────── |  XRCE_READ ← ESP32
```

**Trong mô phỏng:** `mock_agent.py` dùng ROS 2 subscriptions/publications
để giả lập bridge này. Không có serial, không có XRCE.

### 3. Driver ROS 2 (Rosmaster_Lib)

```python
# Trong hệ thật - driver dùng Rosmaster_Lib:
car = Rosmaster()
car.create_receive_threading()

def cmd_vel_callback(msg):
    car.set_car_motion(msg.linear.x, msg.linear.y, msg.angular.z)
    # Rosmaster_Lib tự giao tiếp với board qua serial/USB

# Publish sensors (từ Rosmaster_Lib):
vel = car.get_motor_encoder()  # đọc encoder
pub_joint_states.publish(...)
```

**Trong mô phỏng:** `driver_node.py` nhận từ `mock_agent` thay vì `Rosmaster_Lib`.
Logic tính odom là giống hệt nhau.

### 4. Luồng đầy đủ một lệnh điều khiển

```
time=0ms:  teleop_keyboard → pub /cmd_vel {linear.x: 0.2}
time=1ms:  mock_agent nhận → log "AGENT→CLIENT: vx=0.200"
time=1ms:  mock_agent pub → /micro_ros/cmd_vel_in
time=2ms:  mock_client nhận →
           Vm1=Vm2 = 0.2 - 0*(0.075+0.095) = 0.2 m/s
           Vm3=Vm4 = 0.2 + 0*(0.075+0.095) = 0.2 m/s
           wheel_vel['fl']='rl' = 0.2/0.033 = 6.06 rad/s
           wheel_vel['fr']='rr' = 6.06 rad/s
time=20ms: mock_client timer → pub /micro_ros/encoder
           (position tích phân, velocity=6.06 rad/s)
time=20ms: mock_agent nhận encoder → 
           log "CLIENT→AGENT→ROS2: FL=6.06 RL=6.06 FR=6.06 RR=6.06"
           pub /joint_states (cho robot_state_publisher)
           pub /vel_raw [0.2, 0.2, 0.2, 0.2] m/s
time=20ms: driver nhận /joint_states →
           v_left = v_right = 0.2 m/s
           v_robot = 0.2, omega = 0.0
           x += 0.2 * dt, y = 0.0 (thẳng)
           pub /odom {x: 0.004m, yaw: 0.0}
           broadcast TF: odom → base_footprint
time=33ms: RViz2 render → robot di chuyển về phía trước
```

---

## ❓ FAQ

**Q: Tại sao mock_agent cần thiết? Sao không publish thẳng từ /cmd_vel?**
A: Để học rõ rằng trong hệ thật, KHÔNG có kết nối trực tiếp. Mọi thứ đều
qua Agent. Agent là cửa ngõ duy nhất giữa ROS 2 và micro-ROS.

**Q: Khác biệt lớn nhất giữa mô phỏng và thật là gì?**
A: 3 điểm chính:
1. Không có DDS-XRCE overhead (latency thật ~1-5ms)
2. Không có Motor PID (mô phỏng = kinematics lý tưởng, không có inertia)
3. IMU không có drift thật (gyro drift ~0.1°/s sau vài phút)

**Q: Làm sao test thêm namespace /robot1?**
A: Trong mock_agent.py, thêm prefix: `/robot1/cmd_vel`, `/robot1/odom`...
Hoặc dùng `ros2 launch ... namespace:=robot1`

**Q: Làm sao add SLAM (gmapping/cartographer)?**
A: Cần thêm laser scan. Thêm laser plugin vào URDF, sau đó:
```bash
ros2 launch slam_toolbox online_async_launch.py
```

---

## 🔍 Debug Tricks

```bash
# Kiểm tra frequency thực tế của topic
ros2 topic hz /micro_ros/encoder
ros2 topic hz /odom

# Kiểm tra TF tree (lỗi TF rất hay gặp)
ros2 run tf2_tools view_frames
ros2 run tf2_ros tf2_echo odom base_footprint

# In tất cả nodes + connections
ros2 node info /mock_micro_ros_client
ros2 node info /mock_micro_ros_agent

# Log level (debug để xem chi tiết hơn)
ros2 run mock_micro_ros mock_micro_ros_client \
  --ros-args --log-level debug

# Kiểm tra parameter
ros2 param list /mock_micro_ros_client
ros2 param get /mock_micro_ros_client wheel_radius
```

---

## 🏗️ Mở rộng thêm

Sau khi hiểu kiến trúc cơ bản, bạn có thể mở rộng:

1. **Thêm SLAM**: Cài `slam_toolbox`, thêm `sensor_msgs/LaserScan` topic
2. **Nav2**: Cài `nav2_bringup`, thêm waypoint following
3. **Camera**: Thêm `sensor_msgs/Image` trong mock_client
4. **Multi-robot**: Dùng namespace `/robot1`, `/robot2`
5. **Thật hóa IMU**: Thêm gyro drift model trong mock_client
6. **PID simulation**: Thêm motor inertia và first-order system vào mock_client
