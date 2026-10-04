# Video scripts

The brief asks for **a team video** and **a 1-minute walkthrough** that follows a family or patient group to either a justified collaboration and next step, or an honest gap with a plan.

**Recording setup:**
- Record at 1440×900 on the live site (https://rare-disease-atlas-five.vercel.app) in the **Detailed** view.
- Start the guided tour **"Follow a patient group"** (`lib/tours.ts`, id `maria`), so every click lands where the narration says. Its 8 steps match the rows below one to one.
- Use the precomputed AI proposal (the tour's step 7 shows it), so nothing waits on a live call.
- Numbers marked ⟨…⟩ were read from `/method` on 2026-10-04. Re-check them on the live page right before recording; they are counted live from the data.
- Say "Phenotech" (the project's new name; the live URL still says rare-disease-atlas). Don't say "Maria" or other persona names on screen: the site doesn't show them.

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
| 0:51 | 8. How we know | `/method` numbers | All ⟨2,977⟩ links have a source, ⟨2,286⟩ quotes are checked word for word, and an independent OpenAI reading agrees ⟨88⟩% of the time. From an isolated diagnosis to a justified collaboration, with the next step in hand. |

**Alternative ending (honest gap):** cut from step 6 to the second tour, "Follow a family with no patient group" (SYT2), and use this narration instead:

> "A family with a SYT2 diagnosis finds no patient group. Phenotech says so plainly, points to the registry that already accepts them, turns treatment evidence into questions for their doctor, and helps them start the missing community."

## Team video (about 2:20, about 350 spoken words)

**Goal:** in one pass, give the judges an answer for each of their five criteria: graph quality, evidence integrity, patient progress, 10× impact, and ambition and product craft. The walkthrough shows the product; this video makes the case.

**Recording setup:**
- Two kinds of shot. **Cam** means the speaker on camera (plain background, eye level, a clip-on mic if you have one). **Screen** means a screen recording of the live site at 1440×900 in the Detailed view, with the narration as voice-over.
- Record the voice-over separately, so screen clips can be cut to fit.
- Replace ⟨Name⟩ with real names. Check the numbers marked ⟨…⟩ on `/method` and `/impact` right before recording.
- **Don't say:** "reviewed by experts" or "biochemist-reviewed" (the build report has 0 human-reviewed links; 63 links are AI-reviewed only). Don't say "88% of the time": it is 60 of 68 comparable readings. Don't present any idea as a treatment recommendation.

| Time | Shot | On screen | Narration |
|---|---|---|---|
| 0:00 | Cam | Names as lower thirds | Hi, we're ⟨Name⟩ and ⟨Name⟩, first-year ETH Zurich students in electrical engineering and biochemistry, with ⟨Name / Chronify-CH⟩, who built our protein-structure layer. This is Phenotech. |
| 0:11 | Cam, then Screen | Home page, the search box empty | There are about ten thousand rare diseases; fewer than five percent have an approved treatment. After a diagnosis, parents often become research organisers overnight. They know a gene name, but not who shares their biology, what already exists, or what to do next. |
| 0:28 | Screen | `/mechanisms` or the atlas with the SNARE family highlighted | Different genes can break the same machine, and disease names hide it. Phenotech connects diseases by mechanism and distinctive symptoms, and every link carries its source. |
| 0:39 | Screen | Atlas: a disease, its mechanism chips, then a link's evidence panel | We mapped ⟨45⟩ diseases in four mechanism families in depth: ⟨2,977⟩ sourced links. One joins a lysosomal storage disease to an epilepsy gene through the same protein-misfolding problem. |
| 0:50 | Screen | Search a disease outside the deep tier → its `/d/` page | Beyond that, ⟨11,456⟩ diseases are searchable, with sourced symptoms, genes, pathways, trials and patient groups. |
| 0:56 | Screen | A precomputed AI proposal with its citations; then the view switcher | OpenAI models extract claims from papers, cross-check our curation, and turn a graph path into a plain-language proposal, every sentence cited. Families get a simple view; researchers and biotech get deeper ones. |
| 1:09 | Screen | `/method`: verified quotes, contested links, PrimeKG table | All ⟨2,286⟩ quotes are checked word for word against their source. ⟨75⟩ links carry contradicting evidence, and we show it. An independent OpenAI re-reading agrees with our curators on ⟨60⟩ of ⟨68⟩ readings. On ⟨1,300⟩ external drug–disease cases, the right disease lands in our top five about half the time; chance gives ⟨2⟩ percent. Where we know nothing, we say so. |
| 1:33 | Screen | `/impact`: the three timelines | Our milestone: a small group starts collecting natural history data a trial can use, and picks its first partner. Building your own registry means five or more years of data. Joining one that already accepts your gene takes months at most, even with expert review and consent. That is our 10×. |
| 1:54 | Screen | `/impact`: STXBP1, SLC6A1 and VAMP2 bars | It has happened once: SLC6A1 families reached a trial in six years, not thirteen, by joining STXBP1's on a shared mechanism. VAMP2 shares that machinery and is seven and a half years in, with no trial. Phenotech makes that match findable in minutes. |
| 2:11 | Cam | Logo and live URL | Next: time a real VAMP2 group's journey, get every link expert-reviewed, and add mechanism families one by one. Phenotech: from an isolated diagnosis to a shared path toward treatment. |

**Which criterion each part answers:**

| Criterion | Where |
|---|---|
| Graph quality | 0:28–0:56 (mechanism-based links, the cross-family example, depth plus breadth) |
| Evidence integrity | 1:09 (verified quotes, contested links, independent re-reading, external benchmark, honest gaps) |
| Patient progress | 0:56 (the proposal) and the 1-minute walkthrough |
| 10× impact | 1:33–2:11 (milestone, existing route vs ours, the SLC6A1 precedent) |
| Ambition and product craft | 0:50–1:09 (breadth, views, OpenAI), plus the screen footage throughout |

**If a time limit forces cuts** (in this order): drop the view-switcher sentence at 0:56, then the breadth line at 0:50, then the next-steps line at 2:11 (end on "findable in minutes").

**Before recording, check:**
1. The numbers on `/method` and `/impact` still match the ⟨…⟩ values.
2. The cross-family example at 0:39 (SLC6A1 ↔ GLA/NPC1, protein destabilization) is shown in the atlas, and its evidence panel opens.
3. The proposal shown at 0:56 is precomputed, so nothing waits on a live call.
4. The site shows the name Phenotech (the rename is in progress on `main`).
