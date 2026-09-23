# Repository workflow

- Fetch origin and check working-tree status before starting an upgrade.
- Start independent features from up-to-date origin/main in separate Git worktrees.
- Never switch branches to carry unrelated uncommitted changes into a new feature.
- Use codex/ branch names unless the user has chosen a different name.
- If work depends on an unmerged feature, use an explicitly documented stacked branch
  from that feature's committed tip. Compare against that tip, not main, during review.
- Keep commits focused; use conventional commit messages and stage explicit paths or hunks.
- Review the staged diff and run relevant tests before committing.
- Never stage secrets, local environments, build output, or another contributor's work.
- Preserve dirty work before reorganising it. Do not use destructive cleanup to obtain a clean tree.
- Keep main releasable. Push, PR creation, and merge are separate actions; do not merge
  into main or deploy merely to simplify local development.
- Record dependencies, validation, and limitations for reviewers.
