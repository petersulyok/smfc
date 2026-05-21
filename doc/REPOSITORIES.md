# Plan: Host DEB and RPM repositories on GitHub Pages

## High-level architecture

```
petersulyok/smfc  (existing)
   └── .github/workflows/packages.yml
         • builds smfc_X.Y.Z_all.deb and smfc-X.Y.Z-1.noarch.rpm  (already does this)
         • uploads them as GitHub Release assets               (new step)
         • repository_dispatch → smfc-apt and smfc-rpm          (new step)

petersulyok/smfc-apt   (new repo)              petersulyok/smfc-rpm   (new repo)
   └── gh-pages branch served via Pages           └── gh-pages branch served via Pages
        • dists/stable/…   (reprepro output)           • repodata/    (createrepo_c output)
        • pool/main/s/smfc/*.deb                       • packages/*.rpm
        • smfc-repo.gpg   (public key)                 • smfc-repo.gpg + smfc.repo
   └── .github/workflows/publish-deb.yml           └── .github/workflows/publish-rpm.yml
        on: repository_dispatch                          on: repository_dispatch
```

Trigger flow on each release:
1. `release: published` event on `smfc` fires `packages.yml`.
2. `packages.yml` builds the `.deb` / `.rpm`, uploads them as release assets, then issues `repository_dispatch` to both package repos with the release tag.
3. Each package repo downloads its asset from the public release URL (no cross-repo auth needed for download), regenerates the repository index, signs it, and pushes to `gh-pages`. Pages serves the result.

## Step 1 — Create the GPG signing key (one-time, local)

Generate a dedicated key, not your personal key:

```bash
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Key-Usage: sign
Name-Real: smfc repository
Name-Email: peter@sulyok.net
Expire-Date: 5y
%no-protection
%commit
EOF
```

Then export:

```bash
KEYID=$(gpg --list-keys --with-colons "smfc repository" | awk -F: '/^pub:/ {print $5; exit}')
gpg --armor --export-secret-keys "$KEYID" > smfc-repo-private.asc
gpg --armor --export "$KEYID" > smfc-repo-public.asc
echo "$KEYID" > smfc-repo-keyid.txt
```

Outputs:
- `smfc-repo-private.asc` → goes into GitHub Actions secrets only, **never committed**.
- `smfc-repo-public.asc` → committed to both package repos for users to import.
- `smfc-repo-keyid.txt` → reference for configuring reprepro / repo signing.

## Step 2 — Create `petersulyok/smfc-apt`

Initial layout (committed to `main`, then mirrored to `gh-pages` on first publish):

```
smfc-apt/
├── README.md                 ← user-facing install instructions
├── smfc-repo.gpg             ← armored public key (smfc-repo-public.asc renamed)
├── conf/
│   └── distributions         ← reprepro config (see below)
└── .github/workflows/publish-deb.yml
```

`conf/distributions`:
```
Origin: smfc
Label: smfc
Codename: stable
Suite: stable
Components: main
Architectures: amd64 arm64 all source
Description: smfc APT repository
SignWith: <KEYID>
```

`.github/workflows/publish-deb.yml` (sketch — full file written during implementation):
```yaml
name: Publish DEB package
on:
  repository_dispatch:
    types: [package-published]
  workflow_dispatch:
    inputs:
      release_tag: { description: "smfc release tag", required: true }

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { ref: gh-pages, fetch-depth: 1 }
        # gh-pages may be empty on first run — handled by a bootstrap step
      - name: Install reprepro + gpg
        run: sudo apt-get update && sudo apt-get install -y reprepro gnupg
      - name: Import signing key
        env:
          GPG_PRIVATE_KEY: ${{ secrets.REPO_SIGNING_GPG_KEY }}
        run: echo "$GPG_PRIVATE_KEY" | gpg --batch --import
      - name: Download .deb from release
        env: { GH_TOKEN: ${{ github.token }} }
        run: |
          TAG="${{ github.event.client_payload.release_tag || inputs.release_tag }}"
          gh release download "$TAG" -R petersulyok/smfc -p '*.deb' -D /tmp/in
      - name: Add package to repo
        run: |
          cp conf/distributions /tmp/conf-distributions  # ensure config present
          reprepro -b . includedeb stable /tmp/in/*.deb
      - name: Commit and push gh-pages
        run: |
          git config user.name  "smfc-bot"
          git config user.email "smfc-bot@users.noreply.github.com"
          git add -A
          git commit -m "Publish $TAG"
          git push origin gh-pages
```

