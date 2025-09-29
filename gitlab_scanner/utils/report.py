from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _load_json(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def _load_jsonl(path: str, max_lines: Optional[int] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
                if max_lines is not None and i + 1 >= max_lines:
                    break
    except Exception:
        pass
    return rows


def _merge_users(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    id_map: Dict[Any, Dict[str, Any]] = {}
    name_map: Dict[str, Dict[str, Any]] = {}
    user_map: Dict[str, Dict[str, Any]] = {}
    merged: List[Dict[str, Any]] = []

    def merge_into(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
        for field in ("user_id", "id", "username", "display_name", "name", "email", "role", "last_seen", "web_url"):
            dv = dst.get(field)
            sv = src.get(field)
            if (dv is None or dv == "") and sv:
                dst[field] = sv

    for u in users:
        uid = u.get("user_id") or u.get("id")
        uname = (u.get("username") or "").strip()
        dname_key = (u.get("display_name") or u.get("name") or "").strip().lower()

        target: Optional[Dict[str, Any]] = None
        if uid is not None and uid in id_map:
            target = id_map[uid]
        elif uname and uname.lower() in user_map:
            target = user_map[uname.lower()]
        elif dname_key and dname_key in name_map:
            target = name_map[dname_key]

        if target is None:
            target = {
                "user_id": uid,
                "username": uname or None,
                "display_name": u.get("display_name") or u.get("name"),
                "email": u.get("email"),
                "role": u.get("role"),
                "last_seen": u.get("last_seen"),
                "web_url": u.get("web_url"),
            }
            merged.append(target)
        else:
            merge_into(target, u)

        if uid is not None:
            id_map[uid] = target
        if uname:
            user_map[uname.lower()] = target
        if dname_key:
            name_map[dname_key] = target

    return merged


def generate_html_report(out_dir: str) -> str:
    # Load data
    repos = _load_json(os.path.join(out_dir, "repos.json"))
    users_raw = _load_json(os.path.join(out_dir, "users.json"))
    users = _merge_users(users_raw)
    secrets = _load_json(os.path.join(out_dir, "secrets.json"))
    files = _load_json(os.path.join(out_dir, "files.json"))
    interesting = _load_jsonl(os.path.join(out_dir, "interesting.jsonl"))

    # Summaries
    repos_public = sum(1 for r in repos if (r.get("visibility") == "public"))
    repos_private = sum(1 for r in repos if (r.get("visibility") != "public"))
    total_repos = len(repos)
    total_users = len(users)
    total_secrets = len(secrets)
    total_files = len(files)
    total_interesting = len(interesting)

    # Build HTML
    html_path = os.path.join(out_dir, "report.html")
    html = """
<!DOCTYPE html>
<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\"/>\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
<title>GitLab Scan Report</title>
<link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/modern-css-reset/dist/reset.min.css\"/>
<script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
<style>
 body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif; padding: 16px; color: #222; }}
 h1 {{ margin: 0 0 12px; }}
 .summary {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin: 12px 0 24px; }}
 .card {{ background: #f8f9fb; border: 1px solid #e3e6ef; border-radius: 8px; padding: 12px; }}
 .card .num {{ font-size: 1.6rem; font-weight: 700; }}
 .section {{ margin: 18px 0; }}
 details {{ border: 1px solid #e3e6ef; border-radius: 8px; padding: 10px 12px; background: #fff; }}
 summary {{ font-weight: 700; cursor: pointer; }}
 .toolbar {{ display:flex; gap:8px; align-items:center; margin: 8px 0 12px; }}
 input[type='search'] {{ padding:6px 8px; border:1px solid #cdd3e0; border-radius:6px; width: 280px; }}
 table {{ width: 100%; border-collapse: collapse; }}
 th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #eee; }}
 th {{ cursor: pointer; position: sticky; top: 0; background: #fafbff; }}
 .muted {{ color:#666; font-size: 0.9rem; }}
 .sticky-top {{ position: sticky; top: 0; background: #fff; z-index: 10; }}
 #repoPie {{ width: 200px; height: 200px; max-width: 200px; max-height: 200px; margin: 8px auto 16px; display: block; }}
</style>
</head>
<body>
  <h1>GitLab Scan Report</h1>
  <div class=\"summary\">
    <div class=\"card\"><div class=\"muted\">Repositories</div><div class=\"num\">{total_repos}</div></div>
    <div class=\"card\"><div class=\"muted\">Users</div><div class=\"num\">{total_users}</div></div>
    <div class=\"card\"><div class=\"muted\">Secrets</div><div class=\"num\">{total_secrets}</div></div>
    <div class=\"card\"><div class=\"muted\">Files</div><div class=\"num\">{total_files}</div></div>
    <div class=\"card\"><div class=\"muted\">Interesting files</div><div class=\"num\">{total_interesting}</div></div>
  </div>
  <canvas id=\"repoPie\"></canvas>
  <script>
    const ctx = document.getElementById('repoPie').getContext('2d');
    new Chart(ctx, {{ type: 'pie', data: {{ labels:['Public','Private'], datasets:[{{ data:[{repos_public},{repos_private}], backgroundColor:['#34c759','#ff3b30'] }}] }}, options: {{ responsive: false, plugins: {{ legend: {{ position:'bottom' }} }} }} }});
  </script>

  {repos_section}
  {users_section}
  {secrets_head_section}
  {secrets_hist_section}
  {interesting_section}
  {files_section}

  <script>
    function bindTable(tableId, searchId) {{
      const table = document.getElementById(tableId);
      const search = document.getElementById(searchId);
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      search.addEventListener('input', () => {{
        const q = search.value.toLowerCase();
        rows.forEach(tr => {{
          const txt = tr.innerText.toLowerCase();
          tr.style.display = txt.includes(q) ? '' : 'none';
        }});
      }});
      table.querySelectorAll('th').forEach((th, idx) => {{
        let asc = true;
        th.addEventListener('click', () => {{
          const visible = rows.filter(r => r.style.display !== 'none');
          visible.sort((a,b)=>{{
            const ta = a.children[idx].innerText.toLowerCase();
            const tb = b.children[idx].innerText.toLowerCase();
            if (ta < tb) return asc ? -1 : 1; if (ta>tb) return asc ? 1 : -1; return 0;
          }});
          asc = !asc;
          visible.forEach(r=>tbody.appendChild(r));
        }});
      }});
    }}
    ['reposTable','usersTable','secretsTable','interestingTable','filesTable'].forEach(id => bindTable(id, id+'Search'));
  </script>
</body>
</html>
"""

    # Helper to render each section with search and table
    # We build it as a format-time function to keep code concise
    def render_section(title: str, table_id: str, columns: List[str], rows: List[Dict[str, Any]]) -> str:
        # Build header
        thead = "".join(f"<th>{col}</th>" for col in columns)
        # Build body
        body_rows = []
        for r in rows:
            tds = []
            for col in columns:
                v = r.get(col)
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v)
                if v is None:
                    v = ""
                cell = str(v)
                # Linkify web_url columns
                if col in ("web_url", "fullpath") and v:
                    cell = f"<a href=\"{v}\" target=\"_blank\">{v}</a>"
                tds.append(f"<td>{cell}</td>")
            body_rows.append(f"<tr>{''.join(tds)}</tr>")
        tbody = "".join(body_rows)
        return f"""
        <div class=\"section\">
          <details open>
            <summary>{title}</summary>
            <div class=\"toolbar\">
              <input id=\"{table_id}Search\" type=\"search\" placeholder=\"Search {title}\" />
            </div>
            <div style=\"overflow:auto; max-height: 520px; border:1px solid #f0f1f5; border-radius:6px;\">
              <table id=\"{table_id}\">
                <thead class=\"sticky-top\"><tr>{thead}</tr></thead>
                <tbody>{tbody}</tbody>
              </table>
            </div>
          </details>
        </div>
        """

    # Prepare sections
    repos_section = render_section('Repositories', 'reposTable', ['project_id','path_with_namespace','visibility','default_branch','last_activity_at','web_url'], repos)
    users_section = render_section('Users', 'usersTable', ['user_id','username','display_name','email','web_url'], users)
    # Split secrets by source
    secrets_head = [s for s in secrets if (s.get('source') or 'HEAD') != 'HISTORY']
    secrets_hist = [s for s in secrets if (s.get('source') or '') == 'HISTORY']
    secrets_head_section = render_section('Secrets (HEAD)', 'secretsTable', ['project_id','repo','path','line','rule_id','match','web_url'], secrets_head)
    secrets_hist_section = render_section('Secrets (history commits)', 'secretsHistoryTable', ['project_id','repo','path','line','rule_id','match','web_url'], secrets_hist) if secrets_hist else ''
    interesting_section = render_section('Interesting files', 'interestingTable', ['project_id','repo','path','ref','web_url'], interesting)
    files_section = render_section('All files', 'filesTable', ['project_id','repo','path','size','ref','web_url'], files)

    # Fill values
    html = html.format(
        repos_public=repos_public,
        repos_private=repos_private,
        total_repos=total_repos,
        total_users=total_users,
        total_secrets=total_secrets,
        total_files=total_files,
        total_interesting=total_interesting,
        repos_section=repos_section,
        users_section=users_section,
        secrets_head_section=secrets_head_section,
        secrets_hist_section=secrets_hist_section,
        interesting_section=interesting_section,
        files_section=files_section,
    )

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return html_path


