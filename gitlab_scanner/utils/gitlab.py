from __future__ import annotations

import time
from typing import Any, Dict, Generator, Iterable, Optional
from urllib.parse import quote

import requests

from .logging import Logger


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        verify_ssl: bool,
        timeout_seconds: int,
        rate_limit_rps: float,
        retries: int,
        backoff: Dict[str, Any],
        logger: Logger,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v4"
        self.verify = verify_ssl
        self.timeout = timeout_seconds
        self.rps = max(0.1, float(rate_limit_rps))
        self.retries = int(retries)
        self.backoff = backoff
        self.logger = logger
        self.session = requests.Session()
      # Set a reasonable browser-like user agent to avoid overly strict blocks on HTML endpoints
        try:
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
        except Exception:
            pass
        self._next_ts = 0.0
        self.authenticated = False

    def _throttle(self) -> None:
        now = time.time()
        if now < self._next_ts:
            time.sleep(self._next_ts - now)
        self._next_ts = time.time() + (1.0 / self.rps)

    def _req(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.api}{path}"
        attempt = 0
        while True:
            self._throttle()
            try:
                resp = self.session.request(method, url, timeout=self.timeout, verify=self.verify, **kwargs)
            except requests.RequestException as e:
                if attempt >= self.retries:
                    raise
                self._sleep_backoff(attempt)
                attempt += 1
                continue

            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt >= self.retries:
                    resp.raise_for_status()
                self._sleep_backoff(attempt)
                attempt += 1
                continue

            return resp

    def _sleep_backoff(self, attempt: int) -> None:
        base = float(self.backoff.get("initial_ms", 500)) / 1000.0
        factor = float(self.backoff.get("factor", 2.0))
        max_s = float(self.backoff.get("max_ms", 5000)) / 1000.0
        delay = min(max_s, base * (factor ** attempt))
        try:
            self.logger.debug(f"backoff sleep {delay:.2f}s (attempt {attempt+1})")
        except Exception:
            pass
        time.sleep(delay)

    def fetch_topology(self) -> Dict[str, Any]:
        topo: Dict[str, Any] = {"headers": {}, "help": {}}
        # Headers from root
        try:
            r = self.session.get(self.base_url + "/", timeout=self.timeout, verify=self.verify, allow_redirects=False)
            topo["headers"] = dict(r.headers)
        except Exception:
            pass
        # Help page parse
        try:
            r = self.session.get(self.base_url + "/help", timeout=self.timeout, verify=self.verify)
            if r.ok:
                text = r.text
                import re, json as _json
                # Try to capture the full snowplowStandardContext JSON (with or without gl. prefix) using balanced braces
                mstart = re.search(r"(?:gl\.)?snowplowStandardContext\s*=", text, re.IGNORECASE)
                parsed_ctx = False
                if mstart:
                    brace_pos = text.find("{", mstart.end())
                    if brace_pos != -1:
                        depth = 0
                        end_pos = None
                        for i in range(brace_pos, len(text)):
                            ch = text[i]
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end_pos = i + 1
                                    break
                        if end_pos:
                            raw = text[brace_pos:end_pos]
                            try:
                                ctx = _json.loads(raw)
                                data = (ctx.get("data") or {}) if isinstance(ctx, dict) else {}
                                topo.setdefault("help", {}).update({
                                    "environment": data.get("environment"),
                                    "plan": data.get("plan"),
                                    "realm": data.get("realm"),
                                    "instance_id": data.get("instance_id"),
                                    "unique_instance_id": data.get("unique_instance_id"),
                                    "host_name": data.get("host_name"),
                                    "instance_version": data.get("instance_version"),
                                })
                                parsed_ctx = True
                            except Exception:
                                parsed_ctx = False
                # Fallbacks (and also run if parsed_ctx but version still missing)
                if not parsed_ctx or not (topo.get("help") or {}).get("instance_version"):
                    m = re.search(r"instance_version[\"']\s*:\s*[\"']([^\"']+)[\"']", text, re.IGNORECASE)
                    if m:
                        topo.setdefault("help", {})["instance_version"] = m.group(1)
                if not parsed_ctx or not (topo.get("help") or {}).get("plan"):
                    m2 = re.search(r"\bplan[\"']\s*:\s*[\"']([\w-]+)[\"']", text, re.IGNORECASE)
                    if m2:
                        topo.setdefault("help", {})["plan"] = m2.group(1)
                if not parsed_ctx or not (topo.get("help") or {}).get("environment"):
                    m3 = re.search(r"\benvironment[\"']\s*:\s*[\"']([\w-]+)[\"']", text, re.IGNORECASE)
                    if m3:
                        topo.setdefault("help", {})["environment"] = m3.group(1)
                if not parsed_ctx or not (topo.get("help") or {}).get("host_name"):
                    m4 = re.search(r"host_name[\"']\s*:\s*[\"']([^\"']+)[\"']", text, re.IGNORECASE)
                    if m4:
                        topo.setdefault("help", {})["host_name"] = m4.group(1)
        except Exception:
            pass
        return topo

    def api_version(self) -> Dict[str, Any] | None:
        try:
            r = self._req("GET", "/version")
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            return None

    def set_pat(self, token: str) -> None:
        self.session.headers.update({"PRIVATE-TOKEN": token})
        self.logger.info("Using PAT authentication")

    def login_session(self, username: str, password: str) -> None:
        # Web login to capture session cookie using authenticity_token
        self.logger.info("Logging in with username/password session")
        r = self._req("GET", f"{self.base_url}/users/sign_in")
        r.raise_for_status()
        html = r.text
        token = None
        # Try meta csrf-token
        import re
        m = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if m:
            token = m.group(1)
        if not token:
            # Try authenticity_token hidden input
            m = re.search(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if m:
                token = m.group(1)
        headers = {}
        data = {"user[login]": username, "user[password]": password}
        if token:
            headers["X-CSRF-Token"] = token
            data["authenticity_token"] = token
        r2 = self._req("POST", f"{self.base_url}/users/sign_in", data=data, headers=headers, allow_redirects=True)
        # If login succeeded, GitLab typically redirects and sets _gitlab_session cookie
        if "_gitlab_session" in self.session.cookies.get_dict() or "_gitlab_session" in r2.cookies.get_dict():
            # Verify via API
            if self.is_authenticated():
                self.logger.debug("Session established")
                self.authenticated = True
            else:
                self.logger.auth("Login failed (session not authenticated)")
                self.authenticated = False
        else:
            self.logger.auth("Login failed (no session cookie)")
            self.authenticated = False

    def is_authenticated(self) -> bool:
        resp = self._req("GET", "/user")
        if resp.status_code == 200:
            return True
        return False

    def _iter_projects_page(self, params: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        p = dict(params)
        p.update({"page": page, "per_page": per_page})
        while True:
            resp = self._req("GET", "/projects", params=p)
            if resp.status_code == 401:
                self.logger.warn("Unauthorized while listing projects")
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            p["page"] = page

    def iter_projects(self, include_membership: bool = False) -> Generator[Dict[str, Any], None, None]:
        seen = set()
        # First: membership (private and internal the user is member of)
        if include_membership:
            for item in self._iter_projects_page({"simple": True, "membership": True}):
                pid = item.get("id")
                if pid in seen:
                    continue
                seen.add(pid)
                yield item
        # Then: all public accessible projects
        for item in self._iter_projects_page({"simple": True, "visibility": "public"}):
            pid = item.get("id")
            if pid in seen:
                continue
            seen.add(pid)
            yield item

    def iter_project_members(self, project_id: int) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/projects/{project_id}/members/all", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page

    def iter_project_commits(self, project_id: int) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/projects/{project_id}/repository/commits", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page

    def iter_commit_diffs(self, project_id: int, commit_sha: str) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/projects/{project_id}/repository/commits/{commit_sha}/diff", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page

    def iter_users_global(self) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/users", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page

    def iter_repository_tree(self, project_id: int, ref: str, recursive: bool = True) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page, "ref": ref, "recursive": recursive}
        while True:
            resp = self._req("GET", f"/projects/{project_id}/repository/tree", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                # item: {id (sha for blob), name, type: 'blob'|'tree', path, mode}
                yield item
            page += 1
            params["page"] = page

    def get_blob_meta(self, project_id: int, blob_sha: str) -> Dict[str, Any]:
        resp = self._req("GET", f"/projects/{project_id}/repository/blobs/{blob_sha}")
        resp.raise_for_status()
        return resp.json()

    def get_file_raw(self, project_id: int, path: str, ref: str) -> bytes:
        enc = quote(path, safe="/")
        resp = self._req("GET", f"/projects/{project_id}/repository/files/{enc}/raw", params={"ref": ref})
        if resp.status_code == 401:
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.content

    # HTML fallbacks for public instances where API members endpoints are restricted
    def _extract_usernames_from_members_html(self, html: str) -> Iterable[str]:
        import re
        # Strip scripts/styles to avoid JSON-LD (@context/@type)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        usernames = set()
        # Prefer explicit data attributes
        for rx in (
            r'data-username="([A-Za-z0-9_.-]+)"',
            r'data-user-username="([A-Za-z0-9_.-]+)"',
        ):
            for m in re.findall(rx, html):
                usernames.add(m)
        # Common profile hrefs
        for rx in (
             # relative profile links
            r'href="/(?!groups/|users/|projects/|explore|help|admin|profile|dashboard|oauth|sign(?:in|out)|-/)@?([A-Za-z0-9_.-]+)"',
            r'data-test-selector="member_link"[^>]*href="/(?:@)?([A-Za-z0-9_.-]+)"',
            # absolute profile links on canonical host
            r'href="https?://[^/]+/(?:@)?([A-Za-z0-9_.-]+)"',
        ):
            for m in re.findall(rx, html):
                if isinstance(m, tuple):
                    usernames.add(m[0])
                else:
                    usernames.add(m)
        # Light-weight fallback on @mentions inside table
        table_match = re.search(r"<table[\s\S]*?</table>", html, re.IGNORECASE)
        segment = table_match.group(0) if table_match else html
        for m in re.findall(r"@([A-Za-z0-9][A-Za-z0-9_.-]{1,})", segment):
            usernames.add(m)
        # Filter obvious false positives
        blacklist = {"context", "type", "public", "about", "explore", "help", "admin", "profile", "dashboard", "oauth"}
        return [u for u in usernames if u and u.lower() not in blacklist]

    def scrape_project_members_html(self, path_with_namespace: str, base_override: Optional[str] = None) -> Iterable[Dict[str, Any]]:
        try:
            base = (base_override or self.base_url).rstrip("/")
            url = f"{base}/{path_with_namespace}/-/project_members"
            r = self.session.get(url, timeout=self.timeout, verify=self.verify)
            if not r.ok:
                return []
            html = r.text
            out = []
            for u in self._extract_usernames_from_members_html(html):
                out.append({"id": None, "username": u, "name": None, "email": None, "web_url": f"{self.base_url}/{u}"})
            return out
        except Exception:
            return []

    def scrape_group_members_html(self, full_path: str, base_override: Optional[str] = None) -> Iterable[Dict[str, Any]]:
        try:
            base = (base_override or self.base_url).rstrip("/")
            url = f"{base}/groups/{full_path}/-/group_members"
            r = self.session.get(url, timeout=self.timeout, verify=self.verify)
            if not r.ok:
                return []
            html = r.text
            out = []
            for u in self._extract_usernames_from_members_html(html):
                out.append({"id": None, "username": u, "name": None, "email": None, "web_url": f"{self.base_url}/{u}"})
            return out
        except Exception:
            return []

    def lookup_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._req("GET", f"/users", params={"username": username})
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                return r.json()[0]
            # fallback search
            r2 = self._req("GET", f"/users", params={"search": username})
            if r2.status_code == 200 and isinstance(r2.json(), list) and r2.json():
                return r2.json()[0]
        except Exception:
            return None
        return None

    # Optional Selenium fallback when static HTML does not include members (JS-rendered UIs)
    def scrape_project_members_selenium(self, project_web_url: str) -> Iterable[Dict[str, Any]]:
        try:
            from selenium import webdriver  # type: ignore
            from selenium.webdriver.chrome.options import Options  # type: ignore
            from selenium.webdriver.chrome.service import Service  # type: ignore
            from selenium.webdriver.common.by import By  # type: ignore
            from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
        except Exception:
            return []
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1200,900")
            opts.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
        except Exception:
            return []
        try:
            driver.get(project_web_url.rstrip('/') + "/-/project_members")
            # simple wait
            import time as _t
            _t.sleep(1.2)
            users = {}
            # Try to extract visible usernames and names
            for css in ['a[data-username]', '[data-test-selector="user_link"]', '[data-user-username]']:
                for el in driver.find_elements(By.CSS_SELECTOR, css):
                    uname = (el.get_attribute("data-username") or el.get_attribute("data-user-username") or "").strip()
                    if not uname:
                        continue
                    dname = (el.text or "").strip()
                    if not dname or dname.startswith("@") or dname == uname:
                        # look in same row for a human-readable name
                        try:
                            row = el.find_element(By.XPATH, './ancestor::tr[1]')
                            for c in row.find_elements(By.CSS_SELECTOR, 'a, span, strong, div'):
                                t = (c.text or "").strip()
                                if t and not t.startswith("@") and t.lower() not in {uname.lower(), "public"} and len(t) > 1:
                                    dname = t
                                    break
                        except Exception:
                            pass
                    if uname and uname not in users:
                        users[uname] = dname
            out = []
            for u, dn in users.items():
                out.append({"id": None, "username": u, "name": dn, "email": None, "web_url": f"{self.base_url}/{u}"})
            return out
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def _iter_groups_page(self, params: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        p = dict(params)
        p.update({"page": page, "per_page": per_page})
        while True:
            resp = self._req("GET", "/groups", params=p)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            p["page"] = page

    def iter_groups(self, include_membership: bool = False) -> Generator[Dict[str, Any], None, None]:
        seen = set()
        if include_membership:
            for g in self._iter_groups_page({"membership": True}):
                gid = g.get("id")
                if gid in seen:
                    continue
                seen.add(gid)
                yield g
        for g in self._iter_groups_page({"all_available": True}):
            gid = g.get("id")
            if gid in seen:
                continue
            seen.add(gid)
            yield g

    def iter_group_subgroups(self, group_id: int) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/groups/{group_id}/subgroups", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page

    def iter_group_members(self, group_id: int) -> Generator[Dict[str, Any], None, None]:
        page = 1
        per_page = 100
        params = {"page": page, "per_page": per_page}
        while True:
            resp = self._req("GET", f"/groups/{group_id}/members/all", params=params)
            if resp.status_code == 401:
                return
            resp.raise_for_status()
            arr = resp.json()
            if not arr:
                break
            for item in arr:
                yield item
            page += 1
            params["page"] = page


