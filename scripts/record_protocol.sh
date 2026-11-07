#!/bin/bash
# Guided image/IMU test: prints what to do and when (with a beep), records IMU + all fisheye
# images, and saves the cue schedule (phases.csv) next to the data.
# Usage: scripts/record_protocol.sh [name] [--quick | --short | --slam] [--show]
#   --quick  5-minute version with SLAM on throughout and a known-distance step along a 14-inch MacBook Pro
#   --short  3-minute version: gentle steps first and fast motion last, so a cable drop costs the least
#   --slam   75-second SLAM check over a measured distance: records poses and every 5th image
#   --show   live preview window
#   -> $DATA_DIR/<name>/   then run: scripts/analyze_session.sh $DATA_DIR/<name>
# The analysis finds the rest periods from the data, so starting each step a bit late is fine.
# If the IMU stops arriving (e.g. the cable dropped), the recording stops and says so: a re-plugged
# module restarts its clock, so data from after a re-plug can't be analysed with the data before it.
. "$(dirname "$0")/common.sh"
need_recorder
SHOW=
NAME=
SHORT=0
SLAM=0
QUICK=0
for arg in "$@"; do
    case $arg in
        --show) SHOW=--show ;;
        --no-show) SHOW= ;;
        --short) SHORT=1 ;;
        --slam) SLAM=1 ;;
        --quick) QUICK=1 ;;
        *) NAME=$arg ;;
    esac
done
if [ $(( SHORT + SLAM + QUICK )) -gt 1 ]; then echo "Use only one of --quick, --short and --slam."; exit 1; fi
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
TITLE="10-minute"; NEED_GB=25; NEED_NOTE="10 min at 30 fps needs ~20 GB"

if [ "$SHORT" = 1 ]; then
    PHASES="0,25,still_start,Leave the camera on the table and do not touch it
25,45,slow_rotate,Pick it up: SLOWLY tilt / turn / roll
45,60,still_1,Put it down on the table - do not touch
60,85,translate,Move forward/back / left/right / up/down WITHOUT rotating
85,100,still_2,Put it down - do not touch
100,130,walk,Walk around holding it like a UMI gripper (normal use)
130,145,still_3,Put it down - do not touch
145,165,fast_rotate,Pick it up: rotate FAST (last motion step)
165,180,still_end,Put it down in the same spot and do not touch it"
    TITLE="3-minute"; NEED_GB=8; NEED_NOTE="3 min at 30 fps needs ~7 GB"
fi
REC_ARGS=
if [ "$SLAM" = 1 ]; then
    PHASES="0,10,still_start,Leave the camera on the table and do not touch it
10,20,measured_move,Pick it up: move it SLOWLY along your measured distance
20,30,still_measured,PUT IT DOWN at the far end - do not touch
30,60,walk,Pick it up: walk a slow loop and keep detailed surfaces in view
60,65,return,Go back to the exact starting spot
65,75,still_end,PUT IT DOWN on the starting spot - do not touch"
    TITLE="75-second SLAM"; NEED_GB=1; NEED_NOTE="this test needs ~1 GB"
    REC_ARGS="--slam --save-every 5"
fi
if [ "$QUICK" = 1 ]; then
    PHASES="0,30,still_start,Leave the camera at the first MacBook corner and do not touch it
30,40,ruler_out,SLOWLY slide it along the long edge to the far corner without rotating
40,55,still_ruler_far,STOP at the far corner - do not touch
55,65,ruler_back,SLOWLY slide it back to the first corner without rotating
65,80,still_ruler_start,STOP at the first corner - do not touch
80,100,slow_rotate,Pick it up: SLOWLY tilt / turn / roll
100,115,still_1,Put it down on the table - do not touch
115,145,translate,Move forward/back / left/right / up/down WITHOUT rotating
145,160,still_2,Put it down - do not touch
160,220,walk,Walk around holding it like a UMI gripper (normal use)
220,235,still_3,Put it down - do not touch
235,255,fast_rotate,Pick it up: rotate FAST (last motion step)
255,285,still_end,Put it back at the first MacBook corner and do not touch it"
    TITLE="5-minute"; NEED_GB=13; NEED_NOTE="5 min at 30 fps needs ~11 GB"
    REC_ARGS="--slam"
