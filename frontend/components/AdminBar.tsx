"use client";

import { useEffect, useState } from "react";
import { AdminCreds, clearCreds, loadCreds, saveCreds } from "@/lib/auth";
import { Shield, LogOut, Eye, EyeOff } from "lucide-react";

export function AdminBar({
    includeHidden,
    setIncludeHidden,
    onCredsChanged,
}: {
    includeHidden: boolean;
    setIncludeHidden: (v: boolean) => void;
    onCredsChanged: (creds: AdminCreds | null) => void;
}) {
    const [creds, setCreds] = useState<AdminCreds | null>(null);
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [showPw, setShowPw] = useState(false);

    // Load once. Do NOT call onCredsChanged here (avoids update loops).
    useEffect(() => {
        const c = loadCreds();
        setCreds(c);
    }, []);

    function login() {
        const c = { username: username.trim(), password };
        if(!c.username || !c.password) return;
        saveCreds(c);
        setCreds(c);
        onCredsChanged(c);
    }

    function logout() {
        clearCreds();
        setCreds(null);
        onCredsChanged(null);
    }

    return (
        <div className="rounded-2xl glass soft-ring p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2">
                <div className="h-10 w-10 rounded-2xl bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center">
                    <Shield className="h-5 w-5 text-indigo-200" />
                </div>
                <div>
                    <div className="text-sm font-semibold">Admin</div>
                    <div className="text-xs text-zinc-400">
                        {creds ? `Signed in as ${creds.username}` : "Enter HTTP Basic credentials"}
                    </div>
                </div>
            </div>

            <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="checkbox"
                        checked={includeHidden}
                        onChange={(e) => setIncludeHidden(e.target.checked)}
                        disabled={!creds}
                        className="h-4 w-4 rounded border-white/20 bg-white/10 disabled:opacity-50"
                    />
                    Include hidden
                </label>

                {!creds ? (
                    <div className="flex gap-2 items-center">
                        <input
                            className="input w-40"
                            placeholder="ADMIN_USER"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                        />
                        <div className="relative">
                            <input
                                className="input w-40 pr-10"
                                placeholder="ADMIN_PASS"
                                type={showPw ? "text" : "password"}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                            />
                            <button
                                type="button"
                                onClick={() => setShowPw((v) => !v)}
                                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 hover:bg-white/10 border border-white/10"
                                aria-label="toggle password"
                            >
                                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                        </div>
                        <button className="btn btn-primary" onClick={login}>
                            Login
                        </button>
                    </div>
                ) : (
                    <button className="btn" onClick={logout}>
                        <LogOut className="h-4 w-4 mr-2" />
                        Logout
                    </button>
                )}
            </div>
        </div>
    );
}
