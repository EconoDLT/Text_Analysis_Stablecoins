# Codebook — ECB stance and tone towards stablecoins

**Unit:** a *passage* = one sentence that contains a stablecoin keyword, plus the sentence before and after it
(overlapping windows merged). Code the position of the **ECB speaker**, not of others they quote.

## Stance (`stance_coder1`, `stance_coder2`, `stance_gold`)

| Code | Label | Rule | Example (constructed) |
|---:|---|---|---|
| -1 | restrictive | stresses risks (runs, financial stability, monetary sovereignty, dollarisation, illicit use) as a reason for stricter rules, warnings, enforcement, or a public alternative such as the digital euro | "Without stronger safeguards, a run on a large stablecoin could spread to the banking sector." |
| 0 | neutral | describes facts, market developments or existing rules without taking a position | "Issuers must hold liquid reserves and redeem tokens at par on request." |
| 1 | supportive | stresses benefits (faster, cheaper payments, programmability, innovation), clarifies what is allowed, or welcomes the activity | "Regulated stablecoins can make cross-border payments cheaper and faster." |

Decision rules
1. Mixed passage ("benefits, **but** serious risks"): code the side the speaker concludes with.
2. Supporting *regulation* (e.g. welcoming MiCA because it protects users from stablecoins) is **restrictive**
   stance; welcoming stablecoins *under* clear rules is **supportive**.
3. Supporting the digital euro as an alternative *to* stablecoins is **restrictive**.
4. Positive about tokenisation/DLT in general but silent on stablecoins: **neutral**.

## Tone (`tone_coder1`, `tone_coder2`, `tone_gold`)
Sentiment of the language, regardless of stance: -1 negative, 0 neutral, 1 positive.
"We welcome MiCA, which protects consumers from unsafe tokens" = stance -1, tone +1.

## Procedure
1. Two coders label `labels/validation_sample.csv` independently (columns `*_coder1`, `*_coder2`).
2. Disagreements are discussed; the agreed label goes in `*_gold` (if empty, coder 1 is used).
3. Re-run either script: `outputs/*/validation_metrics.csv` reports accuracy, macro-F1 and Cohen's kappa.
