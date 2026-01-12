#!/usr/bin/env python3
"""
Tiny HTML frontend server for the dashboard backend.

- Serves minimal HTML UI at /
- Uses backend API:
  - POST /auth/token/renew
  - GET  /links           (admin can request hidden with Basic auth + include_hidden=true)
  - PATCH /links/{id}     (admin)
  - DELETE /links/{id}    (admin)
  - PATCH /config         (admin) set NPM base URL

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
    return f"""<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title></head><body>{body}</body></html>"""


def esc(s: Any) -> str:
    s = "" if s is None else str(s)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


async def backend(
    method: str, path: str, *, json: Optional[dict] = None, auth=None
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        return await c.request(method, f"{BACKEND_URL}{path}", json=json, auth=auth)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    include_hidden: bool = False,
    admin_user: str = "",
    admin_pass: str = "",
) -> str:
    auth = (
        (admin_user, admin_pass)
        if (include_hidden and admin_user and admin_pass)
        else None
    )

    links: list[Dict[str, Any]] = []
    error: Optional[str] = None
    r = await backend(
        "GET",
        f"/links?include_hidden={'true' if include_hidden else 'false'}",
        auth=auth,
    )
    if r.status_code == 200:
        links = r.json()
    else:
        error = f"/links HTTP {r.status_code}: {r.text[:300]}"

    body = "<h1>Dashboard</h1>"

    body += f"""
<details>
  <summary>Admin (show hidden / set NPM URL)</summary>
  <form method="get" action="/" style="margin-top:8px;">
    <div><label>Admin user <input name="admin_user" value="{esc(admin_user)}"/></label></div>
    <div><label>Admin pass <input name="admin_pass" type="password" value="{esc(admin_pass)}"/></label></div>
    <div>
      <label><input type="checkbox" name="include_hidden" value="true" {"checked" if include_hidden else ""}/>
      Include hidden</label>
    </div>
    <button type="submit">Apply</button>
  </form>

  <form method="post" action="/set_npm_url" style="margin-top:8px;">
    <div><label>Admin user <input name="admin_user" value="{esc(admin_user)}"/></label></div>
    <div><label>Admin pass <input name="admin_pass" type="password" value="{esc(admin_pass)}"/></label></div>
    <div><label>NPM base URL <input name="npm_base_url" placeholder="http://192.168.1.10:81"/></label></div>
    <button type="submit">Set NPM URL</button>
  </form>
</details>

<h2>Renew NPM Token</h2>
<form method="post" action="/renew">
  <div><label>Identity <input name="identity"/></label></div>
  <div><label>Secret <input name="secret" type="password"/></label></div>
  <button type="submit">Renew token</button>
</form>
<hr/>
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
        name = L.get("name") or ""
        desc = L.get("description") or ""
        emoji = L.get("emoji") or ""
        hidden = bool(L.get("hidden"))

        body += f"""
<li>
  <div><b>{esc(domains)}</b> → {esc(target)} {"(hidden)" if hidden else ""}</div>
  <div>Dashboard: {esc(emoji)} <b>{esc(name)}</b> — {esc(desc)}</div>

  <details>
    <summary>Edit (admin)</summary>
    <form method="post" action="/edit">
      <input type="hidden" name="id" value="{esc(link_id)}"/>
      <div><label>Admin user <input name="admin_user" value="{esc(admin_user)}"/></label></div>
      <div><label>Admin pass <input name="admin_pass" type="password" value="{esc(admin_pass)}"/></label></div>
      <div><label>Emoji <input name="emoji" value="{esc(emoji)}"/></label></div>
      <div><label>Name <input name="name" value="{esc(name)}"/></label></div>
      <div><label>Description <input name="description" value="{esc(desc)}"/></label></div>
      <div><label>Hidden
        <select name="hidden">
          <option value="">(no change)</option>
          <option value="true" {"selected" if hidden else ""}>true</option>
          <option value="false" {"selected" if not hidden else ""}>false</option>
        </select>
      </label></div>
      <button type="submit">Save</button>
    </form>

    <form method="post" action="/reset" style="margin-top:8px;">
      <input type="hidden" name="id" value="{esc(link_id)}"/>
      <div><label>Admin user <input name="admin_user" value="{esc(admin_user)}"/></label></div>
      <div><label>Admin pass <input name="admin_pass" type="password" value="{esc(admin_pass)}"/></label></div>
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


@app.post("/set_npm_url")
async def set_npm_url(
    admin_user: str = Form(...),
    admin_pass: str = Form(...),
    npm_base_url: str = Form(...),
) -> Response:
    await backend(
        "PATCH",
        "/config",
        json={"npm_base_url": npm_base_url},
        auth=(admin_user, admin_pass),
    )
    return RedirectResponse(
        url=f"/?admin_user={admin_user}&include_hidden=true", status_code=303
    )


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
    patch: Dict[str, Any] = {"emoji": emoji, "name": name, "description": description}
    if hidden.strip().lower() in ("true", "false"):
        patch["hidden"] = hidden.strip().lower() == "true"

    await backend("PATCH", f"/links/{id}", json=patch, auth=(admin_user, admin_pass))
    return RedirectResponse(
        url=f"/?include_hidden=true&admin_user={admin_user}", status_code=303
    )


@app.post("/reset")
async def reset(
    id: int = Form(...),
    admin_user: str = Form(...),
    admin_pass: str = Form(...),
) -> Response:
    await backend("DELETE", f"/links/{id}", auth=(admin_user, admin_pass))
    return RedirectResponse(
        url=f"/?include_hidden=true&admin_user={admin_user}", status_code=303
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5174)
