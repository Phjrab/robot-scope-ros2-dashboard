#!/usr/bin/env python3
"""Explicit publisher reroot adapter for immutable VM-specific reviewer scripts.

Only path assignments/constants change in memory. Frozen review files and their
SHA256SUMS are never modified. This is not a fresh independent reviewer.
"""
from pathlib import Path
import ast, json, sys
from publication_checks import HERE, REVISIONS, verify_and_restore


def main():
    verify_and_restore(False)
    kind, output = sys.argv[1], Path(sys.argv[2]).resolve()
    if kind == 'progress':
        source = HERE / 'review/review.py'
        tree = ast.parse(source.read_text(), filename=str(source))
        changed = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in ('HERE', 'ROOT'):
                    value = output if name == 'HERE' else REVISIONS
                    node.value = ast.parse('Path(' + repr(str(value)) + ')', mode='eval').body
                    changed.append(name)
        assert sorted(changed) == ['HERE', 'ROOT']
        ast.fix_missing_locations(tree)
        exec(compile(tree, str(source), 'exec'), {'__file__': str(source), '__name__': '__main__'})
        actual = json.loads((output / 'independent_results.json').read_text())
        expected = json.loads((HERE / 'review/independent_results.json').read_text())
        assert actual == expected, 'Portable review differs from frozen results.'
        print('All six independent geometry/motion reports equal frozen reports exactly.')
    elif kind == 'watchdog':
        source = REVISIONS / 'planning_watchdog_20261024/review/probe_result_races.py'
        original_root = '/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions/planning_watchdog_20261024'
        class Reroot(ast.NodeTransformer):
            count = 0
            def visit_Constant(self, node):
                if node.value == original_root:
                    self.count += 1
                    return ast.copy_location(ast.Constant(str(source.parent.parent)), node)
                return node
        rewriter = Reroot()
        tree = rewriter.visit(ast.parse(source.read_text(), filename=str(source)))
        assert rewriter.count == 1
        ast.fix_missing_locations(tree)
        ns = {'__file__': str(source), '__name__': '__main__'}
        exec(compile(tree, str(source), 'exec'), ns)
        result = ns['out']
        late, cancel = result['post_budget_receive'], result['cancel_during_receive']
        assert late['status'] == 'TIMEOUT' and late['result'] is None
        assert cancel['before_receive_resumes'] == cancel['after_receive_resumes'] == 'CANCELLED' and cancel['result'] is None
        assert late['output']['command'] == cancel['output']['command'] == [0, 0, 0]
        (output / 'independent_race_results.json').write_text(json.dumps(result, indent=2) + '\n')
    else:
        raise ValueError(kind)


if __name__ == '__main__':
    main()
