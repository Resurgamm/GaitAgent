# Backend handover — ChildGait

**Status:** the Android app is complete and verified. The only thing missing is a served model.
This document is what you need to build the thing it talks to.

Everything the app does is real except scoring. Nothing in the app needs to change to accept a
real backend beyond one line, so treat the contract below as fixed and the client as done.

---

## 1. What you are replacing

The app has exactly one seam:

```
app/src/main/java/ai/pediamed/childgait/data/engine/GaitAnalyzer.kt
```

```kotlin
interface GaitAnalyzer {
    val engineName: String
    val isMock: Boolean
    fun analyze(input: SessionInput): Flow<AnalysisProgress>
}
```

Two implementations sit behind it. `MockGaitAnalyzer` fabricates a report; `RemoteGaitAnalyzer` is
a stub with the contract in its KDoc. To switch:

```kotlin
// di/AppModule.kt
fun gaitAnalyzer(context: Context): GaitAnalyzer =
    RemoteGaitAnalyzer(baseUrl = "https://…")     // was MockGaitAnalyzer { … }
```

Setting `isMock = false` in `RemoteGaitAnalyzer` removes the "DEMO — mock inference" banner
automatically. **Leave it true until your scores are real**, including during integration testing:
the banner is the only thing preventing a screenshot of synthetic output being mistaken for a
clinical result.

---

## 2. The input you receive

Two short clips per assessment, uploaded together:

| Part | Plane | Content | Typical length |
| --- | --- | --- | --- |
| `sagittal` | Lateral | Child walking past a side-on camera | 3–5 s |
| `coronal` | Frontal | Child walking toward a walkway-end camera | 3–5 s |

This mirrors the CGV capture protocol: a primary camera at the terminus of an 8 m walkway for the
coronal view, and a secondary camera oriented orthogonally, facing the middle of the walkway, for
the sagittal view. Both run simultaneously.

**The plane is declared by the clinician, not inferred.** The app has two labeled slots and will
not submit until both are filled. Do not try to detect which is which — you are being told, and
the assignment is authoritative.

Clips come from the device's photo picker, so expect: H.264/HEVC MP4, anywhere from 480p to 4K,
24–60 fps, arbitrary rotation metadata, and occasionally a clip where the child leaves frame.

---

## 3. The endpoint

Both clips are short, so this is a single round trip — no event stream, no job polling.

```
POST {baseUrl}/v1/assessments
Content-Type: multipart/form-data
```

Exactly two parts, named `sagittal` and `coronal`.

### Success — `200`

```json
{
  "patternSummary": "Findings consistent with right spastic hemiplegia — unilateral right-sided deviation with a compensating left limb.",
  "clipQuality": { "SAGITTAL": 0.88, "CORONAL": 0.81 },
  "scores": [
    { "item": "IC", "limb": "L", "label": "TYPICAL",  "confidence": 0.85 },
    { "item": "IC", "limb": "R", "label": "ATYPICAL", "confidence": 0.89 }
  ]
}
```

A complete, valid response is checked in at [`docs/example-response.json`](example-response.json)
— all 34 entries. Use it as a fixture.

| Field | Type | Notes |
| --- | --- | --- |
| `patternSummary` | string | One sentence, shown verbatim on the summary card. Keep under ~200 chars. See §6 on wording. |
| `clipQuality` | object | `SAGITTAL` and `CORONAL`, each 0..1. How usable the clip was — framing, occlusion, whether the child stayed in shot. Displayed per clip; also your channel for "this clip was poor". |
| `scores` | array | Exactly **34** entries: 17 items × 2 limbs. |
| `scores[].item` | string | EVGS code from the table in §4. |
| `scores[].limb` | string | `"L"` or `"R"`. |
| `scores[].label` | string | `"TYPICAL"` or `"ATYPICAL"`. |
| `scores[].confidence` | number | 0..1. Not 0..100. |
| `scores[].view` | string | Optional. If present must equal the item's plane; the app derives the plane from the item and ignores a contradictory value. Useful as a self-check. |

### Failure — `4xx` / `5xx`

```json
{ "error": "Sagittal clip contains no detectable person." }
```

The message is surfaced to the user in a snackbar, so write it for a clinician, not a log file.

---

## 4. The item table and the plane split

This is the part most likely to be got wrong, and it is silent when it is.

