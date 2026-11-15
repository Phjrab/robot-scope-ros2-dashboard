# Preserve elevation channels during XT16 decimation

The Hesai input interleaves the 16 elevation channels. Selecting every fourth
record aliases that layout: a live 64,000-point input contained 4,000 points in
each ring, but the old 16,000-point output contained only rings 0, 4, 8 and 12.
Their measured elevations were approximately +15, +7, -1 and -9 degrees;
the missing channels included the lowest -11, -13 and -15 degree returns.

The converter now keeps every fourth occurrence **within each ring**, with
the phase set by the ring number modulo four. Source order and point timestamps
are retained. The full finite input supplies scan start/end, so changing the
selected subset cannot change the clock-offset observation. Invalid ring IDs
are rejected before selection. Both the C++ deployed converter and Python
reference converter implement the same rule. A balanced 64,000-point scan still
produces 16,000 points, with 1,000 in every channel.

This fixes a measured loss of vertical coverage at the sensor ingress. It does
not by itself prove that every later registration failure has the same cause.
In the 2026-11-15 goal stop, the operational SO(3) correction step was 0.105401
rad, exceeding the unchanged 0.1 rad limit. The concurrent translation step
and residual were within their limits. FAST-LIO's internal extrinsic angle
variation during that goal was below 0.1 degree per component, so it does not
explain the six-degree registration correction step on its own.

Stationary input comparison and supervised dynamic validation must be reported
separately. No registration, odometry, freshness, correction, velocity or stop
threshold is relaxed by this change. Existing maps are not rewritten.
