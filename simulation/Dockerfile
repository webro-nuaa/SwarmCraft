ARG REGISTRY_MIRROR=docker.1ms.run/
FROM ${REGISTRY_MIRROR}px4io/px4-dev-simulation-focal:latest

ARG GITHUB_MIRROR=https://gh.idayer.com/https://github.com/

# 克隆PX4源码（如果镜像中没有）
WORKDIR /root
RUN if [ ! -d "PX4-Autopilot" ]; then \
    git clone ${GITHUB_MIRROR}PX4/PX4-Autopilot.git --recursive --depth 1 --branch v1.14.3; \
    fi

WORKDIR /root/PX4-Autopilot

# 编译PX4 SITL
RUN DONT_RUN=1 make px4_sitl gazebo-classic

# 修补启动脚本：移除 gzclient 启动（headless 模式不需要 GUI）
RUN sed -i '/Starting gazebo client/,/gzclient/d' Tools/simulation/gazebo-classic/sitl_multiple_run.sh

# 复制启动脚本
COPY multi-drone-simple.sh /root/multi-drone.sh
RUN chmod +x /root/multi-drone.sh

ENV PX4_HOME_LAT=34.23
ENV PX4_HOME_LON=108.95
ENV PX4_HOME_ALT=488.0

ENTRYPOINT ["/root/multi-drone.sh"]
