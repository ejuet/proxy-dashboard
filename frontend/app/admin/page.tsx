"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AdminCreds, loadCreds, saveCreds, clearCreds } from "@/lib/auth";
import { getConfig, patchConfig, renewToken, health } from "@/lib/api";
import { ArrowLeft, Shield, Save, KeyRound, PlugZap, LogOut } from "lucide-react";

export default function AdminPage() {
    const [creds, setCreds] = useState<AdminCreds | null>(null);

    // Basic auth form
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");

    // Config
    const [npmBase, setNpmBase] = useState("");
    const [configStatus, setConfigStatus] = useState<string | null>(null);

    // Token renew
    const [identity, setIdentity] = useState("");
    const [secret, setSecret] = useState("");
    const [tokenStatus, setTokenStatus] = useState<string | null>(null);

    // Health
    const [healthStatus, setHealthStatus] = useState<string | null>(null);

    useEffect(() => {
        const c = loadCreds();
        if(c) {
            setCreds(c);
            setUsername(c.username);
            setPassword(c.password);
        }
    }, []);

    async function loadConfig() {
        setConfigStatus(null);
        if(!creds) {
            setConfigStatus("Login required for /config");
            return;
        }
        try {
            const cfg = await getConfig(creds);
            setNpmBase(cfg.npm_base_url);
            setConfigStatus("Loaded.");
        } catch(e: any) {
            setConfigStatus(e?.message || "Failed to load config");
        }
    }

    async function saveConfig() {
        setConfigStatus(null);
        if(!creds) {
            setConfigStatus("Login required for /config");
            return;
        }
        try {
            const cfg = await patchConfig({ npm_base_url: npmBase }, creds);
            setNpmBase(cfg.npm_base_url);
            setConfigStatus("Saved.");
        } catch(e: any) {
            setConfigStatus(e?.message || "Failed to save config");
        }
    }

    async function doRenewToken() {
        setTokenStatus(null);
        try {
            await renewToken({ identity, secret });
            setTokenStatus("Token renewed and saved by backend.");
            setSecret("");
        } catch(e: any) {
            setTokenStatus(e?.message || "Failed to renew token");
        }
    }

    async function checkHealth() {
        setHealthStatus(null);
        try {
            const h = await health();
            setHealthStatus(h.ok ? "Backend OK." : "Backend says not ok.");
        } catch(e: any) {
            setHealthStatus(e?.message || "Health check failed");
        }
    }

    function login() {
        const c = { username: username.trim(), password };
        if(!c.username || !c.password) return;
        saveCreds(c);
        setCreds(c);
    }

    function logout() {
        clearCreds();
        setCreds(null);
        setPassword("");
    }

    return (
        <div className="mx-auto max-w-4xl px-4 py-8">
            <div className="flex items-center justify-between">
                <Link href="/" className="btn">
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back
                </Link>
                <button className="btn" onClick={checkHealth}>
                    <PlugZap className="h-4 w-4 mr-2" />
                    Health
                </button>
            </div>

            {healthStatus && (
                <div className="mt-3 rounded-2xl glass soft-ring p-4 text-sm text-zinc-200">
                    {healthStatus}
                </div>
            )}

            <div className="mt-6 rounded-3xl glass soft-ring p-6">
                <div className="flex items-center gap-3">
                    <div className="h-11 w-11 rounded-2xl bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center">
                        <Shield className="h-5 w-5 text-indigo-200" />
                    </div>
                    <div>
                        <h1 className="text-xl font-semibold">Admin tools</h1>
                        <p className="text-sm text-zinc-400 mt-1">
                            Uses HTTP Basic for admin-only endpoints.
                        </p>
                    </div>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                        <div className="text-sm font-semibold">Admin login</div>
                        <p className="mt-1 text-xs text-zinc-400">
                            Stored in sessionStorage (browser tab).
                        </p>

                        <div className="mt-3 grid grid-cols-1 gap-3">
                            <div>
                                <div className="label mb-1">Username</div>
                                <input
                                    className="input"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    placeholder="ADMIN_USER"
                                />
                            </div>
                            <div>
                                <div className="label mb-1">Password</div>
                                <input
                                    className="input"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="ADMIN_PASS"
                                />
                            </div>

                            <div className="flex gap-2">
                                <button className="btn btn-primary" onClick={login}>
                                    Login
                                </button>
                                <button className="btn" onClick={logout} disabled={!creds}>
                                    <LogOut className="h-4 w-4 mr-2" />
                                    Logout
                                </button>
                            </div>

                            <div className="text-xs text-zinc-400">
                                Status:{" "}
                                <span className="text-zinc-200">
                                    {creds ? `signed in as ${creds.username}` : "not signed in"}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                        <div className="text-sm font-semibold">Renew NPM token</div>
                        <p className="mt-1 text-xs text-zinc-400">
                            Calls <code>/auth/token/renew</code> (no admin required).
                        </p>

                        <div className="mt-3 grid grid-cols-1 gap-3">
                            <div>
                                <div className="label mb-1">NPM identity</div>
                                <input
                                    className="input"
                                    value={identity}
                                    onChange={(e) => setIdentity(e.target.value)}
                                    placeholder="email / username"
                                />
                            </div>
                            <div>
                                <div className="label mb-1">NPM secret</div>
                                <input
                                    className="input"
                                    type="password"
                                    value={secret}
                                    onChange={(e) => setSecret(e.target.value)}
                                    placeholder="password"
                                />
                            </div>

                            <button className="btn btn-primary" onClick={doRenewToken}>
                                <KeyRound className="h-4 w-4 mr-2" />
                                Renew token
                            </button>

                            {tokenStatus && (
                                <div className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm text-zinc-200">
                                    {tokenStatus}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                <div className="mt-4 rounded-2xl bg-white/5 border border-white/10 p-4">
                    <div className="flex items-center justify-between gap-2">
                        <div>
                            <div className="text-sm font-semibold">Runtime config</div>
                            <p className="mt-1 text-xs text-zinc-400">
                                View/update <code>npm_base_url</code> via admin endpoints.
                            </p>
                        </div>
                        <button className="btn" onClick={loadConfig} disabled={!creds}>
                            Load
                        </button>
                    </div>

                    <div className="mt-3">
                        <div className="label mb-1">NPM base URL</div>
                        <input
                            className="input"
                            value={npmBase}
                            onChange={(e) => setNpmBase(e.target.value)}
                            placeholder="http://192.168.1.10:81"
                            disabled={!creds}
                        />
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                        <button className="btn btn-primary" onClick={saveConfig} disabled={!creds}>
                            <Save className="h-4 w-4 mr-2" />
                            Save
                        </button>
                        {configStatus && (
                            <span className="text-sm text-zinc-300">{configStatus}</span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
