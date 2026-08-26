# Snapshot Publish Workflow

Use this workflow to publish a sanitized public snapshot without importing private development history.

## Goal

- Keep the private repo on its own history line.
- Keep the public repo on its own reviewed history line.
- Publish each public release as one reviewed snapshot commit.

## First Publish

The first public publish has no parent:

```bash
git remote add public git@github.com:<your-org-or-user>/hermes-jobapps.git
SANITIZED=/tmp/hermes-jobapps-public-snapshot
cd "$SANITIZED"
git add -A
TREE=$(git write-tree)
COMMIT=$(printf 'Initial public release\n' | git commit-tree "$TREE")
git push public "$COMMIT":refs/heads/main
```

## Future Publishes

```bash
git fetch public
SANITIZED=/tmp/hermes-jobapps-public-snapshot
cd "$SANITIZED"
git add -A
TREE=$(git write-tree)
PARENT=$(git rev-parse public/main)
COMMIT=$(printf 'Public snapshot: <title>\n' | git commit-tree "$TREE" -p "$PARENT")
git push public "$COMMIT":refs/heads/main
```

For a substantive update that should receive normal review, create the sanitized
snapshot commit on a branch based on `public/main`, push that branch, open a PR,
and merge it after tests and privacy checks pass. The PR must contain only the
curated public tree; do not merge private history into the public branch.

## Rules

- Publish the sanitized tree, not the private working tree.
- Do not use a normal merge from private history into public history.
- Do not use `git commit` for the snapshot commit if you want a clean commit without tool trailers.
- Fetch the public remote before future publishes.
- Run the privacy audit before every push.
- Audit the reachable public history separately from the current tree. Removing
  sensitive data from history requires an explicitly coordinated history reset;
  a normal PR cannot purge older commits.
