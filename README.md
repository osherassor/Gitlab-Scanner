GitLab Scanner

GitLab Scanner is a Python CLI for reconnaissance and secret scanning against GitLab instances (Self‑Managed or SaaS). It can run unauthenticated for public discovery or with authentication to increase coverage. The tool discovers projects and groups, harvests users, scans repository files for potential secrets based on configurable regex rules, optionally scans commit history, and writes structured JSON/JSONL outputs plus an HTML report per run.

### Features
- Discover projects and groups (public only or public+private when authenticated)
- Harvest users from members, commits, and the API
- Scan repository files for potential secrets using YAML‑defined regex rules
- Optional commit history scan with de‑duplication vs HEAD
- Intelligent skipping of binary/large files
- Structured outputs: JSONL (line‑delimited) and continuously updated JSON snapshots
- Per‑run HTML report
- Rate limiting, retries and timeouts built in

### Requirements
- Python 3.9+
- Works on macOS, Linux, and Windows

### Installation
Install from source:

```bash
pip install -e .
```

Optionally, use an isolated environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
```

### Quick start
Public discovery (no auth):

```bash
gitlab-scanner --base-url https://gitlab.example.com
```

With Personal Access Token (PAT):

```bash
gitlab-scanner --base-url https://gitlab.example.com --token <PAT>
```

With username/password session:

```bash
gitlab-scanner --base-url https://gitlab.example.com \
  --username <USERNAME> --password <PASSWORD>
```

Scan multiple targets from a file (one URL per line; auth flags are not allowed in this mode):

```bash
gitlab-scanner --base-url-file targets.txt
```

### CLI usage
Core flags (see `gitlab_scanner/cli.py`):
- `--base-url <url>`: GitLab base URL (http/https). Mutually exclusive with `--base-url-file`.
- `--base-url-file <path>`: File with base URLs, one per line. Auth flags are not allowed with this option.

Authentication:
- `--token <PAT>`
- `--username <USER> --password <PASS>`

General:
- `--verify-ssl` Enable TLS certificate verification (default: off)
- `--out-dir <path>` Output directory (default: `./gitlab-scan-output`)
- `--rules-yaml <path>` Path to rules YAML (default: `./config/rules.yaml`)

History:
- `--no-scan-history` Disable commit history scanning (HEAD scanning remains enabled)

Logging:
- `--debug` Increase log verbosity for this run

Examples:

```bash
# Safer TLS (recommended for production)
gitlab-scanner --base-url https://gitlab.example.com --verify-ssl

# Custom output directory and custom rules
gitlab-scanner --base-url https://gitlab.example.com \
  --out-dir ./out --rules-yaml ./config/rules.yaml

# Disable history to speed up
gitlab-scanner --base-url https://gitlab.example.com --no-scan-history
```

### Configuration
Runtime configuration is loaded from `config/scan_config.yaml`. It controls logging, output behavior (JSONL and live JSON snapshots), HTTP timeouts/rate‑limits, and scanning limits (max file size, interesting file patterns, binary extensions, etc.).

Secret‑scanning rules are provided in `config/rules.yaml` (or `--rules-yaml`). Each rule contains an `id` and a regex `pattern`. Only textual files are scanned; binary/oversized files are skipped.

### Outputs
Every run creates a unique subfolder under `--out-dir`:

- `repos.json` / `repos.jsonl` – Discovered projects
- `groups.json` / `groups.jsonl` – Discovered groups and subgroups
- `users.json` / `users.jsonl` and `users.csv` – Aggregated users from multiple sources
- `files.json` / `files.jsonl` – Enumerated files per repository
- `interesting.jsonl` – Files matching interesting name/extension patterns
- `secrets.json` / `secrets.jsonl` – Potential secrets with entropy and context
- `skipped.jsonl` – Files skipped due to size/binary/other reasons
- `report.html` – Summary HTML report

Snapshots (`*.json`) remain valid JSON arrays throughout the run; line‑delimited (`*.jsonl`) are written live for stream processing.

### How it works (high‑level)
1) Fetch instance topology and version (best effort).
2) Discover projects and groups (public only or also private when authenticated).
3) Harvest users from group/project membership, commit authors, and (if authenticated) global API.
4) Scan repository file trees for potential secrets using rules. Skip large/binary files and keep progress responsive.
5) Optionally scan commit diffs within a time/commit budget and de‑duplicate matches already present in HEAD.
6) Generate per‑run outputs and an HTML report.

### Ethics and legal notice
This project is provided for research, defensive security, and legitimate testing only. You are solely responsible for complying with all applicable laws, regulations, and terms of service. Do not scan systems you do not own or do not have explicit authorization to test. The authors and contributors assume no liability for misuse or damages arising from the use of this tool.

### Troubleshooting
- TLS warnings: enable `--verify-ssl` and ensure proper CA trust.
- 401/403 responses: provide a valid `--token` or `--username/--password` with appropriate permissions.
- Rate limits: the tool applies backoff and throttling; very large instances may still require patience or narrower scopes.

### Development
Run locally in editable mode:

```bash
pip install -e .[dev]
```

Entry point: `gitlab-scanner` (see `gitlab_scanner/cli.py`).

### License
MIT – see `LICENSE`.

