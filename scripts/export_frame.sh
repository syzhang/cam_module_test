#!/bin/bash
# Save all cameras of one recorded frame side by side as a PNG.
# Usage: scripts/export_frame.sh <session_dir> <frame> <out.png>
. "$(dirname "$0")/common.sh"
"$PYTHON" - "$@" <<'EOF'
import sys, cv2, numpy as np, os
s, fr, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
imgs = [cv2.imread(os.path.join(s, "fisheye", "%08d_%d.pgm" % (fr, c)), cv2.IMREAD_GRAYSCALE) for c in range(4)]
imgs = [i for i in imgs if i is not None]
if not imgs:
    sys.exit("no images for frame %d in %s" % (fr, s))
cv2.imwrite(out, np.hstack(imgs))
print("wrote", out)
EOF
