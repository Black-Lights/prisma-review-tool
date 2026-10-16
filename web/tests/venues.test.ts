import { test } from "node:test";
import assert from "node:assert/strict";
import { isIssn, normalizeVenue } from "../src/lib/venues.ts";

test("WEB#6: an unhyphenated ISSN (as Scopus returns it) becomes NNNN-NNNX", () => {
  assert.equal(normalizeVenue("00189219"), "0018-9219");
  assert.equal(normalizeVenue(" 1234567x "), "1234-567X");
  assert.ok(isIssn(normalizeVenue("00189219")));
});

test("WEB#6: common ISSN spellings normalise to the backend form", () => {
  assert.equal(normalizeVenue("1234-567x"), "1234-567X");
  assert.equal(normalizeVenue("ISSN 0018-9219"), "0018-9219");
  assert.equal(normalizeVenue("issn: 00189219"), "0018-9219");
  assert.equal(normalizeVenue("0018 9219"), "0018-9219");
  assert.equal(normalizeVenue("0018–9219"), "0018-9219"); // en dash
});

test("WEB#6: journal names are kept as typed (trimmed)", () => {
  assert.equal(normalizeVenue("  IEEE Transactions on Geoscience  "), "IEEE Transactions on Geoscience");
  assert.equal(normalizeVenue("Nature"), "Nature");
  assert.ok(!isIssn("Nature"));
  // Too short to be an ISSN: stays a name, and the chip tag says so.
  assert.equal(normalizeVenue("0018921"), "0018921");
  assert.ok(!isIssn("0018921"));
});

test("WEB#6: isIssn uses the backend regex (^\\d{4}-\\d{3}[\\dxX]$)", () => {
  assert.ok(isIssn("0018-9219"));
  assert.ok(isIssn("1234-567X"));
  assert.ok(isIssn("1234-567x"));
  assert.ok(!isIssn("00189219"));
  assert.ok(!isIssn("1234-5678 "));
});
