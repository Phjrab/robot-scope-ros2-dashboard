# C6 isolated replay host

See [HANDOFF](../../../docs/parallel-expansion-20261030/C6/HANDOFF.md) for commands,
formats and product port requirements. `serve.py` is GET-only and binds only
127.0.0.1. It serves fixed UI files and exact C3 dependency modules, never private
recordings, application APIs or arbitrary paths. Open review bundles through the
browser's file picker. No ROS, recorder, controller or asset/network resolver.
