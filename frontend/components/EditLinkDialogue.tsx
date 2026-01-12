"use client";

import { LinkOut, LinkMetaPatch } from "@/lib/api";
import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

export function EditLinkDialog({
    open,
    link,
    onClose,
    onSave,
    onDeleteMeta,
}: {
    open: boolean;
    link: LinkOut | null;
    onClose: () => void;
    onSave: (patch: LinkMetaPatch) => Promise<void>;
    onDeleteMeta: () => Promise<void>;
}) {
    const [name, setName] = useState("");
    const [emoji, setEmoji] = useState("");
    const [description, setDescription] = useState("");
    const [hidden, setHidden] = useState(false);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    const domain = useMemo(
        () => link?.domain_names?.[0] || "",
        [link]
    );

    useEffect(() => {
        if(!link) return;
        setName(link.name || "");
        setEmoji(link.emoji || "");
        setDescription(link.description || "");
        setHidden(Boolean(link.hidden));
        setErr(null);
        setBusy(false);
    }, [link, open]);

    if(!open || !link) return null;

    async function doSave() {
        setBusy(true);
        setErr(null);
        try {
            // Empty strings become null to “clear” fields on backend
            await onSave({
                name: name.trim() ? name.trim() : null,
                emoji: emoji.trim() ? emoji.trim() : null,
                description: description.trim() ? description.trim() : null,
                hidden,
            });
            onClose();
        } catch(e: any) {
            setErr(e?.message || "Failed");
        } finally {
            setBusy(false);
        }
    }

    async function doDelete() {
        if(!confirm("Delete dashboard metadata for this link? (Reverts to defaults)"))
            return;
        setBusy(true);
        setErr(null);
        try {
            await onDeleteMeta();
            onClose();
        } catch(e: any) {
            setErr(e?.message || "Failed");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
                className="absolute inset-0 bg-black/70"
                onClick={() => !busy && onClose()}
            />
            <div className="relative w-full max-w-lg rounded-2xl glass soft-ring p-5">
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <h2 className="text-lg font-semibold">Edit link</h2>
                        <p className="text-sm text-zinc-400 mt-1">
                            {domain || `ID ${link.id}`}
                        </p>
                    </div>
                    <button
                        onClick={() => !busy && onClose()}
                        className="rounded-xl p-2 hover:bg-white/10 border border-white/10"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4">
                    <div className="grid grid-cols-3 gap-3">
                        <div className="col-span-2">
                            <div className="label mb-1">Name</div>
                            <input
                                className="input"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="Pretty title"
                            />
                        </div>
                        <div>
                            <div className="label mb-1">Emoji</div>
                            <input
                                className="input"
                                value={emoji}
                                onChange={(e) => setEmoji(e.target.value)}
                                placeholder="🚀"
                                maxLength={8}
                            />
                        </div>
                    </div>

                    <div>
                        <div className="label mb-1">Description</div>
                        <textarea
                            className="input min-h-[96px] resize-none"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="What is this service?"
                            maxLength={500}
                        />
                    </div>

                    <label className="flex items-center gap-2 text-sm text-zinc-200">
                        <input
                            type="checkbox"
                            checked={hidden}
                            onChange={(e) => setHidden(e.target.checked)}
                            className="h-4 w-4 rounded border-white/20 bg-white/10"
                        />
                        Hidden (only shows for admin with include hidden)
                    </label>

                    {err && (
                        <div className="rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                            {err}
                        </div>
                    )}

                    <div className="flex items-center justify-between gap-3">
                        <button
                            onClick={doDelete}
                            disabled={busy}
                            className="btn"
                        >
                            Delete metadata
                        </button>
                        <div className="flex gap-2">
                            <button
                                onClick={onClose}
                                disabled={busy}
                                className="btn"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={doSave}
                                disabled={busy}
                                className="btn btn-primary"
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
