import argparse
import json
from pathlib import Path
from .dependencies import prepare


def main():
    p = argparse.ArgumentParser(description='Offline C7 diagnostics; never driving authorization.')
    sub = p.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--repo', type=Path, default=Path.cwd())
    prep.add_argument('--output', type=Path, required=True)
    run = sub.add_parser('run')
    run.add_argument('--repo', type=Path, default=Path.cwd())
    run.add_argument('--deps', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--profile', choices=['baseline', 'bounded'], default='baseline')
    run.add_argument('--node', default='node')
    run.add_argument('--config-snapshot', type=Path, help='Expected config JSON or prior result; verifies equality, never changes limits')
    browser = sub.add_parser('browser')
    browser.add_argument('--repo', type=Path, default=Path.cwd())
    browser.add_argument('--deps', type=Path, required=True)
    browser.add_argument('--playwright', type=Path, required=True)
    browser.add_argument('--node', default='node')
    browser.add_argument('--output', type=Path, required=True)
    run.add_argument('--browser-report', type=Path)
    summary = sub.add_parser('summarize')
    summary.add_argument('input', type=Path)
    summary.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.command == 'prepare':
        print(prepare(args.repo, args.output))
    elif args.command == 'browser':
        from .browser import run_browser
        raise SystemExit(run_browser(args.repo,args.deps,args.playwright,args.node,args.output))
    elif args.command == 'summarize':
        from .report import markdown
        args.output.write_text(markdown(json.loads(args.input.read_text())))
    else:
        from .runner import run_diagnostics
        from .report import markdown
        result = run_diagnostics(args.repo, args.deps, args.profile, args.node, args.browser_report, args.config_snapshot)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        args.output.with_suffix('.md').write_text(markdown(result))
        print(json.dumps({'output': str(args.output), 'checks': result['checks']}, indent=2))
        if any(v == 'FAIL' for v in result['checks'].values()):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
