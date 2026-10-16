/**
 * Venue filter entries: an ISSN filters server-side, anything else is matched
 * as a journal name (often only locally, after the call). The backend tells
 * them apart with this exact pattern (prisma_review/search/filters.py,
 * _ISSN_RE), so an ISSN typed without its hyphen silently became a name filter
 * that dropped almost every record (WEB#6).
 */
export const ISSN_RE = /^\d{4}-\d{3}[\dxX]$/;

// Hyphen look-alikes people paste from PDFs and web pages (U+2010..U+2015, U+2212).
const DASHES = /[‐-―−]/g;

export function isIssn(venue: string): boolean {
  return ISSN_RE.test(venue);
}

/** Normalise a venue entry: ISSNs to NNNN-NNNX (uppercase X), names trimmed. */
export function normalizeVenue(raw: string): string {
  const value = raw.trim().replace(/\s+/g, " ");
  const compact = value
    .replace(/^issn[:\s]*/i, "")
    .replace(DASHES, "-")
    .replace(/[\s-]/g, "");
  if (/^\d{7}[\dxX]$/.test(compact)) {
    return `${compact.slice(0, 4)}-${compact.slice(4).toUpperCase()}`;
  }
  return value;
}
