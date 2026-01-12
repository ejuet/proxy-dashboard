#!/usr/bin/env python3
import base64
import json
import os
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_URL = os.environ.get("NPM_BASE_URL", "http://192.168.178.68:81").rstrip("/")
TOKEN_FILE = Path(os.environ.get("NPM_TOKEN_FILE", "./npm_token.json")).expanduser()
CACHE_FILE = Path(
    os.environ.get("NPM_CACHE_FILE", "./npm_proxy_cache.json")
).expanduser()

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

TIMEOUT = 10


def load_token() -> str | None:
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("token")
        return token if isinstance(token, str) and token.strip() else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def save_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(TOKEN_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f)
    except Exception:
        TOKEN_FILE.write_text(json.dumps({"token": token}), encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except Exception:
            pass


def load_cache() -> dict:
    """
    Returns:
      {"updated_at": float, "hosts": list, "base_url": str}
    """
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"updated_at": 0.0, "hosts": [], "base_url": BASE_URL}
        hosts = data.get("hosts")
        if not isinstance(hosts, list):
            hosts = []
        updated_at = data.get("updated_at")
        if not isinstance(updated_at, (int, float)):
            updated_at = 0.0
        base_url = data.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            base_url = BASE_URL
        return {"updated_at": float(updated_at), "hosts": hosts, "base_url": base_url}
    except FileNotFoundError:
        return {"updated_at": 0.0, "hosts": [], "base_url": BASE_URL}
    except Exception:
        return {"updated_at": 0.0, "hosts": [], "base_url": BASE_URL}


