/**
 * Source-level guards for UI findings that have no logic to unit test
 * (accessibility attributes, colour tokens, small hygiene items). Each one
 * failed on the code reviewed at b1bfdb6.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(import.meta.dirname, "..", "src");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");

function sourceFiles(dir = SRC): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(tsx?|css)$/.test(name) ? [full] : [];
  });
}

// Opening tags of every <button ...> together with their content up to </button>.
function buttons(src: string): string[] {
  return src.match(/<button\b[\s\S]*?<\/button>/g) ?? [];
}

test("WEB#10: sortable headers are buttons, not clickable <th> cells", () => {
  const src = read("app/papers/page.tsx");
  assert.doesNotMatch(src, /<th\b[^>]*\bonClick=/);
  assert.match(src, /<button\s+type="button"[\s\S]{0,200}?handleSort\(col\.key\)/);
  assert.match(src, /aria-sort=\{showSearch \? undefined/);
});

test("WEB#11: page size is a select, not a number box that fetches on every keystroke", () => {
  const src = read("app/papers/page.tsx");
  assert.doesNotMatch(src, /type="number"/);
  assert.match(src, /PER_PAGE_OPTIONS\.map/);
});

test("WEB#12: no raw Tailwind palette colours, sources use theme tokens", () => {
  const raw = /\b(?:bg|text|border|ring|from|to|via)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/;
  const offenders = sourceFiles()
    .filter((f) => raw.test(readFileSync(f, "utf8")))
    .map((f) => relative(SRC, f));
  assert.deepEqual(offenders, []);
  assert.match(read("app/globals.css"), /--color-source-crossref:/);
});

test("WEB#16: settings lists document types it does not know so they can be removed", () => {
  assert.match(read("app/settings/page.tsx"), /splitDocTypes\(/);
});

test("WEB#17: icon-only remove buttons have an aria-label, toggles expose their state", () => {
  const settings = read("app/settings/page.tsx");
  const unlabelled = buttons(settings).filter((b) => /<X\b/.test(b) && !/aria-label=/.test(b));
  assert.deepEqual(unlabelled, []);
  assert.match(settings, /aria-pressed=\{active\}/);
  assert.doesNotMatch(settings, /className="relative group">\s*<button className/);
  const screening = read("app/screening/page.tsx");
  assert.match(screening, /aria-expanded=\{showReport\}/);
  assert.match(screening, /aria-expanded=\{showRescreen\}/);
  assert.match(screening, /aria-pressed=\{filter === opt\.value\}/);
});

test("WEB#17: info tooltips also open on keyboard focus", () => {
  for (const rel of ["app/settings/page.tsx", "app/screening/page.tsx"]) {
    const src = read(rel);
    const hoverOnly = src.match(/group-hover:visible(?![^"]*group-focus-within:visible)[^"]*"/g) ?? [];
    assert.deepEqual(hoverOnly, [], `${rel} has hover-only tooltips`);
  }
});

test("WEB#18: hygiene items from the review", () => {
  const papers = read("app/papers/page.tsx");
  assert.doesNotMatch(papers, /sortable:/, "unused sortable field");
  assert.ok(
    papers.indexOf("const showSearch") < papers.indexOf("const handleSort"),
    "handleSort reads showSearch before it is declared",
  );
  assert.doesNotMatch(read("components/ReportPanel.tsx"), /pipeline-progress-report/);
  const withEnv = sourceFiles()
    .filter((f) => readFileSync(f, "utf8").includes("NEXT_PUBLIC_API_URL"))
    .map((f) => relative(SRC, f).replace(/\\/g, "/"));
  assert.deepEqual(withEnv, ["lib/api.ts"], "the API base URL is defined once, in lib/api.ts");
});

test("PIPE#14 / WEB#7: the provider uses the scoped realtime client", () => {
  const src = read("app/providers.tsx");
  assert.match(src, /startRealtimeSync\(/);
  assert.doesNotMatch(src, /new EventSource\(/);
});

test("R-20: the required-keywords tooltip states the whole-word rule the backend applies", () => {
  const src = read("app/settings/page.tsx");
  const tip = src.slice(src.indexOf('label="About required keywords"'));
  const body = tip.slice(0, tip.indexOf("</InfoTip>"));
  assert.doesNotMatch(body, /substring/i);
  assert.match(body, /whole word or phrase/);
  assert.match(body, /plural/);
});
