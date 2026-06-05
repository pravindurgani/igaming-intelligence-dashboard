# Git Push Guide: Pushing Updates to GitHub

This guide explains how to push all local changes to the GitHub repository, overwriting remote files.

## Prerequisites

- Git installed on your machine
- Repository cloned locally
- GitHub access configured (SSH key or HTTPS credentials)

## Repository Info

- **Local Branch**: `release/unified-search-briefing-2025-12-15`
- **Remote Branch**: `main`
- **Remote URL**: `https://github.com/prav-clarion/igaming-intelligence-dashboard.git`

---

## Step-by-Step Push Process

### Step 1: Check Current Status

See what files have changed:

```bash
git status
```

### Step 2: Stage All Changes

Add ALL files (new, modified, deleted):

```bash
git add -A
```

**Note**: `-A` stages everything including:
- New untracked files
- Modified files
- Deleted files

### Step 3: Verify Staged Changes

Double-check what will be committed:

```bash
git status
```

You should see files listed under "Changes to be committed".

### Step 4: Commit Changes

Create a commit with a descriptive message:

```bash
git commit -m "Your commit message here

- Bullet point 1
- Bullet point 2

🤖 Generated with Claude Code"
```

**If nothing to commit** (working tree clean), skip to Step 5.

### Step 5: Force Push to Main

Push local branch to remote `main`, overwriting remote:

```bash
git push origin release/unified-search-briefing-2025-12-15:main --force
```

**Breakdown**:
- `origin` = remote repository (GitHub)
- `release/unified-search-briefing-2025-12-15:main` = push local branch TO remote main
- `--force` = overwrite remote even if histories differ

---

## Quick One-Liner (After Making Changes)

```bash
git add -A && git commit -m "Update: description here" && git push origin release/unified-search-briefing-2025-12-15:main --force
```

---

## Common Scenarios

### Scenario A: Made code changes, need to push

```bash
git add -A
git commit -m "Fix: description of fix"
git push origin release/unified-search-briefing-2025-12-15:main --force
```

### Scenario B: Nothing changed but want to force sync

```bash
git push origin release/unified-search-briefing-2025-12-15:main --force
```

### Scenario C: Check if local matches remote

```bash
git fetch origin
git log --oneline HEAD -3
git log --oneline origin/main -3
```

Both should show the same commit hashes if in sync.

---

## After Pushing to GitHub

### For Streamlit Cloud Deployment

After pushing, **reboot your Streamlit app** to pick up changes:

1. Go to https://share.streamlit.io
2. Find your app: **igaming-intelligence-dashboard**
3. Click the **⋮** (three dots) menu
4. Click **"Reboot app"**
5. Wait 2-3 minutes for redeployment

---

## Troubleshooting

### "Everything up-to-date" but changes not on GitHub

Your local and remote are already synced. Verify with:

```bash
git log --oneline origin/main -1
```

### "Nothing to commit, working tree clean"

No changes to commit. If you expected changes, check:

```bash
git diff
git status
```

### Push rejected (non-fast-forward)

Use `--force` flag:

```bash
git push origin release/unified-search-briefing-2025-12-15:main --force
```

### Authentication failed

Re-authenticate:

```bash
git remote set-url origin https://github.com/prav-clarion/igaming-intelligence-dashboard.git
```

Then retry push (you'll be prompted for credentials).

---

## Summary Commands

| Action | Command |
|--------|---------|
| Check status | `git status` |
| Stage all | `git add -A` |
| Commit | `git commit -m "message"` |
| Push to main | `git push origin release/unified-search-briefing-2025-12-15:main --force` |
| Check remote | `git log --oneline origin/main -3` |
