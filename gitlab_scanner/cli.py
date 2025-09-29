import argparse
import sys
import os
import time
import warnings

# Suppress urllib3 warnings (e.g., NotOpenSSLWarning, InsecureRequestWarning)
warnings.filterwarnings("ignore", module=r"urllib3.*")

from .runner import run


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="gitlab-scanner", description="GitLab reconnaissance and secret scanning tool")
	mx = parser.add_mutually_exclusive_group(required=True)
	mx.add_argument("--base-url", help="GitLab base URL, e.g., https://gitlab.example.com")
	mx.add_argument("--base-url-file", help="Path to file with base URLs, one per line (auth is not allowed)")
	auth = parser.add_argument_group("auth")
	auth.add_argument("--token", help="GitLab Personal Access Token")
	auth.add_argument("--username", help="Username for login session")
	auth.add_argument("--password", help="Password for login session")

	general = parser.add_argument_group("general")
	general.add_argument("--verify-ssl", action="store_true", help="Verify SSL certificates (default off)")
	general.add_argument("--out-dir", default="./gitlab-scan-output", help="Output directory")
	general.add_argument("--rules-yaml", default="./config/rules.yaml", help="Rules YAML path")
	history = parser.add_argument_group("history")
	history.add_argument("--no-scan-history", dest="scan_history", action="store_false", help="Disable commit history scanning")
	logging = parser.add_argument_group("logging")
	logging.add_argument("--debug", action="store_true", help="Enable DEBUG logs for this run")
	return parser


def main(argv=None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)
	# If running via list file, auth is disallowed
	if getattr(args, "base_url_file", None):
		if args.token or args.username or args.password:
			sys.stderr.write("[AUTH] Authentication flags are not allowed with --base-url-file\n")
			return 2
		# read urls
		try:
			urls = []
			with open(args.base_url_file, "r", encoding="utf-8") as fh:
				for ln in fh:
					ln = ln.strip()
					if not ln or ln.startswith("#"):
						continue
					for token in ln.split():
						token = token.lstrip('@').strip()
						if token:
							urls.append(token)
		except OSError as e:
			sys.stderr.write(f"Failed to read base-url file: {e}\n")
			return 2
		exit_code = 0
		from urllib.parse import urlparse
		# validate and collect only proper URLs
		valid_urls = []
		for u in urls:
			pr = urlparse(u)
			if pr.scheme in ("http", "https") and pr.netloc:
				valid_urls.append(u)
			else:
				sys.stderr.write(f"[WARN] Skipping invalid URL: {u}\n")
		# create session directory: targets_<timestamp>_<count>
		ts = time.strftime("%Y%m%d-%H%M%S")
		session_name = f"targets_{ts}_{len(valid_urls)}"
		session_dir = os.path.join(args.out_dir, session_name)
		os.makedirs(session_dir, exist_ok=True)
		for u in valid_urls:
			local_args = argparse.Namespace(**vars(args))
			setattr(local_args, "base_url", u)
			setattr(local_args, "token", None)
			setattr(local_args, "username", None)
			setattr(local_args, "password", None)
			setattr(local_args, "out_dir", session_dir)
			try:
				rc = run(local_args)
			except Exception as e:
				sys.stderr.write(f"[WARN] Scan failed for {u}: {e}\n")
				rc = 1
			if rc != 0:
				exit_code = rc
		return exit_code
	return run(args)


if __name__ == "__main__":
	sys.exit(main())


