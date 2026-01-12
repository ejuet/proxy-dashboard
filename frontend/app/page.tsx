"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminCreds } from "@/lib/auth";
import { getLinks, LinkOut, patchLinkMeta, deleteLinkMeta } from "@/lib/api";
import { LinkCard } from "@/components/LinkCard";
import { AdminBar } from "@/components/AdminBar";
import { EditLinkDialog } from "@/components/EditLinkDialogue";
import { RefreshCw, Settings2 } from "lucide-react";
import Link from "next/link";

export default function HomePage() {
  const [links, setLinks] = useState<LinkOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [adminCreds, setAdminCreds] = useState<AdminCreds | null>(null);
  const [includeHidden, setIncludeHidden] = useState(false);

  const [source, setSource] = useState<string | null>(null);
  const [cacheAt, setCacheAt] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<LinkOut | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if(!q) return links;
    return links.filter((l) => {
      const hay = [
        l.name,
        l.description,
        l.emoji,
        ...(l.domain_names || []),
        l.forward_host,
        String(l.forward_port ?? ""),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [links, query]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const { data, xLinksSource, xCacheAt } = await getLinks({
        includeHidden,
        adminCreds: includeHidden ? adminCreds ?? undefined : undefined,
      });
      setLinks(data);
      setSource(xLinksSource ?? null);
      setCacheAt(xCacheAt ?? null);
    } catch(e: any) {
      setErr(e?.message || "Failed to load links");
      setLinks([]);
      setSource(null);
      setCacheAt(null);
    } finally {
      setLoading(false);
    }
  }, [includeHidden, adminCreds]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveEdit(patch: any) {
    if(!editing || !adminCreds) throw new Error("Not admin");
    const updated = await patchLinkMeta(editing.id, patch, adminCreds);
    setLinks((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  }

  async function deleteMeta() {
    if(!editing || !adminCreds) throw new Error("Not admin");
    await deleteLinkMeta(editing.id, adminCreds);
    // easiest: reload to get default merge from backend
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Hero */}
      <div className="flex flex-col gap-6">
        <div className="rounded-3xl glass soft-ring p-7 overflow-hidden relative">
          <div className="absolute inset-0 opacity-60 pointer-events-none">
            <div className="absolute -top-40 -right-40 h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl" />
            <div className="absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-fuchsia-500/10 blur-3xl" />
          </div>

          <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
                Services
              </h1>

              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                {source && (
                  <span className="rounded-full bg-white/5 border border-white/10 px-3 py-1">
                    source: <span className="text-zinc-200">{source}</span>
                    {source === "cache" && cacheAt ? (
                      <span className="ml-2 text-zinc-400">
                        (fetched: {cacheAt})
                      </span>
                    ) : null}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Link className="btn" href="/admin">
                <Settings2 className="h-4 w-4 mr-2" />
              </Link>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="md:col-span-2 rounded-2xl glass soft-ring p-4">
            <div className="label mb-2">Search</div>
            <input
              className="input"
              placeholder="Find by name, domain, description, host, port…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <AdminBar
            includeHidden={includeHidden}
            setIncludeHidden={setIncludeHidden}
            onCredsChanged={(c) => setAdminCreds(c)}
          />
        </div>

        {/* Status */}
        {err && (
          <div className="rounded-2xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {err}
          </div>
        )}

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 9 }).map((_, i) => (
              <div
                key={i}
                className="h-[132px] rounded-2xl glass soft-ring animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((l) => (
              <LinkCard
                key={l.id}
                link={l}
                adminMode={Boolean(adminCreds)}
                onEdit={(link) => setEditing(link)}
              />
            ))}
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="rounded-2xl glass soft-ring p-10 text-center text-zinc-300">
            No matches.
          </div>
        )}
      </div>

      <EditLinkDialog
        open={Boolean(editing)}
        link={editing}
        onClose={() => setEditing(null)}
        onSave={saveEdit}
        onDeleteMeta={deleteMeta}
      />
    </div>
  );
}
