#!/bin/bash
# Record short comparison sessions: streams only / + saving images / + SDK SLAM.
# Usage: scripts/record_sessions.sh [seconds]   -> $DATA_DIR/<stamp>_{streams,images,slam}
. "$(dirname "$0")/common.sh"
need_recorder
SECS=${1:-30}
STAMP=$(date +%Y%m%d_%H%M%S)
camera_attach || { echo "Camera not found"; exit 1; }
for mode in streams images slam; do
    case $mode in
        streams) args="--no-images" ;;
        images)  args="" ;;
        slam)    args="--no-images --slam" ;;
    esac
    out="$DATA_DIR/${STAMP}_$mode"
    echo "##### $mode -> $out"
    timeout $((SECS + 40)) "$REC" "$out" "$SECS" $args 2>&1 | tr '\r' '\n' | grep -E "^Done|No device|Cannot" \
        || echo "  (no 'Done': recorder crashed or hung)"
    sleep 3
    camera_present || { echo "Camera disappeared after $mode"; break; }
done
echo "Sessions: $DATA_DIR/${STAMP}_*"
