# Business Analysis — Review Findings

> Review of `docs/business-analysis.md`. These are flaws and improvement
> opportunities **visible in the analysis text itself** — internal
> inconsistencies, weak/overstated claims, and gaps a business-analysis handoff
> document should close. No source code was consulted for this review; each
> finding is derived from the document's own statements and diagrams.
>
> **Status (2026-08-15): all 18 findings resolved in `docs/business-analysis.md`.**
> Each finding below is annotated with where the fix landed. The document was also
> retitled *Technical & Product Analysis* and its appendices renumbered.

---

## A. Internal inconsistencies / contradictions

### 1. The most-played "nudge" is described as a tie-breaker, but the flow shows it changing buckets ✅ Resolved
- §4.3 / §11 / §13 insist the playlist bonus is "a tie-breaker, never a veto" and
  "★ helps but never forces a wrong version."
- But §6.2's flow applies the bonus (`PB: +0.02/playlist`) **before** the bucket
  decision (`BK: best ≥ 0.82…`). If bucketing reads the *bonused* score, a
  candidate at 0.78 + 3 playlists (0.84) could cross `AUTO_SCORE` (0.82) or
  `STRONG_THRESHOLD` — i.e. the nudge would change the *outcome*, not just ordering.
- The analysis never states whether bucketing uses the raw or bonused score.
- **Fix:** state explicitly that bucketing uses the raw facet score and the bonus
  affects ordering only (if that is the intent).
- **→ Resolved:** §4.3 and the §6.2 diagram now state the bonus affects ordering
  only; bucketing reads the raw facet score.

### 2. "3 buckets" vs "6 status chips" is never reconciled ✅ Resolved
- §5 glossary and §6.2 define exactly three buckets: `auto / ambiguous / unmatched`.
- §12 lists six chips: `auto / remembered / manual / pick one / skipped / no match`.
- The mapping (remembered/manual/skipped are UI states layered on the 3 buckets) is
  left implicit. A reader can't tell whether a "remembered" row is bucketed `auto`.
- **Fix:** add a small table mapping the 3 buckets to the 6 UI chips.
- **→ Resolved:** §12 now has a bucket→chip mapping table.

### 3. §8 "domain model" mixes stored entities with computed API/DTO fields ✅ Resolved
- `Library.track_count/source_count`, `Source.track_count`,
  `ImportedPlaylist.track_count` are shown as entity attributes, but §9's ER shows
  these are **derived** (`COUNT(...)`), not columns. `Preference.file_label` (used
  for the UI list) isn't shown at all.
- The class diagram conflates persistence with API response shapes.
- **Fix:** split "domain entities" from "API DTOs," or annotate the derived fields.
- **→ Resolved:** §8 tags fields `// derived` / `// DTO-only` (incl. new
  `Preference.file_label`) with an entities-vs-DTOs note.

---

## B. Overstated or unvalidated claims

### 4. The "privacy-by-architecture / never uploads anything" claim is overstated ✅ Resolved
- §1 says "never uploads anything," "everything runs on 127.0.0.1," "entirely local
  and private," and §13 lists "no uploads implied by the UI" as a hard constraint.
- Yet §7 and §10.2 show an **outbound HTTPS call to Spotify's embed page** carrying
  the playlist URL from the user's IP. That is an external network request; Spotify
  learns which playlists are fetched and when.
