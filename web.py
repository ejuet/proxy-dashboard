#!/usr/bin/env python3
"""
Tiny HTML frontend server for the dashboard backend.

- Serves a minimal HTML UI at /
- Uses your backend API for:
  - POST /auth/token/renew
  - GET  /links
  - PATCH /links/{id}
  - DELETE /links/{id}

Run:
  pip install fastapi uvicorn httpx
  export BACKEND_URL="http://127.0.0.1:8080"
  uvicorn frontend:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT = float(os.environ.get("FRONTEND_TIMEOUT", "10"))

app = FastAPI(title="Dashboard Frontend (Minimal)")


def html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
</head>
<body>
{body}
</body>
</html>
"""


async def backend(
    method: str, path: str, *, json: Optional[dict] = None
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.request(method, f"{BACKEND_URL}{path}", json=json)


def esc(s: Any) -> str:
    # tiny escaping (enough for this UI)
    s = "" if s is None else str(s)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, include_hidden: bool = False) -> str:
    # Fetch links (best-effort; show error if backend not ready)
    links: list[Dict[str, Any]] = []
    error: Optional[str] = None
    r = await backend(
        "GET", f"/links?include_hidden={'true' if include_hidden else 'false'}"
    )
    if r.status_code == 200:
        links = r.json()
    else:
        error = f"Backend /links returned HTTP {r.status_code}: {r.text[:300]}"

    toggle = "true" if not include_hidden else "false"
    toggle_text = "Show hidden" if not include_hidden else "Hide hidden"

    body = f"""
<h1>Dashboard</h1>

<p>
  <a href="/?include_hidden={toggle}">{toggle_text}</a>
</p>

<h2>Renew NPM Token</h2>
<form method="post" action="/renew">
  <div>
    <label>Identity <input name="identity" /></label>
  </div>
  <div>
    <label>Secret <input name="secret" type="password" /></label>
  </div>
  <button type="submit">Renew token</button>
</form>

<hr />
"""

    if error:
        body += f"<p><b>Error:</b> {esc(error)}</p>"
        return html_page("Dashboard", body)

    body += "<h2>Links</h2>"
    if not links:
        body += "<p>No links (or none visible).</p>"
        return html_page("Dashboard", body)

    body += "<ul>"
    for L in links:
        link_id = L.get("id")
        domains = ", ".join(L.get("domain_names") or [])
        target = f"{L.get('forward_host') or ''}:{L.get('forward_port') or ''}"
        enabled = "ENABLED" if L.get("enabled") else "DISABLED"
        ssl = "SSL" if L.get("ssl_forced") else "NO_SSL"
        name = L.get("name") or ""
        desc = L.get("description") or ""
        emoji = L.get("emoji") or ""
        hidden = bool(L.get("hidden"))

        body += f"""
  <li>
    <div>
      <b>{esc(domains)}</b> → {esc(target)} [{esc(enabled)}] [{esc(ssl)}]
    </div>
    <div>
      Dashboard: {esc(emoji)} <b>{esc(name)}</b> — {esc(desc)} {"(hidden)" if hidden else ""}
    </div>

    <details>
      <summary>Edit (admin)</summary>
      <form method="post" action="/edit">
        <input type="hidden" name="id" value="{esc(link_id)}" />
        <div><label>Admin user <input name="admin_user" /></label></div>
        <div><label>Admin pass <input name="admin_pass" type="password" /></label></div>
        <div><label>Emoji <input name="emoji" value="{esc(emoji)}" /></label></div>
        <div><label>Name <input name="name" value="{esc(name)}" /></label></div>
        <div><label>Description <input name="description" value="{esc(desc)}" /></label></div>
        <div>
          <label>Hidden
            <select name="hidden">
              <option value="">(no change)</option>
              <option value="true" {"selected" if hidden else ""}>true</option>
              <option value="false" {"selected" if not hidden else ""}>false</option>
            </select>
          </label>
        </div>
        <button type="submit">Save</button>
      </form>

      <form method="post" action="/reset" style="margin-top:8px;">
        <input type="hidden" name="id" value="{esc(link_id)}" />
        <div><label>Admin user <input name="admin_user" /></label></div>
        <div><label>Admin pass <input name="admin_pass" type="password" /></label></div>
        <button type="submit">Reset metadata</button>
      </form>
    </details>
  </li>
"""
    body += "</ul>"

    return html_page("Dashboard", body)


@app.post("/renew")
async def renew(identity: str = Form(...), secret: str = Form(...)) -> Response:
    await backend(
        "POST", "/auth/token/renew", json={"identity": identity, "secret": secret}
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/edit")
async def edit(
    id: int = Form(...),
    admin_user: str = Form(...),
    admin_pass: str = Form(...),
    emoji: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    hidden: str = Form(""),
) -> Response:
    patch: Dict[str, Any] = {
        "emoji": emoji,
        "name": name,
        "description": description,
    }
    if hidden.strip().lower() in ("true", "false"):
        patch["hidden"] = hidden.strip().lower() == "true"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        await client.patch(
            f"{BACKEND_URL}/links/{id}",
            json=patch,
            auth=(admin_user, admin_pass),  # HTTP Basic
        )
    return RedirectResponse(url="/?include_hidden=true", status_code=303)


@app.post("/reset")
async def reset(
    id: int = Form(...),
    admin_user: str = Form(...),
    admin_pass: str = Form(...),
) -> Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        await client.delete(
            f"{BACKEND_URL}/links/{id}",
            auth=(admin_user, admin_pass),  # HTTP Basic
        )
    return RedirectResponse(url="/?include_hidden=true", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5174)
