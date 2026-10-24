#!/usr/bin/env python3
"""Check selected video hashes, decoded frame counts, dimensions and timing."""
from pathlib import Path
import hashlib
import json
import subprocess
from restore_fixtures import ROOT, HERE

R = ROOT / 'experiments/competition_vm/arena_robot_sim/revisions'

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_entries', 'stream=width,height,r_frame_rate,nb_read_frames', '-show_entries', 'format=duration,size', '-of', 'json', str(path)]))

def main():
    manifest = json.loads((HERE / 'PUBLICATION_SUBSET.json').read_text())
    selected = [entry for entry in manifest['included'] if entry['path'].endswith('.mp4')]
    results = []
    old_meta = json.loads((R / 'articulated-20261024/output/RENDER_VALIDATION.json').read_text())
    new_meta = json.loads((R / 'articulated-curved-20261024/output/COMPARISON_VIDEO_VALIDATION.json').read_text())
    flat_meta = json.loads((R / 'full_course_flat_segments_20261024/output/RENDER_VALIDATION.json').read_text())
    expectations = {
        'go2_articulated_slalom_and_blocked.mp4': (960, 770, '15/1', sum(value['frame_count'] for value in old_meta.values())),
        'go2_open_diagnostic_before_after.mp4': (1280, 570, '15/1', int(new_meta['probe']['streams'][0]['nb_frames'])),
        'full_course_partial_closed_loop.mp4': (1280, 860, '12/1', int(flat_meta['ffprobe']['streams'][0]['nb_read_frames'])),
    }
    for entry in selected:
        path = ROOT / entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
        data = probe(path)
        stream = data['streams'][0]
        actual = (stream['width'], stream['height'], stream['r_frame_rate'], int(stream['nb_read_frames']))
        assert actual == expectations[path.name], (path.name, actual, expectations[path.name])
        numerator, denominator = map(int, stream['r_frame_rate'].split('/'))
        assert abs(float(data['format']['duration']) - actual[-1] * denominator / numerator) < .001
        results.append({'path': entry['path'], 'sha256': entry['sha256'], 'status': 'PASS', 'probe': data})
    out = HERE / 'validation/selected_videos.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({'scope': 'File integrity and decoded frame/timing checks; not new physical validation', 'results': results}, indent=2) + '\n')
    print(f'{len(results)} selected videos passed byte and decoded frame/timing checks')

if __name__ == '__main__':
    main()
