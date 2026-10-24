#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TRACE_DIR="$1"
if [[ "${SKIP_LABEL:-0}" != "1" ]]; then
python3 "$HERE/label_frames.py" open_normal --trace-path "$TRACE_DIR/open_normal.json" --title 'OPEN DIAGNOSTIC - CURVED' --motion-label 'HOLONOMIC + YAW'
python3 "$HERE/label_frames.py" open_baseline --trace-path "$TRACE_DIR/open_baseline.json" --title 'OPEN DIAGNOSTIC - BASELINE' --motion-label 'FIXED YAW'
fi
for case in open_normal open_baseline; do
 ffmpeg -y -v error -framerate 15 -i "$HERE/output/$case/labeled/%04d.png" -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p "$HERE/output/go2_articulated_$case.mp4"
done
ffmpeg -y -v error -i "$HERE/output/go2_articulated_open_baseline.mp4" -i "$HERE/output/go2_articulated_open_normal.mp4" -filter_complex "[0:v]scale=640:514,tpad=stop_mode=clone:stop_duration=30,drawtext=text='BASELINE ENDED - LAST FRAME HELD':fontcolor=yellow:fontsize=16:box=1:boxcolor=black@0.7:x=12:y=435:enable='gte(t,26.6)'[a];[1:v]scale=640:514[b];[a][b]hstack=shortest=1,pad=1280:570:0:56:color=0x101720,drawtext=text='OPEN DIAGNOSTIC LAYOUT - NOT ORIGINAL TIGHT LAYOUT':fontcolor=white:fontsize=22:x=20:y=8,drawtext=text='SAME CONES | 1x recorded replay | KINEMATIC / SYNTHETIC PLANAR - NOT DYNAMICS':fontcolor=yellow:fontsize=16:x=20:y=35[v]" -map '[v]' -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p "$HERE/output/go2_open_diagnostic_before_after.mp4"
python3 "$HERE/verify_render.py" --trace-dir "$TRACE_DIR" --cases open_normal open_baseline
