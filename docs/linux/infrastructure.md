# Infrastructure Guide — Flatpak Deployment Setup

This document is for the **maintainer** setting up the deployment infrastructure from scratch. It covers GPG key generation, GitHub Pages configuration for hosting OSTree repositories, and secret setup.

> **This document is internal.** It should not be shared publicly as it describes sensitive procedures (signing key management).

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Repository                            │
│                                                                 │
│  Branch: linux-flatpak           Branch: gh-pages               │
│  ┌────────────────────┐            ┌──────────────────────────┐ │
│  │ Source code        │            │ repo/                    │ │
│  │ scripts/export/    │   build    │   (OSTree)               │ │
│  │   linux/flatpak/   │──────────▶ │ sharly-chess.flatpakrepo │ │
│  │ .github/workflows/ │  publish   │ .nojekyll                │ │
│  └────────────────────┘            └──────────────────────────┘ │
│                                                                 │
│         Secrets:                                                │
│         • GPG_PRIVATE_KEY                                       │
│         • FFE_*                                                 │
│         • CHESS_RESULTS_*                                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
          https://flatpak.sharly-chess.com/
          ├── repo/                    ← users
          └── sharly-chess.flatpakrepo ← remote config file
```

---

## 1. Generate GPG keys

OSTree repositories must be signed with a GPG key so that Flatpak accepts updates. The private key is used by CI to sign, and the public key is embedded in `.flatpakrepo` files so clients can verify.

### Generation

```bash
# Generate a key pair (no passphrase for CI)
gpg --batch --gen-key <<EOF
%no-protection
Key-Type: RSA
Key-Length: 4096
Name-Real: Sharly Chess Flatpak
Name-Email: flatpak@sharly-chess.com
Expire-Date: 0
%commit
EOF
```

### Export

```bash
# Identify the key ID
gpg --list-secret-keys --with-colons | grep "^sec" | cut -d: -f5

# Export the private key (for GitHub Secrets)
gpg --export-secret-keys --armor <KEY_ID> > private.key

# Export the public key (for reference)
gpg --export --armor <KEY_ID> > public.key
```

### Secure storage

- **`private.key`**: Store locally outside the git repository. Never commit it.
- **`public.key`**: Same location, for reference. The public key is auto-generated into `.flatpakrepo` files by the workflow.
- The project's `.gitignore` already excludes `*.key`.

---

## 2. Configure GitHub Pages

### Enable GitHub Pages

1. Go to **Settings → Pages** in the GitHub repository
2. Source: **Deploy from a branch**
3. Branch: **gh-pages** / folder **/ (root)**
4. Save

### Initialise the gh-pages branch

If the `gh-pages` branch does not yet exist:

```bash
git checkout --orphan gh-pages
git rm -rf .
touch .nojekyll    # Prevent Jekyll from processing files
git add .nojekyll
git commit -m "Initialize gh-pages"
git push origin gh-pages
```

> **Important:** The `.nojekyll` file is essential. Without it, GitHub Pages ignores folders starting with an underscore and may incorrectly process binary OSTree files.

### Expected structure on gh-pages

The workflow automatically creates this structure:

```
gh-pages/
├── .nojekyll
├── sharly-chess.flatpakrepo        # Client config
├── repo/                           # OSTree repository
│   ├── config
│   ├── objects/
│   ├── refs/
│   ├── summary
│   ├── summary.sig
│   └── deltas/
```

---

## 3. Configure GitHub secrets

Go to **Settings → Secrets and variables → Actions** in the repository.

### Required secrets

| Secret                              | Contents                                                           | How to obtain                                                                  |
|-------------------------------------|--------------------------------------------------------------------|--------------------------------------------------------------------------------|
| `GPG_PRIVATE_KEY`                   | ASCII-armored contents of `private.key`                            | `cat private.key` and copy in full (including the `-----BEGIN/END-----` lines) |
| `FIDE_DATABASE_ENC_PASSWORD`        | FIDE database encryption password                                  | Provided by the Sharly Chess team                                              |
| `FFE_SQL_SERVER_HOST`               | FFE SQL server host                                                | Provided by the Sharly Chess team                                              |
| `FFE_SQL_SERVER_USER`               | FFE SQL server user                                                | Provided by the Sharly Chess team                                              |
| `FFE_SQL_SERVER_PASSWORD`           | FFE SQL server password                                            | Provided by the Sharly Chess team                                              |
| `FFE_SQL_SERVER_DATABASE`           | FFE server database name                                           | Provided by the Sharly Chess team                                              |
| `FFE_DATABASE_ENC_PASSWORD`         | FFE local database encryption password                             | Provided by the Sharly Chess team                                              |
| `FFE_DATABASE_ZIP_PASSWORD`         | FFE local database zip password (to be removed in future versions) | Provided by the Sharly Chess team                                              |
| `FRA_SCHOOLS_DATABASE_ENC_PASSWORD` | FRA Schools local database encryption password                     | Provided by the Sharly Chess team                                              |
| `CHESS_RESULTS_AES_KEY`             | Chess-Results AES key                                              | Provided by the Sharly Chess team                                              |
| `CHESS_RESULTS_AES_IV`              | Chess-Results AES IV                                               | Provided by the Sharly Chess team                                              |

### Verify the secrets

After configuration, run a test build:

```
GitHub Actions → Sharly-Chess export → Run workflow
  (leave version_tag empty → dev build)
