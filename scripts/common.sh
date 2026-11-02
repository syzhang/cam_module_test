# Shared settings and helpers. Source it:  . "$(dirname "$0")/common.sh"
#
# Override with environment variables:
#   DATA_DIR   where recordings go            (default: <repo>/data)
#   BUILD_DIR  where the recorder/demos build  (default: <repo>/build)
#   PYTHON     python used for scripts/analysis (default: <repo>/.venv/bin/python, else python3)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$REPO/data}"
BUILD_DIR="${BUILD_DIR:-$REPO/build}"
REC="$BUILD_DIR/recorder/cam_recorder"
if [ -z "$PYTHON" ]; then
    if [ -x "$REPO/.venv/bin/python" ]; then PYTHON="$REPO/.venv/bin/python"; else PYTHON=python3; fi
fi
VIDPID="040e:f508"
USBIPD="/mnt/c/Program Files/usbipd-win/usbipd.exe"

is_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }

camera_present() { lsusb 2>/dev/null | grep -q "$VIDPID"; }

# Make sure the camera is visible. Native Linux: wait for it to be plugged in.
# WSL: attach it through usbipd-win (it must have been bound once from an admin PowerShell:
#      usbipd list, then usbipd bind --busid <BUSID>).
camera_attach() {
    camera_present && return 0
    if is_wsl && [ -x "$USBIPD" ]; then
        echo "Attaching camera to WSL via usbipd..."
        "$USBIPD" attach --wsl --hardware-id "$VIDPID" 2>&1 | grep -viE "^usbipd: info|localhost proxy"
    else
        echo "Waiting for the camera (USB $VIDPID) to be plugged in..."
    fi
    for _ in $(seq 1 20); do camera_present && return 0; sleep 1; done
    return 1
}

# Link speed in Mbps (5000 = USB 3, 480 = USB 2), empty if not found.
camera_speed() {
    local d
    for d in /sys/bus/usb/devices/*; do
        if [ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" = "$VIDPID" ]; then
            cat "$d/speed"
            return
        fi
    done
}

need_recorder() {
    if [ ! -x "$REC" ]; then
        echo "Recorder not built ($REC). Run ./setup.sh first."
        exit 1
    fi
}
