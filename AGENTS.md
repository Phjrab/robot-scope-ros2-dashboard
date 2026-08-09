# Repository workflow

- This repository uses a single-branch workflow. Make project changes directly on main.
- Do not create or use agent branches, feature branches, worktrees, or pull requests unless the user explicitly requests one.
- Before editing, run git status --short --branch. Preserve unrelated user changes; never reset, discard, or rewrite them.
- Before committing, run python3 -m unittest discover -s tests -v and the relevant JavaScript or smoke checks.
- After completing a user-requested project change, create a focused commit directly on main and push origin main unless the user explicitly asks to keep it local. Never force-push or rewrite published history.
- Never commit credentials, SSH keys, tokens, environment files, virtual environments, ROS build/install/log trees, rosbag files, or generated map and PCD data.
- Jetson deployment is separate from Git publication. Do not restart services or alter robot or map data unless the user explicitly asks.
