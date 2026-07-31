# Contributing to ops-dras

This guide covers the contributor workflow from forking the repository through
Pull Request review. It also documents the maintainer release process using
Semantic Versioning, Release Please, GitHub Releases, and GHCR images.

## Contribution paths

- **External contributor:** fork the repository, push a branch to your fork,
  and open a Pull Request against `sulaimantok/ops-dras:main`.
- **Maintainer or collaborator:** clone the upstream repository, create a
  feature branch, and open a Pull Request against `main`.

Do not commit `.env`, OpenStack credentials, certificates, private keys,
database files, PostgreSQL dumps, or Terraform/OpenTofu state.

## Fork and clone

Using GitHub CLI:

```bash
gh auth login
gh repo fork sulaimantok/ops-dras --clone
cd ops-dras
```

Verify remotes:

```bash
git remote -v
```

The usual contributor setup is:

```text
origin    git@github.com:YOUR_USERNAME/ops-dras.git
upstream  git@github.com:sulaimantok/ops-dras.git
```

Add the upstream remote when necessary:

```bash
git remote add upstream git@github.com:sulaimantok/ops-dras.git
```

Maintainers can clone the upstream repository directly:

```bash
git clone git@github.com:sulaimantok/ops-dras.git
cd ops-dras
```

## Create a branch

Start from the latest `main`:

```bash
git switch main
git fetch upstream
git pull --ff-only upstream main
git switch -c feat/short-description
```

Maintainers whose `origin` is the upstream repository can use:

```bash
git pull --ff-only origin main
```

Suggested branch names:

```text
feat/vm-recovery
fix/csrf-login
docs/operator-runbook
test/restore-workflow
```

## Local setup

```bash
cp .env.example .env
```

Configure at least:

- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `CLUSTER_CREDENTIALS_KEY`
- `POSTGRES_PASSWORD`

Start the stack:

```bash
docker compose up --build
```

Open `http://localhost:8080`. OpenStack cluster credentials are entered from
the Clusters page and must not be added to source files.

## Database migrations

Create a new Alembic revision for schema changes. Do not rewrite a migration
that may already be deployed.

```bash
alembic revision -m "add recovery metadata"
alembic upgrade head
alembic current
alembic heads
```

Implement both `upgrade()` and `downgrade()`. Unless explicitly designed
otherwise, the repository should have one Alembic head.

## Lint and test

Keep dependency and verification output outside the repository:

```bash
OPS_DRAS_TMP=$(mktemp -d /private/tmp/ops-dras-check.XXXXXX)
trap 'rm -rf "$OPS_DRAS_TMP"' EXIT

python3 -m venv "$OPS_DRAS_TMP/venv"
"$OPS_DRAS_TMP/venv/bin/pip" install -r requirements-dev.txt
"$OPS_DRAS_TMP/venv/bin/ruff" check app tests worker.py config.py
"$OPS_DRAS_TMP/venv/bin/pytest" -q
docker compose config -q
git diff --check
```

Tests that verify the application version must use the version source instead
of a hard-coded release number:

```python
from app.version import __version__
```

Release Please updates `app/version.py`; hard-coded expectations will cause a
release Pull Request to fail after a version bump.

## Review changes before committing

```bash
git status --short
git diff --check
git diff --stat
git diff
```

Confirm that no secrets or runtime files are staged.

## Conventional Commits

ops-dras uses Conventional Commits to determine Semantic Versioning changes:

| Commit | Release impact | Example |
| --- | --- | --- |
| `fix:` | PATCH | `fix: preserve csrf token during login` |
| `feat:` | MINOR | `feat: add incremental volume backup` |
| `feat!:` | MAJOR | `feat!: replace task API response` |
| `BREAKING CHANGE:` | MAJOR | Add it to the commit body/footer |
| `docs:`, `test:`, `refactor:` | Usually no release by themselves | `docs: add deployment guide` |

Examples:

```bash
git add app tests migrations docs README.md
git commit -m "feat: add incremental backups and protection workflow"
```

```bash
git commit -m "fix: hide deleted cinder backups from recovery points"
```

Breaking change:

```bash
git commit -m "feat!: change cluster credential schema" \
  -m "BREAKING CHANGE: deployments must run the new credential migration."
```

## Push and open a Pull Request

```bash
git push -u origin feat/short-description
gh pr create --base main --fill
```

A Pull Request should describe:

- the problem being solved;
- behavior and architecture changes;
- migration or configuration changes;
- validation performed;
- screenshots for UI changes;
- operational risks and rollback considerations when relevant.

Example body:

```markdown
## What changed

- Add incremental Cinder backup support.
- Add recovery-point reconciliation.

## Database

- Add Alembic revision `20260731_03`.

## Validation

- Ruff passed.
- Pytest passed.
- Docker Compose configuration passed.
```

Monitor CI:

```bash
gh pr checks --watch
```

CI runs Ruff, pytest, and Docker Compose configuration validation. Do not merge
until required checks and review are complete.

## Merge the feature Pull Request

After the required review, resolved conversations, and CI check are complete,
the repository owner or an authorized maintainer can merge with:

```bash
gh pr merge PR_NUMBER --squash --delete-branch
```

The repository allows squash merge only. Ensure the resulting squash commit
follows Conventional Commits, for example:

```text
feat: add incremental backups and protection workflow
```

## Release process for maintainers

Merging a Conventional Commit into `main` triggers Release Please. It creates
a Release Pull Request that updates:

- `CHANGELOG.md`
- `app/version.py`
- `.release-please-manifest.json`

Typical version changes:

```text
v0.1.0 + feat: ... -> v0.2.0
v0.2.0 + fix: ...  -> v0.2.1
```

Review the generated changelog and version changes:

```bash
gh pr list --state open
gh pr view RELEASE_PR_NUMBER
gh pr checks RELEASE_PR_NUMBER --watch
```

Merge the Release Pull Request after CI succeeds:

```bash
gh pr merge RELEASE_PR_NUMBER --merge --delete-branch
```

Release Please then creates the `vX.Y.Z` tag and GitHub Release. Publishing the
GitHub Release triggers the multi-architecture GHCR image workflow.

## Required GitHub Actions permissions

The Release Please workflow needs:

```yaml
permissions:
  contents: write
  pull-requests: write
```

The repository must also enable:

```text
Settings
  -> Actions
  -> General
  -> Workflow permissions
  -> Read and write permissions
  -> Allow GitHub Actions to create and approve pull requests
```

Repository administrators can inspect the setting with:

```bash
gh api repos/sulaimantok/ops-dras/actions/permissions/workflow
```

## Verify a release

```bash
git switch main
git pull --ff-only origin main
gh release view vX.Y.Z
gh run list --limit 10
git status --short --branch
```

Verify that:

- `app/version.py` matches the release;
- `CHANGELOG.md` contains the new release entry;
- `.release-please-manifest.json` matches the release;
- the Git tag and GitHub Release exist;
- the GitHub Release contains readable release notes;
- CI and the GHCR image workflow succeeded;
- the local worktree is clean.

GitHub automatically adds source `.tar.gz` and `.zip` archives. These archives
are expected, but they do not replace a human-readable release description.

## Manual release fallback

Use a manual release only after diagnosing why Release Please did not finish,
and only when version, manifest, and changelog are already consistent on
`main`:

```bash
gh release create vX.Y.Z \
  --target main \
  --title "ops-dras vX.Y.Z" \
  --notes-file RELEASE_NOTES.md
```

This still triggers the image workflow because it listens for the
`release: published` event.
