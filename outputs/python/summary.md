# ECB stablecoin stance monitor -- summary (Python)

- Speeches 2019-01-01 to 2026-10-01: **650**; speeches with stablecoin passages: **89**; passages: **400**
- Main stance measure: **nli**; stance distribution: restrictive 144, neutral 233, supportive 23; overall RSI = -0.302
- Overall tone index = -0.115
- Market file check: max |Total - sum(jurisdictions)|/Total = 8.9998
- Structural breaks in monthly RSI (BIC, trim 0.15, h = 14): 2020-06, 2021-08

## Validation against human labels

_(not available)_

## Agreement between methods

| method_a | method_b | n | agreement | kappa |
|---|---|---|---|---|
| stance_dict | stance_nli | 400 | 0.542 | 0.266 |

## Speakers

| speaker | n_passages | n_speeches | rsi | share_restrictive | ti |
|---|---|---|---|---|---|
| Fabio Panetta | 161 | 23 | -0.354 | 0.360 | -0.180 |
| Piero Cipollone | 73 | 26 | -0.247 | 0.397 | -0.082 |
| Christine Lagarde | 49 | 13 | -0.143 | 0.245 | 0.000 |
| Isabel Schnabel | 38 | 4 | -0.316 | 0.368 | 0.105 |
| Benoît Cœuré | 32 | 6 | -0.375 | 0.438 | -0.250 |
| Philip R. Lane | 17 | 4 | -0.118 | 0.235 | 0.059 |
| Luis de Guindos | 12 | 4 | -0.417 | 0.417 | -0.333 |
| Yves Mersch | 12 | 3 | -0.417 | 0.417 | -0.250 |
| Frank Elderson | 3 | 3 | -0.667 | 0.667 | 0.000 |
| Christine Lagarde,Philip R. Lane | 1 | 1 | 0.000 | 0.000 | 0.000 |
| Mario Draghi | 1 | 1 | -1.000 | 1.000 | 0.000 |
| Sabine Lautenschläger | 1 | 1 | 0.000 | 0.000 | -1.000 |

## Stance x tone

| stance | negative | neutral | positive |
|---|---|---|---|
| restrictive | 72 | 57 | 15 |
| neutral | 44 | 148 | 41 |
| supportive | 1 | 7 | 15 |

## USD vs EUR focus

| focus | n_passages | rsi | ti |
|---|---|---|---|
| both | 4 | -0.250 | -0.250 |
| eur | 12 | -0.333 | 0.167 |
| general | 294 | -0.289 | -0.112 |
| usd | 90 | -0.344 | -0.156 |

## Before/after milestones (passage-level, +/-12 months)

| milestone | date | n_before | n_after | mean_before | mean_after | diff | t | p_value |
|---|---|---|---|---|---|---|---|---|
| Libra white paper | 2019-06-18 | 13 | 45 | -0.308 | -0.400 | -0.092 | -0.581 | 0.567 |
| TerraUSD collapse | 2022-05-09 | 73 | 51 | -0.260 | -0.412 | -0.151 | -1.705 | 0.091 |
| MiCA published | 2023-06-09 | 49 | 29 | -0.449 | -0.276 | 0.173 | 1.562 | 0.123 |
| MiCA stablecoin titles apply | 2024-06-30 | 9 | 41 | -0.111 | -0.220 | -0.108 | -0.701 | 0.490 |
| MiCA fully applicable | 2024-12-30 | 10 | 71 | -0.200 | -0.268 | -0.068 | -0.431 | 0.672 |
| GENIUS Act signed | 2025-07-18 | 45 | 111 | -0.200 | -0.243 | -0.043 | -0.359 | 0.721 |
| MiCA transition ends | 2026-07-01 | 113 | 11 | -0.230 | -0.182 | 0.048 | 0.353 | 0.729 |

## Breaks

| m | rss | bic | breaks |
|---|---|---|---|
| 0 | 11.125 | 75.242 |  |
| 1 | 10.483 | 78.741 | 2025-02 |
| 2 | 9.090 | 74.423 | 2020-06,2021-08 |
| 3 | 8.742 | 79.840 | 2020-06,2021-08,2025-02 |
| 4 | 8.400 | 85.178 | 2020-06,2021-08,2024-01,2025-03 |
| 5 | 8.231 | 92.348 | 2020-06,2021-08,2022-11,2024-01,2025-03 |

## ADF tests (constant + trend)

| series | n | lags | adf_stat | p_value |
|---|---|---|---|---|
| rsi_ffill | 94 | 4 | -3.629 | 0.028 |
| attention | 94 | 4 | -3.537 | 0.036 |
| g_total | 93 | 4 | -4.836 | 0.000 |
| g_eu_eea | 93 | 4 | -2.306 | 0.430 |
| d_eu_share | 93 | 4 | -6.801 | 0.000 |
| r_btc | 94 | 4 | -4.367 | 0.002 |

## Market regressions (Newey-West)

