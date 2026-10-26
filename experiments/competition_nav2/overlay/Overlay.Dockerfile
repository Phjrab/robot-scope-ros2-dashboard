ARG STOCK_IMAGE
FROM ${STOCK_IMAGE} AS build
COPY source /src
COPY probe /src/probe
RUN . /opt/ros/humble/setup.sh && cd /src && MAKEFLAGS=-j2 colcon build \
    --base-paths nav2_smac_planner nav2_mppi_controller --executor sequential \
    --build-base /tmp/build --install-base /opt/c3-overlay --merge-install \
    --cmake-args -DBUILD_TESTING=OFF
RUN . /opt/ros/humble/setup.sh && . /opt/c3-overlay/local_setup.sh && \
    cmake -S /src/probe -B /tmp/probe -DC3_PREFIX=/opt/c3-overlay && cmake --build /tmp/probe -j2
FROM ${STOCK_IMAGE}
COPY --from=build /opt/c3-overlay /opt/c3-overlay
COPY --from=build /tmp/probe/checker_probe /opt/c3/checker_probe
COPY provenance.json /opt/c3-overlay-provenance.json
ENTRYPOINT ["/bin/bash", "--noprofile", "--norc", "-c", "source /opt/ros/humble/setup.bash; source /opt/c3-overlay/local_setup.bash; exec \"$@\"", "--"]
