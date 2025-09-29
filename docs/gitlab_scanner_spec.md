## GitLab Scanner – מפרט מלא

### מטרות
- כלי CLI בפייתון לסריקת שרתי GitLab (Self‑Managed/SaaS) ללא/עם הזדהות.
- גילוי פרויקטים/ריפוזיטוריים חשופים, איסוף משתמשים, הורדה וסריקה של קבצים טקסטואליים, איתור סודות לפי כללים מקובץ YAML.
- דילוג על קבצים בינאריים/גדולים, ניהול היסטוריית commits (ברירת מחדל: לסרוק), פלט JSON מסודר.

### קלט, הזדהות ואבטחה
- base URL חובה: `--base-url` (http/https, עם/בלי פורט).
- הזדהות אופציונלית:
  - `--token <PAT>`
  - `--username <u> --password <p>` (Login + Session + Cookies)
- SSL: ברירת מחדל `verify-ssl=false`; ניתן להפעיל עם `--verify-ssl`.
- תמיכה ב־GitLab API v4. שימוש ב־Pagination, ניהול Rate limit/Backoff/Retries.

### CLI Flags (מצומצם)
- חובה:
  - `--base-url <url>`
- או לחלופין:
  - `--base-url-file <path>` (קובץ עם רשימת Base URLs, אחת בכל שורה; ללא תמיכה בהזדהות)
- הזדהות:
  - `--token <pat>` או `--username <u> --password <p>`
- כלליים:
  - `--verify-ssl` (ברירת מחדל: כבוי)
  - `--out-dir <path>` (ברירת מחדל: `./gitlab-scan-output`)
  - `--rules-yaml <path>` (קובץ הכללים; ברירת מחדל: `./config/rules.yaml`)
- היסטוריה:
  - `--no-scan-history` (ברירת מחדל: סריקת היסטוריה מופעלת)
- לוגים:
  - `--debug` (מעלה רמת הלוגים ל-DEBUG עבור הריצה הזו)
  - הערה: בהרצה דרך `--base-url-file` לא ניתן להשתמש ב־`--token/--username/--password`.

