ARG REGISTRY_MIRROR=docker.1ms.run/
FROM ${REGISTRY_MIRROR}osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive

# 切换 apt 镜像源 (阿里云)
RUN sed -i 's@//archive.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list && \
    sed -i 's@//security.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list

# 安装 Foxglove Bridge + Python依赖 (不再使用MAVROS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-foxglove-bridge \
    python3-pip \
    python3-colcon-common-extensions \
    mysql-client \
    && rm -rf /var/lib/apt/lists/*

# 构建 px4_msgs 消息包 (PX4 v1.14.3 兼容分支)
RUN mkdir -p /px4_ws/src && \
    cd /px4_ws/src && \
    git clone https://github.com/PX4/px4_msgs.git --branch release/1.14 --depth 1 && \
    cd /px4_ws && \
    . /opt/ros/humble/setup.sh && \
    colcon build --packages-select px4_msgs --symlink-install && \
    rm -rf /px4_ws/src

# Python 后端依赖
RUN pip3 install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    pymysql \
    pydantic \
    websockets

# FastDDS UDP-only profile (disable shared memory for cross-container DDS)
COPY fastdds-udp.xml /app/fastdds-udp.xml

# 复制后端代码
COPY backend/ /app/backend/

# 复制入口脚本
COPY entrypoints/bridge-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 设置ROS2环境 (px4_msgs在底层之上)
RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc && \
    echo "source /px4_ws/install/setup.bash" >> /root/.bashrc

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