def save_cache(hosts: list) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": time.time(), "hosts": hosts, "base_url": BASE_URL}
    try:
        fd = os.open(str(CACHE_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.chmod(CACHE_FILE, 0o600)
        except Exception:
            pass


def api_get_json(path: str, token: str) -> requests.Response:
    return requests.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )


def fetch_token_with_credentials(identity: str, secret: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/tokens",
        json={"identity": identity, "secret": secret},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Authentication failed (HTTP {r.status_code})")

    token = (r.json() or {}).get("token")
    if not token or not isinstance(token, str) or not token.strip():
        raise RuntimeError("Authentication response did not contain a token")

    save_token(token)
    return token


def fmt_time(ts: float) -> str:
    if not ts:
        return "never"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)


def build_hosts_view(hosts: list) -> list[dict]:
    """
    Normalizes host entries into a simple view model for rendering.
    """
    out: list[dict] = []
    for h in hosts or []:
        if not isinstance(h, dict):
            continue
        domains = h.get("domain_names") or []
        if not isinstance(domains, list):
            domains = []
        domains = [d for d in domains if isinstance(d, str) and d.strip()]

        enabled = bool(h.get("enabled"))
        ssl_forced = bool(h.get("ssl_forced"))
        forward_host = h.get("forward_host")
        forward_port = h.get("forward_port")

        scheme = "https" if ssl_forced else "http"
        links = [{"domain": d, "url": f"{scheme}://{d}"} for d in domains]

        target = ""
        if (
            isinstance(forward_host, str)
            and forward_host.strip()
            and isinstance(forward_port, int)
        ):
            target = f"{forward_host}:{forward_port}"
        elif (
            isinstance(forward_host, str)
            and forward_host.strip()
            and forward_port is not None
        ):
            target = f"{forward_host}:{forward_port}"
        elif isinstance(forward_host, str) and forward_host.strip():
            target = forward_host

        out.append(
            {
                "enabled": enabled,
                "ssl_forced": ssl_forced,
                "scheme": scheme,
                "domains": domains,
                "links": links,
                "target": target,
            }
        )

    # Sort: enabled first, then first domain name
    def key(x: dict):
        first = (x.get("domains") or [""])[0]
        return (0 if x.get("enabled") else 1, str(first).lower())

    out.sort(key=key)
    return out


def render_index(
    hosts: list, needs_login: bool, cache_updated_at: float, status_msg: str | None
) -> bytes:
    view = build_hosts_view(hosts)
    total = len(view)
    enabled_count = sum(1 for x in view if x["enabled"])

    btn_class = "renew-btn warn" if needs_login else "renew-btn"
    note = (
        "<div class='note warn'>Token missing/expired (or API unavailable). Showing cached links. "
        "Renew login highlighted.</div>"
        if needs_login
        else "<div class='note ok'>Token valid. Links are current.</div>"
    )

    status_html = f"<div class='status'>{status_msg}</div>" if status_msg else ""

    rows = []
    for item in view:
        domains_html = " ".join(
            f"<a class='domain' href='{l['url']}' target='_blank' rel='noopener noreferrer'>{l['domain']}</a>"
            for l in item["links"]
        )
        if not domains_html:
            domains_html = "<span class='muted'>(no domains)</span>"

        pill_enabled = (
            "<span class='pill on'>ENABLED</span>"
            if item["enabled"]
            else "<span class='pill off'>DISABLED</span>"
        )
        pill_ssl = (
            "<span class='pill ssl'>SSL</span>"
            if item["ssl_forced"]
            else "<span class='pill nossl'>NO_SSL</span>"
        )
        target = item["target"] or ""
        target_html = f"<span class='target'>→ {target}</span>" if target else ""

        cls = "host enabled" if item["enabled"] else "host disabled"
        rows.append(
            f"<div class='{cls}'>{pill_enabled}{pill_ssl}<div class='domains'>{domains_html}</div>{target_html}</div>"
        )

    if not rows:
        rows_html = "<div class='empty'>No proxies found (and no cache yet).</div>"
    else:
        rows_html = "\n".join(rows)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Proxies</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --card: #121a2a;
      --muted: #93a4c7;
      --text: #e8eefc;
      --ok: #39d98a;
      --warn: #ffcc00;
      --bad: #ff4d4f;
      --link: #8ab4ff;
      --pill: #1f2a44;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: radial-gradient(1200px 600px at 20% 0%, #17223a 0%, var(--bg) 50%, #070a10 100%);
      color: var(--text);
    }}
    .wrap {{
      max-width: 980px;
      margin: 0 auto;
      padding: 22px 16px 40px;
    }}
    header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.2px;
    }}
    .meta {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }}
    .note {{
      margin: 12px 0 14px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      font-size: 14px;
    }}
    .note.ok {{ border-color: rgba(57,217,138,0.35); }}
    .note.warn {{ border-color: rgba(255,204,0,0.45); }}
    .status {{
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .renew {{
      position: fixed;
      top: 14px;
      right: 14px;
      z-index: 10;
    }}
    .renew-btn {{
      appearance: none;
      border: 1px solid rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 999px;
      font-weight: 650;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.35);
    }}
    .renew-btn:hover {{
      background: rgba(255,255,255,0.10);
      border-color: rgba(255,255,255,0.24);
    }}
    .renew-btn.warn {{
      border-color: rgba(255,77,79,0.7);
      box-shadow: 0 0 0 4px rgba(255,77,79,0.15), 0 8px 20px rgba(0,0,0,0.45);
      animation: pulse 1.4s ease-in-out infinite;
    }}
    @keyframes pulse {{
      0% {{ transform: translateY(0); }}
      50% {{ transform: translateY(-1px); }}
      100% {{ transform: translateY(0); }}
    }}
    .grid {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}
    .host {{
      background: rgba(18,26,42,0.82);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 12px 12px;
      display: grid;
      grid-template-columns: auto auto 1fr auto;
      gap: 10px;
      align-items: center;
      overflow: hidden;
    }}
    .host.disabled {{
      opacity: 0.72;
      filter: saturate(0.8);
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: var(--pill);
      border: 1px solid rgba(255,255,255,0.10);
      color: var(--text);
      white-space: nowrap;
    }}
    .pill.on {{ border-color: rgba(57,217,138,0.35); }}
    .pill.off {{ border-color: rgba(255,77,79,0.35); }}
    .pill.ssl {{ border-color: rgba(138,180,255,0.35); }}
    .pill.nossl {{ border-color: rgba(147,164,199,0.25); color: var(--muted); }}
    .domains {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      min-width: 0;
    }}
    a.domain {{
      color: var(--link);
      text-decoration: none;
      font-weight: 650;
      word-break: break-word;
    }}
    a.domain:hover {{
      text-decoration: underline;
    }}
    .target {{
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .muted {{ color: var(--muted); }}
    .empty {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 14px;
      background: rgba(18,26,42,0.55);
      border: 1px dashed rgba(255,255,255,0.18);
      color: var(--muted);
    }}
    footer {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 12px;
    }}
    code {{
      color: var(--text);
      background: rgba(255,255,255,0.06);
      padding: 2px 6px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
    }}
  </style>
