# DVK Marketplace Template (Claude Code)

This folder is a **template** for creating your own Claude Code plugin marketplace repository that includes DVK.

Audience: repo maintainers/team admins. For the full maintainer guide, see `docs/marketplace.md`.

## Create your marketplace repo

1. Create a new GitHub repo (example): `your-org/embedded-marketplace`
2. Copy the contents of this `marketplace-template/` folder into the root of that new repo (keep the `.claude-plugin/` directory).
3. Edit `.claude-plugin/marketplace.json`:
   - Update `name`, `owner`, `metadata`
   - Add/remove plugins under `plugins`
   - For pinned installs, keep `strict: true` and set `version` to match your plugin's tag (Claude Code expects `vX.Y.Z` tags)

## Version pinning (recommended)

If `marketplace.json` uses `"version": "0.1.0"`, the DVK repo should have a matching git tag `v0.1.0` pushed to GitHub.

## Install (users)

In Claude Code:

```text
/plugin marketplace add your-org/embedded-marketplace
/plugin install dvk@embedded-marketplace
```
