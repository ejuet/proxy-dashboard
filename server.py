#!/usr/bin/env python3
"""
Small backend server for a dashboard over Nginx Proxy Manager (NPM).

Features
- POST /auth/token/renew      -> renew/save NPM API token using NPM credentials (identity+secret)
- GET  /links                 -> fetch current proxy-hosts from NPM, merged with local dashboard metadata
- PATCH /links/{id} (admin)   -> edit dashboard metadata (name/description/emoji/hidden) for a link
- DELETE /links/{id} (admin)  -> delete dashboard metadata for a link (reverts to defaults)

Admin protection
- Editing routes require HTTP Basic auth (ADMIN_USER / ADMIN_PASS env vars).

"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

# ----------------------------
# Config
# ----------------------------

BASE_URL = os.environ.get("NPM_BASE_URL", "http://192.168.178.68:81").rstrip("/")
TIMEOUT = float(os.environ.get("NPM_TIMEOUT", "10"))

TOKEN_FILE = Path(os.environ.get("NPM_TOKEN_FILE", "./npm_token.json")).expanduser()
META_FILE = Path(
    os.environ.get("DASH_META_FILE", "./dashboard_links_meta.json")
).expanduser()

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

CORS_ORIGINS = [
    o.strip() for o in os.environ.get("DASH_CORS_ORIGINS", "").split(",") if o.strip()
]

app = FastAPI(title="Dashboard Backend", version="1.0.0")
security = HTTPBasic()

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ----------------------------
# Models
# ----------------------------


class RenewTokenRequest(BaseModel):
    identity: str = Field(..., description="NPM username/email")
    secret: str = Field(..., description="NPM password")


class RenewTokenResponse(BaseModel):
    token: str


class LinkMeta(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    emoji: Optional[str] = Field(
        None, max_length=8, description="A short emoji string like '🔗' or '🚀'"
    )
    hidden: Optional[bool] = None


class LinkOut(BaseModel):
    id: int
    domain_names: list[str] = []
    forward_host: Optional[str] = None
    forward_port: Optional[int] = None
    enabled: Optional[bool] = None
    ssl_forced: Optional[bool] = None

    # dashboard fields (editable)
    name: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None
    hidden: bool = False


# ----------------------------
# Utilities: file perms + JSON
# ----------------------------


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, ensure_ascii=False, indent=2)

    # best-effort: create with user-only perms
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
    finally:
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass

    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError(f"Couldn't read {path}: {e}") from e


# ----------------------------
# Token handling (NPM)
# ----------------------------


def load_token() -> Optional[str]:
    data = _read_json_file(TOKEN_FILE)
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def save_token(token: str) -> None:
    _atomic_write_json(TOKEN_FILE, {"token": token})


async def npm_request(
    method: str,
    path: str,
    token: Optional[str] = None,
    json_body: Optional[dict] = None,
) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.request(
            method=method,
            url=f"{BASE_URL}{path}",
            headers=headers,
            json=json_body,
        )


async def validate_token(token: str) -> bool:
    # Quick validation: this endpoint returns 401 when token invalid/expired
    try:
        r = await npm_request("GET", "/api/nginx/proxy-hosts", token=token)
        return r.status_code != 401
    except httpx.HTTPError:
        return False


async def get_valid_token_or_401() -> str:
    token = load_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No saved NPM token. Call POST /auth/token/renew first.",
        )
    ok = await validate_token(token)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Saved NPM token is invalid/expired. Call POST /auth/token/renew.",
        )
    return token


# ----------------------------
# Dashboard metadata store
# ----------------------------


def load_meta() -> Dict[str, Dict[str, Any]]:
    data = _read_json_file(META_FILE)
    if isinstance(data, dict):
        # Ensure each value is dict
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                out[k] = v
        return out
    return {}


def save_meta(meta: Dict[str, Dict[str, Any]]) -> None:
    _atomic_write_json(META_FILE, meta)


def merge_hosts_with_meta(
    hosts: list[dict], meta: Dict[str, Dict[str, Any]]
) -> list[LinkOut]:
    merged: list[LinkOut] = []
    for h in hosts:
        try:
            hid = int(h.get("id"))
        except Exception:
            continue

        m = meta.get(str(hid), {})
        hidden_val = bool(m.get("hidden", False))

        merged.append(
            LinkOut(
                id=hid,
                domain_names=h.get("domain_names") or [],
                forward_host=h.get("forward_host"),
                forward_port=h.get("forward_port"),
                enabled=h.get("enabled"),
                ssl_forced=h.get("ssl_forced"),
                name=m.get("name"),
                description=m.get("description"),
                emoji=m.get("emoji"),
                hidden=hidden_val,
            )
        )
    return merged


# ----------------------------
# Admin auth
# ----------------------------


def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    # If ADMIN_USER/PASS are not set, editing is disabled by default (safer).
    if not ADMIN_USER or not ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin editing is not configured. Set ADMIN_USER and ADMIN_PASS.",
        )

    user_ok = secrets.compare_digest(creds.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(creds.password, ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )


# ----------------------------
# Routes
# ----------------------------


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/auth/token/renew", response_model=RenewTokenResponse)
async def renew_token(req: RenewTokenRequest) -> RenewTokenResponse:
    """
    Renew NPM API token by sending identity/secret to NPM, then save it to TOKEN_FILE.
    """
    r = await npm_request(
        "POST",
        "/api/tokens",
        json_body={"identity": req.identity, "secret": req.secret},
    )

    # Avoid dumping full proxy HTML; still provide signal
    if r.status_code != 200:
        text = (r.text or "").strip()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"NPM authentication failed (HTTP {r.status_code}): {text[:300]}",
        )

    data = r.json()
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="NPM response did not contain a token.",
        )

    save_token(token.strip())
    return RenewTokenResponse(token=token.strip())


@app.get("/links", response_model=list[LinkOut])
async def get_links(include_hidden: bool = False) -> list[LinkOut]:
    """
    Fetch current proxy-hosts from NPM and merge with dashboard metadata.
    By default, hidden links are filtered out. Use ?include_hidden=true to see them.
    """
    token = await get_valid_token_or_401()
    r = await npm_request("GET", "/api/nginx/proxy-hosts", token=token)

    if r.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="NPM token expired/invalid. Call POST /auth/token/renew.",
        )
    if r.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"NPM error fetching proxy-hosts (HTTP {r.status_code}).",
        )

    hosts = r.json()
    if not isinstance(hosts, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected NPM response shape for proxy-hosts.",
        )

    meta = load_meta()
    merged = merge_hosts_with_meta(hosts, meta)

    if not include_hidden:
        merged = [x for x in merged if not x.hidden]

    # stable-ish ordering: enabled first, then domain
    merged.sort(
        key=lambda x: (
            not bool(x.enabled),
            (x.domain_names[0] if x.domain_names else ""),
        )
    )
    return merged


@app.patch(
    "/links/{link_id}", response_model=LinkOut, dependencies=[Depends(require_admin)]
)
async def patch_link_meta(link_id: int, patch: LinkMeta) -> LinkOut:
    """
    Admin-only: edit dashboard metadata for a link.
    This does NOT modify the NPM proxy-host itself; it only affects the dashboard display.
    """
    token = await get_valid_token_or_401()

    # Confirm link exists in NPM (prevents storing meta for stale IDs)
    r = await npm_request("GET", "/api/nginx/proxy-hosts", token=token)
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="NPM token expired/invalid.")
    r.raise_for_status()
    hosts = r.json()
    if not isinstance(hosts, list) or not any(
        int(h.get("id", -1)) == link_id for h in hosts if isinstance(h, dict)
    ):
        raise HTTPException(
            status_code=404, detail="Link ID not found in NPM proxy-hosts."
        )

    meta = load_meta()
    key = str(link_id)
    current = meta.get(key, {})

    update = patch.model_dump(exclude_unset=True)
    # normalize empty strings to None
    for k in ("name", "description", "emoji"):
        if k in update and isinstance(update[k], str) and not update[k].strip():
            update[k] = None

    current.update(update)

    # If everything is None/absent (except hidden), we can keep it; user might only want hidden.
    meta[key] = current
    save_meta(meta)

    # return merged record
    host = next(h for h in hosts if int(h.get("id", -1)) == link_id)
    merged = merge_hosts_with_meta([host], meta)[0]
    return merged


@app.delete("/links/{link_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_link_meta(link_id: int) -> Response:
    """
    Admin-only: remove dashboard metadata for a link (reverts to default display).
    """
    meta = load_meta()
    meta.pop(str(link_id), None)
    save_meta(meta)
    return Response(status_code=204)


# ----------------------------
# Nice CLI entrypoint
# ----------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
