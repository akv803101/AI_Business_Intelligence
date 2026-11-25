# Builder Masterclass: AI Business Analyst (December)

## Decisions locked from your answers
- **Format:** 2 consecutive weekend days (Sat + Sun), 2 hrs each, under 20 attendees, paid (fee credited to the cohort).
- **Audience:** freshers and managers/leaders, mixed prior skills. One track, with "manager call-outs" at each step.
- **Delivery:** you present pre-baked results (nothing risky live). Learners watch, then replicate on their own using your handout (copy-paste steps).
- **Build:** the BI Flow end to end on the retail orders demo. You host Snowflake, Metabase and Claude access. Tableau is a preview only, shown at the tool-choice step.
- **Headline moment:** the chatbot (Day 2).
- **Outcome after Day 2:** "I built a real dashboard", "I get how AI fits BI" and "I need the cohort to go deeper" (all three).
- **Take-home:** prompt pack, templates, recording, certificate.
- **No cohort pitch** in the sessions. Only state the fee credit as a fact.

Source note: only AI Business Analyst Session 01 has a transcript. I used its summary: BA role evolution, data types, analytical ladder, AI/ML/GenAI hierarchy, tokens/embeddings, hallucination. Sessions 02 to 11 have recordings but no transcript, so the build topics follow the BI Flow.

---

## Day 1: Understand it, then see the data become trusted numbers (120 min)

| Min | Block | Content | Manager call-out |
|---|---|---|---|
| 0-10 | Outcome first | 3-min tour of the finished dashboard and chatbot. "In 2 days you'll see how this is built, and you'll rebuild it yourself from the handout." | |
| 10-30 | The AI business analyst | How the BA role is changing (documentation and analysis automated; judgement stays human). Data types, analytical ladder (descriptive to prescriptive) with one small business example. | What decisions do you want data to support? |
| 30-50 | AI in plain words | AI vs ML vs GenAI. Tokens, embeddings, why models hallucinate. Why numbers from AI must be checked. | The three questions to ask before trusting an AI number |
| 50-55 | Break | | |
| 55-75 | Step 1-2: Connect and profile | Read-only access, list tables, profile columns, nulls, date range. Show the pre-baked profile. | "Is this data fit for the question?" |
| 75-100 | Step 3: Model | One subject, one grain. Many-to-one joins vs row multiplication. Rollups. The view script. | Why joins can silently break counts |
| 100-115 | Step 4: KPIs | KPIs in business words, formula tested against the data, invented thresholds flagged. | Define a KPI so two people calculate the same number |
| 115-120 | Wrap | Homework: replicate steps 1-4 using the handout. | |

**Day 1 handout (copy-paste):** prompts for steps 1-4, KPI template, glossary.

## Day 2: Make it usable, make it trusted, talk to it (120 min)

| Min | Block | Content | Manager call-out |
|---|---|---|---|
| 0-10 | Recap and Q&A | Questions from replicating Day 1. | |
| 10-30 | Step 5: Semantic model | Meanings, synonyms, glossary. Why "revenue" must mean one thing. | The glossary is your company's single source of truth |
| 30-45 | Step 6-7: Design and tool | Layout grid, top-left KPI, one accent colour. Choose a tool: Metabase built, Tableau shown as preview. | What a leadership dashboard must show first |
| 45-50 | Break | | |
| 50-70 | Step 8: Build and QA | Pre-baked dashboard walkthrough. AI summary with number check. QA report: every KPI recomputed in SQL vs the tool. Show one caught mismatch. | Ask for the QA report before you trust a dashboard |
| 70-105 | **Step 9: Chatbot (headline)** | Ask business questions in plain English. Show answers grounded in the semantic model, and what happens when a term is undefined. | Questions leaders can now ask without waiting for an analyst |
| 105-115 | Proof and recap | Walk through what exists: dashboard, QA report, chatbot. What you can replicate on your own. | |
| 115-120 | Close | Handout, recording, certificate. State the fee credit as a fact. No pitch. | |

**Day 2 handout:** prompts for steps 5-9, semantic model template, QA checklist.

---

## Risks to resolve
1. **Replicate on their own** needs an environment per learner or shared sandbox logins. You said you host everything, so each learner needs access after class. Decide how long it stays open.
2. **Steps 1-9 in 4 hrs** is dense when only watching. Keep each block to show, explain, point to the handout.
3. **Cohort bridge** is intentionally absent. The enrol motivation relies on learners feeling the gap on their own (replicate it, hit limits).

## Not yet decided
- Dates, price, seat cap.
- Whether the Tableau preview is pre-recorded or a screenshot.
- Certificate criteria.
