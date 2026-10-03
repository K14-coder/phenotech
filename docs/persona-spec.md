# Profile-specific experience: spec

The atlas serves four people from the brief. The same data gets four different experiences. **The default is Devon, the simplest.** A clear "Switch profile" control sits top right on every page.

| Profile | Who | What they need first | Tone |
|---|---|---|---|
| **Devon** (default) | Newly diagnosed family, no medical background, often searching at 2 a.m. | Reassurance; what this diagnosis means in plain words; who else lives with it; who to contact; what to do this week | Warm, short sentences, no jargon, no numbers they can't use |
| **Maria** | Patient-group leader | Neighbouring communities, reusable assets, partners, a sourced proposal | Practical, action-oriented (today's disease pages) |
| **Dr. Osei** | Researcher or clinician-scientist | Mechanism detail, evidence, who else works on it, patient population, how to reach patients for a study | Dense, precise, everything sourced |
| **Priya** | Biotech or pharma scout | Which diseases fit a therapeutic approach, unmet need, trial readiness, size of the population | Comparative, ranked |

## Global

- **Profile switch:** the top-right control reads "Viewing as: Devon (new to this) ▾". The menu gives each profile a one-line description. The choice is remembered (localStorage, `?as=`). First-time visitors are asked once, gently: "Who are you? (You can change this anytime)". Devon is preselected.
- **Every page reads the profile** and changes its content, not just the order of sections. Devon never sees jargon without a plain-language explanation, and never sees raw confidence numbers. Evidence stays one tap away ("How do we know this?").
- **Safety copy for Devon** is always visible but calm: "This is information, not medical advice. Your child's doctor or genetic counsellor is the right person for decisions."

## Devon

### Landing (`/`)
- A large, friendly prompt: "What diagnosis did you receive?", with a hint: "Type the gene name from the report (for example STXBP1) or the condition name". The variant line is accepted too.
- Three reassurance lines: "You are not alone. This atlas connects families, researchers and studies. Everything here links to its source."
- Nothing else above the fold: no graph, no technical navigation.

### Diagnosis page (`/disease/<id>?as=family`; also `/d/<MONDO>` outside the deep families)
In this order:
1. **"What this means, in plain words"**: 3 or 4 sentences, using the summary and glossary. Example: "STXBP1 is a gene that helps nerve cells pass signals. When one copy doesn't work, the brain gets too little of this protein. This can cause seizures and developmental delay. Every child is different."
2. **"You are not alone"**: the estimated number of people worldwide (population layer), as a rounded range with "estimated", plus the patient groups for this exact diagnosis.
3. **"People you can contact"**: cards for each patient group (name, country, what they offer: family network, registry, conferences, grants) with a "Visit website" button. Then registries the family could join, then clinics or specialist centres if we have them.
4. **"Things you can do this week"**: a short checklist generated from the data:
   - join the patient group's family network;
   - ask about joining the registry (name it, e.g. Simons Searchlight, if it covers this gene);
   - look at studies that are recruiting now (count plus link);
   - ask your doctor about the questions below.
5. **"Questions to bring to your doctor"**: 3–5 plain questions drawn from mechanism, treatment evidence and gaps. Example: "Is my child's variant a type that could qualify for the studies listed here?" A printable one-page version ("Print for your appointment") includes the sources.
6. **"Studies looking for participants"**: recruiting trials and natural history studies, in plain language (what it tests, age range if known, where), with a ClinicalTrials.gov link.
7. **"If there's no group yet"**: the honest version. "We didn't find a group just for this diagnosis. Here are the closest communities and how to start one." Links to the closest related community and to /contribute.
8. A collapsed **"Learn more"** at the bottom. It opens the current detailed sections: mechanism, related diseases, ideas.

## Dr. Osei

The disease page adds or reorders:
1. **"Patient population"**: the prevalence records (type, class, region, source), the estimated affected range, ClinVar variant counts by type, the registry sizes we have, and enrollment of existing studies.
2. **"Trial readiness"**: a scorecard from readiness.json covering registry/natural history, outcome measures, models, trials and phase, approved therapy, organisation, mechanism and funding. Each item is a tick, partial or gap, with evidence chips.
3. **"Reach patients for a study"**: recruitment channels from channels.json (registries with research access, patient organisations' research contacts, active investigators by institution, and trial sponsors). There's a "Draft an outreach message" button (AI, cited, precomputed when available) that writes to the patient organisation proposing a study. It never collects personal data.
4. **"Who else works on this mechanism"** (exists today), plus grants.
5. Full mechanism and evidence detail, variant spectrum, hypotheses and counterexamples (as today).

A **cohort view** (`/research`, researcher landing) shows a table of the 45 deep diseases. Columns: estimated affected, recruiting studies, registry, organisations, readiness score and mechanism class. It is sortable and filterable by family and mechanism, so a researcher can see "how many people are dealing with which problems" and where a trial is feasible.

## Priya

Landing goes to `/approach`, plus the cohort view with the unmet-need and readiness columns first.

## Maria

Today's experience stays as it is (proposal, compare, assets).

## Implementation notes

- Persona-aware content lives in components that read `usePersona()`. Avoid duplicating pages.
- Devon's plain-language text must come from data. Use the summary, glossary and templates filled with real names and counts. Never invent facts. Where data is missing, say so plainly.
- Everything must work on the static deployed site, with no live AI needed.
