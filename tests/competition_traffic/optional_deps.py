"""Skip only absent optional libraries, never missing internal package symbols."""
import importlib.util
import unittest

for dependency in ("cv2", "numpy", "jsonschema"):
    if importlib.util.find_spec(dependency) is None:
        raise unittest.SkipTest("C4 optional replay dependency unavailable: " + dependency)