Pages configuration: Settings → Pages → Source = `gh-pages` branch, `/` root.

Resulting URL: `https://petersulyok.github.io/smfc-apt/`

User-facing install (goes into the repo's README and into smfc's `PACKAGES.md`):
```bash
curl -fsSL https://petersulyok.github.io/smfc-apt/smfc-repo.gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/smfc-repo.gpg
echo "deb [signed-by=/etc/apt/keyrings/smfc-repo.gpg] https://petersulyok.github.io/smfc-apt stable main" \
  | sudo tee /etc/apt/sources.list.d/smfc.list
sudo apt update && sudo apt install smfc
```

## Step 3 — Create `petersulyok/smfc-rpm`

Layout:
```
smfc-rpm/
├── README.md
├── smfc-repo.gpg          ← same public key as smfc-apt
├── smfc.repo              ← /etc/yum.repos.d snippet for users
└── .github/workflows/publish-rpm.yml
```

`smfc.repo`:
```
[smfc]
name=smfc RPM repository
baseurl=https://petersulyok.github.io/smfc-rpm/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://petersulyok.github.io/smfc-rpm/smfc-repo.gpg
```

`.github/workflows/publish-rpm.yml` (sketch):
```yaml
name: Publish RPM package
on:
  repository_dispatch:
    types: [package-published]
  workflow_dispatch:
    inputs:
      release_tag: { description: "smfc release tag", required: true }

jobs:
  publish:
    runs-on: ubuntu-latest
    container: fedora:latest
    steps:
      - run: dnf install -y createrepo_c rpm-sign gnupg2 git gh
      - uses: actions/checkout@v6
        with: { ref: gh-pages, fetch-depth: 1 }
      - name: Import signing key
        env: { GPG_PRIVATE_KEY: ${{ secrets.REPO_SIGNING_GPG_KEY }} }
        run: echo "$GPG_PRIVATE_KEY" | gpg --batch --import
      - name: Download .rpm from release
        env: { GH_TOKEN: ${{ github.token }} }
        run: |
          TAG="${{ github.event.client_payload.release_tag || inputs.release_tag }}"
          mkdir -p packages
          gh release download "$TAG" -R petersulyok/smfc -p '*.rpm' -D packages
      - name: Sign the RPM
        run: |
          echo "%_gpg_name $(gpg --list-keys --with-colons | awk -F: '/^uid:/ {print $10; exit}')" > ~/.rpmmacros
          rpm --addsign packages/*.rpm
      - name: Regenerate repodata
        run: |
          createrepo_c --update .
          gpg --batch --yes --detach-sign --armor repodata/repomd.xml
      - name: Commit and push
        run: |
          git config user.name  "smfc-bot"
          git config user.email "smfc-bot@users.noreply.github.com"
          git add -A && git commit -m "Publish $TAG" && git push origin gh-pages
```

User-facing install:
```bash
sudo dnf config-manager addrepo --from-repofile=https://petersulyok.github.io/smfc-rpm/smfc.repo
sudo dnf install smfc
```

## Step 4 — Update `petersulyok/smfc` `packages.yml`

Two additions at the tail of the existing `packages.yml`:

a) **Attach packages to the GitHub Release** so downstream repos can pull via the public release URL (no cross-repo download token needed).

In `build-deb` and `build-rpm`, after the `actions/upload-artifact` step add:
```yaml
- name: Attach package to release
  env: { GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
  run: gh release upload "${{ github.event.release.tag_name }}" smfc_*.deb --clobber   # (.rpm in rpm job)
```
(`GITHUB_TOKEN` already has release-write scope when the workflow is triggered by a release.)

b) **New `dispatch` job** that runs after both build jobs succeed:
```yaml
  dispatch:
    needs: [build-deb, build-rpm]
    runs-on: ubuntu-latest
    steps:
      - name: Trigger smfc-apt
        env: { GH_TOKEN: ${{ secrets.PACKAGE_REPO_DISPATCH_TOKEN }} }
        run: |
          gh api repos/petersulyok/smfc-apt/dispatches \
             -f event_type=package-published \
             -f 'client_payload[release_tag]=${{ github.event.release.tag_name }}'
      - name: Trigger smfc-rpm
        env: { GH_TOKEN: ${{ secrets.PACKAGE_REPO_DISPATCH_TOKEN }} }
        run: |
          gh api repos/petersulyok/smfc-rpm/dispatches \
             -f event_type=package-published \
             -f 'client_payload[release_tag]=${{ github.event.release.tag_name }}'
```

