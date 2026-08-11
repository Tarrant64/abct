# ABCT — Personal Information & Infrastructure Leak Audit

**Repository:** `Tarrant64/abct` (public)
**Audit date:** 2026-08-11 · **Revised:** 2026-08-11 (owner triage applied)
**Branch audited:** `claude/repo-secrets-audit-4oq59x` @ `f8e5c06`
**Scope:** Accidental disclosure of the developer's *own* private information — personal/home infrastructure, credentials, API keys, wallet addresses, identity.
**Explicitly out of scope:** code vulnerabilities (XSS, SSRF, authz). Those are covered by the existing `sec/` tooling and were ignored here.

> **Owner triage, 2026-08-11.** The repository owner has reviewed all seven findings and
> accepted **F-01**, **F-03** and **F-04** as approved risk: the project is published under a
> real identity by choice, so name, email and OS username exposure are not concerns, and the
> `satoshi` admin default is a known, deliberate default. Those three are retained in §4 for
> the record rather than removed — F-04 in particular is the evidence behind Patch 2 and
> stays in full.
>
> **Remediation set: F-02, F-05, F-06, F-07** (§3), with a punch list in §8.
>
> **Redaction in this edition.** Identity values (real name, email addresses, OS username)
> are shown unredacted — they are accepted risk and already public in commit metadata.
> The home-lab IP address from F-02 is masked as `192.168.<x>.<y>`, because that finding is
> being remediated and republishing the literal value in `HEAD` would work against the fix.
> Everything else — file paths, line numbers, commit SHAs, remediation steps — is intact.

---

## 1. Executive summary

The repository's credential hygiene is **genuinely good**. Across all **1,250 blobs in the entire git object database**, there is not a single real API key, JWT, private key, `user:pass@host` URL, tunnel hostname, or email address ever committed in file content. Every checksum-valid Cardano address in history is already documented in `sec/wallet_allowlist.txt` as a public protocol constant or spec test vector. The July 2026 "personal-address scrub" appears to have been done correctly and completely.

Seven personal-information leaks were found. **None are credentials** — they are identity and infrastructure fingerprints. After owner triage, four require action:

### Remediation set

| # | Finding | Severity | State |
|---|---|---|---|
| F-02 | Real home-lab static IP + full network/storage topology | **HIGH** | Git history — permanent until rewritten |
| F-05 | Personal domain in iOS/Android app identifiers | **LOW** | Working tree — live |
| F-06 | Four stale `.bak2/.bak3` files published; `.gitignore` gives false assurance | **LOW** | Working tree — live |
| F-07 | LAN IP placeholder in an unscanned `.dart` file | **LOW** | Working tree — live |

### Accepted risk — no action

| # | Finding | Owner rationale |
|---|---|---|
| F-01 | Developer's real OS username + local project path | Publishing under a real identity by choice |
| F-03 | Real name + personal email as git author on 83/86 commits | Same — anonymity is not a project goal |
| F-04 | `satoshi` admin password across six sites | Known, deliberate, documented default |

**The single most important structural result is unchanged by the triage:** the existing audit reports **173 findings** on this tree (3 CRITICAL / 134 HIGH / 36 MEDIUM) and **none of them is any of the seven**. The tooling is thorough about code vulnerabilities and effectively blind to personal-information disclosure. Accepting a finding closes the *instance*; it does not close the *detector gap* that let it through unnoticed.

**Two gaps deserve attention regardless of which findings were accepted:**
1. **No CI backstop.** `.github/workflows/` contains only `docker-publish.yml` and `docker-scout.yml`. The leak audit runs *exclusively* in a local pre-push hook that must be installed manually per clone, fails open twice, and is bypassed by `git push --no-verify` or any edit made through the GitHub web UI.
2. **The scanner never reads git history.** F-02 was correctly fixed in the working tree on 2026-07-13 and is still fully public. A working-tree-only scanner reports "clean" on a repository that is not.

---

## 2. Method

| Surface | Coverage |
|---|---|
| Working tree | All 847 tracked files |
| Git history | All 1,250 blobs (`git cat-file --batch-all-objects`), 87 commits, all refs |
| Deleted files | `git log --diff-filter=D` (1 file, benign Flutter template rename) |
| Commit metadata | Author/committer identity + all commit messages |
| Binary artifacts | 114 PNGs, 4 PDFs, 1 DOCX — filenames + embedded metadata |
| Checksum validation | Cardano bech32 addresses validated with the repo's own `_bech32_valid()` |
| Baseline comparison | `python3 sec/security_audit.py` executed; its 173 findings diffed against ours |

