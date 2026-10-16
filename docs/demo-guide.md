# Demo guide — golden scenario

All accounts use the password `Demo-Passw0rd!` (synthetic, demo mode only). The demo page
(<http://localhost:8083/demo>) has one-click sign-in for each account.

| Account | Role | Notes |
|---|---|---|
| noa@patient.healthbridge.test | Patient (Israel) | Main persona |
| daniel@patient.healthbridge.test | Patient | Second patient for isolation checks |
| dr.morgan@pro.healthbridge.test | Cardiologist, Lakeshore Heart Institute (US, Chicago) | |
| dr.bennett@pro.healthbridge.test | Cardiac imaging, Thameside Cardiac Centre (UK, London) | |
| dr.ronen@pro.healthbridge.test | Cardiologist, Cedar Ridge Cardiology Clinic (IL) | Not a consultation participant |
| dr.haddad@pro.healthbridge.test | Family medicine, Tamar Valley Health Fund (IL) | Has a revoked grant |
| dr.shah@pro.healthbridge.test | Endocrinology (UK) | **Unverified** — cannot receive sharing |
| admin@healthbridge.test | Administrator | No clinical access |

Reset first: Administration → Demo configuration → scenario **fresh** → type `RESET`.

## Walkthrough (≈ 10 minutes)

1. **Patient context.** Sign in as Noa. The dashboard already shows her prior history from an HMO, a laboratory,
   an emergency department and a Hebrew nurse note, plus a FHIR lab import. Open **Care gaps**: CBC result missing,
   contradictory lipid timeframes, a date mismatch, a missing X-ray report — each with evidence and the rule.
2. **Ingest the specialist letter.** Documents → Upload → `demo/sample-documents/05-cedar-ridge-cardiology-letter.pdf`.
   Open it when processed: five recommendations, each highlighted in the original text. Confirm or correct one.
3. **Journey.** The Cedar Ridge consultation appears as a *Documented* event linked to the letter.
4. **Care gaps.** "Transthoracic echocardiogram within 6 weeks" is **Unknown** (no imaging report). Note the
   wording: unknown is not "not done". Click **Create clarification item**; it appears in Follow-ups.
   The earlier referral to cardiology is now **Completed & verified** by the letter.
5. **Track a follow-up.** On the letter, "Track as follow-up" for the echocardiogram. No due date is invented —
   only the documented timeframe is shown.
6. **Share deliberately.** Sharing → Share information → Dr. Rachel Morgan → tick only the Cedar Ridge letter →
   *Review what will be shared* → Approve.
7. **Schedule.** Consultations → Schedule → select Dr. Morgan and Dr. Bennett (their local times are shown) →
   add the letter to the agenda → open the consultation → **Share with participants**.
8. **Video.** Join the room as Noa; open two more browser profiles (or one normal + one incognito window per
   person) and sign in as Dr. Morgan and Dr. Bennett; join. Try camera/mic toggles, screen share and chat.
   The side panel shows which documents each participant may open.
9. **Authorized review.** As Dr. Bennett, open the letter (shared) and then try a link to another Noa document —
   *not found*. As Dr. Ronen, the consultation itself is *not found*.
10. **Summary.** As Dr. Morgan: add a note → *Mark consultation completed* → *Write summary* (try *Assemble draft
    from notes* — labelled) → add a proposed follow-up → save → Approve. Status stays *Awaiting approval* until
    Dr. Bennett approves too.
11. **Journey link.** As Noa: acknowledge the summary. The journey now shows the international consultation as
    *Professional-confirmed* with the summary document.
12. **Evidence-based status.** Care gaps → All: "Consider a second opinion…" is **Completed & verified**; the
    echocardiogram is still **Unknown**. Mark the echo task complete without a document → it stays unverified.
13. **Audit and revocation.** Privacy & audit → *Only others' activity*: Dr. Morgan's views and meeting tokens.
    Sharing → revoke Dr. Morgan → she immediately loses access. Admin → Security events → *Verify audit chain*.

Extras: switch to **עברית** (RTL), ask the **Assistant** "What did the cardiologist recommend?" (sourced answer),
"Can you diagnose me?" (refusal), "remind me to request the chest X-ray report" (confirm-to-create).
Upload `90-prompt-injection-test-note.txt` and ask about "personal notes" to see the injection warning.

The **showcase** scenario starts at step 7 with the letter processed, sharing done and a consultation starting in
~30 minutes (the room opens 2 hours before start).
