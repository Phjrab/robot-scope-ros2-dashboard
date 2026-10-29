import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from robot_dashboard.expansion_diagnostics.measure import duration, stats, breakdown, encoded, Measurements
from robot_dashboard.expansion_diagnostics.dependencies import verify, PINS


class DiagnosticTests(unittest.TestCase):
    def test_cross_clock_and_reversed_time_are_unknown(self):
        self.assertEqual(duration({'clock':'a','ns':1}, {'clock':'b','ns':99})['status'], 'UNKNOWN')
        self.assertEqual(duration({'clock':'a','ns':99}, {'clock':'a','ns':1})['status'], 'UNKNOWN')
        self.assertEqual(duration({'clock':'a','ns':1}, {'clock':'a','ns':99})['duration_ns'],98)

    def test_percentiles_and_empty_are_explicit(self):
        self.assertEqual(stats([])['p95_ms'],None)
        self.assertEqual(stats([30,10,20]),dict(n=3,p50_ms=20,p95_ms=30,max_ms=30))

    def test_json_partition_is_additive_with_utf8_and_nested_provenance(self):
        frame={'obstacles':[{'geometry':{'center':[1.,2.,3.]},'provenance':{'source':{'id':'한글'}}}],
               'health':{'state':'ok'},'input_sources':[{'id':'원본'}]}
        parts=breakdown(frame)
        self.assertEqual(parts['total'],len(encoded(frame)))
        self.assertEqual(parts['total'],sum(v for k,v in parts.items() if k!='total'))

    def test_warmup_excluded_and_failure_duration_retained(self):
        m=Measurements()
        m.warmup=True
        m.call('stage',lambda:None)
        self.assertEqual(m.summary(),{})
        m.warmup=False
        with self.assertRaises(ValueError):
            m.call('stage',lambda: (_ for _ in ()).throw(ValueError('expected')))
        self.assertEqual(m.summary()['/stage']['n'],1)
        self.assertEqual(m.events[-1]['outcome'],'RAISED')

    def test_dependency_mismatch_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'pins.json').write_text(json.dumps(PINS))
            file=p/'C1'/'x.py'
            file.parent.mkdir()
            file.write_text('modified')
            file.chmod(0o444)
            with patch('robot_dashboard.expansion_diagnostics.dependencies.git',return_value=b'100644 blob 0000000000000000000000000000000000000000\tx.py\n'):
                with self.assertRaisesRegex(ValueError,'BLOB_DIFFERS'):
                    verify('.',p)

    def test_report_recreation_uses_saved_json_only(self):
        from robot_dashboard.expansion_diagnostics.report import markdown
        evidence=Path(__file__).resolve().parents[2]/'experiments/expansion_20261030/c7_capacity/baseline.json'
        data=json.loads(evidence.read_text())
        first=markdown(data)
        self.assertEqual(first,markdown(json.loads(json.dumps(data))))
        self.assertIn('NOT_DRIVING_AUTHORIZATION',first)

    @unittest.skipUnless(os.environ.get('C7_DEPENDENCY_ROOT'),'explicit exact owner exports required; no automatic fetch')
    def test_actual_owner_boundaries_in_isolated_interpreter(self):
        run=subprocess.run([sys.executable,'-m','tests.expansion_c7.integration_check'],capture_output=True,text=True,timeout=60,
                           env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