| y | term | coef | se_nw | t | p_value | n | r2 | nw_lags |
|---|---|---|---|---|---|---|---|---|
| g_total | const | 0.164 | 0.054 | 3.059 | 0.002 | 92 | 0.186 | 3 |
| g_total | rsi_l1 | 0.006 | 0.051 | 0.121 | 0.903 | 92 | 0.186 | 3 |
| g_total | att_l1 | -0.121 | 0.096 | -1.266 | 0.206 | 92 | 0.186 | 3 |
| g_total | btc_l1 | 0.002 | 0.194 | 0.009 | 0.993 | 92 | 0.186 | 3 |
| g_total | y_l1 | -0.411 | 0.152 | -2.698 | 0.007 | 92 | 0.186 | 3 |
| g_total | M_MiCA published | -0.129 | 0.055 | -2.357 | 0.018 | 92 | 0.186 | 3 |
| g_total | M_MiCA stablecoin titles apply | 0.027 | 0.029 | 0.921 | 0.357 | 92 | 0.186 | 3 |
| g_total | M_GENIUS Act signed | -0.005 | 0.036 | -0.143 | 0.886 | 92 | 0.186 | 3 |
| g_eu_eea | const | 0.063 | 0.033 | 1.924 | 0.054 | 92 | 0.229 | 3 |
| g_eu_eea | rsi_l1 | -0.030 | 0.028 | -1.062 | 0.288 | 92 | 0.229 | 3 |
| g_eu_eea | att_l1 | -0.147 | 0.082 | -1.790 | 0.074 | 92 | 0.229 | 3 |
| g_eu_eea | btc_l1 | 0.070 | 0.065 | 1.082 | 0.279 | 92 | 0.229 | 3 |
| g_eu_eea | y_l1 | 0.314 | 0.125 | 2.509 | 0.012 | 92 | 0.229 | 3 |
| g_eu_eea | M_MiCA published | -0.054 | 0.032 | -1.710 | 0.087 | 92 | 0.229 | 3 |
| g_eu_eea | M_MiCA stablecoin titles apply | 0.022 | 0.023 | 0.947 | 0.344 | 92 | 0.229 | 3 |
| g_eu_eea | M_GENIUS Act signed | 0.016 | 0.020 | 0.780 | 0.435 | 92 | 0.229 | 3 |
| d_eu_share | const | -2.866 | 5.046 | -0.568 | 0.570 | 92 | 0.254 | 3 |
| d_eu_share | rsi_l1 | -3.579 | 3.467 | -1.032 | 0.302 | 92 | 0.254 | 3 |
| d_eu_share | att_l1 | -6.257 | 9.952 | -0.629 | 0.530 | 92 | 0.254 | 3 |
| d_eu_share | btc_l1 | 24.537 | 24.625 | 0.996 | 0.319 | 92 | 0.254 | 3 |
| d_eu_share | y_l1 | -0.490 | 0.176 | -2.789 | 0.005 | 92 | 0.254 | 3 |
| d_eu_share | M_MiCA published | 0.853 | 4.778 | 0.178 | 0.858 | 92 | 0.254 | 3 |
| d_eu_share | M_MiCA stablecoin titles apply | 0.326 | 1.215 | 0.268 | 0.789 | 92 | 0.254 | 3 |
| d_eu_share | M_GENIUS Act signed | 3.030 | 3.688 | 0.822 | 0.411 | 92 | 0.254 | 3 |

## Granger tests

| cause | effect | lags | F | p_value | n |
|---|---|---|---|---|---|
| rsi_ffill | g_total | 2 | 0.097 | 0.908 | 93 |
| g_total | rsi_ffill | 2 | 2.136 | 0.124 | 93 |
| rsi_ffill | g_eu_eea | 2 | 0.549 | 0.580 | 93 |
| g_eu_eea | rsi_ffill | 2 | 3.850 | 0.025 | 93 |
| rsi_ffill | d_eu_share | 2 | 0.085 | 0.919 | 93 |
| d_eu_share | rsi_ffill | 2 | 0.945 | 0.393 | 93 |

## Distinctive terms by stance

| stance | term | count | log_ratio |
|---|---|---|---|
| restrictive | vulnerable | 11 | 2.624 |
| restrictive | challenge | 7 | 2.219 |
| restrictive | size | 7 | 2.219 |
| restrictive | undermine | 7 | 2.219 |
| restrictive | affected | 6 | 2.085 |
| restrictive | concentration | 6 | 2.085 |
| restrictive | supervised | 6 | 2.085 |
| restrictive | taxation | 6 | 2.085 |
| restrictive | functioning | 11 | 1.931 |
| restrictive | comprehensive | 5 | 1.931 |
| restrictive | deregulation | 5 | 1.931 |
| restrictive | ground | 5 | 1.931 |
| restrictive | importance | 5 | 1.931 |
| restrictive | introduce | 5 | 1.931 |
| restrictive | occur | 5 | 1.931 |
| neutral | trillion | 12 | 2.552 |
| neutral | electronic | 10 | 2.385 |
| neutral | bridge | 7 | 2.067 |
| neutral | conference | 7 | 2.067 |
| neutral | correlation | 7 | 2.067 |
| neutral | cryptography | 7 | 2.067 |
| neutral | sources | 7 | 2.067 |
| neutral | actually | 6 | 1.933 |
| neutral | calculations | 6 | 1.933 |
| neutral | history | 6 | 1.933 |
| neutral | panetta | 12 | 1.859 |
| neutral | among | 11 | 1.779 |
| neutral | june | 11 | 1.779 |
| neutral | ledger | 11 | 1.779 |
| neutral | november | 11 | 1.779 |
| supportive | reduce | 5 | 1.204 |
| supportive | countries | 6 | 0.783 |
| supportive | access | 5 | 0.223 |
| supportive | tokenised | 8 | -0.105 |
| supportive | europe | 5 | -0.154 |
| supportive | within | 5 | -0.262 |
| supportive | cross-border | 6 | -0.316 |
| supportive | currencies | 7 | -0.318 |
| supportive | digital | 21 | -0.399 |
| supportive | provide | 5 | -0.427 |
| supportive | payment | 16 | -0.574 |
| supportive | monetary | 11 | -0.659 |
| supportive | european | 7 | -0.680 |
| supportive | use | 5 | -0.693 |
| supportive | need | 5 | -0.709 |

