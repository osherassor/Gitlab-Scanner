import os
import sys
import time
import json
import warnings
import csv
import yaml
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from .utils.config import load_config
from .utils.logging import Logger
from .utils.output import OutputWriters
from .utils.report import generate_html_report
from .utils.gitlab import GitLabClient


def run(args) -> int:
    config = load_config()

    # CLI overrides
    base_url = args.base_url
    verify_ssl = bool(args.verify_ssl)
    base_out_dir = args.out_dir
    rules_yaml = args.rules_yaml
    scan_history = True if getattr(args, "scan_history", True) else False

    if args.debug:
        config["logging"]["level"] = "debug"

    # HTTP verify override from CLI
    config.setdefault("http", {}).setdefault("verify_ssl", False)
    if verify_ssl:
        config["http"]["verify_ssl"] = True
    # Suppress noisy TLS warnings when verify is disabled; always hide NotOpenSSLWarning
    try:
        import urllib3

        warnings.filterwarnings("ignore", category=urllib3.exceptions.NotOpenSSLWarning)
        if not config["http"]["verify_ssl"]:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    # Build unique run directory name (lazy create upon first write)
    parsed = urlparse(base_url)
    host = parsed.hostname or "unknown-host"
    scheme = (parsed.scheme or "http").lower()
    port = parsed.port
    safe_host = host.replace(".", "-").replace(":", "-")
    ts = time.strftime("%Y%m%d-%H%M%S")
    parts = [safe_host, scheme]
    if port:
        parts.append(str(port))
    parts.append(ts)
    run_dir_name = "-".join(parts)
    out_dir = os.path.join(base_out_dir, run_dir_name)

    logger = Logger(config.get("logging", {}))
    logger.info(f"Scanning {base_url}")
    writers = None

    # Fetch topology/version early
    topo = None
    help_has_ver = False
    try:
        topo_client = GitLabClient(
            base_url=base_url,
            verify_ssl=config["http"]["verify_ssl"],
            timeout_seconds=config.get("execution", {}).get("timeout_seconds", 20),
            rate_limit_rps=config.get("execution", {}).get("rate_limit_rps", 5),
            retries=0,
            backoff={"initial_ms": 100, "max_ms": 1000, "factor": 2.0},
            logger=logger,
        )
        topo = topo_client.fetch_topology()
        # If authenticated later, we will try API version too and update topo
        ver = (topo.get("help") or {}).get("instance_version")
        if ver:
            logger.ver(f"GitLab version {ver}")
            help_has_ver = True
    except Exception as e:
        logger.debug(f"topology fetch error: {e}")
    client = GitLabClient(
        base_url=base_url,
        verify_ssl=config["http"]["verify_ssl"],
        timeout_seconds=config.get("execution", {}).get("timeout_seconds", 20),
        rate_limit_rps=config.get("execution", {}).get("rate_limit_rps", 5),
        retries=config.get("execution", {}).get("retries", 1),
        backoff=config.get("execution", {}).get("backoff", {"initial_ms": 500, "max_ms": 5000, "factor": 2.0}),
        logger=logger,
    )

    # Auth
    if args.token:
        client.set_pat(args.token)
    elif args.username and args.password:
        client.login_session(args.username, args.password)
        if not client.authenticated:
            logger.info("Authentication failed; continuing with public discovery only")
    # If authenticated, try API /version and enrich topo
    api_has_ver = False
    try:
        if topo is None:
            topo = {}
        api_ver = client.api_version()
        if api_ver:
            topo["api_version"] = api_ver
            if not (topo.get("help") or {}).get("instance_version") and api_ver.get("version"):
                logger.ver(f"GitLab version {api_ver.get('version')}")
                api_has_ver = True
    except Exception:
        pass

    # If version still not found, emit yellow WARN with reason
    if not help_has_ver and not api_has_ver:
        if args.token or (args.username and args.password):
            logger.tag("WARN", "version not found: /api/v4/version unavailable and /help did not expose instance_version", "yellow")
        else:
            logger.tag("WARN", "version not found: /help did not expose instance_version; /api/v4/version requires authentication", "yellow")

    # Banners
    if logger.banners:
        logger.banner("discovery mode")

    # Discovery: list projects
    repos_jsonl = None
    repos_snapshot = None

    project_count = 0
    # Discovery progress line
    logger.progress_colored("Discovery: repos=0")
    try:
        for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
            project_count += 1
            record = {
                "project_id": proj.get("id"),
                "path_with_namespace": proj.get("path_with_namespace"),
                "visibility": ("private" if proj.get("visibility") != "public" else "public"),
                "default_branch": proj.get("default_branch"),
                "last_activity_at": proj.get("last_activity_at"),
                "fullpath": f"{base_url}/{proj.get('path_with_namespace')}",
                "ssh_url_to_repo": proj.get("ssh_url_to_repo"),
                "http_url_to_repo": proj.get("http_url_to_repo"),
                "web_url": proj.get("web_url"),
                "name": proj.get("name"),
                "archived": bool(proj.get("archived")),
                "topics": proj.get("topics") or [],
            }
            logger.repo(
                f"id={record['project_id']} path={record['path_with_namespace']} name={record['name']} vis={record['visibility']} branch={record['default_branch']}"
            )
            if writers is None:
                if not os.path.isdir(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                    logger.info(f"Output directory: {out_dir}")
                writers = OutputWriters(out_dir, config.get("output", {}), logger)
                repos_jsonl = writers.jsonl("repos.jsonl")
                repos_snapshot = writers.snapshot("repos.json")
            repos_jsonl.write(record)  # type: ignore
            repos_snapshot.add(record)  # type: ignore
            logger.progress_colored(f"Discovery: repos={project_count}")
    except Exception as e:
        logger.warn(f"Discovery error: {e}")

    if repos_snapshot is not None:
        repos_snapshot.flush()
    else:
        logger.info("No accessible projects found; skipping output directory creation")
    logger.progress_end()
    try:
        logger.sum(f" Discovered {project_count} projects")
    except Exception:
        logger.info(f"Discovered {project_count} projects")
    # Early exit: if nothing discovered, skip remaining stages for this target
    if project_count == 0:
        logger.sum(" Skipping remaining stages: no projects or target unreachable")
        return 0

    # Groups harvesting stage (collect groups/subgroups before users)
    if logger.banners:
        logger.banner("groups harvesting")
    groups_jsonl = None
    groups_snapshot = None
    discovered_group_ids: List[int] = []
    try:
        include_membership = bool(args.token or (args.username and args.password))
        for g in client.iter_groups(include_membership=include_membership):
            if writers is None:
                if not os.path.isdir(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                    logger.info(f"Output directory: {out_dir}")
                writers = OutputWriters(out_dir, config.get("output", {}), logger)
            if groups_jsonl is None:
                groups_jsonl = writers.jsonl("groups.jsonl")
                groups_snapshot = writers.snapshot("groups.json")
            grec = {
                "group_id": g.get("id"),
                "full_path": g.get("full_path"),
                "name": g.get("name"),
                "visibility": g.get("visibility"),
                "web_url": g.get("web_url"),
                "parent_id": g.get("parent_id"),
            }
            logger.group(f"id={grec['group_id']} path={grec['full_path']} vis={grec['visibility']}")
            groups_jsonl.write(grec)  # type: ignore
            groups_snapshot.add(grec)  # type: ignore
            if isinstance(grec["group_id"], int):
                discovered_group_ids.append(grec["group_id"])  # track
            # Subgroups
            try:
                for sg in client.iter_group_subgroups(grec["group_id"]):
                    srec = {
                        "group_id": sg.get("id"),
                        "full_path": sg.get("full_path"),
                        "name": sg.get("name"),
                        "visibility": sg.get("visibility"),
                        "web_url": sg.get("web_url"),
                        "parent_id": sg.get("parent_id"),
                    }
                    logger.group(f"id={srec['group_id']} path={srec['full_path']} vis={srec['visibility']}")
                    groups_jsonl.write(srec)  # type: ignore
                    groups_snapshot.add(srec)  # type: ignore
                    if isinstance(srec["group_id"], int):
                        discovered_group_ids.append(srec["group_id"])  # track
            except Exception as e:
                logger.warn(f"Subgroups fetch error for group {grec['group_id']}: {e}")
    except Exception as e:
        logger.warn(f"Groups harvesting error: {e}")
    if groups_snapshot is not None:
        groups_snapshot.flush()
    try:
        logger.sum(f" Groups stage complete: groups={len(discovered_group_ids)}")
    except Exception:
        pass

    # User harvesting stage
    if logger.banners:
        logger.banner("user harvesting")
    users_snapshot = None
    users_jsonl = None
    users_seen = set()
    users_accum: List[Dict[str, Any]] = []
    def _emit_user(u: Dict[str, Any], source: str, role: str = None) -> None:
        nonlocal users_snapshot, users_jsonl
        key = (u.get("id"), u.get("username"), u.get("name"), u.get("email"), source)
        if key in users_seen:
            return
        users_seen.add(key)
        rec = {
            "user_id": u.get("id"),
            "username": u.get("username"),
            "display_name": u.get("name"),
            "email": u.get("email"),
            "source": [source],
            "role": role,
            "last_seen": u.get("last_sign_in_at") or u.get("last_activity_on"),
            "web_url": u.get("web_url"),
        }
        if writers is None:
            # If no repo results were found earlier, create out_dir now for users
            os.makedirs(out_dir, exist_ok=True)
            logger.info(f"Output directory: {out_dir}")
        if users_snapshot is None:
            users_jsonl = OutputWriters(out_dir, config.get("output", {}), logger).jsonl("users.jsonl")
            users_snapshot = OutputWriters(out_dir, config.get("output", {}), logger).snapshot("users.json")
        logger.user(f"id={rec['user_id']} username={rec['username']} name={rec['display_name']} source={source}")
        users_jsonl.write(rec)  # type: ignore
        users_snapshot.add(rec)  # type: ignore
        users_accum.append(rec)

    

    try:
        # From discovered groups (prefer groups first for better coverage)
        if discovered_group_ids:
            budget_s = int(config.get("execution", {}).get("user_stage_group_budget_seconds", 30))
            deadline = time.time() + max(5, budget_s)
            logger.info("Harvesting group members (from discovered groups)")
            for gid in discovered_group_ids:
                if time.time() > deadline:
                    logger.info("Group member harvesting budget reached; continuing")
                    break
                try:
                    for gm in client.iter_group_members(gid):
                        if time.time() > deadline:
                            break
                        _emit_user(gm, source="group_member", role=gm.get("access_level"))
                except Exception as e:
                    logger.warn(f"Group members error for group {gid}: {e}")
        # Public scrape fallbacks when unauthenticated: scrape HTML for group members
        if not (client.authenticated or args.token) and groups_snapshot is not None:
            try:
                logger.info("Scraping public group members (HTML)")
                # read groups snapshot content
                # we use the snapshot writer path by re-opening the file
                with open(os.path.join(out_dir, "groups.json"), "r", encoding="utf-8") as fh:
                    import json as _json
                    groups_arr = _json.load(fh)
                for g in groups_arr:
                    fp = g.get("full_path")
                    web_url = g.get("web_url") or ""
                    base_override = None
                    try:
                        from urllib.parse import urlparse as _up
                        pu = _up(web_url)
                        if pu.scheme and pu.netloc:
                            base_override = f"{pu.scheme}://{pu.netloc}"
                    except Exception:
                        base_override = None
                    if not fp:
                        continue
                    for m in client.scrape_group_members_html(fp, base_override=base_override):
                        _emit_user(m, source="group_member", role=None)
            except Exception as e:
                logger.warn(f"Public group scrape error: {e}")

        # From project members (API)
        for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
            pid = proj.get("id")
            try:
                for m in client.iter_project_members(pid):
                    _emit_user(m, source="member", role=m.get("access_level"))
            except Exception as e:
                logger.warn(f"Members fetch error for project {pid}: {e}")
        # Public scrape fallbacks for project members when unauthenticated
        if not (client.authenticated or args.token):
            try:
                logger.info("Scraping public project members (HTML)")
                for proj in client.iter_projects(include_membership=False):
                    ns = proj.get("path_with_namespace")
                    web_url = proj.get("web_url") or ""
                    base_override = None
                    try:
                        from urllib.parse import urlparse as _up
                        pu = _up(web_url)
                        if pu.scheme and pu.netloc:
                            base_override = f"{pu.scheme}://{pu.netloc}"
                    except Exception:
                        base_override = None
                    if not ns:
                        continue
                    scraped = list(client.scrape_project_members_html(ns, base_override=base_override))
                    # If HTML static scrape failed, try Selenium fallback (best-effort)
                    if not scraped and web_url:
                        logger.debug(f"Selenium fallback for members: {web_url}")
                        scraped = list(client.scrape_project_members_selenium(web_url))
                    # Attempt API enrichment per username
                    for m in scraped:
                        u = m.get("username")
                        if u:
                            det = client.lookup_user_by_username(u)
                            if det:
                                m["id"] = det.get("id")
                                m["name"] = det.get("name") or m.get("name")
                                m["email"] = det.get("public_email") or m.get("email")
                                m["web_url"] = det.get("web_url") or m.get("web_url")
                        _emit_user(m, source="member", role=None)
            except Exception as e:
                logger.warn(f"Public project scrape error: {e}")
        # From commit authors (name + email only)
        for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
            pid = proj.get("id")
            try:
                commit_limit = 200  # cap to keep stage responsive
                count = 0
                for c in client.iter_project_commits(pid):
                    pseudo = {
                        "id": None,
                        "username": None,
                        "name": c.get("author_name"),
                        "email": c.get("author_email"),
                        "web_url": None,
                        "last_sign_in_at": c.get("committed_date"),
                    }
                    _emit_user(pseudo, source="commit")
                    count += 1
                    if count >= commit_limit:
                        break
            except Exception as e:
                logger.warn(f"Commits fetch error for project {pid}: {e}")
        # Global users if auth available
        if client.authenticated or args.token:
            try:
                for gu in client.iter_users_global():
                    _emit_user(gu, source="api")
            except Exception as e:
                logger.warn(f"Global users fetch error: {e}")
    except Exception as e:
        logger.warn(f"User harvesting error: {e}")

    # If no projects found, skip subsequent stages
    if project_count == 0:
        logger.info("No projects discovered; skipping user harvesting and next stages")
        return 0

    if users_snapshot is not None:
        users_snapshot.flush()
        # Build merged CSV (dedup and enrich across sources)
        def merge_into(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
            for field in ("user_id", "username", "display_name", "email", "role", "last_seen", "web_url"):
                if (dst.get(field) is None or dst.get(field) == "") and src.get(field):
                    dst[field] = src.get(field)

        id_map: Dict[Any, Dict[str, Any]] = {}
        name_map: Dict[str, Dict[str, Any]] = {}
        agg: List[Dict[str, Any]] = []

        for r in users_accum:
            rid = r.get("user_id")
            rname_key = (r.get("display_name") or "").strip().lower()

            target = None
            if rid is not None and rid in id_map:
                target = id_map[rid]
            elif rname_key and rname_key in name_map:
                target = name_map[rname_key]

            if target is None:
                # create new aggregate record
                target = {
                    "user_id": r.get("user_id"),
                    "username": r.get("username"),
                    "display_name": r.get("display_name"),
                    "email": r.get("email"),
                    "role": r.get("role"),
                    "last_seen": r.get("last_seen"),
                    "web_url": r.get("web_url"),
                }
                agg.append(target)
                if rid is not None:
                    id_map[rid] = target
                if rname_key:
                    name_map[rname_key] = target
            else:
                merge_into(target, r)
                # Ensure both maps point to the unified object
                if rid is not None:
                    id_map[rid] = target
                if rname_key:
                    name_map[rname_key] = target

        csv_path = os.path.join(out_dir, "users.csv")
        os.makedirs(out_dir, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["user_id", "username", "display_name", "email", "role", "last_seen", "web_url"],
            )
            writer.writeheader()
            for row in agg:
                writer.writerow(row)
        logger.sum(f" Users stage complete: {len(agg)} unique; CSV written")

    # (removed duplicate groups harvesting; groups are already collected after Discovery)

    # Shared scan config for secrets/files
    max_size = int((config.get("scan", {}) or {}).get("max_file_size_bytes", 104857600))
    binary_exts = set((config.get("scan", {}) or {}).get("binary_extensions", []))

    def is_binary_by_ext(path: str) -> bool:
        lower = path.lower()
        for ext in binary_exts:
            if lower.endswith(ext.lower()):
                return True
        return False

    # Files stage moved below secrets

    # Secrets harvesting stage (banner only for now)
    if logger.banners:
        logger.banner("harvesting secrets")

    # Load rules
    rules: List[Dict[str, Any]] = []
    try:
        primary_rules = rules_yaml or os.path.join("config", "rules.yaml")
        with open(primary_rules, "r", encoding="utf-8") as rf:
            ry = yaml.safe_load(rf) or {}
            rules = ry.get("rules") or []
    except Exception as e:
        logger.warn(f"Failed to load rules from {primary_rules}: {e}")
        # Fallback to merged rules if present
        try:
            fallback_rules = os.path.join("config", "rules_merged.yaml")
            with open(fallback_rules, "r", encoding="utf-8") as rf2:
                ry2 = yaml.safe_load(rf2) or {}
                rules = ry2.get("rules") or []
                logger.info("Loaded rules from config/rules_merged.yaml")
        except Exception as e2:
            logger.warn(f"Failed to load fallback rules: {e2}")
            rules = []

    import re
    compiled_rules: List[Tuple[str, re.Pattern]] = []
    for r in rules:
        rid = str(r.get("id") or r.get("name") or "rule")
        pat = r.get("pattern")
        if not pat:
            continue
        try:
            rx = re.compile(pat, re.MULTILINE)
            compiled_rules.append((rid, rx))
        except Exception as e:
            logger.warn(f"Invalid regex for rule {rid}: {e}")

    # Writers for secrets
    secrets_jsonl = writers.jsonl("secrets.jsonl")
    secrets_snapshot = writers.snapshot("secrets.json")

    # Entropy calc
    from math import log2
    def shannon_entropy(s: str) -> float:
        if not s:
            return 0.0
        freq = {}
        for ch in s:
            freq[ch] = freq.get(ch, 0) + 1
        n = len(s)
        return -sum((c / n) * log2(c / n) for c in freq.values())

    min_entropy = float((config.get("scan", {}) or {}).get("min_entropy_for_reporting", 3.5))
    dedup: set = set()
    total_findings = 0
    secrets_files_scanned = 0

    # Start secrets progress line
    logger.progress_colored("Secrets: findings=0 files_scanned~0")

    for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
        pid = proj.get("id")
        default_branch = proj.get("default_branch") or "main"
        visibility = ("private" if proj.get("visibility") != "public" else "public")
        repo_path = proj.get("path_with_namespace")
        proj_findings = 0
        try:
            for node in client.iter_repository_tree(pid, ref=default_branch, recursive=True):
                if node.get("type") != "blob":
                    continue
                path = node.get("path") or node.get("name")
                if not path:
                    continue
                # skip binaries and large
                size = None
                try:
                    meta = client.get_blob_meta(pid, node.get("id"))
                    size = meta.get("size")
                except Exception:
                    pass
                if size is not None and int(size) > max_size:
                    continue
                if is_binary_by_ext(path):
                    continue
                # fetch content
                try:
                    raw = client.get_file_raw(pid, path, default_branch)
                except Exception:
                    continue
                # decode
                text = None
                for enc in ("utf-8", "latin-1"):
                    try:
                        text = raw.decode(enc)
                        break
                    except Exception:
                        continue
                if text is None:
                    continue
                lines = text.splitlines()
                secrets_files_scanned += 1
                for ln, line in enumerate(lines, start=1):
                    for rid, rx in compiled_rules:
                        try:
                            for m in rx.finditer(line):
                                match_txt = m.group(0)
                                ent = shannon_entropy(match_txt)
                                if ent < min_entropy and any(ch.isalpha() for ch in match_txt):
                                    # low entropy, but keep if rule likely keyword-based; still record
                                    pass
                                key = (pid, path, ln, rid, match_txt)
                                if key in dedup:
                                    continue
                                dedup.add(key)
                                rec = {
                                    "path": path,
                                    "line": ln,
                                    "rule_id": rid,
                                    "match": match_txt,
                                    "line_text": line.strip()[:1000],
                                    "entropy": round(ent, 2),
                                    "repo": repo_path,
                                    "project_id": pid,
                                    "source": "HEAD",
                                    "web_url": f"{base_url}/{repo_path}/-/blob/{default_branch}/{path}#L{ln}",
                                    "raw_url": f"{client.api}/projects/{pid}/repository/files/{path}/raw?ref={default_branch}",
                                    "fullpath": f"{base_url}/{repo_path}/-/blob/{default_branch}/{path}",
                                    "visibility": visibility,
                                }
                                secrets_jsonl.write(rec)
                                secrets_snapshot.add(rec)
                                proj_findings += 1
                                total_findings += 1
                                logger.progress_colored(f"Secrets: findings={total_findings} files_scanned~{secrets_files_scanned}")
                        except Exception:
                            continue
        except Exception as e:
            logger.warn(f"Secrets scan error for project {pid}: {e}")
        if proj_findings:
            logger.info(f"Secrets in {repo_path}: findings={proj_findings}")

    logger.progress_end()
    secrets_snapshot.flush()
    logger.sum(f" Secrets stage complete: findings={total_findings}")

    # Files harvesting stage (after secrets)
    if logger.banners:
        logger.banner("files harvesting")
    if writers is None:
        os.makedirs(out_dir, exist_ok=True)
        logger.info(f"Output directory: {out_dir}")
        writers = OutputWriters(out_dir, config.get("output", {}), logger)
    files_jsonl = writers.jsonl("files.jsonl")
    files_snapshot = writers.snapshot("files.json")
    skipped_jsonl = writers.jsonl("skipped.jsonl")
    interesting_jsonl = writers.jsonl("interesting.jsonl")
    import re
    interesting_exts = set((config.get("scan", {}) or {}).get("interesting_extensions", []))
    fname_patterns = (config.get("scan", {}) or {}).get("file_name_patterns", [])
    compiled_fname_patterns = [re.compile(p) for p in fname_patterns]

    def is_interesting_name(path: str) -> bool:
        for rx in compiled_fname_patterns:
            if rx.search(path):
                return True
        for ext in interesting_exts:
            if path.lower().endswith(ext.lower()):
                return True
        return False

    total_files = 0
    total_skipped = 0
    total_interesting = 0
    for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
        pid = proj.get("id")
        default_branch = proj.get("default_branch") or "main"
        proj_files = 0
        proj_skipped = 0
        proj_interesting = 0
        try:
            for node in client.iter_repository_tree(pid, ref=default_branch, recursive=True):
                if node.get("type") != "blob":
                    continue
                path = node.get("path") or node.get("name")
                if not path:
                    continue
                size = None
                try:
                    meta = client.get_blob_meta(pid, node.get("id"))
                    size = meta.get("size")
                except Exception:
                    pass
                if size is not None and int(size) > max_size:
                    skipped_jsonl.write({
                        "repo": proj.get("path_with_namespace"),
                        "path": path,
                        "reason": "too_large",
                        "size": int(size),
                        "raw_url": f"{client.api}/projects/{pid}/repository/files/{path}/raw?ref={default_branch}",
                        "web_url": f"{base_url}/{proj.get('path_with_namespace')}/-/blob/{default_branch}/{path}",
                    })
                    proj_skipped += 1
                    total_skipped += 1
                    continue
                if is_binary_by_ext(path):
                    skipped_jsonl.write({
                        "repo": proj.get("path_with_namespace"),
                        "path": path,
                        "reason": "binary_ext",
                        "size": size,
                        "raw_url": f"{client.api}/projects/{pid}/repository/files/{path}/raw?ref={default_branch}",
                        "web_url": f"{base_url}/{proj.get('path_with_namespace')}/-/blob/{default_branch}/{path}",
                    })
                    proj_skipped += 1
                    total_skipped += 1
                    continue
                rec = {
                    "project_id": pid,
                    "repo": proj.get("path_with_namespace"),
                    "path": path,
                    "size": size,
                    "ref": default_branch,
                    "web_url": f"{base_url}/{proj.get('path_with_namespace')}/-/blob/{default_branch}/{path}",
                    "raw_url": f"{client.api}/projects/{pid}/repository/files/{path}/raw?ref={default_branch}",
                    "interesting_name": is_interesting_name(path),
                }
                files_jsonl.write(rec)  # type: ignore
                files_snapshot.add(rec)  # type: ignore
                proj_files += 1
                total_files += 1
                if rec["interesting_name"]:
                    interesting_jsonl.write(rec)  # type: ignore
                    proj_interesting += 1
                    total_interesting += 1
                logger.progress_colored(f"Files: scanned={total_files} interesting={total_interesting} skipped={total_skipped}")
        except Exception as e:
            logger.warn(f"File listing error for project {pid}: {e}")
        logger.info(
            f"Files for {proj.get('path_with_namespace')}: scanned={proj_files} interesting={proj_interesting} skipped={proj_skipped}"
        )

    if files_snapshot is not None:
        files_snapshot.flush()
    logger.progress_end()
    logger.sum(f" Files stage complete: scanned={total_files} interesting={total_interesting} skipped={total_skipped}")
    # Commit history scanning (optional)
    scan_history_enabled = True if getattr(args, "scan_history", True) else False
    if scan_history_enabled:
        if logger.banners:
            logger.banner("history harvesting")
        history_findings = 0
        history_dedup: set = set()
        # Build HEAD dedup for intelligent suppression (same project+path+line+rule+match)
        head_keys = set(dedup)
        # Limit history budget to avoid very long runs
        history_budget_s = int(config.get("execution", {}).get("history_budget_seconds", 120))
        history_deadline = time.time() + max(30, history_budget_s)
        history_files_scanned = 0
        for proj in client.iter_projects(include_membership=bool(args.token or (args.username and args.password))):
            if time.time() > history_deadline:
                logger.info("History budget reached; stopping")
                break
            pid = proj.get("id")
            repo_path = proj.get("path_with_namespace")
            default_branch = proj.get("default_branch") or "main"
            try:
                commit_cap = int(config.get("scan", {}).get("history_commit_cap", 500))
                count = 0
                for c in client.iter_project_commits(pid):
                    if time.time() > history_deadline:
                        break
                    sha = c.get("id") or c.get("sha")
                    if not sha:
                        continue
                    count += 1
                    if count > commit_cap:
                        break
                    try:
                        for d in client.iter_commit_diffs(pid, sha):
                            if time.time() > history_deadline:
                                break
                            # d has: old_path, new_path, diff (unified), new_file, renamed_file, deleted_file
                            path = d.get("new_path") or d.get("old_path")
                            diff = d.get("diff") or ""
                            if not path or not diff:
                                continue
                            if is_binary_by_ext(path):
                                continue
                            history_files_scanned += 1
                            # Iterate added lines only: lines starting with '+' but not '+++'
                            for line in diff.splitlines():
                                if not line.startswith('+') or line.startswith('+++'):
                                    continue
                                text_line = line[1:]
                                for rid, rx in compiled_rules:
                                    try:
                                        for m in rx.finditer(text_line):
                                            match_txt = m.group(0)
                                            ent = shannon_entropy(match_txt)
                                            if ent < min_entropy and any(ch.isalpha() for ch in match_txt):
                                                pass
                                            key = (pid, path, None, rid, match_txt)
                                            # If exact same found in HEAD (same path+rule+match+line) suppress; we don't know exact HEAD line from diff, so suppress on path+rule+match only
                                            head_key_relaxed = (pid, path, rid, match_txt)
                                            if (pid, path, None, rid, match_txt) in history_dedup:
                                                continue
                                            # relaxed head suppression
                                            if any(k[0] == pid and k[1] == path and k[3] == rid and k[4] == match_txt for k in head_keys):
                                                continue
                                            history_dedup.add(key)
                                            rec = {
                                                "path": path,
                                                "line": None,
                                                "rule_id": rid,
                                                "match": match_txt,
                                                "line_text": text_line[:1000],
                                                "entropy": round(ent, 2),
                                                "repo": repo_path,
                                                "project_id": pid,
                                                "source": "HISTORY",
                                                "commit": sha,
                                                "web_url": f"{base_url}/{repo_path}/-/commit/{sha}",
                                                "raw_url": None,
                                                "fullpath": f"{base_url}/{repo_path}/-/commit/{sha}",
                                                "visibility": ("private" if proj.get("visibility") != "public" else "public"),
                                            }
                                            secrets_jsonl.write(rec)
                                            secrets_snapshot.add(rec)
                                            history_findings += 1
                                            logger.progress_colored(f"History: findings={history_findings} files_scanned~{history_files_scanned}")
                                    except Exception:
                                        continue
                    except Exception as e:
                        logger.warn(f"Commit diffs error for project {pid} @ {sha}: {e}")
            except Exception as e:
                logger.warn(f"History scan error for project {pid}: {e}")
        logger.progress_end()
        secrets_snapshot.flush()
        logger.sum(f" History stage complete: findings={history_findings}")

    # Generate HTML report at end
    try:
        report_path = generate_html_report(out_dir)
        logger.info(f"Report written: {report_path}")
    except Exception as e:
        logger.warn(f"Report generation failed: {e}")

    return 0