</head>
<body>
  <div class="renew">
    <a class="{btn_class}" href="/renew" title="Renew NPM token">
      🔐 Renew login
    </a>
  </div>

  <div class="wrap">
    <header>
      <div>
        <h1>Available proxies</h1>
        <div class="meta">
          NPM: <code>{BASE_URL}</code><br/>
          Cached last updated: <code>{fmt_time(cache_updated_at)}</code><br/>
          Showing: <code>{enabled_count}</code> enabled / <code>{total}</code> total
        </div>
        {status_html}
      </div>
    </header>

    {note}

    <div class="grid">
      {rows_html}
    </div>

    <footer>
      Tip: the renew button uses your browser’s Basic Auth prompt; credentials are only used to fetch a new NPM token.
    </footer>
  </div>
</body>
</html>
"""
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "NPMProxyList/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # quieter logs; still useful
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), fmt % args)
        )

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        headers: dict | None = None,
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.handle_index()
            return
        if parsed.path == "/renew":
            self.handle_renew()
            return
        if parsed.path == "/healthz":
            self._send(HTTPStatus.OK, b"ok\n", content_type="text/plain; charset=utf-8")
            return
        self._send(
            HTTPStatus.NOT_FOUND,
            b"not found\n",
            content_type="text/plain; charset=utf-8",
        )

    def handle_index(self):
        cache = load_cache()
        cache_hosts = cache["hosts"]
        cache_updated_at = cache["updated_at"]

        token = load_token()
        needs_login = False
        status_msg = None

        hosts_to_show = cache_hosts

        if token:
            try:
                r = api_get_json("/api/nginx/proxy-hosts", token)
                if r.status_code == 200:
                    hosts = r.json()
                    if isinstance(hosts, list):
                        save_cache(hosts)
                        hosts_to_show = hosts
                        cache_updated_at = time.time()
                    else:
                        status_msg = (
                            "API returned unexpected payload; showing cached list."
                        )
                elif r.status_code == 401:
                    needs_login = True
                    status_msg = "Token expired/invalid; showing cached list."
                else:
                    needs_login = (
                        True  # treat as "not current" so user can try renewing
                    )
                    status_msg = (
                        f"API error (HTTP {r.status_code}); showing cached list."
                    )
            except requests.RequestException as e:
                needs_login = True
                status_msg = f"API unreachable ({e}); showing cached list."
        else:
            needs_login = True
            status_msg = "No token saved; showing cached list."

        body = render_index(
            hosts_to_show,
            needs_login=needs_login,
            cache_updated_at=cache_updated_at,
            status_msg=status_msg,
        )
        self._send(HTTPStatus.OK, body)

    def handle_renew(self):
        # Basic-auth prompt
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            self._send(
                HTTPStatus.UNAUTHORIZED,
                b"Authentication required.\n",
                content_type="text/plain; charset=utf-8",
                headers={
                    "WWW-Authenticate": 'Basic realm="NPM Admin Login", charset="UTF-8"'
                },
            )
            return

        try:
            b64 = auth.split(" ", 1)[1].strip()
            raw = base64.b64decode(b64).decode("utf-8", errors="strict")
            identity, secret = raw.split(":", 1)
        except Exception:
            self._send(
                HTTPStatus.UNAUTHORIZED,
                b"Bad Authorization header.\n",
                content_type="text/plain; charset=utf-8",
                headers={
                    "WWW-Authenticate": 'Basic realm="NPM Admin Login", charset="UTF-8"'
                },
            )
            return

        try:
            token = fetch_token_with_credentials(identity, secret)

            # best-effort refresh cache right after renewal
            try:
                r = api_get_json("/api/nginx/proxy-hosts", token)
                if r.status_code == 200:
                    hosts = r.json()
                    if isinstance(hosts, list):
                        save_cache(hosts)
            except requests.RequestException:
                pass

            # redirect back to index
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        except Exception as e:
            # keep prompt available on refresh
            self._send(
                HTTPStatus.UNAUTHORIZED,
                (f"Renew failed: {e}\n").encode("utf-8"),
                content_type="text/plain; charset=utf-8",
                headers={
                    "WWW-Authenticate": 'Basic realm="NPM Admin Login", charset="UTF-8"'
                },
            )


def main() -> int:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving on http://{HOST}:{PORT}  (NPM_BASE_URL={BASE_URL})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
