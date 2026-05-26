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

## Rules

- Publish the sanitized tree, not the private working tree.
- Do not use a normal merge from private history into public history.
- Do not use `git commit` for the snapshot commit if you want a clean commit without tool trailers.
- Fetch the public remote before future publishes.
- Run the privacy audit before every push.
