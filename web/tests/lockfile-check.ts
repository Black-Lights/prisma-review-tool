/**
 * Static consistency check of package-lock.json against package.json, the
 * same kind of mismatch `npm ci` refuses to install (WEB#1), plus the supply
 * chain audit rules: every tarball from registry.npmjs.org with an integrity
 * hash, and no install scripts beyond the reviewed ones.
 */

type Deps = Record<string, string>;

interface LockEntry {
  version?: string;
  resolved?: string;
  integrity?: string;
  link?: boolean;
  hasInstallScript?: boolean;
  dependencies?: Deps;
  optionalDependencies?: Deps;
  devDependencies?: Deps;
  peerDependencies?: Deps;
  peerDependenciesMeta?: Record<string, { optional?: boolean }>;
  bundleDependencies?: string[] | boolean;
}

export interface PackageJson {
  dependencies?: Deps;
  devDependencies?: Deps;
}

export interface Lockfile {
  lockfileVersion: number;
  packages: Record<string, LockEntry>;
}

// Packages whose install scripts were reviewed (same set as main's lockfile).
export const ALLOWED_INSTALL_SCRIPTS = ["node_modules/sharp", "node_modules/unrs-resolver"];

type Version = { nums: [number, number, number]; pre: string[] };

function parseVersion(v: string): Version | null {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$/.exec(v.trim());
  if (!m) return null;
  return { nums: [Number(m[1]), Number(m[2]), Number(m[3])], pre: m[4] ? m[4].split(".") : [] };
}

function compare(a: Version, b: Version): number {
  for (let i = 0; i < 3; i++) if (a.nums[i] !== b.nums[i]) return a.nums[i] - b.nums[i];
  if (!a.pre.length || !b.pre.length) return b.pre.length - a.pre.length;
  for (let i = 0; i < Math.max(a.pre.length, b.pre.length); i++) {
    const x = a.pre[i];
    const y = b.pre[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (x === y) continue;
    const nx = /^\d+$/.test(x);
    const ny = /^\d+$/.test(y);
    if (nx && ny) return Number(x) - Number(y);
    if (nx !== ny) return nx ? -1 : 1;
    return x < y ? -1 : 1;
  }
  return 0;
}

// Does `version` satisfy one comparator such as "^1.2.3", ">=4", "~1.2", "1.x" or "*"?
function comparatorOk(version: Version, comp: string): boolean {
  if (comp === "" || comp === "*" || comp === "x") return true;
  const m = /^(\^|~|>=|<=|>|<|=)?\s*v?(\d+|x|\*)(?:\.(\d+|x|\*))?(?:\.(\d+|x|\*))?(-[0-9A-Za-z.-]+)?$/.exec(comp);
  if (!m) throw new Error(`unsupported range comparator: ${comp}`);
  const op = m[1] ?? "";
  const wild = (s: string | undefined) => s === undefined || s === "x" || s === "*";
  const major = Number(m[2]);
  const parts = [m[2], m[3], m[4]];
  const base = parseVersion(
    `${wild(parts[0]) ? 0 : parts[0]}.${wild(parts[1]) ? 0 : parts[1]}.${wild(parts[2]) ? 0 : parts[2]}${m[5] ?? ""}`,
  )!;
  const c = compare(version, base);
  if (op === ">=") return c >= 0;
  if (op === ">") return c > 0;
  if (op === "<=") return c <= 0;
  if (op === "<") return c < 0;
  let upper: Version;
  if (op === "^") {
    if (major > 0 || wild(parts[1])) upper = { nums: [major + 1, 0, 0], pre: ["0"] };
    else if (Number(parts[1]) > 0 || wild(parts[2])) upper = { nums: [0, Number(parts[1]) + 1, 0], pre: ["0"] };
    else upper = { nums: [0, 0, Number(parts[2]) + 1], pre: ["0"] };
  } else if (op === "~" || wild(parts[2])) {
    upper = wild(parts[1])
      ? { nums: [major + 1, 0, 0], pre: ["0"] }
      : { nums: [major, Number(parts[1]) + 1, 0], pre: ["0"] };
  } else {
    return c === 0; // exact version
  }
  return c >= 0 && compare(version, upper) < 0;
}

export function satisfies(version: string, range: string): boolean {
  const v = parseVersion(version);
  if (!v) return false;
  return range.split("||").some((alt) => {
    const comps = alt.trim().replace(/(>=|<=|>|<|=|\^|~)\s+/g, "$1").split(/\s+/);
    return comps.every((comp) => comparatorOk(v, comp));
  });
}

// Node resolution inside the lock tree: nearest node_modules/<name> walking up.
function resolveDep(packages: Lockfile["packages"], from: string, name: string): LockEntry | null {
  let base = from;
  for (;;) {
    const key = `${base ? `${base}/` : ""}node_modules/${name}`;
    if (packages[key]) return packages[key];
    if (!base) return null;
    const idx = base.lastIndexOf("/node_modules/");
    base = idx >= 0 ? base.slice(0, idx) : "";
  }
}

export function lockfileProblems(pkg: PackageJson, lock: Lockfile): string[] {
  const problems: string[] = [];
  const root = lock.packages[""] ?? {};
  for (const field of ["dependencies", "devDependencies"] as const) {
    const want = pkg[field] ?? {};
    const have = root[field] ?? {};
    for (const name of new Set([...Object.keys(want), ...Object.keys(have)])) {
      if (want[name] !== have[name]) {
        problems.push(`root ${field}.${name}: package.json ${want[name]} vs lockfile ${have[name]}`);
      }
    }
  }

  for (const [path, entry] of Object.entries(lock.packages)) {
    if (entry.link) continue;
    const checks: [Deps | undefined, boolean][] = [
      [entry.dependencies, false],
      [entry.optionalDependencies, false],
      [entry.peerDependencies, true],
    ];
    if (path === "") checks.push([entry.devDependencies, false]);
    for (const [deps, peer] of checks) {
      for (const [name, range] of Object.entries(deps ?? {})) {
        if (peer && entry.peerDependenciesMeta?.[name]?.optional) continue;
        // Bundled dependencies ship inside the package tarball, not in the lock tree.
        const bundled = entry.bundleDependencies;
        if (bundled === true || (Array.isArray(bundled) && bundled.includes(name))) continue;
        if (range.startsWith("npm:") || range.includes("/") || range.includes(":")) continue;
        const dep = resolveDep(lock.packages, path, name);
        if (!dep) {
          problems.push(`${path || "<root>"} needs ${name}@${range}: missing from lockfile`);
        } else if (dep.version && !satisfies(dep.version, range)) {
          problems.push(`${path || "<root>"} needs ${name}@${range}: lockfile has ${dep.version}`);
        }
      }
    }
    if (path !== "") {
      if (!entry.resolved?.startsWith("https://registry.npmjs.org/")) {
        problems.push(`${path}: resolved from ${entry.resolved ?? "nowhere"}`);
      }
      if (!entry.integrity?.startsWith("sha512-")) problems.push(`${path}: no sha512 integrity`);
      if (entry.hasInstallScript && !ALLOWED_INSTALL_SCRIPTS.includes(path)) {
        problems.push(`${path}: unreviewed install script`);
      }
    }
  }
  return problems;
}
