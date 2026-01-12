"use client";

import { LinkOut } from "@/lib/api";
import { bestLinkUrl } from "@/lib/url";
import { ExternalLink, Lock } from "lucide-react";

export function LinkCard({
    link,
    adminMode,
    onEdit,
}: {
    link: LinkOut;
    adminMode?: boolean;
    onEdit?: (link: LinkOut) => void;
}) {
    const url = bestLinkUrl(link.domain_names);
    const title = link.name || link.domain_names?.[0] || `Link #${link.id}`;
    const emoji = link.emoji || "🔗";
    const desc = link.description || "";
    const secondary = `${link.forward_host ?? "—"}:${link.forward_port ?? "—"}`;

    return (
        <div className="group relative">
            <a
                href={url || "#"}
                onClick={(e) => {
                    if(!url) e.preventDefault();
                }}
                target="_blank"
                rel="noreferrer"
                className="block h-full rounded-2xl glass soft-ring p-5 transition
                   hover:translate-y-[-2px] hover:bg-white/7 hover:ring-white/15"
            >
                <div className="flex items-start gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/7 border border-white/10 text-xl">
                        {emoji}
                    </div>

                    <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                            <h3 className="truncate text-base font-semibold tracking-tight">
                                {title}
                            </h3>
                            {link.hidden && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-200 border border-amber-500/20">
                                    <Lock className="h-3.5 w-3.5" />
                                    hidden
                                </span>
                            )}
                        </div>

                        {
                            <p className="mt-1 line-clamp-2 text-sm text-zinc-300/90">
                                {desc || <br />}
                            </p>
                        }
                        <div className="mt-4 flex items-center justify-between gap-3">
                            <div className="min-w-0">
                                <p className="truncate text-xs text-zinc-400">
                                    {link.domain_names?.[0] || "—"}
                                </p>
                                <p className="truncate text-[11px] text-zinc-500">
                                    {secondary}
                                </p>
                            </div>

                            <div className="flex items-center gap-2 text-zinc-400">
                                <ExternalLink className="h-4 w-4 opacity-70 group-hover:opacity-100" />
                            </div>
                        </div>
                    </div>
                </div>
            </a>

            {adminMode && onEdit && (
                <button
                    onClick={() => onEdit(link)}
                    className="absolute top-3 right-3 rounded-xl bg-black/30 hover:bg-black/45 border border-white/10 px-3 py-1.5 text-xs"
                >
                    Edit
                </button>
            )}
        </div>
    );
}
