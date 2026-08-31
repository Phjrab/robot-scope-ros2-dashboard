# Robot-side wireless checkout staging

The reviewed robot-side service contract uses the fixed, currently absent
path `/home/unitree/project/robot-scope`. This is a deployment prerequisite,
not permission to repoint a unit to an older checkout or to create the path
before `APPROVE_WIRELESS_XT16_DEPLOY`.

During the approved deployment, freeze the exact `main` commit that passed the
final repository tests and record its full commit ID and source archive
SHA-256 in the private deployment manifest. Produce the archive from the clean
operator checkout; never package `.git`, credentials, private environment
files, node modules, ROS build/install/log trees, maps, PCD, bags or Dataset
content.

On the robot-side Jetson:

1. Reconfirm `/home/unitree/project/robot-scope` is absent. If it appeared,
   stop and inventory it instead of overwriting or merging it.
2. Transfer the archive over strict host-key-checked SSH to a new private
   staging directory and verify its SHA-256 against the private deployment
   manifest.
3. Extract without privilege into a new directory owned by `unitree`, reject
   absolute paths, parent traversal, symlinks escaping the tree and unexpected
   device/FIFO/socket entries, then verify the required runner and forced
   command files against the source manifest.
4. Rename that complete directory once to the fixed service path. Do not use a
   mutable symlink, partial copy or live in-place update.
5. Install the reviewed root-owned service and forced-command files from that
   exact tree, validate their hashes and leave every new unit disabled and
   inactive.

If a prior fixed directory is found in a later update, first stop only the new
wireless sensor services, rename the complete prior tree to a commit-labelled
private rollback directory, and then rename the fully verified new tree into
place. Rollback reverses those two complete-directory renames. It does not
touch Control Bridge, camera services, `eth0`/`wlan0`, credentials shared with
other features, maps or Dataset data.

The robot-side checkout resolves code provenance only. It does not authorize
PTC access, service start, firewall mutation, Mapping, Nav2, a control lease or
motion. The external Orin remains the mapping owner.
