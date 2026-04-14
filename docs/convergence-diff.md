# Convergence Diff — Postmortem vs. Lessons Learned

**Date:** 2026-04-14
**Sources:**
- [docs/postmortem-v1.md](postmortem-v1.md) (independent audit, this repo)
- `/Users/bensivan/Desktop/Dira Dream 2.0/Claude v1 lessons learned and Execution plan/DiraDream_v2_Lessons_Learned.md` (human-authored, external)

**Purpose:** Identify where the two documents agree (validates the insight), where they disagree (needs discussion before v2), and where each has unique content the other should absorb.

---

## Convergence / Divergence Table

| Topic | Lessons Learned says | Postmortem says | Status |
|---|---|---|---|
| Parallel-line wall detection is the right approach | ✓ | ✓ | **Converge** |
| Negative-space room detection is the right approach | ✓ | ✓ | **Converge** |
| Wall-splitting for 3D openings (not CSG) | ✓ | ✓ | **Converge** |
| Build 2D to 80% before touching 3D | ✓ | ✓ | **Converge** |
| Tech stack (FastAPI + Konva + R3F + Heebo + react-intl) | Keep all | Keep all | **Converge** |
| Ground-truth annotations are #1 asset | ✓ | ✓ | **Converge** |
| Scorecard must run on every change | After every commit | CI gate, block PRs | **Converge** (PM stronger) |
| Stairwells share walls → connectivity filter can't separate them | ✓ (noted) | ✓ (Wave B attempt confirmed) | **Converge** |
| Automatic legend cropping fails | ✓ (don't crop) | ✓ (user-confirmed bbox) | **Converge** on problem; **diverge** on fix — LL says envelope detection, PM says mandatory user confirmation |
| Gap-based door detection works | LL asserts yes (Step 6 of pipeline) | PM says no — wildly unstable (0 → 29 per sample) because arcs aren't tagged | **Diverge** — needs discussion |
| Arc tagging at extraction | Not mentioned | #1 accuracy blocker in v1 | **PM-only** |
| Feature flags for pipeline cutover | Keep old until new proven | Delete ~4,000 LOC of legacy in Week 1 | **Diverge** — needs discussion |
| Agent system (10 agents) | Not discussed | Drop or cut to 3 (GEO/WEB/ARC); only VG + 3D left fingerprints | **PM-only** |
| Knowledge base audit (25 files) | Not discussed | 2 files have wrong numbers, 6 never referenced | **PM-only** |
| Specific v1 accuracy number | ~54% ceiling | Unstable, not a single number — door counts are noise (0-29), room types ~12% correct on S2 | **Diverge** — LL optimistic, PM sees noise floor |
| Duplication across `geometry/` vs `services/` | Not discussed | Room + mamad + size-range logic duplicated; will diverge under pressure | **PM-only** |
| Fixture detection via raster template-match (OpenCV) | Not mentioned | Recommended for type classification | **PM-only** |
| Reusable files to carry forward | FirstPersonController, Minimap, MobileControls, Hebrew strings | All of those + wallMerger, openingUtils, coordinateUtils, types/floorplan.ts, services/wall_detection, services/room_detection | **Converge** (PM adds backend keepers) |
| Hard refresh / Vite tips / session opener protocol | ✓ | Not covered | **LL-only** — worth keeping |
| Room count expectations per apt type (3-room = 7-8 rooms) | ✓ | Not covered | **LL-only** — worth keeping |
| Per-PDF segment/GT inventory table | ✓ | Partially (scorecard) | **LL-only** — worth keeping |
| Timeline to 80% | Not stated | 8-12 weeks | **PM-only** |

---

## Top 3 Items Needing Discussion

### 1. Feature flags vs. clean cutover

- **LL:** Keep `USE_NEW_PIPELINE=true/false` — never delete old code until new code is proven. The safety net is valuable.
- **PM:** The safety net has become tech debt. `backend/geometry/` is ~4,000 LOC of legacy that nobody runs in production but every PR still has to avoid breaking. Duplicated classification logic across `geometry/` and `services/` has already drifted (new pipeline has a "largest interior ≥ 18 sqm = salon" rule that legacy doesn't).
- **Decision needed:** v2 must pick one. The strategic bet is whether the cost of regressions exceeds the cost of carrying two pipelines. PM argues delete-in-Week-1. LL argues keep until proven.

### 2. Door detection optimism

- **LL:** Pipeline Step 6 assumes gap-based detection works (gap + arc = door, gap + perpendicular lines = window).
- **PM:** Scorecard shows it doesn't work. Door counts swing from 0 (Sample 7) to 29 (Sample 0) on the current code. The root cause is that Bézier arcs are flattened to polylines during extraction and never tagged as arcs, so the detector has no signal to distinguish a door arc from a furniture curve.
- **Decision needed:** v2 must schedule arc tagging at extraction in **Sprint 1**, not Sprint 3. Without it, the entire door/window detection stage is building on sand.

### 3. Automatic envelope detection vs. user-confirmed bbox

- **LL:** Detect the closed loop of exterior centerline walls and keep everything inside it. Geometric approach solves legend + stairwell + neighbour outlines in one pass.
- **PM:** Wave B (2026-04-14) attempted a connectivity-based version of exactly this. It failed: at 25cm tolerance the stairwell merged with the apartment (no separation); at 15cm the apartment fragmented into sub-components and the salon vanished. No tolerance worked. Geometric outer-loop detection is harder than it looks because stairwells share exterior walls with the apartment.
- **Decision needed:** v2 should ship a mandatory user-drawn/confirmed apartment bbox as the first-class input. Fast, deterministic, unblocks Samples 0/1/6 immediately. Automatic envelope detection can still be attempted as a "suggestion" the user can accept or override — but it must not be on the critical path.

---

## Recommendation

**Merge both documents into a single v2 spec.** Neither alone is sufficient:

- **Lessons Learned** has better domain facts (Israeli PDF characteristics, room count expectations per apartment type, per-PDF inventory), better process tips (hard refresh, session opener, scorecard-on-every-commit), and the author's ground-level feel for what worked and what didn't.

- **Postmortem** has harder accuracy numbers from the scorecard, a sharper code-deletion list, the agent and knowledge-base audits, and identifies the arc-tagging blocker that LL misses.

Together they cover the strategic (what to build), tactical (how to sequence sprints), and process (how to run the work) layers that v2 needs. Save both in the v2 project repo and treat them as the source of truth for the Sprint 0 planning session.

---

*End of convergence diff.*
