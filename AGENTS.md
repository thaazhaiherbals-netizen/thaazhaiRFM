# Repository workflow

- Permanent branches are develop (integration) and main (production).
- Fetch origin and check status before starting work. Start each feature or fix on
  a focused codex/ branch from up-to-date origin/develop, with a clean checkout.
- Use a temporary worktree only when concurrent work needs isolation. Remove it
  after merge; do not leave recovery or release branches as permanent workspaces.
- Delivery path: feature branch -> PR to develop -> PR from develop to main.
- Never merge feature branches directly into main or commit directly on develop/main.
- Railway production follows main. Do not deploy feature/develop code directly
  unless the user explicitly requests an exception.
- Keep commits focused; stage explicit paths/hunks, review the staged diff, and run
  relevant checks. Do not stage secrets, build output or unrelated edits.
- Preserve and reconcile uncommitted work before cleanup; never carry mixed changes
  into a new feature branch. Keep recovery copies outside active branches.
- After feature merge, delete its local/remote branch and temporary worktree once
  its changes are verified included. Keep develop and main.
- After a release, synchronize develop with main through a normal fast-forward or
  PR as appropriate; never force-push shared branches.
- Record scope, validation and limitations for reviewers.