Detection classes swept: RFC1918 + public IPs, dynamic-DNS/tunnel hosts, `.local`/LAN names, home paths, personal emails, API-key shapes for 12 vendors, JWTs, PEM key blocks, basic-auth URLs, base64/hex blobs, wallet addresses across 6 chains, Apple Team IDs, provisioning UUIDs, keystore passwords, app-group identifiers.

---

## 3. Remediation set

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

#### Remediation

This cannot be un-published by an ordinary commit. Two things need to happen, and **step A matters more than step B**.

**A. Neutralise the value (do this first — it is what actually ends the exposure).**
The leaked address is RFC1918. It is only meaningful to someone already inside that LAN, or to someone who later gains a foothold and wants to know where to look. Re-IP the container and confirm the subnet is not reachable from the internet:

```sh
# on the Unraid host
docker stop abct-dashboard && docker rm abct-dashboard
ABCT_STATIC_IP=192.168.<new>.<new> abct-docker/deploy_from_git.sh
# then verify nothing on that subnet is port-forwarded at the router
```
Also consider relocating `/mnt/user/appdata/ABCT/.env`, since its path is the genuinely sensitive half of this finding.

**B. Rewrite history (optional — closes the record, does not undo the disclosure).**

Blast radius is real but bounded: the first affected commit is `19a36f9`, and **64 of 87 commits** sit at or after it, so every one of those SHAs changes.

```sh
pip install git-filter-repo
git clone --mirror https://github.com/Tarrant64/abct.git abct-mirror
cd abct-mirror
printf '<the-leaked-ip>==>192.168.0.10\n/mnt/user/appdata==>/srv/appdata\n' > ../replacements.txt
git filter-repo --replace-text ../replacements.txt
git push --force --mirror
```

Caveats to weigh before doing this:
- Anyone holding a clone must re-clone; existing PR branches and any forks keep the old objects.
- GitHub retains unreachable objects and serves them by SHA until garbage collection. A rewrite alone does **not** purge them — you must open a GitHub Support ticket to request GC of the old objects.
- Search engines, the GitHub Archive dataset and any mirror may already have crawled it.

**Recommendation:** do A unconditionally. Do B only if you want the record clean for its own sake — with 64 rewritten SHAs on a public repo, and the value already indexed, B buys tidiness rather than security. The part that actually pays forward is Patch 3, which catches the next one before it ships.

---

### F-05 — Personal domain in iOS/Android app identifiers *(LOW, live)*

| File | Value |
|---|---|
| `mobile/ios/Runner.xcodeproj/project.pbxproj` (30 occurrences) | `teamcata.com.ABCT-Mobile` |
| `mobile/android/app/build.gradle.kts:38,55` | `namespace` / `applicationId` = `com.teamcata.abct` |
| `mobile/android/app/src/main/kotlin/com/teamcata/abct/MainActivity.kt` | package path |
| 4 × `*.entitlements` | `group.com.teamcata.abct` |
| `mobile/macos/Runner/Configs/AppInfo.xcconfig:11` | `teamcata.com.ABCT-Mobile` |
| Plus 9 more files | `README.md`, build scripts, Swift sources — 20 files, 55 occurrences total |

Ties the project to the `teamcata` handle. (In passing: the iOS identifier `teamcata.com.ABCT-Mobile` is malformed reverse-DNS; Android correctly uses `com.teamcata.abct`.)

**Positive finding:** `DEVELOPMENT_TEAM` is empty (`project.pbxproj:1127`), no Apple Team ID, no provisioning-profile UUIDs, and no `NSAppTransportSecurity` exception domains anywhere. That is good hygiene on the highest-risk Xcode fields.

**Why every existing check missed it:** `.pbxproj`, `.entitlements`, `.xcconfig`, `.kts` and `.kt` appear in **no** extension list in the tooling.

#### Remediation — recommend deferring

**This is the same identity class as F-01 and F-03, which you accepted.** A `teamcata` handle discloses no more than a real name and personal email already do, and the change is not free:

