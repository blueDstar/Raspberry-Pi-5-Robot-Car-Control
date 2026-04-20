cmake_minimum_required(VERSION 3.8)
project(yahboom_description)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

# Cài toàn bộ thư mục con vào share
install(DIRECTORY
  urdf
  rviz
  meshes
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

ament_package()
