"""Optional fixed lamp-region experiment; never feeds stable mission evidence."""
import math
from experiments.competition_vm.traffic_signals.core import classify_roi


def lamp_diagnostic(bgr, bbox):
    x1, y1, x2, y2 = bbox
    # A predefined housing prior, independent of pixels, colors, labels or GT.
    upper = (x1, y1, x2, math.ceil(y1 + .55*(y2-y1)))
    def measure(box, variant):
        return {k: v for k, v in classify_roi(bgr, box, variant=variant).items() if k != "mask"}
    return {"profile": "upper-housing-55pct.v1", "diagnostic_only": True,
            "color_reconstruction_claimed": False, "native_region": list(upper),
            "housing_combined": measure(bbox, "combined"),
            "upper_combined": measure(upper, "combined"),
            "upper_hsv_only": measure(upper, "hsv")}
