#!/bin/bash
# Record one session with cam_recorder.
# Usage: scripts/record.sh <name> <seconds> [--no-images] [--slam] [--show] [--save-every N]
#   -> $DATA_DIR/<name>/{imu.csv, fisheye.csv, pose.csv, fisheye/*.pgm, meta.txt}
. "$(dirname "$0")/common.sh"
need_recorder
NAME=${1:?usage: record.sh <name> <seconds> [recorder options]}
SECS=${2:-60}
shift 2
camera_attach || { echo "Camera not found"; exit 1; }
"$REC" "$DATA_DIR/$NAME" "$SECS" "$@"
