import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SECRET_MASK,
  configConflict,
  configEditedSince,
  maskSecrets,
  savePayload,
  secretDisplayValue,
  secretInputValue,
  secretState,
  settingsView,
  splitDocTypes,
  versionMtimeMs,
} from "../src/lib/configForm.ts";

test("WEB#3: the save payload carries the version the form was loaded from", () => {
  const draft = { project: { name: "A" }, _version: "111-10" };
  const payload = savePayload(draft, "222-20");
  assert.equal(payload._version, "222-20");
  assert.equal(draft._version, "111-10", "the draft itself is not mutated");
  assert.deepEqual(savePayload(draft, null), { project: { name: "A" } });
});

test("WEB#3: a 409 config_changed error is recognised, other errors are not", () => {
  const err = {
    status: 409,
    detail: { error: "config_changed", message: "The config changed on disk.", current_version: "333-30" },
  };
  assert.deepEqual(configConflict(err), { message: "The config changed on disk.", currentVersion: "333-30" });
  assert.equal(configConflict({ status: 409, detail: "Cannot switch while pipeline is running" }), null);
  assert.equal(configConflict({ status: 500, detail: { error: "config_changed" } }), null);
  assert.equal(configConflict(new Error("network")), null);
  assert.equal(configConflict(null), null);
});

test("WEB#13 client: a stored key shows as an empty box, never as the mask text", () => {
  assert.equal(secretDisplayValue(SECRET_MASK), "");
  assert.equal(secretDisplayValue("abc"), "abc");
  assert.equal(secretDisplayValue(undefined), "");
});

test("WEB#13 client: emptying the box keeps a stored key; typing replaces it", () => {
  assert.equal(secretInputValue("", SECRET_MASK), SECRET_MASK);
  assert.equal(secretInputValue("new-key", SECRET_MASK), "new-key");
  assert.equal(secretInputValue("", ""), "");
  assert.equal(secretInputValue("", undefined), "");
});

test("WEB#13 client: secret states for the badge next to the key inputs", () => {
  assert.equal(secretState(SECRET_MASK, SECRET_MASK), "stored");
  assert.equal(secretState("", SECRET_MASK), "removed");
  assert.equal(secretState("typed", SECRET_MASK), "new");
  assert.equal(secretState("", ""), "unset");
  assert.equal(secretState(undefined, undefined), "unset");
});

test("WEB#3: secrets typed into the form are masked before going into the query cache", () => {
  const masked = maskSecrets({
    api_keys: { scopus: "real-key", openalex_key: "", openalex_email: "a@b.c" },
    project: { name: "A" },
  });
  assert.deepEqual(masked.api_keys, { scopus: SECRET_MASK, openalex_key: "", openalex_email: "a@b.c" });
  assert.deepEqual(maskSecrets({ project: { name: "A" } }), { project: { name: "A" } });
});

test("WEB#8: the config version encodes the file mtime, used to flag edits after the last run", () => {
  assert.equal(versionMtimeMs("1760000000123456789-512"), 1760000000123);
  assert.equal(versionMtimeMs(null), null);
  assert.equal(versionMtimeMs("garbage"), null);
  const run = new Date(1760000000000).toISOString();
  assert.equal(configEditedSince("1760000000123456789-512", run), true);
  assert.equal(configEditedSince("1759999999000000000-512", run), false);
  assert.equal(configEditedSince("1760000000123456789-512", null), false);
});

test("WEB#16: document types the UI does not know are reported so they can be shown and removed", () => {
  const known = ["journal-article", "review"] as const;
  assert.deepEqual(splitDocTypes(["review", "article", "journal-article", "letter"], known), {
    known: ["review", "journal-article"],
    unknown: ["article", "letter"],
  });
  assert.deepEqual(splitDocTypes(undefined, known), { known: [], unknown: [] });
});

test("R-22: a form with unsaved edits stays on its project when another one becomes active", () => {
  const alpha = { project: "alpha", label: "Alpha", config: { _version: "1-1" } };
  const alphaNewer = { project: "alpha", label: "Alpha", config: { _version: "2-2" } };
  const beta = { project: "beta", label: "Beta review", config: { _version: "9-9" } };

  // Clean: follow the active project, wait while it loads.
  assert.deepEqual(settingsView(null, null), { kind: "loading" });
  assert.deepEqual(settingsView(null, beta), { kind: "form", form: beta, movedTo: null });
  // Dirty on the active project: live config (so a change on disk is seen).
  assert.deepEqual(settingsView(alpha, alphaNewer), { kind: "form", form: alphaNewer, movedTo: null });
  // Dirty while the queries reload after a switch: keep the edits, never a spinner.
  assert.deepEqual(settingsView(alpha, null), { kind: "form", form: alpha, movedTo: null });
  // Dirty after the switch: keep the edits and say which project is active now.
  assert.deepEqual(settingsView(alpha, beta), { kind: "form", form: alpha, movedTo: "Beta review" });
});
