<h1 align="center">🦊 GitLab Scanner</h1>

<p align="center">
  <strong>Recon and secret-scan a GitLab instance in one command.</strong><br>
  Public discovery without auth, deeper coverage with a token. Repo files + commit history + structured JSON / JSONL / HTML output.
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/osherassor/Gitlab-Scanner?style=for-the-badge&logo=github&color=ffd700" alt="Stars">
  <img src="https://img.shields.io/github/last-commit/osherassor/Gitlab-Scanner?style=for-the-badge&logo=git&color=00d4aa" alt="Last commit">
  <img src="https://img.shields.io/badge/python-3.9%2B-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-informational?style=for-the-badge" alt="License">
</p>

---

## What is this?

A Python CLI for GitLab — Self-Managed or SaaS — that walks the instance, enumerates projects/groups/users, scans repository files (and optionally commit history) for secrets using regex rules you control, then writes everything to a per-run output folder with a clean HTML report on top.

Run it unauthenticated against a public instance, or with a Personal Access Token / username+password for the deep dive.

## 🚀 Quick start

```bash
pip install -e .

# Public discovery — no auth
gitlab-scanner --base-url https://gitlab.example.com

# With a Personal Access Token
gitlab-scanner --base-url https://gitlab.example.com --token <PAT>

# With user/pass
gitlab-scanner --base-url https://gitlab.example.com \
  --username <USER> --password <PASS>

# Multi-target sweep (no auth flags allowed in this mode)
gitlab-scanner --base-url-file targets.txt
```

## ✨ Features

- 🔭 **Discovery** — projects + groups (public, or public + private when authenticated)
- 👥 **User harvesting** — pulled from membership, commits, and the API
- 🕵️ **Repo file scanning** — YAML-defined regex rules for secrets
- 🕰️ **Commit history scan** — optional, with HEAD de-duplication
- 🧠 **Smart skipping** — binary and oversized files are bypassed
- 📦 **Structured output** — JSONL streams during the run, JSON snapshots stay valid arrays throughout
- 📊 **Per-run HTML report** — drop-in for client deliverables
- ⚙️ **Built-in rate limiting, retries, timeouts**

## 🔧 CLI essentials

| Flag | Description |
|---|---|
| `--base-url <url>` | GitLab base URL — mutually exclusive with `--base-url-file` |
| `--base-url-file <path>` | Multiple targets, one per line (no auth flags allowed here) |
| `--token <PAT>` | Personal Access Token |
| `--username` / `--password` | Session-based auth |
| `--verify-ssl` | Enable TLS cert verification (default: off) |
| `--out-dir <path>` | Output directory (default: `./gitlab-scan-output`) |
| `--rules-yaml <path>` | Custom rules file (default: `./config/rules.yaml`) |
| `--no-scan-history` | Disable commit history scan (HEAD scanning stays on) |
| `--debug` | Verbose logging |

```bash
# Production-safe TLS
gitlab-scanner --base-url https://gitlab.example.com --verify-ssl

# Custom output + custom rules
gitlab-scanner --base-url https://gitlab.example.com \
  --out-dir ./out --rules-yaml ./config/rules.yaml

# Faster — skip history
gitlab-scanner --base-url https://gitlab.example.com --no-scan-history
```

## 🛠️ Configuration

Two YAMLs control behavior:

| File | Controls |
|---|---|
| `config/scan_config.yaml` | Logging, output (JSONL streaming + JSON snapshots), HTTP timeouts/rate limits, scan limits (max file size, interesting file patterns, binary extensions) |
| `config/rules.yaml` | Secret-scanning regex rules — each entry has an `id` and a `pattern`. Only textual files are scanned |

## 📤 Outputs

Every run gets its own subfolder under `--out-dir`:

| File | Contents |
|---|---|
| `repos.json` / `.jsonl` | Discovered projects |
| `groups.json` / `.jsonl` | Discovered groups + subgroups |
| `users.json` / `.jsonl` / `.csv` | Aggregated users |
| `files.json` / `.jsonl` | Enumerated files per repo |
| `interesting.jsonl` | Files matching interesting name/extension patterns |
| `secrets.json` / `.jsonl` | Potential secrets with entropy + context |
| `skipped.jsonl` | Skipped files with reasons |
| `report.html` | Summary HTML report |

`*.json` snapshots stay valid throughout the run; `*.jsonl` streams live for downstream pipelines.

## 🧠 How it works (high level)

1. Fetch instance topology + version (best effort).
2. Discover projects + groups (auth-gated visibility).
3. Harvest users from group/project members, commit authors, and (auth) the global API.
4. Scan repo file trees with regex rules, skipping binary/large files.
5. Optional commit-diff scan inside a time/commit budget, de-duped against HEAD matches.
6. Write per-run outputs + HTML report.

## 🧯 Troubleshooting

- **TLS warnings** — turn on `--verify-ssl` and ensure CA trust is correct
- **401 / 403** — provide a valid `--token` or `--username`/`--password` with sufficient scope
- **Rate limits** — backoff is built in; very large instances may still need narrower scopes or patience

## 🤝 Pairs well with

- 🗂️ **[smb_files_scanner](https://github.com/osherassor/smb_files_scanner)** — the same secret-pattern philosophy, but for SMB shares instead of GitLab repos. Run both to cover both surfaces on an internal engagement.
- 🧰 **[MyCyberTool](https://github.com/osherassor/MyCyberTool)** — when something interesting comes out of a bundle / page / leaked file, push it through the secrets scanner there for a second opinion.

## 🛠️ Development

```bash
# Editable install + dev extras
pip install -e .[dev]
```

Entry point: `gitlab-scanner` → `gitlab_scanner/cli.py`.

## ⚖️ Responsible use

For research, defensive security, and authorized testing only. Don't scan instances you don't own or aren't engaged on. You're responsible for ToS / legal compliance.

## 📄 License

MIT
