# ABCT — Personal Information & Infrastructure Leak Audit

**Repository:** `Tarrant64/abct` (public)
**Audit date:** 2026-08-11
**Branch audited:** `claude/repo-secrets-audit-4oq59x` @ `f8e5c06`
**Scope:** Accidental disclosure of the developer's *own* private information — personal/home infrastructure, credentials, API keys, wallet addresses, identity.
**Explicitly out of scope:** code vulnerabilities (XSS, SSRF, authz). Those are covered by the existing `sec/` tooling and were ignored here.

> ⚠️ **This is the redacted edition, safe for the public repository.** Usernames,
> personal email addresses, the real name and the home-lab IP address are replaced
> with `<placeholders>`. File paths, line numbers, commit SHAs and every tooling
> gap are intact, so this version is fully actionable for fixing the pre-push
> checks. The unredacted edition was delivered privately and must not be committed.

---

## 1. Executive summary

The repository's credential hygiene is **genuinely good**. Across all **1,250 blobs in the entire git object database**, there is not a single real API key, JWT, private key, `user:pass@host` URL, tunnel hostname, or email address ever committed in file content. Every checksum-valid Cardano address in history is already documented in `sec/wallet_allowlist.txt` as a public protocol constant or spec test vector. The July 2026 "personal-address scrub" appears to have been done correctly and completely.

The leaks that remain are **not credentials — they are identity and infrastructure fingerprints**, and they all sit in exactly the places the pre-push audit structurally cannot see:

| # | Finding | Severity | Where |
|---|---|---|---|
| F-01 | Developer's real OS username + local project path | **HIGH** | Working tree, live |
| F-02 | Real home-lab static IP + full network/storage topology | **HIGH** | Git history, permanent |
| F-03 | Real name + personal email as git author on 83/86 commits | **MEDIUM** | Git metadata, permanent |
| F-04 | `satoshi` admin password sited where 3 of 4 detectors are blind | **MEDIUM** | Working tree, live |
| F-05 | Personal domain in iOS/Android app identifiers | **LOW** | Working tree, live |
| F-06 | Four stale `.bak2/.bak3` files published; `.gitignore` gives false assurance | **LOW** | Working tree, live |
| F-07 | LAN IP placeholder in an unscanned `.dart` file (blind-spot demonstrator) | **LOW** | Working tree, live |

**The single most important structural result:** the existing audit reports **173 findings** on this tree (3 CRITICAL / 134 HIGH / 36 MEDIUM) and **none of them is any of the seven above**. The tooling is thorough about code vulnerabilities and effectively blind to personal-information disclosure.

**Two gaps deserve immediate attention regardless of the findings:**
1. **No CI backstop.** `.github/workflows/` contains only `docker-publish.yml` and `docker-scout.yml`. The leak audit runs *exclusively* in a local pre-push hook that must be installed manually per clone, fails open twice, and is bypassed by `git push --no-verify` or any edit made through the GitHub web UI.
2. **The scanner never reads git history.** F-02 was correctly fixed in the working tree on 2026-07-13 and is still fully public. A working-tree-only scanner reports "clean" on a repository that is not.

---

## 2. Method

| Surface | Coverage |
|---|---|
| Working tree | All 847 tracked files |
| Git history | All 1,250 blobs (`git cat-file --batch-all-objects`), 86 commits, all refs |
| Deleted files | `git log --diff-filter=D` (1 file, benign Flutter template rename) |
| Commit metadata | Author/committer identity + all commit messages |
| Binary artifacts | 114 PNGs, 4 PDFs, 1 DOCX — filenames + embedded metadata |
| Checksum validation | Cardano bech32 addresses validated with the repo's own `_bech32_valid()` |
| Baseline comparison | `python3 sec/security_audit.py` executed; its 173 findings diffed against ours |

