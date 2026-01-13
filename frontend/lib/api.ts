import { AdminCreds, basicAuthHeader } from "./auth";

export type LinkOut = {
    id: number;
    domain_names: string[];
    forward_host?: string | null;
    forward_port?: number | null;
    name?: string | null;
    description?: string | null;
    emoji?: string | null;
    hidden: boolean;
};

export type LinkMetaPatch = {
    name?: string | null;
    description?: string | null;
    emoji?: string | null;
    hidden?: boolean;
};

export type ConfigOut = { npm_base_url: string };
export type ConfigPatch = { npm_base_url: string };

export type RenewTokenReq = { identity: string; secret: string };
export type RenewTokenRes = { token: string };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE

function mustBase(): string {
    if(!API_BASE) {
        throw new Error("Missing NEXT_PUBLIC_API_BASE in env");
    }
    return API_BASE.replace(/\/+$/, "");
}

async function apiFetch(
    path: string,
    opts: RequestInit & { adminCreds?: AdminCreds } = {}
) {
    const base = mustBase();
    const headers = new Headers(opts.headers || {});
    headers.set("Accept", "application/json");

    if(opts.adminCreds) {
        headers.set("Authorization", basicAuthHeader(opts.adminCreds));
    }

    const res = await fetch(`${base}${path}`, {
        ...opts,
        headers,
        cache: "no-store",
    });

    const xLinksSource = res.headers.get("X-Links-Source");
    const xCacheAt = res.headers.get("X-Links-Cache-Fetched-At");

    if(!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const data = await res.json();
            if(data?.detail) detail = String(data.detail);
        } catch {
            // ignore
        }
        const err = new Error(detail) as Error & {
            status?: number;
            xLinksSource?: string | null;
            xCacheAt?: string | null;
        };
        err.status = res.status;
        err.xLinksSource = xLinksSource;
        err.xCacheAt = xCacheAt;
        throw err;
    }

    return { res, xLinksSource, xCacheAt };
}

export async function getLinks(params?: {
    includeHidden?: boolean;
    adminCreds?: AdminCreds;
}) {
    const q =
        params?.includeHidden ? "?include_hidden=true" : "";
    const { res, xLinksSource, xCacheAt } = await apiFetch(`/links${q}`, {
        method: "GET",
        adminCreds: params?.adminCreds,
    });
    const data = (await res.json()) as LinkOut[];
    return { data, xLinksSource, xCacheAt };
}

export async function patchLinkMeta(
    id: number,
    patch: LinkMetaPatch,
    adminCreds: AdminCreds
) {
    const { res } = await apiFetch(`/links/${id}`, {
        method: "PATCH",
        adminCreds,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    return (await res.json()) as LinkOut;
}

export async function deleteLinkMeta(id: number, adminCreds: AdminCreds) {
    await apiFetch(`/links/${id}`, {
        method: "DELETE",
        adminCreds,
    });
}

export async function getConfig(adminCreds: AdminCreds) {
    const { res } = await apiFetch(`/config`, {
        method: "GET",
        adminCreds,
    });
    return (await res.json()) as ConfigOut;
}

export async function patchConfig(patch: ConfigPatch, adminCreds: AdminCreds) {
    const { res } = await apiFetch(`/config`, {
        method: "PATCH",
        adminCreds,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    return (await res.json()) as ConfigOut;
}

export async function renewToken(req: RenewTokenReq) {
    const { res } = await apiFetch(`/auth/token/renew`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
    });
    return (await res.json()) as RenewTokenRes;
}

export async function health() {
    const { res } = await apiFetch(`/health`, { method: "GET" });
    return (await res.json()) as { ok: boolean };
}