- The bundle identifier is an app's **identity of record**. Changing it on a published iOS app means a new App Store listing, not an update — existing installs cannot upgrade across it.
- `group.com.teamcata.abct` is the App Group backing watch/widget data sharing. Changing it orphans everything currently in the shared container (`SharedPortfolioSnapshotStore`), and the watch complication and widget both read from it.
- `keychain-access-groups` is derived from `PRODUCT_BUNDLE_IDENTIFIER`, so stored credentials are orphaned too.

**My recommendation:** move F-05 to accepted risk alongside F-01/F-03 — it is the same disclosure at a much higher remediation cost. If you want it changed regardless, do it *before* any App Store submission, never after, and treat it as a migration:

```sh
# pre-submission only; sequence matters
rg -l 'teamcata' mobile/ | xargs sed -i 's/com\.teamcata\.abct/dev.abct.app/g; s/teamcata\.com\.ABCT-Mobile/dev.abct.ABCT-Mobile/g'
git mv mobile/android/app/src/main/kotlin/com/teamcata mobile/android/app/src/main/kotlin/dev/abct
# then: bump the App Group in all 4 entitlements, add a one-shot migration
#       that copies the old shared container before the identifier flips
```

Your call — the cost is the point, not the difficulty.

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

#### Remediation

```sh
git rm --cached frontend/apis.html.bak2 frontend/nft-wall.html.bak2 \
                frontend/security.html.bak2 frontend/services.html.bak3
git commit -m "chore: untrack stale frontend backups superseded by .gitignore rules"
```
The files stay on disk and become genuinely ignored. Then wire the assertion in Patch 5 so this class cannot recur — note it needs `--no-index`, without which git silently reports nothing for tracked files, which is exactly why this went unnoticed.

---

### F-07 — LAN IP in an unscanned `.dart` file *(LOW, live)*

**`mobile/lib/features/profiles/profiles_screen.dart:187`**
```dart
hintText: _connectionType == ConnectionType.local
    ? 'http://192.168.1.100:8000'
```

`192.168.1.100` is a generic first-host-on-a-default-subnet placeholder used as UI hint text, and the parallel value at `abct-docker/unraid/abct-dashboard.xml:89` is explicitly labelled `Example:`. **These are benign** — they are not your address and disclose nothing.

They are in the remediation set because they demonstrate the exposure: `.dart` files are in no extension list in the tooling, and **96 tracked `.dart` files** are scanned by nothing. Had this line held the real address from F-02, the pre-push audit would have passed it without comment — which is exactly what happened in `deploy_from_git.sh`.

#### Remediation

The value is fine; what needs fixing is that nothing would have caught it if it weren't. Cover the file type (Patch 5), and optionally switch the hint to a documentation-range address so the new `PII-002` detector has nothing to special-case:

```dart
? 'http://192.0.2.10:8000'   // RFC 5737 documentation range
```
Same for `abct-docker/unraid/abct-dashboard.xml:89`.

---

## 4. Accepted risk — retained for the record

These three were reviewed and accepted by the repository owner. No action is required. They remain documented because the *detector gaps* behind them are still real, and because F-04 is the evidence for Patch 2.

### F-01 — Developer's real OS username and local project path *(accepted)*

**`screenshots/glass-phase1/SCREENSHOT-GUIDE.md:7`**
```
2. Start the backend: `cd /home/ccata/Claude/ABCT/dashboard && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
```
Discloses the OS account name (`ccata`) and local directory layout. Introduced in `818230a` (2026-06-28), still in `HEAD`.

**Owner disposition:** accepted — the project is published under a real identity by choice, so username exposure is not a concern.

**Detector note:** the file is `.md`, absent from the generic `.py`/`.html`/`.js` file lists (`security_audit.py:131-133`); the wallet scanner reads `.md` but only for addresses. No home-path detector exists. Because this class is accepted, `PII-001` in Patch 4 is **downgraded to optional** — its remaining value is catching a path that reveals *directory structure on a server*, not a username.

---

### F-03 — Real name and personal email in git authorship *(accepted)*

```
     83  chris.cata@outlook.com | Chris Cata
      2  team@abct.dev          | ABCT Team
      1  shopifystig@gmail.com  | TheD0SH