Detection classes swept: RFC1918 + public IPs, dynamic-DNS/tunnel hosts, `.local`/LAN names, home paths, personal emails, API-key shapes for 12 vendors, JWTs, PEM key blocks, basic-auth URLs, base64/hex blobs, wallet addresses across 6 chains, Apple Team IDs, provisioning UUIDs, keystore passwords, app-group identifiers.

---

## 3. Findings

### F-01 — Developer's real OS username and local project path *(HIGH, live in working tree)*

**`screenshots/glass-phase1/SCREENSHOT-GUIDE.md:7`**

```
2. Start the backend: `cd /home/<dev-user>/<path>/dashboard && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
```

Discloses the developer's Linux account name (`<dev-user>`) and their local directory layout (`~/Claude/ABCT/dashboard`). This correlates directly with the git author identity in F-03 (`<Developer Real Name>`) and with the corporate address `<dev-user>@<employer>.com`, tying the pseudonymous GitHub handle `Tarrant64` to a named individual at a named employer.

Introduced in `818230a` (2026-06-28) and **still present in `HEAD`**.

**Why every existing check missed it:** the file is `.md`, so it is absent from the generic `.py`/`.html`/`.js` file lists entirely (`sec/security_audit.py:131-133`). The wallet scanner *does* read `.md`, but only looks for wallet addresses. **No username, home-path, or absolute-path detector exists anywhere in the tooling.**

**Fix:** replace with a relative path — `cd /path/to/abct` or simply `cd <repo-root>`.

---

### F-02 — Real home-lab static IP and full network/storage topology *(HIGH, permanent in git history)*

**`abct-docker/deploy_from_git.sh`** — introduced `19a36f9` (2026-04-13), carried through `818230a` and `3c7d83f`, removed `e5347f6` (2026-07-13). **Exposure window: 3 months. Still publicly retrievable from git history and the GitHub API.**

```sh
ABCT_STATIC_IP="${ABCT_STATIC_IP:-192.168.<x>.<y>}"      # host address on the dev's LAN
ABCT_DOCKER_NETWORK="${ABCT_DOCKER_NETWORK:-br0}"       # bridge interface
ABCT_DATA_PATH="${ABCT_DATA_PATH:-/mnt/user/appdata/abct-dashboard}"
ENV_FILE="/mnt/user/appdata/ABCT/.env"                  # host path of the REAL .env
```

Together these disclose: the subnet in use (`192.168.<x>.0/24`), a specific reserved host address, the Docker bridge topology, that the host is an **Unraid** server (`/mnt/user/appdata` is Unraid-specific), and the **exact filesystem path of the developer's real, populated `.env` file**. That last line is the highest-value item for an attacker who obtains any file-read primitive on that host.

The developer noticed and fixed this — commit `e5347f6` is titled *"fix: Configurable env file and no hardcoded static IP in deploy_from_git.sh"*. `CHANGELOG.md:1092` also records *"Removed default Unraid IP (192.168.x.x) from all scripts"*, which serves as a signpost telling anyone reading the changelog exactly which commits to go dig up.

**Why every existing check missed it:** `sec/security_audit.py` scans the working tree only. There is no history scan anywhere in the tooling, and no IP or host-path detector at all. The scanner reports this repository clean of it.

**Fix:** this cannot be un-published by a normal commit. Options, in order of preference:
1. Accept it (the address is RFC1918 and only meaningful to someone already inside the LAN) but **re-IP the host** and confirm nothing on `192.168.<x>.0/24` is exposed to the internet.
2. Rewrite history with `git filter-repo --replace-text` and force-push. Costly on a public repo with forks, and the value is already indexed.
3. Add the history scan (§5, Gap 3) so the *next* one is caught before it ships.

---

### F-03 — Real name and personal email in git authorship on 83 of 86 commits *(MEDIUM, permanent)*

```
     83  <personal>@<provider>.com | <Developer Real Name>
      2  team@abct.dev          | ABCT Team
      1  <second-persona>@<provider>.com  | <Second Persona>
