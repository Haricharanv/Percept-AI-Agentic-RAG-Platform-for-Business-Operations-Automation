# Knowledge Base Data Strategy: Synthetic + Real-World Hybrid Sourcing

**Agentic RAG Platform for Business Operations Automation**

## Purpose

Per Section 6.1 of the Final Implementation Plan, each vertical's knowledge base is populated **primarily from synthetic data**, supplemented with real public data **where available**. This is not a uniform rule — the mix differs per vertical, driven by data privacy and public availability. This document summarizes the intended split, required volumes, and where real-world data applies.

## Why Hybrid, Not Purely Synthetic

Pure synthetic data risks two failure modes: (1) it can look unrealistic if not carefully styled, and (2) it never proves the system works against real-world phrasing and structure. Pure real data risks two different failure modes: (1) for most verticals, no public real data exists at all (employee records, contracts, meeting transcripts are inherently private), and (2) even where real data exists, it can't be relied upon to contain deliberately matching pairs — which the demo needs to prove retrieval genuinely works, not just returns *something*.

The resolution: use real data where it exists and is public, and always add deliberately-planted synthetic pairs to guarantee a demonstrable match exists.

## Per-Vertical Breakdown

### Vertical 1 — Post-Incident Knowledge Synthesis
**Real-world data used**: Yes — real postmortems from the **`danluu/post-mortems`** public GitHub archive (a well-known, publicly maintained aggregator of published engineering incident writeups).
**How combined**: ~10–15 real postmortems selected for clearly identifiable root causes, **plus** ~10 synthetic postmortems written to deliberately reuse 3–4 of those same root-cause patterns (different service names, different wording) — this guarantees at least one genuine matching pair exists for the retrieval demo, since the real archive can't be relied on to contain one naturally.
**Suggested volume**: ~15–25 postmortems total, covering 4–5 distinct root-cause categories with at least 2 examples per category.
**KB placement**: Both real and synthetic files are ingested identically — dropped into `seed_data/post_incident/`, no code distinguishes them.

### Vertical 2 — Internal Mobility & Skill-Gap Matching
**Real-world data used**: Yes, but **style reference only** — real/adapted public job postings, used to inform realistic role-description phrasing. These are **never embedded into the KB**.
**How combined**: The actual KB content (employee profiles) is 100% synthetic, since real employee histories cannot be used. Real job postings only shape how the synthetic role-posting text is written.
**Suggested volume**: ~30–50 synthetic employee profiles across 4–6 departments — enough that the hard structural filter (department + minimum experience) still leaves a real pool for the semantic ranking step to meaningfully rank.
**Note**: Per Section 8.2, role postings themselves are stored relationally only and are never retrieved against later.

### Vertical 3 — Contract Obligation & Renewal Tracking
**Real-world data used**: None specified.
**How combined**: Fully synthetic — LLM-generated contracts styled like vendor/NDA agreements.
**Suggested volume**: ~8–12 contracts, 5–10 clauses each (chunked at clause level per Section 8.3, yielding 50–100+ embeddings). Include a few clauses with deliberately similar wording across different contracts, to demonstrate the `search_similar_contracts` cross-reference tool.

### Vertical 4 — Meeting Action-Item Enforcement
**Real-world data used**: None specified.
**How combined**: Fully synthetic — meeting transcripts and owner-activity records (tickets, commits, follow-up mentions) are both synthesized, since real internal meeting content is inherently private.
**Suggested volume**: ~10–15 transcripts with 3–5 action items each, plus matching owner-activity records tied to the same synthetic owners. Both `source_type`s (`action_item`, `owner_activity`) need real content, since the vertical's two retrieval paths (recurrence check, completion check) each search a different one.

## Summary Table

| Vertical | Real data | Suggested volume |
|---|---|---|
| V1 — Post-Incident | `danluu/post-mortems` (embedded) | ~15–25 postmortems |
| V2 — Internal Mobility | Public job postings (style only, not embedded) | ~30–50 employee profiles |
| V3 — Contract Tracking | None | ~8–12 contracts (50–100+ clause chunks) |
| V4 — Meeting Action Items | None | ~10–15 transcripts + matching activity records |

## Every Place Synthetic Data Is Needed

1. **KB content itself** — the core corpus per vertical, per the table above.
2. **Deliberately planted similar/duplicate cases** — engineered, not left to chance, so retrieval has a guaranteed match to demonstrate.
3. **Style-reference-only real data** (V2, and optionally V1) — informs realistic phrasing without being embedded.
4. **Owner-activity records** (V4) — synthetic evidence of work, tied to the same synthetic owners appearing in transcripts.
5. **Live demo submission(s)** — the one document uploaded during a real demo should be pre-written deliberately, calibrated to either clearly match seeded precedent (confident autonomous action) or clearly not (clean escalation).
6. **Test-suite fixtures** — small synthetic snippets inside `pytest` tests exist purely for code correctness and should remain conceptually separate from demo/KB content.

## Mechanism Note

Both real and synthetic files are placed together in `backend/seed_data/<vertical>/` and copied into staging by `seed.py`, which is itself the first-ingestion pathway (Section 6.4). `ingest_staging_folder()` treats every file identically regardless of origin — the hybrid nature lives entirely in *which files are curated into that folder*, not in any code-level distinction.

## Demo Inputs vs. Seed Data (addendum)

Two genuinely different things, kept in separate folders:

- `backend/seed_data/<vertical>/` — goes INTO the KB automatically
  (via `seed.py`). Never meant to be re-uploaded through the UI.
- `backend/demo_inputs/<vertical>/` — curated files for manually
  testing/demoing the Submit page. Never auto-ingested. Must be
  genuinely new content, not copies of seed files — submitting a seed
  file back to itself only proves a trivial near-1.0 self-match, not
  real retrieval.

Each vertical's `demo_inputs/` folder includes a `README.md`
explaining what each file is expected to demonstrate. This
explanation MUST live in the README, never as a comment inside the
demo file itself — an inline note becomes part of the actual
extracted/embedded content and can distort retrieval or extraction.

## File-Type Diversity Requirement

Each vertical's **seed data** (not demo inputs) must include at least
one `.pdf` and one `.docx` file, alongside `.txt` — this is the only
way to get real integration coverage of `extract_text()`'s PDF/DOCX
branches beyond synthetic unit tests.
