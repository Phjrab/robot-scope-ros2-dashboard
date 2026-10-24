#!/usr/bin/env python3
"""Portable entry point for the unchanged historical partial-course renderer."""
from pathlib import Path
import sys
from restore_fixtures import ROOT, restore

if __name__ == '__main__':
    restore()
    revisions = ROOT / 'experiments/competition_vm/arena_robot_sim/revisions'
    sys.path.insert(0, str(revisions / 'full_course_flat_segments_20261024'))
    import render_segments
    render_segments.SLALOM = revisions / 'left_slalom_20261024/results/slalom_5.json'
    render_segments.main()