```

The project clearly *intends* to present a team identity — `ABCT Team <team@abct.dev>` — but **96.5% of commits are authored under a real full name and a personal Outlook address.** A third identity (`<Second Persona> <<second-persona>@<provider>.com>`, one commit, `c328a21`) links this repository to an unrelated personal persona.

Commit authorship is inherent to git and is not a "leak" in the sense of a misplaced secret, but if the `team@abct.dev` identity reflects an intent to keep the maintainer's real identity separate from the project, that intent is not being met. Combined with F-01 and F-05, the real name, personal email, employer, OS username and home-lab topology are all recoverable from this one repository.

**Why every existing check missed it:** commit metadata is not file content. No file-content scanner can see this; it needs a separate identity check.

**Fix:** decide which identity the project should carry, then:
```sh
git config user.name  "ABCT Team"
git config user.email "team@abct.dev"
```
and add a pre-push assertion that the author identity matches (§6). Existing history would need a rewrite to change retroactively — likely not worth it, but the going-forward fix is one line.

---

### F-04 — `satoshi` admin password sited where 3 of 4 detectors are blind *(MEDIUM, live)*

`satoshi` is the **documented default** (`README.md:115`: *"**Admin**: `admin` / `satoshi`"*), so this is not a leaked *personal* password. It is included because it is the sharpest available demonstration of the secret-detector's structural blind spots, and because it carries real deployment risk.

| Location | Form | Caught by `MED-SEC`? | Why not |
|---|---|---|---|
| `backend/database.py:275` | `os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")` | ❌ | `security_audit.py:487-488` — *"Skip if using os.getenv"* — `continue`s on the entire line |
| `backend/migrate_multiuser.py:69` | `os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")` | ❌ | same early-`continue` |
| `backend/check_auth.py:48,65,81,92` | `bcrypt.hashpw("satoshi".encode(...))` | ❌ | no `password=` assignment, so none of the 3 regexes match |
| `backend/migrate_to_multiuser.py:149` | `password = "admin"` | ✅ | matches `password\s*=\s*["']` |
| `frontend/login.html:396` | `document.getElementById('password').value = 'satoshi'` | ❌ | secrets check runs on **Python files only** |
| `frontend/v2/login.html:156` | same auto-fill | ❌ | same |

The `os.getenv` exemption is the important one. It was written to suppress false positives on `password = os.getenv("PW")`, but its effect is to **blind the scanner to precisely the place default credentials actually live** — the second argument. Any real secret written as `os.getenv("X", "<real-secret>")` is invisible to this repository's audit today.

**Deployment consequence:** a deployment that never sets `ABCT_ADMIN_PASSWORD` silently comes up with `admin`/`satoshi`, and both login pages pre-fill the password box with it.

**Fix:** see §6, Patch 2 — match the *default argument* of `os.getenv`/`os.environ.get` rather than skipping the line.

---

### F-05 — Personal domain in iOS/Android app identifiers *(LOW, live)*

| File | Value |
|---|---|
| `mobile/ios/Runner.xcodeproj/project.pbxproj` (30 occurrences) | `teamcata.com.ABCT-Mobile` |
| `mobile/android/app/build.gradle.kts:38,55` | `namespace` / `applicationId` = `com.teamcata.abct` |
| `mobile/android/app/src/main/kotlin/com/teamcata/abct/MainActivity.kt` | package path |
| 4 × `*.entitlements` | `group.com.teamcata.abct` |
| `mobile/macos/Runner/Configs/AppInfo.xcconfig:11` | `teamcata.com.ABCT-Mobile` |

Ties the project to the `teamcata` handle/domain. This is plausibly deliberate branding rather than an accident, hence LOW — but it is one more edge in the identity graph alongside F-01 and F-03. (Note in passing: the iOS identifier `teamcata.com.ABCT-Mobile` is malformed reverse-DNS; Android correctly uses `com.teamcata.abct`.)