```

If the build fails at the "Import GPG key" or "Inject secrets" step, check that the secrets are correctly set (no extra spaces, no missing line breaks).

---

## 4. Configure workflow permissions

The repository must allow workflows to write:

1. **Settings → Actions → General**
2. "Workflow permissions" section: select **Read and write permissions**
3. Check **Allow GitHub Actions to create and approve pull requests**

---

## 5. How the OSTree repository works

### Commit signing

The workflow imports the GPG key from the secret, then:

1. `flatpak build-commit-from` imports commits from the staging repos
2. `flatpak build-sign` signs all application commits
3. `flatpak build-update-repo --gpg-sign` updates and signs the summary

### .flatpakrepo files

These files **do not exist** in the source code. They are **generated dynamically** by the `export.yml` workflow on each publication (step "Generate .flatpakrepo files"), then pushed to `gh-pages`.

The workflow:
1. Exports the GPG public key in binary format (`gpg --export`)
2. Encodes it in base64
3. Generates both files with a heredoc `cat <<EOF`

**Production** (`sharly-chess.flatpakrepo`):
```ini
[Flatpak Repo]
Title=Sharly Chess
Url=https://flatpak.sharly-chess.com/repo/
Homepage=https://github.com/Sharly-Chess/sharly-chess
Comment=Official repository for Sharly Chess
Description=Play chess and manage tournaments with Sharly Chess
GPGKey=<BASE64_PUBLIC_KEY>
```

Public URL:
- https://flatpak.sharly-chess.com/sharly-chess.flatpakrepo

### Static deltas

Two types of delta are generated:

1. **Incremental deltas** (`--generate-static-deltas`): For version-to-version updates
2. **From-empty deltas** (`ostree static-delta generate --empty REF`): For the first full installation

Without from-empty deltas, a first installation downloads thousands of small individual OSTree objects (very slow). With them, everything is grouped into a few large files.

### Commit history

`flatpak build-commit-from --force` preserves the commit chain by reparenting the new commit onto the existing tip of the destination repository. This enables:

- `flatpak remote-info --log` to view history
- `flatpak update --commit=HASH` for rollback
- Delta updates between consecutive versions

---

## 6. GPG key renewal

If the GPG key expires or is compromised:

1. Generate a new key pair (see section 1)
2. Update the `GPG_PRIVATE_KEY` secret in GitHub
3. **Rebuild all active versions** to re-sign them:
   ```
   GitHub Actions → Sharly-Chess export → Run workflow
     version_tag: <each_version>
   ```
4. Users will need to re-add the remote (because the `GPGKey` in `.flatpakrepo` will have changed):
   ```bash
   flatpak remote-delete --user sharly-chess
   flatpak remote-add --user sharly-chess https://flatpak.sharly-chess.com/sharly-chess.flatpakrepo
   ```

---

## 7. Infrastructure troubleshooting

### Build succeeds but GitHub Pages does not update

- Check that GitHub Pages is enabled on the `gh-pages` branch
- Check that `.nojekyll` exists at the root of `gh-pages`
- Wait a few minutes (GitHub Pages propagation)
- Check in **Settings → Pages** for any deployment errors

### Error "GPG: no secret key"

- Check that the `GPG_PRIVATE_KEY` secret contains the complete **private** key (including the header lines)
- Ensure there are no extra spaces or stray line breaks

### OSTree repository grows too large

- `--prune` is already enabled in the workflow to clean up obsolete objects
- If necessary, recreate the repository from scratch by deleting `repo/` on `gh-pages`, then rebuild

### GitHub Pages size limit

GitHub Pages has a limit of 1 GB per repository. Monitor the size of `gh-pages`:

```bash
git checkout gh-pages
du -sh repo/
```

If the limit is approached, consider reducing history depth or migrating to an alternative host.

---

## 8. Setup checklist

When setting up this infrastructure on a fresh repository:

- [ ] GitHub secrets configured (7 secrets — see section 3)
- [ ] GitHub Pages enabled on `gh-pages`
- [ ] Workflow permissions set to "Read and write"
- [ ] `.nojekyll` present on `gh-pages`
- [ ] Run a dev build (manual dispatch on `export.yml`)
- [ ] Verify the `.flatpakrepo` is accessible via the GitHub Pages URL
- [ ] Test installation on a Linux machine: `flatpak remote-add --user ...`
- [ ] Run a production build (dispatch with `version_tag`)
- [ ] Verify rollback: `flatpak remote-info --user --log ...`