```
96.5% of commits are authored under a real full name and a personal Outlook address, against a project-facing `ABCT Team <team@abct.dev>` identity. A third identity appears once (`c328a21`).

**Owner disposition:** accepted — anonymity is not a project goal.

**Detector note:** commit metadata is not file content, so no file scanner can see this. Because this class is accepted, `GIT-001` (author-identity assertion) is **dropped from Patch 4** rather than downgraded. The one thing still worth a moment: `shopifystig@gmail.com` is a *different* persona from the other two. If that account is unrelated to this project and you would rather it not be linked, that single commit is the only thing tying them together — otherwise ignore it.

---

### F-04 — `satoshi` admin password across six sites *(accepted — retained in full)*

`satoshi` is the **documented default** (`README.md:115`: *"**Admin**: `admin` / `satoshi`"*). The owner has confirmed it is deliberate. It is retained in full because it remains the sharpest available demonstration of the secret-detector's structural blind spots — **this table is the justification for Patch 2.**

| Location | Form | Caught by `MED-SEC`? | Why not |
|---|---|---|---|
| `backend/database.py:275` | `os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")` | ❌ | `security_audit.py:487-488` — *"Skip if using os.getenv"* — `continue`s on the entire line |
| `backend/migrate_multiuser.py:69` | `os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")` | ❌ | same early-`continue` |
| `backend/check_auth.py:48,65,81,92` | `bcrypt.hashpw("satoshi".encode(...))` | ❌ | no `password=` assignment, so none of the 3 regexes match |
| `backend/migrate_to_multiuser.py:149` | `password = "admin"` | ✅ | matches `password\s*=\s*["']` |
| `frontend/login.html:396` | `document.getElementById('password').value = 'satoshi'` | ❌ | secrets check runs on **Python files only** |
| `frontend/v2/login.html:156` | same auto-fill | ❌ | same |

**Owner disposition:** accepted — known and deliberate.

**Detector note — this is the part that still matters.** The `os.getenv` exemption was written to suppress false positives on `password = os.getenv("PW")`. Its actual effect is to **blind the scanner to the second argument** — the default — which is where hardcoded credentials live. Any *future* real secret written as `os.getenv("X", "<real-secret>")` is invisible to this repository's audit today. Accepting `satoshi` does not make that safe; Patch 2 does.

---

## 5. What is clean — verified negative results

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

## 6. Why the pre-push audit missed all seven — tooling gap analysis

The existing tooling is well-built for what it targets. These gaps are all about the *personal-information* class specifically, and **the owner triage does not close any of them** — accepting a finding closes the instance, not the blind spot.

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

## 7. Recommended patches

Re-prioritised against the owner triage: detectors for accepted classes are downgraded or dropped, and the infrastructure classes behind F-02 move to the front.

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
Retained at full priority despite F-04 being accepted — the accepted value is `satoshi`, but the blind spot applies to every future default.
```python
GETENV_DEFAULT = re.compile(
    r'os\.(?:getenv|environ\.get)\(\s*["\'][A-Z_0-9]+["\']\s*,\s*["\']([^"\']{6,})["\']'
)
# flag when the captured default is not an obvious placeholder
PLACEHOLDER = re.compile(r'^(your_|xxx|change|placeholder|example|<|todo|replace)', re.I)
```
Add `satoshi` to an explicit accepted-defaults list so the check runs clean today and still fires on anything new.

### Patch 3 — Scan git history, not just the working tree *(closes Gap 3)*
The direct fix for the F-02 class.
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
Run in CI (Patch 1) rather than on every pre-push — it takes ~30 s on this repo's 1,250 blobs. Seed a `sec/history_baseline.json` with today's accepted set so it does not block on F-02 forever.

### Patch 4 — Add the missing detector classes *(closes Gap 7)*
New check IDs, all **non-baselineable** alongside `WALLET-*`. Priorities reflect the triage.

