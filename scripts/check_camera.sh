#!/bin/bash
# Check the camera is connected at USB 3 and that IMU + fisheye actually stream (4 s probe).
# Usage: scripts/check_camera.sh        exit code 0 = ready
. "$(dirname "$0")/common.sh"
need_recorder

if ! camera_attach; then
    echo "FAIL: camera not found."
    is_wsl && "$USBIPD" list
    exit 1
fi

SPEED=$(camera_speed)
echo "Camera $VIDPID linked at ${SPEED:-?} Mbps"
if [ "${SPEED:-0}" -lt 5000 ]; then
    echo "FAIL: USB 2 link. The fisheye cameras do not stream below USB 3 (no error, just no frames)."
    echo "      Re-plug it: flip the USB-C plug, use a USB 3 port and a USB 3 cable, avoid hubs."
    exit 2
fi
echo "usbfs memory limit: $(cat /sys/module/usbcore/parameters/usbfs_memory_mb 2>/dev/null) MB"

OUT="$DATA_DIR/_probe"
rm -rf "$OUT"
RES=$(timeout 60 "$REC" "$OUT" 4 --no-images 2>&1 | tr '\r' '\n' | grep -E "^Done|No device")
echo "Probe: ${RES:-recorder gave no result}"
FE=$(echo "$RES" | sed -n 's/.*fisheye \([0-9]*\).*/\1/p')
IMU=$(echo "$RES" | sed -n 's/.*imu \([0-9]*\).*/\1/p')
if [ "${FE:-0}" -lt 10 ] || [ "${IMU:-0}" -lt 100 ]; then
    echo "FAIL: streams not running (imu=${IMU:-0}, fisheye=${FE:-0} in 4 s). Re-plug the camera and retry."
    exit 3
fi
echo "OK: camera ready (imu ${IMU} samples, fisheye ${FE} frames in 4 s)"
