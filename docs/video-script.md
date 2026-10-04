# Video scripts

The brief asks for **a team video** and **a 1-minute walkthrough** that follows a family or patient group to either a justified collaboration and next step, or an honest gap with a plan.

Record at 1440×900 in the deployed app, with the guided tour ("Follow Maria") open, so every click lands where the narration says. Use precomputed AI outputs so nothing waits on a live call. Numbers marked ⟨…⟩ get checked against the app's "How we know" page right before recording.

## 1-minute walkthrough: Maria and VAMP2 (about 150 spoken words)

| Time | Screen | Narration |
|---|---|---|
| 0:00 | Home, typing "VAMP2" | Maria leads a patient group for VAMP2: a rare disorder with no treatment and only a handful of known families. She types the gene name. |
| 0:07 | Disease page, mechanism chips | The atlas explains what goes wrong: VAMP2 breaks the machinery nerve cells use to release their signals. Every claim opens its source. |
| 0:15 | Question 1: STXBP1 closest, then the evidence panel | Organised by mechanism instead of by name, the closest neighbour is STXBP1, a much larger community. Each link shows its quotes, its strength, and what contradicts it. |
| 0:25 | Question 2: "Already covers VAMP2" | What already exists? Simons Searchlight already enrols VAMP2 families today. STXBP1's natural history study and outcome measures could be adapted. |
| 0:34 | Compare page VAMP2 vs STXBP1 | Before joining forces, the atlas shows what the two diseases share, what differs, and which questions an expert must answer first. |
| 0:43 | Proposal (precomputed) | Maria drafts a proposal to the STXBP1 Foundation. Every sentence links to the evidence it rests on. |
| 0:51 | "How we know" | Every link is sourced, every quote checked word for word, and a second, independent OpenAI reading agrees ⟨88⟩% of the time. From an isolated diagnosis to a justified collaboration, with the next step in hand. |

**Alternative ending (honest gap), if we cut to SYT2 instead of the proposal:** "A SYT2 family finds no patient group. The atlas says so, shows where it looked, points to the registry that already accepts them, and suggests how to build the missing community."

## Team video (about 2 minutes)

1. **Who we are (15 s).** Two first-year ETH Zurich students: electrical engineering and biochemistry. Three weeks into university.
2. **The problem (20 s).** About 10,000 rare diseases; fewer than 5% have an approved treatment. Families like Maria's become research organisers overnight, but the knowledge they need is scattered, and disease names hide shared biology.
3. **The insight (15 s).** Different genes can break the same machine. We built the atlas around mechanism and symptoms, starting with one family of disorders, the SNAREopathies, and doing it properly.
4. **What we built (30 s).**
   - A graph of ⟨397⟩ nodes and ⟨671⟩ links from 11 public sources.
   - Every link has a source, an evidence level and contradicting evidence where it exists.
   - OpenAI extracts claims from papers, reconciles names, and explains paths and drafts proposals with every sentence cited. Users sign in with their own ChatGPT plan.
   - Features: variant lookup from a genetic report, a therapy-approach view for scouts, and testable ideas nobody has tried yet.
5. **Why we trust it (20 s).**
   - ⟨705⟩ quotes string-verified against their sources.
   - An independent OpenAI re-reading agrees with our curation ⟨88⟩% of the time; disagreements go to a biochemist.
   - Gaps are shown, not hidden.
6. **10× (20 s).** STXBP1 families waited about 13 years from gene discovery to a first trial. SLC6A1 families got there in about 6, by joining STXBP1's trial on a shared mechanism. VAMP2 families are 7.5 years in with no trial, and VAMP2 shares that machinery. The atlas makes those matches findable in minutes.
7. **Next (10 s).** Test it with real patient groups, starting with VAMP2, and grow the map one mechanism family at a time.