| ID | Detects | Severity | Priority |
|---|---|---|---|
| `PII-002` | RFC1918 / CGNAT IPs — allowlist `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `127.0.0.1`, `0.0.0.0`, `169.254.169.254`, and any line matching `example\|placeholder\|RFC` | HIGH | **Primary — F-02 class** |
| `PII-003` | Dynamic-DNS & tunnel hosts: `duckdns.org`, `ngrok.io`, `ngrok-free.app`, `*.ts.net`, `no-ip.org`, `ddns.net`, `myqnapcloud.com`, `synology.me`, `trycloudflare.com`, `hopto.org` | CRITICAL | **Primary** |
| `PII-005` | Host-storage paths: `/mnt/user/appdata/`, `/volume[0-9]/`, `/srv/dev-disk-by-*` | MEDIUM | **Primary — F-02 class** |
| `SEC-101` | Broadened secret regex — `token\|pwd\|passwd\|auth\|credential\|dsn\|webhook\|bearer` — across **all** text extensions | HIGH | **Primary** |
| `PII-006` | Vendor account IDs: Apple `DEVELOPMENT_TEAM` (10 chars `[A-Z0-9]`), AWS account numbers, GCP project IDs | MEDIUM | Secondary |
| `PII-001` | Absolute home paths — `/Users/<name>/`, `/home/<name>/`, `C:\Users\<name>\` | LOW | *Optional* — F-01 accepted; value is now server directory structure, not usernames |
| `PII-004` | Emails outside an allowlisted domain set | LOW | *Optional* — F-03 accepted; keep only to catch **third-party** addresses |
| ~~`GIT-001`~~ | ~~Commit author identity assertion~~ | — | **Dropped** — F-03 accepted, real identity is intentional |

### Patch 5 — Close the extension and self-exclusion gaps *(closes Gaps 4, 6, 8; fixes F-06 and F-07 detection)*
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
Report `PII-*` and `WALLET-*` in their own summary block above the vulnerability findings, and add them to the non-baselineable set at `security_agent.py:173`. Consider changing the baseline signature from `check_id:file:line` to `check_id:file:sha256(matched_text)` so line drift stops causing churn.

---

## 8. Punch list

Ordered. Items marked *decide* need a call before work starts.

**F-02 — home-lab IP and storage topology**
- [ ] Re-IP the ABCT container off `192.168.<x>.<y>`; verify the subnet is not port-forwarded at the router
- [ ] Relocate `/mnt/user/appdata/ABCT/.env` (its path is the sensitive half)
- [ ] *decide* — history rewrite via `git filter-repo --replace-text`? 64 of 87 SHAs change; forks keep old objects; needs a GitHub Support ticket to purge. Recommended **only** for tidiness, not security
- [ ] Consider softening `CHANGELOG.md:1092`, which signposts the affected commits

**F-06 — stale backups**
- [ ] `git rm --cached frontend/{apis,nft-wall,security}.html.bak2 frontend/services.html.bak3`

**F-07 — unscanned `.dart` placeholder**
- [ ] Switch `profiles_screen.dart:187` and `abct-dashboard.xml:89` hints to `192.0.2.10` (RFC 5737)

**F-05 — app identifiers** *(recommend deferring)*
- [ ] *decide* — same identity class as accepted F-01/F-03, but costs a bundle-ID migration: new App Store listing, orphaned App Group + keychain. If yes, do it pre-submission only

**Tooling — the part that pays forward**
- [ ] Patch 1 · CI backstop *(highest value)*
- [ ] Patch 5 · invert extension list → +223 files covered
- [ ] Patch 3 · git-history scan → the F-02 class, caught next time
- [ ] Patch 2 · `os.getenv` default-argument detection
- [ ] Patch 4 · `PII-002`, `PII-003`, `PII-005`, `SEC-101` first; `PII-001`/`PII-004` optional; `GIT-001` dropped
- [ ] Patch 6 · separate PII lane, non-baselineable

---

## 9. Appendix — reproduction commands

```sh
# F-02 — the leaked host, still in history
git log --all --oneline -S'<the-leaked-ip>'   # masked here; substitute the real value
git show 19a36f9:abct-docker/deploy_from_git.sh | sed -n '1,20p'

# F-05
rg -c 'teamcata' --glob '!.git' .

# F-06 — note --no-index; without it git reports nothing for tracked files
git ls-files | git check-ignore --stdin --no-index --verbose

# F-04 detector gap (accepted finding, live gap)
rg -n 'os\.getenv\([^)]*,\s*["'"'"'][^"'"'"']{4,}' backend/

# Full object-database sweep (the check that does not exist today)
git cat-file --batch-all-objects --batch-check='%(objecttype) %(objectname) %(objectsize)' \
  | awk '$1=="blob" && $3<2000000 {print $2}' | git cat-file --batch \
  | grep -aoE '<your-pattern-here>' | sort -u

# Baseline: what the current audit reports (173 findings, none of the seven)
python3 sec/security_audit.py --project-root .
```
