#!/usr/bin/env python3
"""
Small backend server for a dashboard over Nginx Proxy Manager (NPM).

Features
- POST /auth/token/renew        -> renew/save NPM API token using NPM credentials (identity+secret)
- GET  /links                  -> fetch current proxy-hosts from NPM, merged with local dashboard metadata
                                  (non-admin: only non-hidden links; admin can request hidden via ?include_hidden=true)
- PATCH /links/{id} (admin)    -> edit dashboard metadata (name/description/emoji/hidden) for a link
- DELETE /links/{id} (admin)   -> delete dashboard metadata for a link (reverts to defaults)
- GET  /config (admin)         -> view runtime config (incl. NPM base URL)
- PATCH /config (admin)        -> update runtime config (incl. NPM base URL)

Caching behavior (NEW)
- On successful /links live fetch, cache raw NPM proxy-hosts to DASH_LINKS_CACHE_FILE (default ./dashboard_links_cache.json)
- If token missing/expired OR NPM is unreachable, /links falls back to cached hosts (if present)
- When serving cached links, /links sets headers:
    X-Links-Source: cache
    X-Links-Cache-Fetched-At: <iso8601 UTC timestamp>
  Otherwise:
    X-Links-Source: live

Admin protection
- Editing/config routes require HTTP Basic auth (ADMIN_USER / ADMIN_PASS env vars).
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
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

DEFAULT_BASE_URL = os.environ.get("NPM_BASE_URL", "http://192.168.178.68:81").rstrip(
    "/"
)
TIMEOUT = float(os.environ.get("NPM_TIMEOUT", "10"))

TOKEN_FILE = Path(os.environ.get("NPM_TOKEN_FILE", "./npm_token.json")).expanduser()
META_FILE = Path(
    os.environ.get("DASH_META_FILE", "./dashboard_links_meta.json")
).expanduser()

# NEW: persistent runtime config (so admin can change NPM URL)
CONFIG_FILE = Path(
    os.environ.get("DASH_CONFIG_FILE", "./dashboard_config.json")
).expanduser()

# NEW: cache for proxy-host links
LINKS_CACHE_FILE = Path(
    os.environ.get("DASH_LINKS_CACHE_FILE", "./dashboard_links_cache.json")
).expanduser()

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "DASH_CORS_ORIGINS",
        "*",
    ).split(",")
    if o.strip()
]

app = FastAPI(title="Dashboard Backend", version="1.2.0")

# Two security modes:
# - security: required (auto_error=True) -> for admin-only routes
# - security_optional: optional (auto_error=False) -> for conditional admin access (e.g. include_hidden)
security = HTTPBasic()
security_optional = HTTPBasic(auto_error=False)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
# Runtime config (admin-changeable)
# ----------------------------

_runtime_base_url: str = DEFAULT_BASE_URL


def _validate_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("NPM base URL cannot be empty.")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("NPM base URL must start with http:// or https://")
    return url


def load_runtime_config() -> None:
    global _runtime_base_url
    data = _read_json_file(CONFIG_FILE)
    if isinstance(data, dict) and isinstance(data.get("npm_base_url"), str):
        try:
            _runtime_base_url = _validate_base_url(data["npm_base_url"])
            return
        except Exception:
            # Fall back to env default if config file contains bad value
            pass
    _runtime_base_url = DEFAULT_BASE_URL


def save_runtime_config() -> None:
    _atomic_write_json(CONFIG_FILE, {"npm_base_url": _runtime_base_url})


def get_base_url() -> str:
    return _runtime_base_url


# Load on startup import
load_runtime_config()

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

    # dashboard fields (editable)
    name: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None
    hidden: bool = False


class ConfigOut(BaseModel):
    npm_base_url: str


class ConfigPatch(BaseModel):
    npm_base_url: str = Field(
        ..., description="Base URL of NPM, e.g. http://192.168.1.10:81"
    )


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
    base = get_base_url()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.request(
            method=method,
            url=f"{base}{path}",
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
# Links cache (NEW)
# ----------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_links_cache() -> tuple[Optional[list[dict]], Optional[str]]:
    """
    Returns (hosts, fetched_at_iso).
    hosts is the raw list from NPM /api/nginx/proxy-hosts.
    """
    data = _read_json_file(LINKS_CACHE_FILE)
    if not isinstance(data, dict):
        return None, None

    hosts = data.get("hosts")
    fetched_at = data.get("fetched_at")

    if not isinstance(hosts, list):
        return None, None
    if fetched_at is not None and not isinstance(fetched_at, str):
        fetched_at = None

    hosts = [h for h in hosts if isinstance(h, dict)]
    return hosts, fetched_at


def save_links_cache(hosts: list[dict]) -> None:
    _atomic_write_json(
        LINKS_CACHE_FILE,
        {
            "fetched_at": _utc_now_iso(),
            "hosts": hosts,
        },
    )


# ----------------------------
# Dashboard metadata store
# ----------------------------


def load_meta() -> Dict[str, Dict[str, Any]]:
    data = _read_json_file(META_FILE)
    if isinstance(data, dict):
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


def _admin_configured_or_503() -> None:
    if not ADMIN_USER or not ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin editing is not configured. Set ADMIN_USER and ADMIN_PASS.",
        )


def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    _admin_configured_or_503()

    user_ok = secrets.compare_digest(creds.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(creds.password, ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )


def is_admin(creds: Optional[HTTPBasicCredentials]) -> bool:
    if not creds:
        return False
    if not ADMIN_USER or not ADMIN_PASS:
        return False
    return secrets.compare_digest(
        creds.username, ADMIN_USER
    ) and secrets.compare_digest(creds.password, ADMIN_PASS)


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
async def get_links(
    include_hidden: bool = False,
    creds: Optional[HTTPBasicCredentials] = Depends(security_optional),
    response: Response = None,
) -> list[LinkOut]:
    """
    Fetch current proxy-hosts from NPM and merge with dashboard metadata.

    - Non-logged-in users: only non-hidden links
    - Admin: can request hidden links using ?include_hidden=true (requires HTTP Basic auth)

    Caching behavior:
    - On successful live fetch, cache the NPM hosts to disk.
    - If token is missing/expired OR NPM fetch fails, serve cached hosts if available.
    - When serving cache, response includes headers indicating cached source.
    """
    if include_hidden and not is_admin(creds):
        _admin_configured_or_503()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin credentials required to include hidden links.",
            headers={"WWW-Authenticate": "Basic"},
        )

    hosts: Optional[list[dict]] = None
    source = "live"
    cache_fetched_at: Optional[str] = None

    # Try live fetch if we have a token that validates
    token = load_token()
    if token:
        token_ok = await validate_token(token)
        if token_ok:
            try:
                r = await npm_request("GET", "/api/nginx/proxy-hosts", token=token)

                # Token might expire between validate and request
                if r.status_code == 401:
                    hosts = None
                elif r.is_error:
                    hosts = None
                else:
                    data = r.json()
                    if isinstance(data, list):
                        hosts = [h for h in data if isinstance(h, dict)]
                        save_links_cache(hosts)
                    else:
                        hosts = None
            except httpx.HTTPError:
                hosts = None

    # Fallback to cache if live not available
    if hosts is None:
        cached_hosts, cache_fetched_at = load_links_cache()
        if cached_hosts is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No valid NPM token and no cached links available. Call POST /auth/token/renew.",
            )
        hosts = cached_hosts
        source = "cache"

    meta = load_meta()
    merged = merge_hosts_with_meta(hosts, meta)

    if not include_hidden:
        merged = [x for x in merged if not x.hidden]

    merged.sort(key=lambda x: (x.domain_names[0] if x.domain_names else ""))

    # Tell the user whether cache was used
    if response is not None:
        response.headers["X-Links-Source"] = source
        if source == "cache" and cache_fetched_at:
            response.headers["X-Links-Cache-Fetched-At"] = cache_fetched_at

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
    for k in ("name", "description", "emoji"):
        if k in update and isinstance(update[k], str) and not update[k].strip():
            update[k] = None

    current.update(update)
    meta[key] = current
    save_meta(meta)

    host = next(h for h in hosts if int(h.get("id", -1)) == link_id)
    return merge_hosts_with_meta([host], meta)[0]


@app.delete("/links/{link_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_link_meta(link_id: int) -> Response:
    """
    Admin-only: remove dashboard metadata for a link (reverts to default display).
    """
    meta = load_meta()
    meta.pop(str(link_id), None)
    save_meta(meta)
    return Response(status_code=204)


# NEW: admin-configurable NPM URL
@app.get("/config", response_model=ConfigOut, dependencies=[Depends(require_admin)])
def get_config() -> ConfigOut:
    return ConfigOut(npm_base_url=get_base_url())


@app.patch("/config", response_model=ConfigOut, dependencies=[Depends(require_admin)])
def patch_config(patch: ConfigPatch) -> ConfigOut:
    global _runtime_base_url
    try:
        _runtime_base_url = _validate_base_url(patch.npm_base_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    save_runtime_config()
    return ConfigOut(npm_base_url=_runtime_base_url)


# ----------------------------
# Nice CLI entrypoint
# ----------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