**Positive finding:** `DEVELOPMENT_TEAM` is empty (`project.pbxproj:1127`), no Apple Team ID, no provisioning-profile UUIDs, and no `NSAppTransportSecurity` exception domains anywhere. That is good hygiene on the highest-risk Xcode fields.

**Why every existing check missed it:** `.pbxproj`, `.entitlements`, `.xcconfig`, `.kts` and `.kt` appear in **no** extension list in the tooling.

---

### F-06 — Four stale backup files published; `.gitignore` gives false assurance *(LOW, live)*

```
frontend/apis.html.bak2        1,167 lines   (live version: 2,273)
frontend/nft-wall.html.bak2      606 lines   (live version: 1,697)
frontend/security.html.bak2      905 lines   (live version: 1,309)
frontend/services.html.bak3      591 lines   (live version:   938)
```

`.gitignore:82-84` declares `*.bak`, `*.bak2`, `*.bak3`. Those rules **work for new files but have no effect on these four**, because git ignore rules do not apply to already-tracked paths — they were committed before the rules were added. The presence of the rules creates a false impression that no `.bak` files are published.

**I diffed all four against their live counterparts: they contain no credentials, hosts, or wallet addresses** — only superseded markup and JS. So this is a hygiene and stale-code-exposure finding, not a data leak. It matters mainly as a pattern: the next `.bak` file created *before* someone thinks to check would be equally invisible, and `.bak2` is in no scanner extension list either.

**Fix:** `git rm --cached frontend/*.bak2 frontend/*.bak3` and add a pre-push assertion that no tracked path matches an active ignore rule (§6, Patch 5).

---

### F-07 — LAN IP in an unscanned `.dart` file *(LOW, live — blind-spot demonstrator)*

**`mobile/lib/features/profiles/profiles_screen.dart:187`**
```dart
hintText: _connectionType == ConnectionType.local
    ? 'http://192.168.1.100:8000'
```

`192.168.1.100` is a generic first-host-on-a-default-subnet placeholder used as UI hint text, and the parallel value at `abct-docker/unraid/abct-dashboard.xml:89` is explicitly labelled `Example:`. **These are benign.**

They are reported because they demonstrate the exposure: `.dart` files are in no extension list in the tooling, and **96 tracked `.dart` files** are scanned by nothing. Had this line held the real `192.168.<x>.<y>` from F-02, the pre-push audit would have passed it without comment — which is exactly what happened in `deploy_from_git.sh`.

---

## 4. What is clean — verified negative results

These were checked exhaustively and came back clean. Recording them matters: it tells you where *not* to spend hardening effort.

| Class | Result |
|---|---|
| Real API keys (Blockfrost, TapTools, GitHub, AWS, Google, Slack, Stripe, OpenAI, Docker, GitLab) | **None, ever.** Only `mainnetXXXXXXXX…` placeholders (15 occurrences across history) |
| JWTs | None |
| PEM private keys | 3 hits — all are validation string literals in `backend/routers/security.py:282-284` plus a `"\n..."` doc placeholder in `docs/Exchange-Integration.md:43`. No key material |
| `user:pass@host` URLs | None |
| Dynamic-DNS / tunnel hostnames (duckdns, ngrok, Tailscale, No-IP, QNAP, Synology, Cloudflare) | None |
| Email addresses in **file content** | None (F-03 is commit metadata, a different class) |
| Public-routable personal IPs | None. Only `93.184.216.34` (IANA example.com) in an SSRF test |
| Cardano wallet addresses | 24 unique across all history. **All 16 checksum-valid ones are allowlisted and documented**; the other 8 fail bech32 validation (synthetic test data) |
| EVM / BTC / SOL addresses | All allowlisted as protocol contracts or BIP-39 `abandon abandon … about` test vectors |
| Apple Team ID, provisioning UUIDs, keystore passwords, ATS exception domains | None |
| PNG / PDF / DOCX embedded metadata | Clean. DOCX is `python-docx`-generated with no author; sampled PNGs carry no EXIF |
| Deleted files in history | 1 — `MainActivity.kt` moved from the `com.example.abct_mobile` Flutter template. Benign |
| `.env.example` | All 300+ values are genuine placeholders or safe defaults. No copied-from-real values |
| `sec/wallet_allowlist.txt` | Reviewed all 372 lines. Correctly curated, well-documented, each entry attributed to its source file |

