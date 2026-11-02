#!/bin/bash
# Print the test machine, OS, SDK and camera details as a markdown table.
# Usage: scripts/sysinfo.sh [log_dir_with_sdk_logs]   (firmware is read from SDK logs if given)
. "$(dirname "$0")/common.sh"
. /etc/os-release
CPU=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')
MODEL=$(cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name 2>/dev/null | tr '\n' ' ')
MEM=$(awk '/MemTotal/ {printf "%.1f GB", $2/1048576}' /proc/meminfo)
SDK=$(dpkg-query -W -f='${Version}' xvsdk 2>/dev/null)
FW=""
[ -n "$1" ] && FW=$(grep -ahoE "Device [Vv]ersion ?: ?[^ ]+[^(]*" "$1"/*.log 2>/dev/null | head -1 | sed 's/Device [Vv]ersion *: *//')
SN=$(lsusb -v -d "$VIDPID" 2>/dev/null | awk '/iSerial/ {print $3}' | head -1)
ENV="native Linux"; is_wsl && ENV="WSL2 (USB via usbipd / USB/IP)"
cat <<EOF
| item | value |
|---|---|
| machine | ${MODEL:-?} |
| CPU | $CPU ($(nproc) threads) |
| RAM | $MEM |
| OS | $PRETTY_NAME, kernel $(uname -r) |
| environment | $ENV |
| USB controllers | $(lspci 2>/dev/null | grep -i usb | cut -d: -f3 | sed 's/^ //' | paste -sd ';' - | cut -c1-150) |
| camera | USB $VIDPID, SN ${SN:-?}, link $(camera_speed) Mbps |
| firmware | ${FW:-? (see SDK log)} |
| SDK | ${SDK:-not installed} |
| usbfs memory | $(cat /sys/module/usbcore/parameters/usbfs_memory_mb 2>/dev/null) MB |
EOF