- **Fix:** scope the claim precisely ("never uploads *your library, choices, or
  files*") and acknowledge the one outbound call in the privacy discussion, not just
  the architecture diagram.
- **→ Resolved:** §1 scoped to your data + a new "one outbound call" paragraph.

### 5. Scraping Spotify's embed page is flagged as *fragile* but not as a *legal/ToS* risk ✅ Resolved
- §14 covers "scraping breaks if Spotify changes the page." It does **not** mention
  that scraping may violate Spotify's Terms of Service — a real business risk for a
  productionised, distributed app.
- **Fix:** add a legal/ToS risk row to the risk table.
- **→ Resolved:** §14 has a Spotify legal/ToS risk row.

### 6. The core business premise (§2.1) is stated more strongly than reality ✅ Resolved
- "streaming can't be beat-matched/cued reliably" — rekordbox now supports streaming
  integrations (TIDAL, Beatport, SoundCloud, Apple Music) with analysis/beatgrids.
  The ownership argument is still valid for gigs, but the flat claim is outdated.
- **Fix:** reframe as "owned files are required for offline/reliable performance and
  are independent of subscription state."
- **→ Resolved:** §2.1 reframed around ownership/offline reliability.

### 7. The multi-device persona conflicts with the single-machine architecture ✅ Resolved
- §3 says the "Multi-device DJ" has each device "match against its own files and
  remember its own choices," and §4.1 says "one library per device."
- But the app is a single local instance reading the **local** filesystem with a
  **local** SQLite and **no sync** (by design). A library named "Studio PC" created
  on the MacBook can only be populated via **XML import** (files not locally present)
  — folder-scan can't reach another machine's files, and preferences don't sync
  across machines.
- The analysis presents per-device libraries as one clean feature without
  reconciling: (a) run one app instance per machine → prefs/libraries don't share;
  or (b) one instance + XML imports → the exported `.m3u8` paths (§4.6, "path-based")
  point at *another* device's paths.
- **Fix:** state which model is intended and note the path-portability implication of
  exporting from an XML-imported library.
- **→ Resolved:** §3 note states intended model (a) and the path-portability caveat.

---

## C. Gaps a "business analysis" should close

### 8. No matching-accuracy metrics for what the doc calls "the core IP" ✅ Resolved
- §11 calls matching "the product's core IP," but there's no precision/recall, no
  golden-set results, no "auto is correct X% of the time," no false-positive rate for
  auto-selection. The single most important number for a handoff is missing.
- **Fix:** add an evaluation methodology plus current accuracy figures.
- **→ Resolved:** new §11.1 with evaluation method + metrics table (figures TBD).

### 9. No security considerations at all ✅ Resolved
- The app runs an unauthenticated HTTP server on localhost, accepts a
  **user-supplied folder path** (path traversal / arbitrary FS read scope), ingests
  **raw XML** (rekordbox import → XXE parsing risk) and raw playlist bodies, and
  fetches a **user-supplied URL** (SSRF surface). None of this appears in §14. A
  localhost-only app is still reachable by other local processes and by browser
  DNS-rebinding.
- **Fix:** add a security/hardening row (or section) to the risk table.
- **→ Resolved:** §14 has a security/hardening row (path/XXE/SSRF/DNS-rebinding).

### 10. Non-functional / performance claims are unquantified ✅ Resolved
- §1 "matches against it in seconds" and §10.1 "8 parse workers" give no scale
  envelope (library size, scan throughput, match latency at N tracks).
- **Fix:** quantify or mark as TBD — designers and packagers need bounds.
- **→ Resolved:** §14 performance/scale row added (bounds marked TBD).

### 11. No competitive / market context — the "business" content is thin ✅ Resolved
- The document is titled *Business Analysis* but is ~90% architecture/technical spec
  (component, ER, sequence diagrams, thresholds, API surface). There is no competitor
  scan (e.g. Lexicon DJ, Rekord Buddy, Mixo, existing Spotify→rekordbox utilities),
  no market sizing, no monetization/pricing, no success KPIs, no go-to-market.
- **Fix:** either retitle it "Technical & Product Analysis" or add a genuine business
  section.
- **→ Resolved:** retitled *Technical & Product Analysis* **and** added §15 (business
  & market context); appendices renumbered to §16/§17/§18.

### 12. The >100-track fallback has an unaddressed UX gap ✅ Resolved
- §4.4 / §14: playlists over ~100 tracks must use paste-text, which "has no track
  cap." But the analysis never says **how a user obtains** a 200-track list as text
  when the embed truncates at 100. The fallback isn't actually a workaround for the
  truncation problem it's paired with.
- **Fix:** note the gap or the intended source of the text list.
- **→ Resolved:** §4.4 note explains the gap and intended text source.

### 13. "Developer tunes thresholds" persona has no mechanism ✅ Resolved
- §3 and §11 assume thresholds get tuned, but they "live in `score.py`" — tuning
  means editing and redeploying source. No config surface, no per-library override.
- **Fix:** flag as a productionisation item (currently implied to be a feature).
- **→ Resolved:** §3 persona note + §11 note flag it as a productionisation item.

---

## D. Smaller nits

### 14. No doc metadata ✅ Resolved
- For a handoff artifact there's a "Status" line but no version number, date, or
  owner. **Fix:** add last-updated/version/owner.
- **→ Resolved:** header now has version/last-updated/owner/scope table.

### 15. ER relationships imply FKs that don't exist ✅ Resolved
- §9's ER draws `TRACKS ||--o{ PLAYLIST_TRACKS` and `PREFERENCES` relationships, but
  §8 states these references are **not foreign-keyed**. The crow's-foot lines imply
  enforced referential integrity that doesn't exist.
- **Fix:** annotate these as "logical, non-FK."
- **→ Resolved:** §9 draws them dashed + "logical, non-FK" and an integrity note.

### 16. §11 duration "~22 s tolerance" isn't derivable from the text ✅ Resolved
- Given only "1.0 within 3 s, linear decay," the decay slope isn't stated, so the
  "22 s" figure can't be reproduced by a reader.
- **Fix:** give the slope or drop the derived number.
- **→ Resolved:** §11 states the slope (0.0 at ~45s), making ±22s derivable.

### 17. §11 lists `AUTO_MARGIN` but §6.2's diagram omits it ✅ Resolved
- §11 lists `AUTO_MARGIN` ("best must beat 2nd by this"), but §6.2's diagram only
  shows the ≥0.82 / version / duration gates.
- **Fix:** align the diagram with the constant list, or note the omission is a
  deliberate simplification.
- **→ Resolved:** §6.2 diagram now includes the "beats 2nd by ≥ 0.10 margin" gate.

### 18. Implementation-detail leakage ✅ Resolved
- The "Generation" counter (glossary + §7) and the ActiveLibrary singleton are
  internal caching mechanics surfacing in a business/domain document.
- **Fix:** move to an "implementation notes" appendix so the domain model stays
  conceptual.
- **→ Resolved:** moved to §18 "Appendix C — Implementation notes"; §5 glossary
  points there.

---

## Priority summary

| # | Finding | Type | Impact | Status |
|---|---|---|---|---|
| 1 | Nudge tie-breaker vs bucket change | Contradiction | High | ✅ Resolved |
| 4 | "Never uploads anything" overstated | Overstatement | High | ✅ Resolved |
| 7 | Multi-device persona vs single-machine arch | Contradiction | High | ✅ Resolved |
| 8 | No matching-accuracy metrics | Gap | High | ✅ Resolved |
| 9 | No security considerations | Gap | High | ✅ Resolved |
| 11 | No competitive/market context | Gap | High | ✅ Resolved |
| 2 | 3 buckets vs 6 chips unreconciled | Inconsistency | Medium | ✅ Resolved |
| 5 | Spotify scraping ToS/legal risk | Overstatement | Medium | ✅ Resolved |
| 6 | "Streaming can't be beat-matched" outdated | Overstatement | Medium | ✅ Resolved |
| 10 | Performance claims unquantified | Gap | Medium | ✅ Resolved |
| 12 | >100-track fallback UX gap | Gap | Medium | ✅ Resolved |
| 13 | Threshold tuning has no mechanism | Gap | Medium | ✅ Resolved |
| 3 | Domain model mixes entities and DTOs | Inconsistency | Low | ✅ Resolved |
| 14–18 | Doc metadata, ER FKs, duration math, diagram gaps, impl leakage | Nits | Low | ✅ Resolved |