---

## 5. Why the pre-push audit missed all seven — tooling gap analysis

The existing tooling is well-built for what it targets. These gaps are all about the *personal-information* class specifically.

### Gap 1 — No CI backstop *(critical)*
`.github/workflows/` contains only `docker-publish.yml` and `docker-scout.yml` (container CVE scanning). **Nothing runs `sec/security_audit.py` server-side.** The audit exists only as a local pre-push hook, which means it does not run for: a fresh clone where nobody ran `sec/install_security_hook.sh`, a push from a second machine, edits made in the GitHub web UI, merges of external PRs, or anyone who types `--no-verify`.

### Gap 2 — The hook fails open twice
`sec/pre-push-hook.sh:27` exits 0 if `security_agent.py` is missing; `:33` exits 0 if `python3` is not on `PATH`. Both print a warning and allow the push. Combined with Gap 1, a leak can reach `main` without any check ever having executed.

### Gap 3 — Working-tree-only scanning
No code path in `sec/` reads git history. F-02 lived in the tree for 3 months, was removed, and remains public — and the scanner has reported "clean" on it ever since.

### Gap 4 — Extension blindness
- Generic checks build their file list from `rglob("*.py")`, `rglob("*.html")`, `rglob("*.js")` only (`security_audit.py:131-133`). **446 of 847 tracked files are outside that set.**
- `WALLET_TEXT_EXTENSIONS` (`security_audit.py:507-511`) covers 18 extensions. **223 tracked files fall outside it**, including:

| Ext | Count | Ext | Count | Ext | Count |
|---|---|---|---|---|---|
| `.dart` | 96 | `.h` | 8 | `.kts` | 3 |
| `.swift` | 43 | `.plist` | 7 | `.bak2/.bak3` | 4 |
| `.gitignore` | 9 | `.entitlements` | 6 | `.pbxproj` | 2 |
| `.xcconfig` | 8 | `.dot`/`.cpp`/`.cc` | 12 | `.properties` | 2 |

Plus `Dockerfile`, `Podfile`, `.docx`, `.rb`, `.rc`, `.cmake`, `.storyboard`, `.xib` — extensionless and rare-extension files are invisible to both lists.

### Gap 5 — The `os.getenv` early-`continue`
`security_audit.py:487-488`. Skipping the whole line to avoid false positives blinds the scanner to default arguments, which is where hardcoded credentials actually live (F-04).

### Gap 6 — The secrets check is Python-only and three regexes deep
`security_audit.py:473-477` iterates `self.python_files` with `password=`, `api_key=`, `secret=`. It cannot see `.js`, `.dart`, `.yml`, `.sh`, `Dockerfile`, or any variable named `token`, `pwd`, `passwd`, `auth`, `credential`, `dsn`, `webhook`, `bearer`.

### Gap 7 — Entire detection classes are absent
There is **no** detector for: IP addresses, hostnames, domains, email addresses, OS usernames, absolute home paths, internal port maps, MAC addresses, cloud/vendor account IDs, or Apple Team IDs. Findings F-01, F-02, F-03, F-05 and F-07 are all in classes the tooling has never had a check for.

### Gap 8 — `sec/` excludes itself
`"/sec/"` is in `exclude_patterns` (`security_audit.py:145`) and `_wallet_scan_files()` `continue`s on any path starting with `sec/` (`:572`). The 33 KB `wallet_allowlist.txt` is never scanned by the tool it configures. It is correctly curated today — but nothing enforces that, and an allowlisted address is a *published* address.

