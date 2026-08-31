# XT16 private correction acquisition and installation

## Scope and approval boundary

This runbook covers one read-only correction query to the fixed XT16 at
`192.168.123.20:9347`, private manifest staging and later installation on the
external Orin. It does not change the sensor, start the Hesai driver, relay,
Mapping, FAST-LIO, Nav2, Dataset Capture or Control Bridge, and it never issues
a robot command.

Do not run the acquisition executable, transfer private artifacts or install
anything until the operator has supplied the exact deployment phrase
`APPROVE_WIRELESS_XT16_DEPLOY`. Building and reviewing the helper is
hardware-free; executing it opens PTC and therefore belongs to the approved
deployment transaction.

## Measured parser identity and optional firetime

The exact pinned source was inspected at these revisions:

| Component | Revision |
| --- | --- |
| Hesai ROS wrapper | `e7e112f0809f0eed5e3c81c55a1a0376474db234` |
| Hesai SDK | `9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168` |

The measured packet header begins `EE FF 06 01`, which selects the SDK's
`PandarXT`/UDP 6.1 (`XTM1`) parser for the marketed XT16. A historic live wired
run of this exact unit also logged `init 6_1 XTM1 parser`, loaded its generic
CSV correction successfully and continued publishing at 10 Hz after the
optional firetime file was absent. The fixed deployment artifact is therefore:

```text
/etc/robot-scope/hesai/xt16-correction.csv
```

`firetimes_path` is optional and intentionally empty for the proven baseline.
The sensor-specific CSV must be acquired from this mounted sensor; substituting
an SDK sample, another sensor's file or an invented firetime is prohibited.

## Approved acquisition transaction

Use only the clean robot-side wrapper checkout and confirm both revisions
before building. Local modifications, a different SDK submodule or the
external Orin's modified vendor checkout block the transaction.

Build `tools/hesai_xt16_calibration` in a new private temporary build
directory with `HESAI_SDK_ROOT` set to the absolute pinned SDK path. The helper
links the pinned PTC client without changing the vendor checkout. It accepts
no network arguments, connects only to `192.168.123.20:9347`, calls only the
generic read-only `GetCorrectionInfo`, accepts only a bounded non-NUL response,
never prints the payload and refuses to overwrite or follow its output. The
manifest stage performs the strict 16-channel PandarXT CSV validation.

Immediately before running it, confirm:

- the robot is stationary and the E-stop operator is present;
- Control Bridge, Mapping, Nav2 and Dataset Capture are inactive;
- no Hesai driver or other PTC client is active;
- robot-side `eth0` is still `192.168.123.18/24` with no default gateway;
- the private staging directory is a real operator-owned directory, mode
  `0700`, and contains no previous output.

Run the helper once with `--approved-read-only-ptc` and the absolute private
staging directory. It creates only `xt16-correction.csv`, mode `0600`. Stop if
the response is outside the bounded CSV contract or if any unexpected
sensor/process state appears. Do not retry automatically.

The pinned SDK does not expose a documented PTC serial decoder for this model.
Read the installed sensor's serial from its physical label and have a
second operator cross-check it against the mounted XT16. Enter it into
`xt16-serial.txt` inside the same private directory with mode `0600`; do not
place it in a command argument, terminal transcript, Git, public diagnostic or
ticket. Then run:

```text
python3 scripts/hesai_calibration_manifest.py stage \
  ABSOLUTE_PRIVATE_DIRECTORY --timestamp-utc ISO_8601_UTC_Z
```

The stage command creates, without printing the serial or hash, a JSON
`xt16-calibration.manifest` that binds:

- product model `XT16` and pinned parser identity `PandarXT`;
- the physically cross-checked private serial;
- exact ROS wrapper and SDK revisions;
- fixed read-only acquisition method and UTC time;
- fixed installed correction path, bounded measured byte length and SHA-256.

There is intentionally no firetime entry.

## Transfer, install and validation

Transfer the three staged files only over the already authenticated SSH path
to a new mode-`0700` temporary directory on the external Orin. Before changing
the fixed targets, record whether they exist, their hashes, owner and mode in
the private rollback manifest. An unexpected existing target, symlink or
untracked backup stops deployment for review.

Install the correction and manifest atomically as `root`, group
`jetson_orin_nano`, mode `0640`, at:

```text
/etc/robot-scope/hesai/xt16-correction.csv
/etc/robot-scope/hesai/xt16-calibration.manifest
```

Do not install `xt16-serial.txt`; securely remove it and all transfer staging
copies only after the private deployment and rollback manifests are complete.
Run the validator as the runtime account:

```text
sudo -u jetson_orin_nano \
  /home/jetson_orin_nano/project/robot-scope/scripts/hesai_calibration_manifest.py \
  validate
```

The wireless driver runner performs the same validation before sourcing ROS or
starting the driver. Missing, symlinked, non-regular, wrong-owner/group,
broadly accessible, wrong-revision, wrong-model, wrong-path, wrong-length or
hash-mismatched state fails closed before any Hesai process starts. HW-2 still
must prove the driver accepts the exact correction and publishes one healthy
`/lidar_points`; repository validation cannot claim that hardware result.

## Rollback

Stop only launcher-owned wireless mapping children before restoring files.
Restore the exact prior correction/manifest pair from the private rollback
record, or remove the two new targets if neither existed. Never remove maps,
Dataset data, shared credentials, camera/control state, vendor workspaces or
network profiles. Leave all wireless mapping units disabled and inactive.
