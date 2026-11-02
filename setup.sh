#!/bin/bash
# One-time setup on Ubuntu (20.04 recommended by the vendor; 22.04/24.04 also work):
#   1. apt dependencies          4. Python venv (.venv) with the analysis packages
#   2. vendor SDK .deb           5. build the recorder and the vendor demos into build/
#   3. udev rule for USB access
# The vendor SDK is not in this repo: unzip the vendor package into the folder named in sdk.conf
# (default ../vendor_sdk), or pass --sdk DIR / SDK_DIR=... . The .deb and udev rule are found inside it.
# Usage: ./setup.sh [--sdk DIR] [--no-sdk] [--no-demos]   (asks for sudo for steps 1-3)
#        SDK_DEB=/path/to/sdk.deb ./setup.sh               to install a specific .deb
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
ENV_SDK_DIR="$SDK_DIR"
. "$REPO/sdk.conf"
SDK_DIR="${ENV_SDK_DIR:-$SDK_DIR}"
INSTALL_SDK=1
BUILD_DEMOS=1
while [ $# -gt 0 ]; do
    case $1 in
        --sdk) SDK_DIR="$2"; shift ;;
        --no-sdk) INSTALL_SDK=0 ;;
        --no-demos) BUILD_DEMOS=0 ;;
        *) echo "unknown option $1"; exit 1 ;;
    esac
    shift
done
step() { echo; echo "=== $* ==="; }

if [ "$INSTALL_SDK" = 1 ]; then
    case $SDK_DIR in /*) ;; *) SDK_DIR="$REPO/$SDK_DIR" ;; esac
    sdk_missing() {
        echo "Vendor SDK not found in: $SDK_DIR ($1)"
        echo "Unzip the vendor SDK package into that folder (or set SDK_DIR in sdk.conf),"
        echo "or run: ./setup.sh --sdk /path/to/unzipped/sdk"
        exit 1
    }
    [ -d "$SDK_DIR" ] || sdk_missing "folder does not exist"
    SDK_DIR="$(cd "$SDK_DIR" && pwd)"
    # Prefer the exact build these tests were made with, else the newest .deb in the package.
    if [ -z "$SDK_DEB" ]; then
        while IFS= read -r f; do
            [ "$(sha256sum "$f" | cut -d' ' -f1)" = "$SDK_DEB_SHA256" ] && SDK_DEB="$f" && break
        done < <(find "$SDK_DIR" -name "*.deb" | sort -r)
        SDK_DEB="${SDK_DEB:-$(find "$SDK_DIR" -name "*.deb" | sort | tail -1)}"
    fi
    [ -f "$SDK_DEB" ] || sdk_missing "no .deb found"
    UDEV_RULE="$(find "$SDK_DIR" -name "*.rules" | head -1)"
    [ -f "$UDEV_RULE" ] || sdk_missing "no udev .rules file found"
    echo "SDK: $SDK_DEB"
    if [ "$(sha256sum "$SDK_DEB" | cut -d' ' -f1)" != "$SDK_DEB_SHA256" ]; then
        echo "Note: this .deb is not the build these tests were made with (sha256 in sdk.conf); results may differ."
    fi
fi

. /etc/os-release
echo "OS: $PRETTY_NAME ($(uname -m)), kernel $(uname -r)"
[ "$VERSION_ID" = "20.04" ] || echo "Note: the SDK is built for Ubuntu 20.04 (focal); other versions worked in testing but are not vendor-supported."

if [ "$INSTALL_SDK" = 1 ]; then
    step "1/5 apt dependencies"
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential cmake pkg-config git gdb usbutils \
        libusb-1.0-0-dev libudev-dev libjpeg-dev zlib1g-dev libopencv-dev rapidjson-dev libeigen3-dev \
        libboost-dev libboost-chrono-dev libboost-date-time-dev libboost-filesystem-dev libboost-system-dev \
        libboost-thread-dev libboost-program-options-dev libcereal-dev liboctomap-dev libv4l-dev \
        dh-exec doxygen graphviz lsb-release \
        python3-pip python3-venv python3-numpy python3-opencv

    step "2/5 vendor SDK: $(basename "$SDK_DEB")"
    sudo dpkg -i "$SDK_DEB" || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --fix-broken
    sudo ldconfig
    dpkg -s xvsdk | grep -E "^(Status|Version)"

    step "3/5 udev rule (USB access without root)"
    sudo cp "$UDEV_RULE" /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger || true
    echo "Re-plug the camera if it was already connected."
fi

step "4/5 Python environment (.venv, uses the system OpenCV)"
python3 -m venv --system-site-packages "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --upgrade pip
"$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
"$REPO/.venv/bin/python" -c "import cv2, numpy, pandas, matplotlib; print('python ok: cv2', cv2.__version__, 'numpy', numpy.__version__, 'pandas', pandas.__version__)"

step "5/5 build"
cmake -S "$REPO/recorder" -B "$REPO/build/recorder" -DCMAKE_BUILD_TYPE=Release > /dev/null
make -C "$REPO/build/recorder" -j"$(nproc)" 2>&1 | grep -E "error|warning|Built target" || true
test -x "$REPO/build/recorder/cam_recorder" && echo "recorder: $REPO/build/recorder/cam_recorder"
if [ "$BUILD_DEMOS" = 1 ]; then
    for d in all_stream multi-devices-c-interface; do
        rm -rf "$REPO/build/src/$d"
        mkdir -p "$REPO/build/src"
        cp -r "/usr/share/xvsdk/$d" "$REPO/build/src/$d"
        cmake -S "$REPO/build/src/$d" -B "$REPO/build/$d" -DCMAKE_BUILD_TYPE=Release > /dev/null
        make -C "$REPO/build/$d" -j"$(nproc)" 2>&1 | grep -E "error|Built target" || true
    done
fi

echo
echo "Setup done. Plug the camera into a USB 3 port, then:"
echo "  scripts/check_camera.sh      # USB 3 link + 4 s stream probe"
echo "  scripts/run_full_test.sh     # everything: stream tests, vendor demos, guided 10-min test, analysis"
