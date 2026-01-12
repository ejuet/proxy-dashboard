export function bestLinkUrl(domainNames: string[]): string | null {
    if(!domainNames || domainNames.length === 0) return null;
    const d = domainNames[0]?.trim();
    if(!d) return null;

    // If it already looks like a URL
    if(d.startsWith("http://") || d.startsWith("https://")) return d;

    // Best effort: default to https
    return `https://${d}`;
}
