# Claude Code Marketplace (Maintainers)

This page is for **maintainers/team admins** who want to publish a Claude Code plugin marketplace that includes DVK (and other embedded-related plugins).

End users should follow `README.md` and install via:

```text
/plugin marketplace add <ORG>/<marketplace-repo>
/plugin install dvk@<marketplace-name>
```

## Recommended: version-pinned installs

Claude Code marketplace entries are typically pinned to a git tag like `v0.1.0`.

- In the marketplace repo, set the plugin entry `"version": "0.1.0"` and `"strict": true`
- In the DVK repo, create and push a matching git tag `v0.1.0`

## Create your marketplace repository

1. Create a new GitHub repo (example): `<ORG>/embedded-marketplace`
2. Copy `marketplace-template/` into the root of that new repo (keep `.claude-plugin/marketplace.json`).
3. Edit `.claude-plugin/marketplace.json`:
   - Update `name`, `owner`, `metadata`
   - Under `plugins`, keep or update the DVK entry:
     - `"url": "https://github.com/lj123as/Device-Verification-Kit.git"`
     - `"version": "0.1.0"` (match DVK tag `v0.1.0`)
     - `"strict": true`

## Install / verify

In Claude Code:

```text
/plugin marketplace add <ORG>/embedded-marketplace
/plugin install dvk@embedded-marketplace
```

