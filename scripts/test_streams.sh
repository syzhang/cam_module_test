#!/bin/bash
# Start each stream on its own through the SDK's Python wrapper and report whether it works.
# Usage: scripts/test_streams.sh [out_dir] [streams...]     default streams: imu stereo rgb tof
# Writes <out_dir>/streams.md and per-stream logs; sample images land in <out_dir>.
. "$(dirname "$0")/common.sh"
OUT="${1:-$DATA_DIR/$(date +%Y%m%d_%H%M%S)_streams}"
shift
STREAMS="${*:-imu stereo rgb tof}"
mkdir -p "$OUT"
camera_attach || { echo "Camera not found"; exit 1; }

{
    echo "# Stream test ($(date '+%Y-%m-%d %H:%M'))"
    echo
    echo "| stream | result | rate | details |"
    echo "|---|---|---|---|"
} > "$OUT/streams.md"

for s in $STREAMS; do
    echo "##### $s"
    log="$OUT/smoke_$s.log"
    STREAMS=$s timeout 60 "$PYTHON" -u "$REPO/scripts/smoke_test.py" 8 "$OUT" > "$log" 2>&1
    code=$?
    # smoke_test prints e.g. "imu      1619 unique samples  ~202.3 Hz"
    rate=$(grep -E "Hz" "$log" | grep -E "^$s " | awk '{print $5, $6}')
    detail=$(grep -E "^(fisheye|rgb|tof):" "$log" | head -1)
    case $code in
        0)   num=$(echo "$rate" | cut -d' ' -f1 | tr -dc '0-9.')
             result=$(awk -v r="${num:-0}" 'BEGIN{exit !(r+0 > 0)}' && echo "OK" || echo "no data") ;;
        139) result="CRASH (segfault)" ;;
        124) result="HANG (timeout)" ;;
        *)   result="FAIL (exit $code)" ;;
    esac
    [ "$code" -eq 139 ] && detail="$(dmesg 2>/dev/null | tail -1 | cut -c1-80)"
    echo "  -> $result ${rate}"
    echo "| $s | $result | ${rate:--} | ${detail:--} |" >> "$OUT/streams.md"
    sleep 3
    camera_present || { echo "Camera disappeared after $s"; echo "| (camera disconnected after $s) | | | |" >> "$OUT/streams.md"; break; }
done
echo
cat "$OUT/streams.md"
