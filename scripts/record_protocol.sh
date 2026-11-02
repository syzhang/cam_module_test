#!/bin/bash
# Guided 10-minute image/IMU test: prints what to do and when (with a beep), records IMU + all
# fisheye images, and saves the cue schedule (phases.csv) next to the data.
# Usage: scripts/record_protocol.sh [name] [--show]      (--show opens a live preview window)
#   -> $DATA_DIR/<name>/   then run: scripts/analyze_session.sh $DATA_DIR/<name>
# The analysis finds the rest periods from the data, so starting each step a bit late is fine.
. "$(dirname "$0")/common.sh"
need_recorder
SHOW=
NAME=
for arg in "$@"; do
    case $arg in
        --show) SHOW=--show ;;
        --no-show) SHOW= ;;
        *) NAME=$arg ;;
    esac
done
NAME=${NAME:-$(date +%Y%m%d_%H%M%S)_protocol}
OUT="$DATA_DIR/$NAME"

# start_s,end_s,phase,instruction
PHASES="0,60,still_start,Put the camera on the table and do not touch it
60,80,slow_pitch,Pick it up: SLOWLY tilt up and down (nod)
80,100,slow_yaw,SLOWLY turn left and right (shake head)
100,120,slow_roll,SLOWLY roll clockwise / anticlockwise
120,140,still_1,Put it down on the table - do not touch
140,160,fast_pitch,Pick it up: tilt up/down FAST
160,180,fast_yaw,Turn left/right FAST
180,200,fast_roll,Roll FAST
200,220,still_2,Put it down - do not touch
220,250,translate_fb,Move forward/back WITHOUT rotating (keep it pointing the same way)
250,280,translate_lr,Move left/right WITHOUT rotating
280,300,translate_ud,Move up/down WITHOUT rotating
300,320,still_3,Put it down - do not touch
320,480,walk,Walk around the room holding it like a UMI gripper (normal use)
480,500,still_4,Put it down - do not touch
500,540,mixed_fast,Mixed fast motion: rotate and move quickly in all directions
540,600,still_end,Put it back on the table in the same spot and do not touch it"

if ! camera_attach; then
    echo "Camera not found. Plug it in, then run this again."
    exit 1
fi
SPEED=$(camera_speed)
if [ "${SPEED:-0}" -lt 5000 ]; then
    echo "WARNING: camera is linked at ${SPEED:-?} Mbps (USB 2). The fisheye cameras will NOT stream."
    echo "Re-plug it (flip the USB-C plug, use a USB 3 port/cable), then run this again."
    read -rp "Type 'imu' + Enter to record IMU only anyway, or just Enter to exit: " ans
    [ "$ans" = "imu" ] || exit 1
fi
FREE_GB=$(df -BG --output=avail "$DATA_DIR" 2>/dev/null | tail -1 | tr -dc 0-9)
[ -n "$FREE_GB" ] && [ "$FREE_GB" -lt 25 ] && echo "WARNING: only ${FREE_GB} GB free in $DATA_DIR (10 min at 30 fps needs ~20 GB)."

echo "=================================================================="
echo " 10-minute guided test -> $OUT"
echo " Follow the instructions as they appear. Each step lasts 20-160 s."
if [ -n "$SHOW" ]; then echo " Preview window: press q in it to stop early."; else echo " Press Ctrl+C here to stop early (data so far is kept)."; fi
echo "=================================================================="
echo "$PHASES" | awk -F, '{printf "  %3d-%3ds  %s\n", $1, $2, $4}'
echo
read -rp "Place the camera on the table, then press Enter to start... "

mkdir -p "$OUT"
echo "start_s,end_s,phase,instruction" > "$OUT/phases.csv"
echo "$PHASES" >> "$OUT/phases.csv"

# Ctrl+C reaches the recorder too (it stops and flushes); keep this script alive to finish up.
trap 'echo; echo "Stopping early..."' INT
"$REC" "$OUT" 600 $SHOW > "$OUT/recorder.log" 2>&1 &
REC_PID=$!
# Wait until the recorder actually starts recording, so cues line up with the data.
until grep -q "Recording to" "$OUT/recorder.log" 2>/dev/null; do
    if ! kill -0 $REC_PID 2>/dev/null; then
        echo "Recorder stopped before recording:"; tail -5 "$OUT/recorder.log"; exit 1
    fi
    sleep 0.2
done
T0=$(date +%s)

while IFS=, read -r start end phase text; do
    while [ $(( $(date +%s) - T0 )) -lt "$start" ]; do
        kill -0 $REC_PID 2>/dev/null || break 2
        sleep 0.2
    done
    kill -0 $REC_PID 2>/dev/null || break
    printf '\a'
    echo
    echo "[$(printf '%3d' "$start")s]  >>> $text  ($((end - start)) s)"
done <<< "$PHASES"

wait $REC_PID
echo
tr '\r' '\n' < "$OUT/recorder.log" | grep -E "^Done|No device"
camera_present || echo "NOTE: the camera is no longer connected (it dropped off USB during the recording)."
echo "Session: $OUT"
echo "Analyse: $REPO/scripts/analyze_session.sh \"$OUT\""
