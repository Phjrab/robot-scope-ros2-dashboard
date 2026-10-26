ARG STOCK_IMAGE
FROM ${STOCK_IMAGE} AS build
COPY probe /src/probe
RUN . /opt/ros/humble/setup.sh && cmake -S /src/probe -B /tmp/probe && cmake --build /tmp/probe -j2
FROM ${STOCK_IMAGE}
COPY --from=build /tmp/probe/checker_probe /opt/c3/checker_probe
