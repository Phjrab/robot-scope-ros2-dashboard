# The build driver resolves BASE_IMAGE to ros:humble-ros-base-jammy@sha256:... .
# No floating base is accepted by the driver. Dependency downloads occur at build only.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG PACKAGE_SPECS="ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-rmw-fastrtps-cpp python3-numpy python3-scipy python3-yaml"
RUN apt-get update && apt-get install --no-install-recommends -y ${PACKAGE_SPECS} \
    && dpkg-query -W -f='${Package}\t${Version}\n' > /opt/c3-packages.tsv \
    && rm -rf /var/lib/apt/lists/*
ENV ROS_DISTRO=humble ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=193 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ENV PYTHONDONTWRITEBYTECODE=1 ROS_LOG_DIR=/tmp/c3-ros-logs
ENTRYPOINT ["/bin/bash", "--noprofile", "--norc", "-c", "source /opt/ros/humble/setup.bash; exec \"$@\"", "--"]
