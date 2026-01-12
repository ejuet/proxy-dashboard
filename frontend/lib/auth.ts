export type AdminCreds = { username: string; password: string };

const KEY = "dash_admin_creds_v1";

export function saveCreds(creds: AdminCreds) {
    sessionStorage.setItem(KEY, JSON.stringify(creds));
}

export function loadCreds(): AdminCreds | null {
    try {
        const raw = sessionStorage.getItem(KEY);
        if(!raw) return null;
        const parsed = JSON.parse(raw);
        if(
            typeof parsed?.username === "string" &&
            typeof parsed?.password === "string"
        ) {
            return parsed;
        }
        return null;
    } catch {
        return null;
    }
}

export function clearCreds() {
    sessionStorage.removeItem(KEY);
}

export function basicAuthHeader(creds: AdminCreds): string {
    // btoa is fine in browser
    return `Basic ${btoa(`${creds.username}:${creds.password}`)}`;
}