### Gap 9 — Everything except `WALLET-*` can be baselined away
`security_agent.py:173,183` exempt `WALLET-*` from the baseline — a good design. But `MED-SEC` (hardcoded secrets) and every other check **can** be waved through with `--save-baseline`. Any new personal-info check should join `WALLET-*` in the non-baselineable set. Separately, the baseline signature is `check_id:file_path:line_number` (`:223`), so inserting a line above a suppressed finding re-reports it as new, while a genuinely unchanged secret stays suppressed indefinitely.

### Gap 10 — Alert fatigue
The audit currently emits **173 findings** on a clean push (3 CRITICAL / 134 HIGH / 36 MEDIUM), 100 of them a single check ID (`HIGH-001`). Even a perfectly-implemented new leak check would surface as one line inside that wall. Personal-info findings need their own severity lane and their own summary block.

---

## 6. Recommended patches

Ordered by value per unit of effort.

### Patch 1 — Add a CI backstop *(closes Gaps 1, 2)*
```yaml
# .github/workflows/leak-audit.yml
name: Leak Audit
on: [push, pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }          # full history — required for Patch 3
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: python3 sec/security_audit.py --project-root . --only-checks WALLET,PII
```
This is the highest-value single change in this report: it makes every other check unbypassable.

### Patch 2 — Fix the `os.getenv` blindness *(closes Gap 5)*
Replace the line-skip at `security_audit.py:487-488` with a rule that inspects the default argument:
```python
GETENV_DEFAULT = re.compile(
    r'os\.(?:getenv|environ\.get)\(\s*["\'][A-Z_0-9]+["\']\s*,\s*["\']([^"\']{6,})["\']'
)
# flag when the captured default is not an obvious placeholder
PLACEHOLDER = re.compile(r'^(your_|xxx|change|placeholder|example|<|todo|replace)', re.I)
```

### Patch 3 — Scan git history, not just the working tree *(closes Gap 3)*
```python
def _history_blobs(self):
    """Every blob ever committed — catches secrets removed in a later commit."""
    out = subprocess.run(["git", "cat-file", "--batch-all-objects",
                          "--batch-check=%(objecttype) %(objectname) %(objectsize)"],
                         cwd=self.project_root, capture_output=True, text=True).stdout
    for line in out.splitlines():
        kind, sha, size = line.split()
        if kind == "blob" and int(size) < self.WALLET_MAX_FILE_BYTES:
            yield sha
```
Run in CI (Patch 1) rather than on every pre-push — it takes ~30 s on this repo's 1,250 blobs. Seed a `sec/history_baseline.json` with today's known-accepted set so it does not block on F-02 forever.

### Patch 4 — Add the missing detector classes *(closes Gap 7)*
New check IDs, all **non-baselineable** alongside `WALLET-*`:

| ID | Detects | Severity |
|---|---|---|
| `PII-001` | Absolute home paths: `/Users/<name>/`, `/home/<name>/`, `C:\Users\<name>\` — allowlist `/home/user/`, `/home/runner/` | HIGH |
| `PII-002` | RFC1918 / CGNAT IPs — allowlist `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `127.0.0.1`, `0.0.0.0`, `169.254.169.254`, and any line matching `example|placeholder|RFC` | HIGH |
| `PII-003` | Dynamic-DNS & tunnel hosts: `duckdns.org`, `ngrok.io`, `ngrok-free.app`, `*.ts.net`, `no-ip.org`, `ddns.net`, `myqnapcloud.com`, `synology.me`, `trycloudflare.com`, `hopto.org` | CRITICAL |
| `PII-004` | Emails not on an allowlisted domain (`example.*`, `*.invalid`, `noreply@*`) | HIGH |
| `PII-005` | Host-storage paths: `/mnt/user/appdata/`, `/volume[0-9]/`, `/srv/dev-disk-by-*` | MEDIUM |
| `PII-006` | Vendor account IDs: Apple `DEVELOPMENT_TEAM` (10 chars `[A-Z0-9]`), AWS account numbers, GCP project IDs | MEDIUM |
| `SEC-101` | Broadened secret regex — `token|pwd|passwd|auth|credential|dsn|webhook|bearer` — across **all** text extensions | HIGH |
| `GIT-001` | Commit author/committer email not on the project's allowlisted identity list | MEDIUM |

