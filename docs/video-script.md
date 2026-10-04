# Video scripts

The brief asks for **a team video** and **a 1-minute walkthrough** that follows a family or patient group to either a justified collaboration and next step, or an honest gap with a plan.

**Recording setup:**
- Record at 1440×900 on the live site (https://rare-disease-atlas-five.vercel.app) in the **Detailed** view.
- Start the guided tour **"Follow a patient group"** (`lib/tours.ts`, id `maria`), so every click lands where the narration says. Its 8 steps match the rows below one to one.
- Use the precomputed AI proposal (the tour's step 7 shows it), so nothing waits on a live call.
- Numbers marked ⟨…⟩ were read from `/method` on 2026-10-04. Re-check them on the live page right before recording; they are counted live from the data.
- Say "Phenotech" (FEE-no-tech). Don't say "Maria" or other persona names on screen: the site doesn't show them.

## 1-minute walkthrough: "Follow a patient group" (about 150 spoken words)

| Time | Tour step | Screen | Narration |
|---|---|---|---|
| 0:00 | 1. Start with the gene name | Home, typing "VAMP2" | A small patient group for VAMP2 (a rare disorder with no treatment and only a handful of known families) opens Phenotech and types the gene name. |
| 0:07 | 2. What goes wrong | Disease page, mechanism chips | The page explains in plain words what goes wrong: VAMP2 breaks the machinery nerve cells use to release their signals. Every chip opens its source. |
| 0:15 | 3. The closest disease | Closest disease: STXBP1 | Organised by mechanism instead of by name, the closest neighbour is STXBP1, a much larger community. |
| 0:21 | 4. Every link shows its evidence | Limiting evidence open | Every link shows its quotes and its strength, and what limits or contradicts it is listed too, never hidden. |
| 0:28 | 5. Work that already exists | "Already covers VAMP2" | Simons Searchlight already enrols VAMP2 families today, and STXBP1's natural history study and outcome measures could be adapted. |
| 0:36 | 6. Before we join forces | Compare VAMP2 vs STXBP1 | Side by side: what the two communities share, what differs, and what an expert should check first. |
| 0:44 | 7. A sourced proposal | Precomputed proposal | The group drafts a proposal to the STXBP1 Foundation. Every sentence links to the evidence it rests on. |
| 0:51 | 8. How we know | `/method` numbers | All ⟨2,977⟩ links have a source, ⟨2,130⟩ quotes are checked word for word, and an independent OpenAI reading agrees ⟨88⟩% of the time. From an isolated diagnosis to a justified collaboration, with the next step in hand. |

**Alternative ending (honest gap):** cut from step 6 to the second tour, "Follow a family with no patient group" (SYT2), and use this narration instead:

> "A family with a SYT2 diagnosis finds no patient group. Phenotech says so plainly, points to the registry that already accepts them, turns treatment evidence into questions for their doctor, and helps them start the missing community."

## Team video (about 2 minutes)

1. **Who we are (15 s).** Two first-year ETH Zurich students, in electrical engineering and biochemistry, three weeks into university. Collaborator Chronify-CH built the mechanistic similarity layer.
2. **The problem (20 s).**
   - About 10,000 rare diseases, and fewer than 5% have an approved treatment.
   - Families become research organisers overnight, but the knowledge they need is scattered, and disease names hide shared biology.
3. **The insight (15 s).** Different genes can break the same machine. Phenotech connects diseases by mechanism and distinctive symptoms. We went deep where we could check every claim, and broad everywhere else.
4. **What we built (35 s).**
   - **Depth:** ⟨45⟩ diseases in 4 mechanism families, curated with verbatim, source-checked quotes: ⟨1,412⟩ nodes and ⟨2,977⟩ links.
   - **Breadth:** ⟨11,456⟩ diseases searchable, ⟨10,309⟩ with sourced automated data.
   - **Four views**, from Simple for families to Industry for biotech.
   - **A DNA checker** that runs on your device against all of ClinVar.
   - **Community:** live trial and grant alerts, and a research queue where volunteers extend the atlas.
   - **OpenAI** extracts and cross-checks claims, explains paths and drafts proposals, with every sentence cited.
5. **Why we trust it (20 s).**
   - ⟨2,130⟩ quotes string-verified against their sources; ⟨75⟩ contested links shown with their counter-evidence.
   - An independent OpenAI re-reading agrees with our curation ⟨88⟩% of the time.
   - On ⟨1,300⟩ external PrimeKG cases, the hidden disease lands in the top 5 ⟨49⟩% of the time, against ⟨2⟩% by chance.
   - Gaps are shown, not hidden.
6. **10× (20 s).**
   - STXBP1 families waited about 13 years from gene discovery to a first trial.
   - SLC6A1 families got there in about 6, by joining STXBP1's trial on a shared mechanism.
   - VAMP2 families are 7.5 years in with no trial, and VAMP2 shares that machinery.
   - Phenotech makes those matches findable in minutes.
7. **Next (10 s).** Test it with real patient groups, starting with VAMP2, get the biochemist review finished, and grow the deep tier one mechanism family at a time.