| # | Code | Plane | Item |
| --- | --- | --- | --- |
| 1 | `IC` | Sagittal | Initial Contact in Stance |
| 2 | `HL` | Sagittal | Heel Lift in Stance |
| 3 | `SAD` | Sagittal | Max Ankle Dorsiflexion in Stance |
| 4 | `HVV` | **Coronal** | Hind-foot Varus/Valgus in Stance |
| 5 | `FRT` | **Coronal** | Foot Rotation in Stance |
| 6 | `FCL` | Sagittal | Foot Clearance in Swing |
| 7 | `WAD` | Sagittal | Max Ankle Dorsiflexion in Swing |
| 8 | `KPA` | **Coronal** | Knee Progression Angle in Mid-Stance |
| 9 | `KEX` | Sagittal | Peak Knee Extension in Stance |
| 10 | `KPS` | Sagittal | Knee Position in Terminal Swing |
| 11 | `KFX` | Sagittal | Peak Knee Flexion in Swing |
| 12 | `HEX` | Sagittal | Peak Hip Extension in Stance |
| 13 | `HFX` | Sagittal | Peak Hip Flexion during Swing |
| 14 | `POB` | **Coronal** | Pelvic Obliquity at Mid-Stance |
| 15 | `PRT` | **Coronal** | Pelvic Rotation at Mid-Stance |
| 16 | `TSG` | Sagittal | Peak Sagittal Trunk Position in Stance |
| 17 | `TLT` | **Coronal** | Maximum Trunk Lateral Shift |

**Six coronal items:** `HVV`, `FRT`, `KPA`, `POB`, `PRT`, `TLT`.
**Eleven sagittal items:** everything else.

So: **22 scores from the sagittal clip, 12 from the coronal clip.**

Score each item from the clip whose plane can actually see it. A lateral view cannot resolve
hind-foot varus or pelvic obliquity; a frontal view cannot resolve knee flexion arc or forward
trunk lean. Scoring `KEX` off the coronal clip will produce a number, and that number will be
meaningless — this split is the whole reason the app takes two clips instead of one.

The app surfaces provenance in the UI ("Scored from: Coronal clip"), so a clinician reviewing a
finding will see which camera it came from. Getting this wrong is visible to them, not just to you.

Full clinical definitions and the native 0/1/2 ordinal criteria for every item are in
`app/src/main/java/ai/pediamed/childgait/data/model/Evgs.kt`, transcribed from Appendix B of the
paper. That is the reference the app shows users; keep your scoring aligned to it.

### Binary, not ordinal

EVGS is natively a three-point scale (0 normal, 1 moderate deviation, 2 marked deviation). The
paper binarises it by merging 1 and 2, because score 2 is too rare in the cohort to learn from,
and the app follows suit. So `TYPICAL` = 0, `ATYPICAL` = 1 or 2.

If your model produces the full ordinal scale, keep it internally and collapse at the API boundary
— but tell us, because surfacing severity is an obvious next step for the UI and we would rather
not re-derive it later.

---

## 5. Validate before you integrate

```bash
./tools/validate-response.py your-response.json
curl -s -F sagittal=@a.mp4 -F coronal=@b.mp4 $BASE/v1/assessments | ./tools/validate-response.py -
```

It checks every rule above: all 34 present, no duplicates, plane split 22/12, codes valid, ranges
valid, `view` consistent, plus soft warnings for the mistakes that look plausible (constant
confidences, 0..100 sent as 0..1).

```
$ ./tools/validate-response.py docs/example-response.json
VALID — 34 scores, plane split correct, 0 warning(s)
```

Wire it into your CI. A response that violates the contract does not crash the app — it renders a
report that is quietly wrong, which is worse.

---

## 6. Wording of `patternSummary`

This string appears on the summary card, directly under the flagged-item count, and it is the one
piece of free text you control. It is read by clinicians.

The mock's convention: `"Findings consistent with <pattern> — <clause>."` Note what it does not do:

- It does not name a diagnosis. "Findings consistent with a bilateral equinus pattern" — not
  "the child has cerebral palsy".
- It does not recommend action.
- It hedges by construction. A screening tool with ~85% per-item accuracy has not diagnosed
  anything.

If your model outputs a classification head over conditions, phrase the summary from the observed
kinematics rather than the class label. This is a screening aid for a pediatrician, not a report.

---

## 7. Target performance

From Table 4 of the paper, ChildGait-Video per-item accuracy against expert annotation:

| | Left limb | Right limb |
| --- | --- | --- |
| Range across items | 70–93% | 74–93% |
| Mean | 84% | 84% |
| Mean F1 | 0.83 | 0.83 |

For context, on the same test split: fine-tuned VideoMAE v2 reached 69%/72%; gait-recognition
models (GaitSet through BiggerGait) 45–56%; skeleton models 58–70%; zero-shot MLLMs and a
fine-tuned Qwen3-VL-4B sat at 50–59%, barely above chance on a binary task. A pediatrician human
baseline scored 93.8%, with inter-rater ICC 0.93.

**Two caveats before you treat 84% as the bar.** The test split is small — per-item accuracies are
quantised on denominators of roughly 26–28 videos, so a single sample moves a number by ~4 points
and the 95% CI on 84% is around ±13. And the paper's significance test pools McNemar over the 34
items rather than over samples, which overstates significance given left/right and shared-video
dependence. Treat 84% as "the right order of magnitude", and build a larger held-out split.