### Patch 5 — Close the extension and self-exclusion gaps *(closes Gaps 4, 6, 8)*
```python
# Replace the fixed extension allowlist with a binary-file denylist:
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2",
              ".ttf", ".otf", ".zip", ".gz", ".pdf", ".mp4", ".db"}

def _scan_files(self):
    """Scan every tracked file that isn't binary — denylist, not allowlist,
    so a new file type is covered the day it lands."""
    for rel in git_ls_files():
        p = self.project_root / rel
        if p.suffix.lower() in BINARY_EXT:
            continue
        if p.stat().st_size > self.WALLET_MAX_FILE_BYTES:
            continue
        yield p
```
This single inversion brings all 96 `.dart`, 43 `.swift`, 8 `.xcconfig`, 7 `.plist`, 6 `.entitlements`, 2 `.pbxproj` and the `Dockerfile`/`Podfile` under coverage. Stop excluding `sec/` — instead exempt only `sec/wallet_allowlist.txt` from `WALLET-*` specifically, so the rest of `sec/` is audited normally.

Also add a tracked-vs-ignored assertion:
```sh
git ls-files | git check-ignore --stdin --no-index --verbose
# any output = a tracked file matching an active ignore rule (catches F-06)
```
Note the `--no-index` flag — without it, git silently reports nothing for tracked files, which is why this class went unnoticed.

### Patch 6 — Separate the personal-info lane *(closes Gaps 9, 10)*
Report `PII-*`, `GIT-*` and `WALLET-*` in their own summary block above the vulnerability findings, and add them all to the non-baselineable set at `security_agent.py:173`. Consider changing the baseline signature from `check_id:file:line` to `check_id:file:sha256(matched_text)` so line drift stops causing churn.

### Patch 7 — Housekeeping
```sh
# F-01
sed -i 's#/home/<dev-user>/<path>/dashboard#/path/to/abct#' \
    screenshots/glass-phase1/SCREENSHOT-GUIDE.md
# F-06
git rm --cached frontend/apis.html.bak2 frontend/nft-wall.html.bak2 \
                frontend/security.html.bak2 frontend/services.html.bak3
# F-03
git config user.name "ABCT Team" && git config user.email "team@abct.dev"
```

---

## 7. Appendix — reproduction commands

```sh
# F-01
rg -n '/home/[a-z]+/|/Users/[A-Za-z]+/' -g '!.git' .

# F-02 — the leaked host, still in history
git log --all --oneline -S'192.168.<x>.<y>'
git show 19a36f9:abct-docker/deploy_from_git.sh | sed -n '1,20p'

# F-03
git log --all --format='%ae|%an' | sort | uniq -c | sort -rn

# F-04
rg -n 'os\.getenv\([^)]*,\s*["'"'"'][^"'"'"']{4,}' backend/

# F-06 — note --no-index; without it git reports nothing for tracked files
git ls-files | git check-ignore --stdin --no-index --verbose

# Full object-database sweep (the check that does not exist today)
git cat-file --batch-all-objects --batch-check='%(objecttype) %(objectname) %(objectsize)' \
  | awk '$1=="blob" && $3<2000000 {print $2}' | git cat-file --batch \
  | grep -aoE '<your-pattern-here>' | sort -u

# Baseline: what the current audit reports (173 findings, none of the above)
python3 sec/security_audit.py --project-root .
```