הערה: כל שאר ההגדרות המתקדמות (globs, refs, retries, timeouts, concurrency, JSONL/snapshots, צבעים, קובץ לוג וכו') מוגדרות ב־`config/scan_config.yaml` בלבד כדי לשמור CLI נקי ופשוט.

### קובץ קונפיגורציית YAML (`config/scan_config.yaml`)
```yaml
version: 1
logging:
  level: debug          # debug | info | warn | error
  color: true           # auto | true | false
  timestamps: true
  log_file: null        # path לקובץ לוג או null
  banners: true         # הדפסת כותרות שלבים ל-stdout
output:
  write_jsonl: true                 # כתיבת <name>.jsonl בלייב
  live_snapshot:
    enabled: true                   # לשמור את <name>.json כ-JSON תקף כל הזמן
    interval_seconds: 5             # כל כמה שניות לייצר snapshot
    max_batch: 500                  # או אחרי כמה רשומות
    pretty: true                    # עימוד יפה בקובצי ה-JSON
scan:
  max_file_size_bytes: 104857600
  api_page_size: 100
  refs: default          # default | tags | all
  include_globs: []
  strict_include: false   # הסורק תמיד יעבור על הכל; globs לשימוש עתידי בלבד
  exclude_globs: []
  interesting_extensions:
    - ".env"
    - ".config"
    - ".conf"
    - ".cfg"
    - ".ini"
    - ".properties"
    - ".yml"
    - ".yaml"
    - ".json"
    - ".xml"
    - ".toml"
    - ".pem"
    - ".key"
    - ".cer"
    - ".crt"
    - ".csr"
    - ".der"
    - ".pfx"
    - ".p12"
    - ".ppk"
    - ".ovpn"
    - ".rdp"
    - ".sql"
    - ".dump"
    - ".bak"
    - ".backup"
    - ".ps1"
    - ".bat"
    - ".cmd"
    - ".sh"
    - ".log"
    - ".har"
    - ".pcap"
    - ".pcapng"
    - ".sqlite"
    - ".db"
    - ".db3"
    - ".s3cfg"
    - ".tfvars"
    - ".tfstate"
    - ".tf"
    - ".hcl"
    - ".hcl.json"
    - ".jks"
    - ".keystore"
    - ".bks"
    - ".apk"
    - ".aab"
    - ".ipa"
    - ".mobileprovision"
    - ".rdb"
    - ".sqlite3"
    - ".mdf"
    - ".ldf"
    - ".dmp"
    - ".psql"
    - ".bak"
    - ".bkp"
    - ".bk"
    - ".old"
    - ".orig"
    - ".save"
    - ".sav"
    - ".psm1"
    - ".psd1"
    - ".reg"
    - ".snk"
    - ".kdbx"
    - ".psafe3"
    - ".mobileconfig"
    - ".tblk"
    - ".rdg"
    - ".ica"
    - ".box"
    - ".ovf"
    - ".ova"
    - ".vmdk"
    - ".vhd"
    - ".vhdx"
    - ".vdi"
    - ".qcow"
    - ".qcow2"
    - ".img"
    - ".raw"
    - ".dd"
    - ".mem"
    - ".msix"
    - ".msixbundle"
    - ".7z"
    - ".rar"
    - ".tar"
    - ".tgz"
    - ".gz"
    - ".bz2"
    - ".xz"
    - ".zst"
    - ".lz4"
    - ".pkr.hcl"
    - ".pkrvars.hcl"
  file_name_patterns:
    - "(?i)\\.env(\\.|$)"
    - "(?i)credentials?"
    - "(?i)secrets?"
    - "(?i)tokens?"
    - "(?i)apikey|api[_-]?key"
    - "(?i)password|passwd|pwd"
    - "(?i)config(\\.|$)"
    - "(?i)settings?(\\.|$)"
    - "(?i)^Dockerfile$"
    - "(?i)docker-?compose(\\.ya?ml)?$"
    - "(?i)^id_rsa(\\.pub)?$"
    - "(?i)^id_ed25519(\\.pub)?$"
    - "(?i)^known_hosts$"
    - "(?i)^authorized_keys$"
    - "(?i)\\.kube[/\\\\]config$|^kubeconfig$"
    - "(?i)client_secret\\.json$"
    - "(?i)service[_-]?account\\.json$"
    - "(?i)^\\.npmrc$|^\\.pypirc$|^\\.netrc$"
    - "(?i)^\\.git-credentials$|^\\.gitconfig$|^\\.gitattributes$"
    - "(?i)^\\.docker[/\\\\]config\\.json$"
    - "(?i)^\\.bash_history$|^\\.zsh_history$|^\\.ssh[/\\\\]config$"
    - "(?i)\\.aws[/\\\\](credentials|config)$"
    - "(?i)^\\.azure[/\\\\]accessTokens\\.json$"
    - "(?i)^\\.gcloud[/\\\\]credentials\\.db$"
    - "(?i)\\.s3cfg$"
    - "(?i)^\\.gitlab-ci\\.ya?ml$"
    - "(?i)^\\.github[/\\\\]workflows[/\\\\].+\\.ya?ml$"
    - "(?i)^Jenkinsfile(\\..+)?$|^jenkins[/\\\\].+\\.groovy$"
    - "(?i)^azure-pipelines\\.ya?ml$|^\\.circleci[/\\\\]config\\.ya?ml$|^\\.travis\\.ya?ml$|^bitbucket-pipelines\\.ya?ml$|^\\.drone\\.ya?ml$|^\\.gitlab[/\\\\]ci[/\\\\].+\\.ya?ml$|^buildkite[/\\\\].*pipeline\\.ya?ml$"
    - "(?i)secret(s)?\\.ya?ml$|values(\\..+)?\\.ya?ml$|Chart\\.ya?ml$|kustomization\\.ya?ml$|ingress.*\\.ya?ml$|deployment.*\\.ya?ml$|configmap.*\\.ya?ml$"
    - "(?i).+\\.tf$|.+\\.tfvars(\\.json)?$|terraform\\.tfstate(\\.backup)?$|\\.terraform\\.lock\\.hcl$"
    - "(?i)^ansible\\.cfg$|^hosts$|^inventory(\\.\\w+)?$|group_vars[/\\\\].+|host_vars[/\\\\].+|vault.*\\.ya?ml$|^vault-password-file$"
    - "(?i)^\\.yarnrc(\\.yml)?$|^\\.pnpmfile\\.cjs$|^pnpm-workspace\\.ya?ml$|^requirements\\.txt$|^Pipfile(\\.lock)?$|^poetry\\.(toml|lock)$|^Gemfile(\\.lock)?$|^composer\\.(json|lock)$|^auth\\.json$|\\.m2[/\\\\]settings\\.xml$|^NuGet\\.Config$|^gradle.properties$"
    - "(?i)application\\.(properties|ya?ml)$|web\\.config$|app\\.config$|secrets\\.json$|local_settings\\.py$|settings\\.py$"
    - "(?i)google-services\\.json$|GoogleService-Info\\.plist$"
    - "(?i)^id_dsa(\\.pub)?$"
    - "(?i)^\\.htpasswd$|^\\.htaccess$"
    - "(?i)^dump\\.(rdb|sql)$|^backup\\.(sql|dmp|psql)$|^db\\.sqlite3$|.+\\.(sqlite3|mdf|ldf)$"
    - "(?i)^PublishSettings\\.xml$|^azure(Profile|RMProfile)\\.json$"
    - "(?i)service.*account.*\\.json$|secrets?\\.(ya?ml|json|ini|env)$|credentials?\\.(ya?ml|json|ini)$|production\\.env$|docker\\.env$"
    - "(?i)^mRemoteNG\\.xml$|^TeamViewer\\.ini$|^Default\\.rdp$|^PUTTY\\.RND$"
    - "(?i)^filezilla\\.xml$|^sitemanager\\.xml$|^recentservers\\.xml$|^Sites\\.dat$|^ws_?ftp\\.ini$|^Sites\\.dat$|^.*\\.duck$|^CoreFTP\\.dat$|^FlashFXP\\.dat$"
    - "(?i)^ultravnc\\.ini$|^tvnserver\\.cfg$|^\\.vnc[/\\]passwd$|^VNC-Server\\.json$|^RealVNC.*config.*\\.txt$"
    - "(?i)^Termius.*\\.(config|json)$|^KeePass\\.config\\.xml$"
    - "(?i)^Everything\\.(db|dbb|ini|efu|txt|zip)$|^Everything-.*\\.db$"
    - "(?i)^\\.DS_Store$|^Thumbs\\.db$"
    - "(?i)^application_default_credentials\\.json$|^local\\.settings\\.json$"
    - "(?i)^rclone\\.conf$|^\\.boto$|^boto\\.cfg$"
    - "(?i)^\\.oci[/\\\\]config$|oci_api_key\\.(pem|p12)$|^\\.gnupg[/\\\\]private-keys-v1\\.d/"
    - "(?i)^SAM$|^SYSTEM$|^SECURITY$|^SOFTWARE$|^NTDS\\.dit$|^shadow$|^gshadow$|^passwd$"
    - "(?i)^unattend\\.(xml|txt)$|^sysprep\\.(inf|xml)$|^applicationHost\\.config$|^Groups\\.xml$"
    - "(?i)^sitemanager\\.xml$|^recentservers\\.xml$|^WinSCP\\.ini$|^confCons\\.xml$|^RDCMan\\.settings$"
    - "(?i)^id_rsa(\\..+)?$|^id_ed25519(\\..+)?$"
  binary_extensions:
    # Images
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".gif"
    - ".bmp"
    - ".tiff"
    - ".webp"
    - ".ico"
    - ".icns"
    - ".heic"
    - ".heif"
    # Audio
    - ".mp3"
    - ".wav"
    - ".flac"
    - ".aac"
    - ".oga"
    - ".ogg"
    - ".wma"
    - ".m4a"
    - ".opus"
    - ".amr"
    # Video
    - ".mp4"
    - ".mkv"
    - ".avi"
    - ".mov"
    - ".wmv"
    - ".flv"
    - ".webm"
    - ".mpeg"
    - ".mpg"
    - ".mts"
    - ".m2ts"
    - ".3gp"
    - ".3g2"
    # Archives/Compressed
    - ".zip"
    - ".7z"
    - ".rar"
    - ".tar"
    - ".tgz"
    - ".gz"
    - ".bz2"
    - ".xz"
    - ".zst"
    - ".lz4"
    - ".cab"
    - ".iso"
    - ".dmg"
    - ".apk"
    - ".aab"
    - ".ipa"
    - ".jar"
    - ".war"
    - ".ear"
    # Executables/Libraries/Objects
    - ".exe"
    - ".dll"
    - ".sys"
    - ".so"
    - ".dylib"
    - ".o"
    - ".obj"
    - ".a"
    - ".lib"
    - ".pdb"
    - ".class"
    - ".pyc"
    - ".pyo"
    - ".pyd"
    # Documents/Binaries
    - ".pdf"
    - ".doc"
    - ".docx"
    - ".xls"
    - ".xlsx"
    - ".ppt"
    - ".pptx"
    - ".odt"
    - ".ods"
    - ".odp"
    - ".rtf"
    # Design/Graphics
    - ".psd"
    - ".ai"
    - ".eps"
    - ".indd"
    - ".sketch"
    - ".fig"
    # Databases/Columnar
    - ".sqlite"
    - ".sqlite3"
    - ".db"
    - ".db3"
    - ".rdb"
    - ".mdf"
    - ".ldf"
    - ".ndf"
    - ".accdb"
    - ".mdb"
    - ".parquet"
    - ".orc"
    - ".avro"
    - ".feather"
    # VM/Disk images
    - ".vmdk"
    - ".vhd"
    - ".vhdx"
    - ".vdi"
    - ".qcow"
    - ".qcow2"
    - ".img"
    - ".raw"
    - ".dd"
    - ".mem"
    # Dumps/Captures
    - ".dmp"
    - ".pcap"
    - ".pcapng"
    - ".har"
  binary_mime_prefixes:
    - "image/"
    - "video/"
    - "audio/"
    - "font/"
    - "model/"
    - "application/octet-stream"
    - "application/zip"
    - "application/x-7z-compressed"
    - "application/x-rar-compressed"
    - "application/x-tar"
    - "application/gzip"
    - "application/x-bzip2"
    - "application/x-xz"
    - "application/zstd"
    - "application/x-lz4"
    - "application/pdf"
    - "application/vnd.ms-"
    - "application/vnd.openxmlformats-officedocument"
    - "application/java-archive"
    - "application/x-msdownload"
    - "application/x-dosexec"
    - "application/x-executable"
    - "application/x-object"
    - "application/x-sharedlib"
    - "application/x-iso9660-image"
    - "application/x-apple-diskimage"
    - "application/vnd.android.package-archive"
  min_entropy_for_reporting: 3.5
  history:
    enabled: true
    depth: null
    since: null
    suppress_history_duplicates: true
```

### stdout ולוגים (Verbosity & Banners)
- רמות פלט:
  - רגיל: שורות מצב קצרות.
  - `--debug`: שורות DEBUG עם מזהי פרויקט, ref, עמודי API, counters, ו-timings. העדפת רמת לוג ניתנת גם דרך `logging.level` בקובץ הקונפיג.
- כותרות שלבים (באנרים) ל־stdout:
  - `## Starting discovery mode ##` (בכחול)
  - `## Starting user harvesting ##`
  - `## Starting secret harvesting ##`
  - `## Starting commits and history harvesting ##` (אם מופעל)
- פורמט לוג:
  - טיימסטמפ ISO-8601, רמת לוג, הודעה; צבעים לפי TTY או לפי `logging.color` בקובץ הקונפיג.
  - כתיבה לקובץ נשלטת דרך `logging.log_file` בקובץ הקונפיג.
  - תגיות: `[REPO]` ירוק לכל פרויקט; `[AUTH]` אדום לשגיאות הזדהות; `[USER]` ירוק למשתמשים שנאספו; `[VER]` ירוק לגרסת השרת בתחילת הריצה.

### כתיבה בלייב של JSON
- לכל אחד מהקבצים (`repos.json`, `users.json`, `files.json`, `interesting.json`, `secrets.json`, `skipped.json`):
  - כתיבה לייב ב־JSONL: `*.jsonl` כאשר `output.write_jsonl=true` (ברירת מחדל: true). כל רשומה בשורה נפרדת, נשטפת מיד לדיסק.
  - Snapshot JSON תקין ורב־פעמי: `*.json` נשמר כ־JSON Array תקף לאורך הריצה באמצעות snapshot מחזורי לפי `output.live_snapshot` (ברירת מחדל: מופעל). קצב ע"פ `interval_seconds` או `max_batch` המינימלי מביניהם.
  - בסיום הריצה ייווצר snapshot סופי; אם הופסק באמצע, קובצי ה־JSONL מכילים את כל הרשומות עד לעצירה.

### תיקיות Output לפי ריצה
- לכל ריצה נוצרת תיקייה ייחודית תחת `out-dir` (ברירת מחדל: `./gitlab-scan-output`):
  - תבנית שם: `<host-with-dashes>-<scheme>[-port]-<YYYYMMDD-HHMMSS>`
  - דוגמה: `gitlab-scan-output/127-0-0-1-http-20250916-205712`
  - כל קובצי הפלט נשמרים בתיקייה זו.

### מדיניות סריקה
- גילוי פרויקטים/ריפוזיטוריים:
  - ללא הזדהות: רק ציבוריים.
  - עם הזדהות: ציבוריים + פרטיים בהתאם להרשאות (ניתן להגביל עם דגלים).
- `visibility`: 'public' | 'private' בלבד.
- משתמשים:
  - מ־commit authors, project/group members, users גלובליים (אם מותר).
- קבצים:
  - עץ קבצים דרך API (`repository/tree`) ו־raw (`repository/files/:raw`).
  - דילוג על בינאריים, על קבצים מעל הסף, ועל מסלולים שנפסלו לפי globs.
- “קובץ מעניין”:
  - אם הסיומת ∈ `interesting_extensions` או השם/נתיב תואם `file_name_patterns`.
  - שמירת הסיבה המדויקת במערך `interesting_reasons`.

### חיפוש סודות
- Regex לפי `rules` מתוך YAML (אין hard‑code בקוד).
- לכל התאמה: `rule_id`, `severity`, חישוב entropy על ה־match (Shannon), הקשר (`line`, `line_text`, `context_excerpt`).
- היסטוריה:
  - אם history.enabled=true: סריקת commits לפי `depth`/`since`/`refs`.
  - דה־דופ מול HEAD אם `suppress_history_duplicates=true`:
    - התאמות בהיסטוריה עם אותה שורה בדיוק (לאחר נרמול CRLF→LF), אותו `rule_id` ו־`match`, באותו קובץ – ינופו אם קיימת התאמה זהה ב־HEAD.
- דה־דופ פנימי:
  - HEAD: לפי (project_id, path, line, rule_id, match).
  - היסטוריה: לפי (project_id, commit_id, path, line, rule_id, match).

### פלטים (JSON, UTF‑8)
כל הקבצים הם JSON Arrays ונשמרים בתיקיית ה־Output.

#### repos.json
- שדות:
  - `project_id: number`
  - `path_with_namespace: string`
  - `visibility: "public" | "private"`
  - `default_branch: string | null`
  - `last_activity_at: string (ISO-8601)`
  - `fullpath: string (URL לפרויקט)`
  - `ssh_url_to_repo: string`
  - `http_url_to_repo: string`
  - `web_url: string`
  - `name: string`
  - `archived: boolean`
  - `topics: string[]`

#### users.json
- שדות:
  - `user_id: number | null`
  - `username: string | null`
  - `display_name: string | null`
  - `email: string | null`
  - `source: string[]`  // ["commit","member","global","api"]
  - `role: string | null`
  - `last_seen: string | null (ISO-8601)`
  - `web_url: string | null`

#### files.json
- שדות:
  - `project_id: number`
  - `repo: string`  // path_with_namespace
  - `path: string`
  - `size: number | null`
  - `ref: string`
  - `is_binary: boolean`
  - `mime: string | null`
  - `web_url: string`
  - `raw_url: string`
  - `visibility: "public" | "private"`
  - `last_commit_id: string | null`
  - `last_commit_author: string | null`
  - `last_commit_date: string | null (ISO-8601)`
  - `interesting: boolean`
  - `interesting_reasons: string[]`

#### interesting.json
- שדות:
  - `project_id: number`
  - `repo: string`
  - `path: string`
  - `ref: string`
  - `size: number | null`
  - `reasons: string[]`
  - `web_url: string`
  - `raw_url: string`
  - `visibility: "public" | "private"`

#### secrets.json
- שדות:
  - `project_id: number`
  - `repo: string`
  - `path: string`
  - `line: number`
  - `rule_id: string`
  - `match: string`
  - `line_text: string`
  - `entropy: number`
  - `severity: "low" | "medium" | "high" | "critical"`
  - `ref: string`
  - `commit_id: string | null`
  - `commit_author: string | null`
  - `committed_date: string | null (ISO-8601)`
  - `source: string`  // "HEAD" | branch/tag/commit id
  - `web_url: string`
  - `raw_url: string`
  - `fullpath: string`
  - `visibility: "public" | "private"`
  - `context_excerpt: string | null`

#### skipped.json
- שדות:
  - `project_id: number`
  - `repo: string`
  - `path: string`
  - `ref: string`
  - `reason: string`  // "binary_ext" | "binary_mime" | "too_large" | "download_error" | "excluded_glob" | "non_text"
  - `size: number | null`
  - `raw_url: string`
  - `web_url: string`

#### summary.json (אופציונלי)
- `counters`: { repos, users, files, interesting, secrets, skipped }
- `run_config`: צילום הגדרות הריצה (flags/scan config)
- `base_url`, `started_at`, `finished_at`, `duration_ms`

### דה־דופ וסינון כפילויות
- files: לפי (project_id, ref, path)
- interesting: לפי (project_id, ref, path)
- secrets:
  - HEAD: (project_id, path, line, rule_id, match)
  - היסטוריה: (project_id, commit_id, path, line, rule_id, match)
  - סינון כפילויות היסטוריות מול HEAD אם `suppress_history_duplicates=true`

### ביצועים ועמידות
- Pagination לפי `api_page_size`.
- Rate limit פנימי + backoff על 429/5xx.
- Retries לפי `--retries`.
- Concurrency נשלט (IO-bound), עם הקפדה על RPS.
- Timeouts לכל בקשת API.

### טיפול בשגיאות ושוליים
- LFS/Submodules: מדווחים/מדולגים; אם כשל raw – reason: `download_error`.
- Archived/Empty repos: נתמכים; ייתכנו תוצאות ריקות.
- קידוד טקסט: אם לא ניתן לפענח – reason: `non_text`.


