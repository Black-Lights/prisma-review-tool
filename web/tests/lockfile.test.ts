import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { lockfileProblems, satisfies, type Lockfile, type PackageJson } from "./lockfile-check.ts";

const WEB = join(import.meta.dirname, "..");
const readJson = <T,>(name: string): T => JSON.parse(readFileSync(join(WEB, name), "utf8")) as T;

test("WEB#1: package-lock.json matches package.json and passes the audit rules", () => {
  const problems = lockfileProblems(readJson<PackageJson>("package.json"), readJson<Lockfile>("package-lock.json"));
  assert.deepEqual(problems, []);
});

test("WEB#1 / WEB#18: next and eslint-config-next are pinned to the same exact version", () => {
  const pkg = readJson<PackageJson>("package.json");
  assert.match(pkg.dependencies?.next ?? "", /^\d+\.\d+\.\d+$/);
  assert.equal(pkg.devDependencies?.["eslint-config-next"], pkg.dependencies?.next);
});

test("WEB#1: the checker flags a dependency missing from the lockfile", () => {
  const lock: Lockfile = {
    lockfileVersion: 3,
    packages: {
      "": { dependencies: { a: "^1.0.0" } },
      "node_modules/a": {
        version: "1.2.0",
        resolved: "https://registry.npmjs.org/a/-/a-1.2.0.tgz",
        integrity: "sha512-x",
        optionalDependencies: { "@emnapi/runtime": "1.11.3" },
      },
    },
  };
  const problems = lockfileProblems({ dependencies: { a: "^1.0.0" } }, lock);
  assert.equal(problems.length, 1);
  assert.match(problems[0], /@emnapi\/runtime@1\.11\.3: missing/);
});

test("WEB#1: the checker flags off-registry tarballs and new install scripts", () => {
  const lock: Lockfile = {
    lockfileVersion: 3,
    packages: {
      "": {},
      "node_modules/evil": {
        version: "1.0.0",
        resolved: "https://example.com/evil.tgz",
        integrity: "sha512-x",
        hasInstallScript: true,
      },
    },
  };
  const problems = lockfileProblems({}, lock);
  assert.ok(problems.some((p) => p.includes("resolved from https://example.com")));
  assert.ok(problems.some((p) => p.includes("unreviewed install script")));
});

test("satisfies() covers the range forms used in the lockfile", () => {
  assert.ok(satisfies("1.11.3", "^1.4.0"));
  assert.ok(!satisfies("2.0.0", "^1.4.0"));
  assert.ok(satisfies("0.3.5", "^0.3.1"));
  assert.ok(!satisfies("0.4.0", "^0.3.1"));
  assert.ok(satisfies("1.2.9", "~1.2.3"));
  assert.ok(!satisfies("1.3.0", "~1.2.3"));
  assert.ok(satisfies("4.1.0", ">= 4.0.0 <5"));
  assert.ok(satisfies("3.9.9", "3.x.x || ^4"));
  assert.ok(satisfies("1.2.1", "1.2.1"));
  assert.ok(!satisfies("1.2.3", "1.2.1"));
  assert.ok(satisfies("16.2.6", "*"));
  assert.ok(satisfies("19.0.0-rc.1", "^19.0.0-rc.0"));
});

test("WEB#9: the Next config is the typed next.config.ts", () => {
  assert.ok(existsSync(join(WEB, "next.config.ts")), "next.config.ts is missing");
  assert.ok(!existsSync(join(WEB, "next.config.js")), "next.config.js should not exist next to next.config.ts");
  const src = readFileSync(join(WEB, "next.config.ts"), "utf8");
  assert.match(src, /import type \{ NextConfig \} from "next"/);
  assert.match(src, /const nextConfig: NextConfig =/);
});
