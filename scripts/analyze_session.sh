#!/bin/bash
# Run every analysis that applies to a recorded session:
#   analyze.py           delivery: rates, loss on the device clock, latency, jitter   -> <session>/analysis/
#   image_metrics.py     per-frame exposure, sharpness, noise, feature motion         -> <session>/image_metrics.csv
#   protocol_analysis.py (if phases.csv) IMU rests, bias, gyro integration, blur,
#                        image-IMU time alignment                                     -> <session>/protocol_analysis/
# Usage: scripts/analyze_session.sh <session_dir> [--skip-images]
. "$(dirname "$0")/common.sh"
S=${1:?usage: analyze_session.sh <session_dir> [--skip-images]}
S="$(cd "$S" && pwd)"
A="$REPO/analysis"
export PYTHONIOENCODING=utf-8 MPLBACKEND=Agg

echo "=== stream delivery ==="
"$PYTHON" "$A/analyze.py" "$S" | grep -vE "^$" | head -40

if [ "$2" != "--skip-images" ] && [ -d "$S/fisheye" ] && [ -n "$(ls -A "$S/fisheye" 2>/dev/null | head -1)" ]; then
    echo "=== image metrics ($(ls "$S/fisheye" | wc -l) images; takes a while) ==="
    "$PYTHON" "$A/image_metrics.py" "$S" | grep -E "wrote|frame [0-9]*000/"
fi

if [ -f "$S/phases.csv" ]; then
    echo "=== protocol analysis ==="
    "$PYTHON" "$A/protocol_analysis.py" "$S" > /dev/null && echo "written: $S/protocol_analysis/protocol_report.md"
fi
echo
echo "Reports:"
ls "$S"/analysis/report.md "$S"/protocol_analysis/protocol_report.md 2>/dev/null
