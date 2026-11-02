#!/bin/bash
# Full module test, start to finish, into one folder with one combined REPORT.md:
#   1. camera check        USB 3 link + 4 s stream probe
#   2. stream test         each stream on its own (IMU, fisheye, RGB, ToF): works / crashes / no data
#   3. vendor demos        the SDK's own demos, to tell SDK bugs from ours   (skip: --no-demos)
#   4. comparison sessions 30 s streams-only / +images / +SDK SLAM          (skip: --no-sessions)
#   5. guided 10-min test  rests, rotations, translations, walking (interactive, follow the cues)
#   6. analysis            delivery, image quality, IMU quality, image-IMU time alignment
# Usage: scripts/run_full_test.sh [--no-demos] [--no-sessions] [--show]
# Output: $DATA_DIR/<stamp>_fulltest/REPORT.md  (+ all raw data and per-step reports)
. "$(dirname "$0")/common.sh"
need_recorder
DEMOS=1; SESSIONS=1; SHOW=
for a in "$@"; do
    case $a in
        --no-demos) DEMOS=0 ;;
        --no-sessions) SESSIONS=0 ;;
        --show) SHOW=--show ;;
        *) echo "unknown option $a"; exit 1 ;;
    esac
done
STAMP=$(date +%Y%m%d_%H%M%S)
RUN="$DATA_DIR/${STAMP}_fulltest"
mkdir -p "$RUN"
S="$REPO/scripts"
echo "Full test -> $RUN"

# The module has been seen to hang or drop off USB; after each crashy step make sure it's back.
ready() {
    while ! bash "$S/check_camera.sh" > "$RUN/check_camera.log" 2>&1; do
        tail -3 "$RUN/check_camera.log"
        echo "Camera not ready. Re-plug it (USB 3 port), then press Enter to retry, or type 'skip' + Enter to skip: "
        read -r ans
        [ "$ans" = "skip" ] && return 1
    done
    grep "OK:" "$RUN/check_camera.log"
}

echo; echo "===== 1. camera check ====="
ready || { echo "No camera, stopping."; exit 1; }

echo; echo "===== 2. stream test ====="
bash "$S/test_streams.sh" "$RUN/streams" imu stereo rgb tof
ready || true

if [ "$DEMOS" = 1 ]; then
    echo; echo "===== 3. vendor demos ====="
    bash "$S/vendor_demos.sh" "$RUN/vendor_demos"
    ready || true
fi

if [ "$SESSIONS" = 1 ]; then
    echo; echo "===== 4. comparison sessions (30 s each) ====="
    for mode in streams images slam; do
        case $mode in streams) args="--no-images" ;; images) args="" ;; slam) args="--no-images --slam" ;; esac
        printf '%-8s ' "$mode"
        timeout 90 "$REC" "$RUN/session_$mode" 30 $args 2>&1 | tr '\r' '\n' | grep -E "^Done|No device" \
            || echo "(no 'Done': recorder crashed or hung)"
        sleep 3
        ready > /dev/null || break
    done
fi

echo; echo "===== 5. guided 10-minute test ====="
ready || true
bash "$S/record_protocol.sh" "$(basename "$RUN")/protocol" $SHOW

echo; echo "===== 6. analysis ====="
for d in "$RUN"/session_*; do
    [ -f "$d/imu.csv" ] && "$PYTHON" "$REPO/analysis/analyze.py" "$d" > /dev/null 2>&1
done
[ -f "$RUN/protocol/imu.csv" ] && bash "$S/analyze_session.sh" "$RUN/protocol"

# ---- combined report ----------------------------------------------------------------------
R="$RUN/REPORT.md"
{
    echo "# Camera module full test — $(date '+%Y-%m-%d %H:%M')"
    echo
    echo "## Test machine"
    echo
    bash "$S/sysinfo.sh" "$RUN/streams"
    echo
    echo "## 1–2. Streams (each started on its own)"
    echo
    sed '1,2d' "$RUN/streams/streams.md" 2>/dev/null
    if [ -f "$RUN/vendor_demos/vendor_demos.md" ]; then
        echo
        echo "## 3. Vendor demos"
        echo
        sed '1,2d' "$RUN/vendor_demos/vendor_demos.md"
    fi
    for mode in streams images slam; do
        rep="$RUN/session_$mode/analysis/report.md"
        [ -f "$rep" ] || continue
        echo
        echo "## 4. Session: $mode (30 s)"
        echo
        sed '1,2d' "$rep" | grep -vE "^Plots:|^- [a-z_]*\.png"
        [ "$mode" = slam ] && [ -f "$RUN/session_slam/pose.csv" ] && \
            echo && echo "SLAM pose samples: $(($(wc -l < "$RUN/session_slam/pose.csv") - 1))"
    done
    if [ -f "$RUN/protocol/analysis/report.md" ]; then
        echo
        echo "## 5. Guided test: delivery"
        echo
        sed '1,2d' "$RUN/protocol/analysis/report.md" | grep -vE "^Plots:|^- [a-z_]*\.png"
    fi
    if [ -f "$RUN/protocol/protocol_analysis/protocol_report.md" ]; then
        echo
        echo "## 6. Guided test: IMU, images, image–IMU alignment"
        echo
        sed '1,2d' "$RUN/protocol/protocol_analysis/protocol_report.md" | sed 's/^## /### /'
        echo
        echo "Plots: \`protocol/protocol_analysis/*.png\`, contact sheet: \`protocol/contact_sheet.png\`."
    fi
    echo
    echo "Compare with the WSL results in \`docs/wsl_results/\` of the repo."
} > "$R"
echo
echo "Done. Combined report: $R"