`PACKAGE_REPO_DISPATCH_TOKEN` = a fine-grained PAT (or GitHub App token) scoped to `smfc-apt` + `smfc-rpm` with **Actions: write** permission only. Stored as a repo secret on `smfc`.

## Step 5 — Configure secrets

| Secret name                     | Where                       | Value                                                          |
|---------------------------------|-----------------------------|----------------------------------------------------------------|
| `REPO_SIGNING_GPG_KEY`          | smfc-apt, smfc-rpm          | Contents of `smfc-repo-private.asc`                            |
| `PACKAGE_REPO_DISPATCH_TOKEN`   | smfc                        | Fine-grained PAT, Actions:write on smfc-apt+smfc-rpm           |

No passphrase chosen above (`%no-protection`). If you want a passphrase, add `REPO_SIGNING_GPG_PASSPHRASE` and pass via `--pinentry-mode loopback --passphrase-fd 0` in the workflows.

## Step 6 — Documentation updates in `petersulyok/smfc`

- `PACKAGES.md`: add a new top section "Installing from the apt/yum repositories" with the curl/echo and dnf snippets, mark current "build from artifacts" content as the alternative for offline builds.
- `README.md` chapter 9.2: replace the "available as build artifacts" sentence with "available from the smfc apt and yum repositories — see PACKAGES.md".

## Step 7 — Bootstrap & verification order

Order matters — workflows fail without their inputs:

1. Generate GPG key locally (Step 1).
2. Create `smfc-apt` repo on GitHub. Add `REPO_SIGNING_GPG_KEY` secret. Commit initial layout (`README.md`, `smfc-repo.gpg`, `conf/distributions`, `.github/workflows/publish-deb.yml`). Create empty `gh-pages` branch (`git checkout --orphan gh-pages && git rm -rf . && git commit --allow-empty -m "init" && git push origin gh-pages`). Enable Pages on `gh-pages`.
3. Create `smfc-rpm` repo, same pattern, with `smfc.repo` and `publish-rpm.yml`. Enable Pages.
4. Create the fine-grained PAT on github.com → Settings → Developer settings → Tokens, scoped to both new repos with Actions:write only. Add as `PACKAGE_REPO_DISPATCH_TOKEN` secret in `smfc`.
5. Update `smfc/.github/workflows/packages.yml` with the release-asset upload step and dispatch job; merge.
6. Cut a test release (e.g. `v5.x.y-rc1`). Watch:
   - `smfc` → `packages.yml`: both build jobs succeed, both `.deb`/`.rpm` appear on the release page, `dispatch` job succeeds.
   - `smfc-apt` → `publish-deb`: succeeds, `gh-pages` branch updated, package appears under `pool/`.
   - `smfc-rpm` → `publish-rpm`: succeeds, `gh-pages` updated.
7. End-to-end verify from a clean container:
   - `docker run --rm -it debian:trixie bash -c "<curl|echo|apt> commands … && apt install -y smfc && smfc --version"`
   - `docker run --rm -it fedora:latest bash -c "<dnf config-manager> … && dnf install -y smfc && smfc --version"`

## Notes / decisions to revisit

- **Architecture in reprepro**: listed `amd64 arm64 all source`. Since smfc is `Architecture: all`, only `all` is strictly needed, but listing the binary arches lets apt clients on those architectures fetch without warnings. No source uploads are wired up — leave that out unless we add a separate `dpkg-source` step.
- **Old version retention**: reprepro keeps only the latest of each name in a suite by default; once a new `.deb` is added, the previous one is dereferenced and `reprepro --keepunreferenced clearvanished` removes orphan pool files. If you want to keep older versions accessible, switch to `aptly` (snapshots) — slightly more setup. RPM via `createrepo_c` keeps every package in `packages/` so history accumulates naturally.
- **Two workflows duplicate the "download release asset" pattern**: acceptable for two consumers; if you ever add a third (e.g. an Arch repo), consider a tiny composite action in a shared repo.
- **Failure mode**: if `dispatch` fires but a package repo workflow fails, you can re-run it manually via `workflow_dispatch` with the same release tag — both publish workflows accept that input. No state machine needed.