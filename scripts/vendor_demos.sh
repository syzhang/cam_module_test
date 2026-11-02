#!/bin/bash
# Run the vendor's own demos (built by setup.sh) under gdb for a fixed time and report crashes.
# Confirms whether a stream problem (e.g. the RGB crash) is in the SDK rather than our code.
# Usage: scripts/vendor_demos.sh [out_dir]
. "$(dirname "$0")/common.sh"
OUT="${1:-$DATA_DIR/$(date +%Y%m%d_%H%M%S)_vendor_demos}"
SECS=${SECS:-15}
mkdir -p "$OUT"
camera_attach || { echo "Camera not found"; exit 1; }
command -v gdb > /dev/null || { echo "gdb not installed (sudo apt install gdb)"; exit 1; }
OFF="rgb2:0 tof:0 sgbm:0 slam:0 eyetracking:0 ir:0 RGBD:0 Dewarp:0 stereo_planes:0"

echo "# Vendor demos ($(date '+%Y-%m-%d %H:%M'), ${SECS}s each)" > "$OUT/vendor_demos.md"
echo >> "$OUT/vendor_demos.md"

run() {  # name, log, command...
    local name=$1 log=$2; shift 2
    echo "##### $name"
    (cd "$(dirname "$1")" && timeout -s INT "$SECS" gdb -q -batch -ex run -ex bt --args "$@" > "$log" 2>&1 < /dev/null)
    if grep -q "SIGSEGV" "$log"; then
        echo "- **$name**: CRASH (SIGSEGV)" | tee -a "$OUT/vendor_demos.md"
        grep -A8 "SIGSEGV" "$log" | grep -E "^#[0-9]" | head -4 | sed 's/^/    /' | tee -a "$OUT/vendor_demos.md"
    elif grep -qiE "cannot open display|cannot connect to X|initialize GTK" "$log"; then
        echo "- **$name**: needs a desktop session (the stream demo opens OpenCV windows; DISPLAY not set)" | tee -a "$OUT/vendor_demos.md"
    elif grep -q "no device found" "$log"; then
        echo "- **$name**: no device found" | tee -a "$OUT/vendor_demos.md"
    else
        echo "- **$name**: ran ${SECS}s without crashing" | tee -a "$OUT/vendor_demos.md"
        grep -aE "fps" "$log" | grep -v "^\s" | tail -2 | cut -c1-160 | sed 's/^/    /' | tee -a "$OUT/vendor_demos.md"
    fi
    sleep 3
}

AS="$BUILD_DIR/all_stream/all_stream"
CI="$BUILD_DIR/multi-devices-c-interface/multi-devices-c-interface"
run "stream demo: RGB only" "$OUT/all_stream_rgb.log" "$AS" "" "rgb:1 fisheye:0 imu:0 $OFF"
run "stream demo: fisheye + IMU" "$OUT/all_stream_fe.log" "$AS" "" "rgb:0 fisheye:1 imu:1 $OFF"
run "stream demo: ToF only" "$OUT/all_stream_tof.log" "$AS" "" "rgb:0 fisheye:0 imu:0 tof:1 rgb2:0 sgbm:0 slam:0 eyetracking:0 ir:0 RGBD:0 Dewarp:0 stereo_planes:0"
run "C interface (fisheye + SLAM + RGB)" "$OUT/c_interface.log" "$CI"
echo
echo "Report: $OUT/vendor_demos.md"