The app displays confidences drawn around these published per-item values, so if your calibration
differs markedly the numbers on screen will stop matching the paper. That is fine — just expected.

### Method, for reference

The paper's winning configuration: VideoMAE v2 encoder pre-trained on Kinetics-710, fine-tuned on
CGV with two additions — **token-level kinematic prompting** (render the skeleton onto the RGB
frame so patches carrying joints become implicit kinematic tokens) and **mask-guided patch
pruning** (keep only patches with sufficient foreground mask, deterministically, instead of
MAE-style random masking). Ablation: prompting +3, pruning +9, both +15 over the VideoMAE v2
baseline; random masking *hurts*. Input is 16 frames at 30 fps (32 frames gained a further ~3.7
points at quadratic cost).

---

## 8. Consent and data handling — read before your first request

**The app currently has no network code at all.** That is why the import screen says "Clips stay
on this device. Nothing is uploaded."

The moment `RemoteGaitAnalyzer` goes live, pediatric clinical video starts leaving the device, and
that statement becomes false. Before you ship:

1. **The UI copy must change.** `ImportScreen.kt` and the README both make the no-upload claim.
2. **Consent is a separate question from the code.** The CGV dataset was collected under IRB
   approval 202106202 as a retrospective study. Live upload from a clinic is a different activity
   and needs its own review.
3. **De-identification.** The dataset pipeline mosaics faces (RetinaFace + SAM 3) with manual
   verification of every output. Clips arriving from a phone are *not* de-identified. Decide
   whether that happens on device before upload or server-side on receipt — and if server-side,
   the raw video exists on your infrastructure and that has to be justified.
4. **Retention.** Decide whether clips are kept after scoring. The dataset licence (CC BY-NC 4.0)
   explicitly forbids using this video as foundation-model training material without separate
   authorisation; clips uploaded from clinics are not covered by it at all.
5. **Transport.** TLS, obviously. Also: no identifiers in URLs or logs, and consider whether the
   `sessionId` should be derivable from anything.

None of this is the app's problem to solve, which is exactly why it is on this list — it will
otherwise fall between the two teams.

---

## 9. Getting the app running to test against

```bash
./setup-toolchain.sh          # once: JDK + SDK + Gradle into ./toolchain, nothing global
source env.sh
./gradlew assembleDebug
```

To exercise the flow without a phone:

```bash
sdkmanager --sdk_root="$ANDROID_HOME" emulator "system-images;android-35;google_apis;arm64-v8a"
./run-emulator.sh --headless
./tools/make-test-video.sh 4 --push     # generates and pushes both synthetic clips
```

`tools/dev-loop.sh` rebuilds, reinstalls and screenshots on every save (~2 s), which is the
fastest way to see your responses rendered. `tools/uidrive.py` drives the UI by on-screen label
if you want to script it.

Note the synthetic clips are stick figures — fine for exercising the report, useless as model
input. Use real footage to test anything involving pose.

---

## 10. Open questions for you

Things the app has taken a position on that you may want to revisit:

1. **Ordinal vs binary.** We collapse to typical/atypical because the paper does. If your model
   gives 0/1/2 reliably, say so and we will surface severity.
2. **Per-clip confidence.** `clipQuality` is currently one number per clip. If you can report *why*
   a clip scored poorly (child left frame, occlusion, too few gait cycles) that is more actionable
   and we would show it.
3. **Latency budget.** The mock takes 3–7 s deliberately. If real inference takes 30 s+ we should
   move to a job + poll model rather than a blocking request — tell us early, it changes the
   progress UI.
4. **Which items your model is weakest on.** The paper's worst are `WAD` (70% left) and `SAD` (74%
   right). If certain items are unreliable, returning them with a low confidence is better than
   returning them confidently — the UI already renders confidence per item.
5. **Single-clip fallback.** Currently both clips are required. If a clinician only has one, we
   could score that plane and mark the other 6 or 11 items unobserved. Worth doing?

---

## Reference

| Thing | Where |
| --- | --- |
| The interface you implement | `data/engine/GaitAnalyzer.kt` |
| Contract, in code | `data/engine/RemoteGaitAnalyzer.kt` (KDoc) |
| Where to flip the binding | `di/AppModule.kt` |
| Item definitions and criteria | `data/model/Evgs.kt` |
| Golden response fixture | `docs/example-response.json` |
| Contract validator | `tools/validate-response.py` |
| What the mock does, and why | `README.md`, "What the mock does" |
| Screenshots of every screen | `docs/screenshots/` |
| Recorded walkthrough | `demo.mp4` (regenerate with `tools/record-demo.sh`) |