fi
DURATION=$(echo "$PHASES" | tail -1 | cut -d, -f2)
STALL_S=6   # the recorder reports its counts every 2 s

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
[ -n "$FREE_GB" ] && [ "$FREE_GB" -lt "$NEED_GB" ] && echo "WARNING: only ${FREE_GB} GB free in $DATA_DIR ($NEED_NOTE)."

echo "=================================================================="
echo " $TITLE guided test -> $OUT"
echo " Follow the instructions as they appear."
echo " Hold the cable together with the camera so the plug isn't tugged."
[ "$SLAM" = 1 ] && echo " Mark out a measured distance on a table first."
[ "$QUICK" = 1 ] && echo " Close a 14-inch MacBook Pro flat on a hard table. Its long edge (about 31.3 cm) is your ruler." && echo " Start with the camera touching that edge at one corner, and keep the same point against the edge when sliding."
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
"$REC" "$OUT" "$DURATION" $REC_ARGS $SHOW > "$OUT/recorder.log" 2>&1 &
REC_PID=$!
# Wait until the recorder actually starts recording, so cues line up with the data.
until grep -q "Recording to" "$OUT/recorder.log" 2>/dev/null; do
    if ! kill -0 $REC_PID 2>/dev/null; then
        echo "Recorder stopped before recording:"; tail -5 "$OUT/recorder.log"; exit 1
    fi
    sleep 0.2
done
T0=$(date +%s)

# Returns 1 once the recorder's IMU count has not grown for STALL_S seconds.
LAST_IMU=-1; LAST_CHANGE=$T0; LAST_CHECK=0
stream_alive() {
    local now n
    now=$(date +%s)
    [ "$now" -gt "$LAST_CHECK" ] || return 0
    LAST_CHECK=$now
    n=$(tr '\r' '\n' < "$OUT/recorder.log" | sed -n 's/.*imu  *\([0-9][0-9]*\) (.*/\1/p' | tail -1)
    if [ -n "$n" ] && [ "$n" != "$LAST_IMU" ]; then
        LAST_IMU=$n; LAST_CHANGE=$now
    fi
    [ $(( now - LAST_CHANGE )) -lt "$STALL_S" ]
}

# Stop the recorder so it saves its data; don't wait forever if the SDK hangs on the lost device.
STALLED=0
stop_stalled() {
    STALLED=1
    printf '\a\a\a'
    echo
    echo "!!! Data stopped arriving about $(( LAST_CHANGE - T0 )) s in, so the recording is being stopped."
    echo "stopped_at_s=$(( LAST_CHANGE - T0 ))" > "$OUT/stream_stopped.txt"
    kill -INT $REC_PID 2>/dev/null
    for _ in $(seq 1 75); do
        kill -0 $REC_PID 2>/dev/null || return 0
        sleep 0.2
    done
    echo "Recorder did not stop by itself; killing it. The newest samples may be missing."
    kill -KILL $REC_PID 2>/dev/null
}

while IFS=, read -r start end phase text; do
    WARNED=0
    while [ $(( $(date +%s) - T0 )) -lt "$start" ]; do
        kill -0 $REC_PID 2>/dev/null || break 2
        stream_alive || { stop_stalled; break 2; }
        # Early warning before each rest, so the camera is down and still when the rest starts.
        case $phase in still*)
            if [ "$WARNED" = 0 ] && [ $(( start - ($(date +%s) - T0) )) -le 5 ]; then
                WARNED=1
                printf '\a'
                echo "        ... get ready, PUT IT DOWN in 5 s"
            fi ;;
        esac
        sleep 0.2
    done
    kill -0 $REC_PID 2>/dev/null || break
    printf '\a'
    echo
    echo "[$(printf '%3d' "$start")s]  >>> $text  ($((end - start)) s)"
done <<< "$PHASES"

while [ "$STALLED" = 0 ] && kill -0 $REC_PID 2>/dev/null; do
    stream_alive || { stop_stalled; break; }
    sleep 0.2
done
wait $REC_PID 2>/dev/null
echo
tr '\r' '\n' < "$OUT/recorder.log" | grep -E "^Done|No device"
camera_present || echo "NOTE: the camera is no longer connected (it dropped off USB during the recording)."
if [ "$STALLED" = 1 ]; then
    echo "Check the plug is seated, re-plug if needed, and run the test again."
    echo "The data up to that point is kept and can still be analysed:"
fi
echo "Session: $OUT"
echo "Analyse: $REPO/scripts/analyze_session.sh \"$OUT\""
[ "$STALLED" = 0 ] || exit 3
