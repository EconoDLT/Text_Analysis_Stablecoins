#!/usr/bin/env python3
"""
ECB Stablecoin Stance Monitor -- prototype (Python version).

Pipeline (identical to R/ecb_stablecoin.R; both read config/config.json):
  1. Load ECB speeches (2019-01-01 .. 2026-10-01), clean text, split into sentences.
  2. Keep stablecoin passages: keyword sentence +/- `window` neighbouring sentences.
  3. Label every passage
       - stance  (restrictive -1 / neutral 0 / supportive +1)
           a) dictionary baseline (transparent word lists)
           b) zero-shot NLI language model (DeBERTa-v3, no training needed)  <- main measure
           c) optional generative LLM (Qwen2.5-Instruct) with the codebook as prompt
       - tone    (negative -1 / neutral 0 / positive +1) with FinBERT-tone
  4. Human validation: export a random sample to labels/validation_sample.csv; once a
     coder fills it in, re-running the script reports accuracy, macro-F1 and Cohen's kappa.
  5. Monthly indices: attention, Regulatory Stance Index RSI = (N+ - N-)/N, Tone Index.
  6. Analysis: speakers, stance x tone, USD vs EUR focus, distinctive words, before/after
     milestones, structural breaks (Bai-Perron), ADF, and the link to stablecoin supply
     (OLS with Newey-West errors + Granger tests).
  7. Writes CSV tables, PNG figures and outputs/summary.md.

Usage:
    python python/ecb_stablecoin.py                 # dictionary + NLI stance + FinBERT tone
    python python/ecb_stablecoin.py --models none   # dictionary only (fast, no downloads)
    python python/ecb_stablecoin.py --llm           # also run the generative LLM labeller
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

STANCE_NAMES = {-1: "restrictive", 0: "neutral", 1: "supportive"}
STANCE_CODES = {v: k for k, v in STANCE_NAMES.items()}


# ----------------------------------------------------------------------------- setup
def parse_args():
    p = argparse.ArgumentParser(description="ECB stablecoin stance monitor (prototype)")
    p.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   help="repository root (default: parent of this script)")
    p.add_argument("--models", choices=["none", "nli"], default="nli",
                   help="'nli' = zero-shot NLI stance + FinBERT tone; 'none' = dictionary only")
    p.add_argument("--llm", action="store_true", help="also label stance with a generative LLM")
    p.add_argument("--batch", type=int, default=8, help="batch size for the language models")
    return p.parse_args()


def log(msg):
    print(f"[ecb-stablecoin] {msg}", flush=True)


# ----------------------------------------------------------------------------- 1. text
MOJIBAKE = {  # UTF-8 read as Mac Roman / Windows-1252 (seen in exported CSVs)
    "‚Äô": "'", "‚Äò": "'", "‚Äú": '"', "‚Äù": '"',
    "‚Äì": "-", "‚Äî": "-", "‚Ç¨": "EUR ", "Â ": " ",
    "â€™": "'", "â€˜": "'", "â€œ": '"', "â€\u009d": '"',
    "â€“": "-", "â€”": "-", "â‚¬": "EUR ",
}
UNICODE_PUNCT = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
                 "—": "-", "‑": "-", "€": "EUR ", " ": " "}


def clean_text(x: str) -> str:
    if not isinstance(x, str):
        return ""
    for k, v in MOJIBAKE.items():
        x = x.replace(k, v)
    for k, v in UNICODE_PUNCT.items():
        x = x.replace(k, v)
    x = re.sub(r"\[\d+\]", " ", x)          # footnote markers [12]
    x = re.sub(r"\s+", " ", x)
    return x.strip()


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) > 0]


def load_speeches(cfg, root):
    path = os.path.join(root, cfg["files"]["speeches"])
    df = pd.read_csv(path, sep="|", quoting=3, dtype=str, keep_default_na=False,
                     encoding="utf-8", encoding_errors="replace", on_bad_lines="warn")
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    df = df[(df["date"] >= cfg["period"]["start"]) & (df["date"] <= cfg["period"]["end"])].copy()
    for c in ["speakers", "title", "subtitle", "contents"]:
        df[c] = df[c].map(clean_text)
    df = df[df["contents"].str.len() > 0]
    df = df.drop_duplicates(subset=["contents"])
    df = df.sort_values(["date", "title", "speakers"], kind="mergesort").reset_index(drop=True)
    df["speech_id"] = [f"S{i + 1:05d}" for i in range(len(df))]
    df.loc[df["speakers"] == "", "speakers"] = "(unknown)"
    return df


def extract_passages(sp, cfg):
    kw = re.compile(cfg["keywords"], re.I)
    cite = re.compile(cfg["citation_filter"], re.I)
    w = int(cfg["window"])
    rows, n_sent = [], []
    for r in sp.itertuples(index=False):
        sents = split_sentences(r.contents)
        n_sent.append(len(sents))
        ok = [not cite.search(s) for s in sents]
        hits = [i for i, s in enumerate(sents) if ok[i] and kw.search(s)]
        windows = []
        for i in hits:
            a, b = max(0, i - w), min(len(sents) - 1, i + w)
            if windows and a <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], b)
            else:
                windows.append([a, b])
        for k, (a, b) in enumerate(windows):
            text = " ".join(sents[j] for j in range(a, b + 1) if ok[j])
            rows.append(dict(passage_id=f"{r.speech_id}_P{k + 1:02d}", speech_id=r.speech_id,
                             date=r.date, speaker=r.speakers, title=r.title, text=text,
                             n_words=len(text.split())))
    sp = sp.assign(n_sentences=n_sent)
    ps = pd.DataFrame(rows, columns=["passage_id", "speech_id", "date", "speaker", "title", "text", "n_words"])
    return sp, ps


def tag_focus(ps, cfg):
    usd = ps["text"].str.contains(cfg["focus"]["usd"], case=False, regex=True)
    eur = ps["text"].str.contains(cfg["focus"]["eur"], case=False, regex=True)
    ps["focus"] = np.select([usd & eur, usd, eur], ["both", "usd", "eur"], "general")
    return ps


# ----------------------------------------------------------------------------- 3. labels
def dictionary_stance(ps, cfg):
    def count(words, text):
        t = text.lower()
        return sum(len(re.findall(r"\b" + re.escape(wd), t)) for wd in words)
    res = ps["text"].map(lambda t: count(cfg["dictionary"]["restrictive"], t))
    sup = ps["text"].map(lambda t: count(cfg["dictionary"]["supportive"], t))
    ps["dict_n_res"], ps["dict_n_sup"] = res, sup
    ps["stance_dict"] = np.sign(sup - res).astype(int)
    return ps


def nli_stance(ps, cfg, batch):
    from transformers import pipeline
    log(f"zero-shot NLI stance with {cfg['models']['stance_nli']} ...")
    clf = pipeline("zero-shot-classification", model=cfg["models"]["stance_nli"], device=-1)
    lab = cfg["nli_labels"]
    inv = {v: k for k, v in lab.items()}
    out = clf(ps["text"].tolist(), candidate_labels=list(lab.values()),
              hypothesis_template=cfg["nli_template"], multi_label=False, batch_size=batch)
    if isinstance(out, dict):
        out = [out]
    probs = [{inv[l]: s for l, s in zip(o["labels"], o["scores"])} for o in out]
    for k in ["restrictive", "neutral", "supportive"]:
        ps[f"nli_p_{k[:3]}"] = [p[k] for p in probs]
    ps["stance_nli"] = [STANCE_CODES[max(p, key=p.get)] for p in probs]
    return ps


def finbert_tone(ps, cfg, batch):
    from transformers import pipeline
    log(f"tone with {cfg['models']['tone']} ...")
    clf = pipeline("text-classification", model=cfg["models"]["tone"], device=-1,
                   truncation=True, max_length=512)
    out = clf(ps["text"].tolist(), batch_size=batch)
    m = {"positive": 1, "neutral": 0, "negative": -1}
    ps["tone"] = [m[o["label"].lower()] for o in out]
    ps["tone_score"] = [o["score"] for o in out]
    return ps


def llm_stance(ps, cfg):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = cfg["models"]["llm"]
    log(f"generative LLM stance with {name} (slow on CPU) ...")
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, torch_dtype="auto")
    model.eval()
    labels = []
    for t in ps["text"]:
        msg = [{"role": "user", "content": cfg["llm_prompt"].replace("{text}", t)}]
        ids = tok.apply_chat_template(msg, add_generation_prompt=True, return_tensors="pt")
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=5, do_sample=False)
        ans = tok.decode(gen[0, ids.shape[1]:], skip_special_tokens=True).strip().lower()
        hit = re.search(r"restrictive|neutral|supportive", ans)
        labels.append(STANCE_CODES[hit.group(0)] if hit else np.nan)
    ps["stance_llm"] = labels
    return ps


# ----------------------------------------------------------------------------- 4. validation
def cohen_kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    cats = np.union1d(a, b)
    po = np.mean(a == b)
    pe = sum(np.mean(a == c) * np.mean(b == c) for c in cats)
    return np.nan if pe == 1 else (po - pe) / (1 - pe)


def macro_f1(gold, pred):
    f = []
    for c in (-1, 0, 1):
        tp = np.sum((pred == c) & (gold == c))
        fp = np.sum((pred == c) & (gold != c))
        fn = np.sum((pred != c) & (gold == c))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(f))


def validation(ps, cfg, root):
    path = os.path.join(root, "labels", "validation_sample.csv")
    if not os.path.exists(path):
        n = min(int(cfg["validation_n"]), len(ps))
        smp = ps.sample(n=n, random_state=int(cfg["seed"]))[["passage_id", "date", "speaker", "text"]]
        smp = smp.sort_values("passage_id")
        for c in ["stance_coder1", "stance_coder2", "stance_gold", "tone_coder1", "tone_coder2", "tone_gold"]:
            smp[c] = ""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        smp.to_csv(path, index=False)
        log(f"validation sample written to {path} -- fill in the coder columns (-1/0/1) and re-run")
        return None
    v = pd.read_csv(path, dtype={"passage_id": str})
    rows = []

    def gold(prefix):
        g = pd.to_numeric(v.get(f"{prefix}_gold"), errors="coerce")
        c1 = pd.to_numeric(v.get(f"{prefix}_coder1"), errors="coerce")
        return g.fillna(c1), c1, pd.to_numeric(v.get(f"{prefix}_coder2"), errors="coerce")

    for dim, methods in [("stance", ["stance_dict", "stance_nli", "stance_llm"]), ("tone", ["tone"])]:
        g, c1, c2 = gold(dim)
        both = c1.notna() & c2.notna()
        if both.sum() > 0:
            rows.append(dict(dimension=dim, method="coder1_vs_coder2", n=int(both.sum()),
                             accuracy=float(np.mean(c1[both] == c2[both])),
                             macro_f1=np.nan, kappa=cohen_kappa(c1[both], c2[both])))
        m = v[["passage_id"]].merge(ps, on="passage_id", how="left")
        for meth in methods:
            if meth not in m.columns:
                continue
            pred = pd.to_numeric(m[meth], errors="coerce")
            ok = g.notna() & pred.notna()
            if ok.sum() == 0:
                continue
            rows.append(dict(dimension=dim, method=meth, n=int(ok.sum()),
                             accuracy=float(np.mean(g[ok].values == pred[ok].values)),
                             macro_f1=macro_f1(g[ok].values, pred[ok].values),
                             kappa=cohen_kappa(g[ok].values, pred[ok].values)))
    if not rows:
        log("validation sample exists but has no human labels yet")
        return None
    return pd.DataFrame(rows)


def method_agreement(ps):
    cols = [c for c in ["stance_dict", "stance_nli", "stance_llm"] if c in ps.columns]
    rows = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = ps[cols[i]], ps[cols[j]]
            ok = a.notna() & b.notna()
            rows.append(dict(method_a=cols[i], method_b=cols[j], n=int(ok.sum()),
                             agreement=float(np.mean(a[ok] == b[ok])), kappa=cohen_kappa(a[ok], b[ok])))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- 5. indices
def index_from(x):
    x = pd.Series(x).dropna()
    return np.nan if len(x) == 0 else (np.sum(x == 1) - np.sum(x == -1)) / len(x)


def monthly_indices(sp, ps, cfg):
    months = pd.period_range(cfg["period"]["start"], cfg["period"]["end"], freq="M")
    sp = sp.assign(month=sp["date"].dt.to_period("M"))
    ps = ps.assign(month=ps["date"].dt.to_period("M"))
    mention = ps.groupby("speech_id").size()
    sp["mentions"] = sp["speech_id"].isin(mention.index)
    rows = []
    for m in months:
        s, p = sp[sp["month"] == m], ps[ps["month"] == m]
        rows.append(dict(month=str(m), n_speeches=len(s), n_speeches_stablecoin=int(s["mentions"].sum()),
                         n_passages=len(p), n_restrictive=int((p["stance"] == -1).sum()),
                         n_neutral=int((p["stance"] == 0).sum()), n_supportive=int((p["stance"] == 1).sum()),
                         rsi=index_from(p["stance"]),
                         ti=index_from(p["tone"]) if "tone" in p else np.nan))
    mi = pd.DataFrame(rows)
    mi["attention"] = np.where(mi["n_speeches"] > 0, mi["n_speeches_stablecoin"] / mi["n_speeches"].clip(lower=1), 0.0)
    mi["rsi_ffill"] = mi["rsi"].ffill()
    mi["ti_ffill"] = mi["ti"].ffill()
    return mi


# ----------------------------------------------------------------------------- 6. analysis
def speaker_table(ps):
    g = ps.groupby("speaker")
    out = pd.DataFrame({"n_passages": g.size(),
                        "n_speeches": g["speech_id"].nunique(),
                        "rsi": g["stance"].apply(index_from),
                        "share_restrictive": g["stance"].apply(lambda x: np.mean(x == -1)),
                        "ti": g["tone"].apply(index_from) if "tone" in ps else np.nan})
    return out.reset_index().sort_values(["n_passages", "speaker"], ascending=[False, True])


def stance_tone_table(ps):
    if "tone" not in ps or ps["tone"].isna().all():
        return None
    t = pd.crosstab(ps["stance"].map(STANCE_NAMES), ps["tone"].map({-1: "negative", 0: "neutral", 1: "positive"}))
    return t.reindex(index=["restrictive", "neutral", "supportive"],
                     columns=["negative", "neutral", "positive"], fill_value=0)


def focus_table(ps):
    g = ps.groupby("focus")
    return pd.DataFrame({"n_passages": g.size(), "rsi": g["stance"].apply(index_from),
                         "ti": g["tone"].apply(index_from) if "tone" in ps else np.nan}).reset_index()


def top_terms(ps, cfg, k=15, min_count=5):
    stop = set(cfg["stopwords"])
    toks = ps["text"].str.lower().str.findall(r"[a-z][a-z-]{2,}")
    toks = toks.map(lambda ws: [w for w in ws if w not in stop])
    rows = []
    vocab = set(w for ws in toks for w in ws)
    V = len(vocab)
    for lab in (-1, 0, 1):
        inside = pd.Series([w for ws, s in zip(toks, ps["stance"]) if s == lab for w in ws]).value_counts()
        outside = pd.Series([w for ws, s in zip(toks, ps["stance"]) if s != lab for w in ws]).value_counts()
        n_in, n_out = inside.sum(), outside.sum()
        if n_in == 0:
            continue
        cand = inside[inside >= min_count]
        lr = np.log((cand + 1) / (n_in + V)) - np.log((outside.reindex(cand.index).fillna(0) + 1) / (n_out + V))
        tab = pd.DataFrame({"term": cand.index, "count": cand.values.astype(int), "log_ratio": lr.values})
        tab = tab.sort_values(["log_ratio", "count", "term"], ascending=[False, False, True], kind="mergesort").head(k)
        for r in tab.itertuples(index=False):
            rows.append(dict(stance=STANCE_NAMES[lab], term=r.term, count=int(r.count), log_ratio=float(r.log_ratio)))
    return pd.DataFrame(rows)


def milestone_tests(ps, cfg):
    from scipy import stats
    rows = []
    h = int(cfg["event_window_months"])
    for ms in cfg["milestones"]:
        d = pd.Timestamp(ms["date"])
        pre = ps[(ps["date"] >= d - pd.DateOffset(months=h)) & (ps["date"] < d)]["stance"].dropna()
        post = ps[(ps["date"] >= d) & (ps["date"] < d + pd.DateOffset(months=h))]["stance"].dropna()
        r = dict(milestone=ms["label"], date=ms["date"], n_before=len(pre), n_after=len(post),
                 mean_before=pre.mean() if len(pre) else np.nan, mean_after=post.mean() if len(post) else np.nan,
                 diff=np.nan, t=np.nan, p_value=np.nan)
        if len(pre) >= 2 and len(post) >= 2:
            t = stats.ttest_ind(post, pre, equal_var=False)
            r.update(diff=post.mean() - pre.mean(), t=float(t.statistic), p_value=float(t.pvalue))
        rows.append(r)
    return pd.DataFrame(rows)


def bai_perron_mean(y, trim=0.15, max_breaks=5):
    """Mean-shift breaks by dynamic programming (Bai & Perron 2003), BIC as in R strucchange."""
    y = np.asarray(y, float)
    n = len(y)
    h = int(math.floor(trim * n))
    cs, cs2 = np.concatenate([[0], np.cumsum(y)]), np.concatenate([[0], np.cumsum(y ** 2)])

    def ssr(i, j):  # segment y[i..j] inclusive
        L = j - i + 1
        s = cs[j + 1] - cs[i]
        return cs2[j + 1] - cs2[i] - s * s / L

    M = min(max_breaks, n // h - 1)
    INF = float("inf")
    # best[m][j]: min SSR of y[0..j] with m breaks; arg[m][j]: last break position
    best = [[INF] * n for _ in range(M + 1)]
    arg = [[-1] * n for _ in range(M + 1)]
    for j in range(h - 1, n):
        best[0][j] = ssr(0, j)
    for m in range(1, M + 1):
        for j in range((m + 1) * h - 1, n):
            for b in range(m * h - 1, j - h + 1):
                v = best[m - 1][b] + ssr(b + 1, j)
                if v < best[m][j]:
                    best[m][j], arg[m][j] = v, b
    res = []
    for m in range(0, M + 1):
        rss = best[m][n - 1]
        if not np.isfinite(rss):
            continue
        bps, j = [], n - 1
        for mm in range(m, 0, -1):
            j = arg[mm][j]
            bps.append(j)
        df = (m + 1) + m + 1
        ll = -0.5 * n * (math.log(2 * math.pi) + math.log(rss / n) + 1)
        res.append(dict(m=m, rss=rss, bic=-2 * ll + df * math.log(n), breaks=sorted(bps)))
    return pd.DataFrame(res), h


def adf(x):
    from statsmodels.tsa.stattools import adfuller
    x = pd.Series(x).dropna().values
    k = int(math.trunc((len(x) - 1) ** (1 / 3)))
    r = adfuller(x, maxlag=k, autolag=None, regression="ct")
    return dict(n=len(x), lags=k, adf_stat=float(r[0]), p_value=float(r[1]))


# ----------------------------------------------------------------------------- market data
def read_any(path):
    if path.lower().endswith((".xlsx", ".xls", ".xslx")):
        return pd.read_excel(path, engine="openpyxl", keep_default_na=False, na_values=[""])
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def find_file(root, rel):
    p = os.path.join(root, rel)
    if os.path.exists(p):
        return p
    stem = os.path.splitext(p)[0]
    cand = sorted(glob.glob(stem + ".*"))
    return cand[0] if cand else None


def load_market(cfg, root):
    sc_path, btc_path = find_file(root, cfg["files"]["stablecoins"]), find_file(root, cfg["files"]["bitcoin"])
    if sc_path is None or btc_path is None:
        log("market files not found -- skipping market analysis")
        return None, None
    sc = read_any(sc_path)
    sc = sc.rename(columns={sc.columns[0]: "Date"})
    sc["Date"] = pd.to_datetime(sc["Date"], errors="coerce")
    sc = sc.dropna(subset=["Date"])
    juris = [c for c in sc.columns if c not in ("Date", "Total")]
    for c in juris + ["Total"]:
        sc[c] = pd.to_numeric(sc[c], errors="coerce")
    check = dict(columns=juris, max_rel_diff_total_vs_sum=float(
        np.nanmax(np.abs(sc[juris].sum(axis=1, min_count=1) - sc["Total"]) / sc["Total"])))
    groups = cfg["jurisdiction_groups"]
    known = set(c for g in groups.values() for c in g)
    extra = [c for c in juris if c not in known]
    if extra:
        log(f"jurisdiction columns not in any group (added to 'other'): {extra}")
    for g, cols in groups.items():
        cols = [c for c in cols if c in sc.columns] + (extra if g == "other" else [])
        sc[g] = sc[cols].sum(axis=1, min_count=1).fillna(0.0)
    sc["month"] = sc["Date"].dt.to_period("M")
    m = sc.sort_values("Date", kind="mergesort").groupby("month").tail(1).set_index("month")  # last row of each month
    m = m[["Total"] + list(groups)].rename(columns={"Total": "total"})
    m["eu_share"] = m["eu_eea"] / m["total"]
    for c in ["total", "eu_eea", "us", "offshore"]:
        v = m[c].where(m[c] > 0)
        m[f"g_{c}"] = np.log(v).diff()
    m["d_eu_share"] = m["eu_share"].diff() * 100

    b = read_any(btc_path)
    b["date"] = pd.to_datetime(b["event_date"].astype(str).str[:10], errors="coerce")
    b["close"] = pd.to_numeric(b["close_price_usd"], errors="coerce")
    b = b.dropna(subset=["date", "close"]).sort_values("date")
    b["month"] = b["date"].dt.to_period("M")
    bm = b.groupby("month").tail(1).set_index("month")["close"]
    m["r_btc"] = np.log(bm).diff().reindex(m.index)
    m.index = m.index.astype(str)
    return m.reset_index(), check


def market_models(mi, mk, cfg):
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import grangercausalitytests
    d = mi.merge(mk, on="month", how="inner")
    mdates = {ms["label"]: ms["date"][:7] for ms in cfg["milestones"]}
    for lab in cfg["regression_milestones"]:
        d[f"M_{lab}"] = (d["month"] >= mdates[lab]).astype(float)
    d["rsi_l1"] = d["rsi_ffill"].shift(1)
    d["att_l1"] = d["attention"].shift(1)
    d["btc_l1"] = d["r_btc"].shift(1)
    reg_rows, gr_rows = [], []
    p = int(cfg["granger_lags"])
    for y in ["g_total", "g_eu_eea", "d_eu_share"]:
        d["y_l1"] = d[y].shift(1)
        xs = ["rsi_l1", "att_l1", "btc_l1", "y_l1"] + [f"M_{l}" for l in cfg["regression_milestones"]]
        dd = d[[y] + xs].replace([np.inf, -np.inf], np.nan).dropna()
        xs = [x for x in xs if dd[x].std() > 0]  # drop constant dummies
        if len(dd) < len(xs) + 10:
            continue
        T = len(dd)
        L = int(math.floor(4 * (T / 100) ** (2 / 9)))
        fit = sm.OLS(dd[y], sm.add_constant(dd[xs])).fit(cov_type="HAC", cov_kwds={"maxlags": L, "use_correction": False})
        for v in ["const"] + xs:
            reg_rows.append(dict(y=y, term=v, coef=fit.params[v], se_nw=fit.bse[v], t=fit.tvalues[v],
                                 p_value=fit.pvalues[v], n=T, r2=fit.rsquared, nw_lags=L))
        g = d[[y, "rsi_ffill"]].replace([np.inf, -np.inf], np.nan).dropna()
        for cause, effect in [("rsi_ffill", y), (y, "rsi_ffill")]:
            r = grangercausalitytests(g[[effect, cause]], maxlag=[p])[p][0]["ssr_ftest"]
            gr_rows.append(dict(cause=cause, effect=effect, lags=p, F=float(r[0]), p_value=float(r[1]), n=len(g)))
    return pd.DataFrame(reg_rows), pd.DataFrame(gr_rows), d


# ----------------------------------------------------------------------------- figures
def figures(mi, ps, spk, breaks, mk_d, cfg, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = pd.PeriodIndex(mi["month"], freq="M").to_timestamp()
    fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax[0].bar(x, mi["n_passages"], width=25, color="#4C72B0")
    ax[0].set_ylabel("stablecoin passages")
    ax[1].plot(x, mi["rsi_ffill"], color="#C44E52", label="RSI (stance)")
    if mi["ti_ffill"].notna().any():
        ax[1].plot(x, mi["ti_ffill"], color="#55A868", ls="--", label="Tone index")
    ax[1].axhline(0, color="grey", lw=0.5)
    ax[1].set_ylim(-1.05, 1.05)
    ax[1].set_ylabel("index (-1 restrictive, +1 supportive)")
    for ms in cfg["milestones"]:
        for a in ax:
            a.axvline(pd.Timestamp(ms["date"]), color="grey", ls=":", lw=0.8)
        ax[0].text(pd.Timestamp(ms["date"]), ax[0].get_ylim()[1] * 0.95, ms["label"], rotation=90,
                   fontsize=6, va="top", ha="right")
    for b in breaks:
        ax[1].axvline(pd.Timestamp(b + "-01"), color="#C44E52", lw=1.5, alpha=0.4)
    ax[1].legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig1_attention_stance.png"), dpi=200)
    plt.close(fig)

    s = spk[spk["n_passages"] >= 5].sort_values("rsi")
    if len(s):
        fig, ax = plt.subplots(figsize=(7, 0.4 * len(s) + 1.2))
        ax.barh(s["speaker"], s["rsi"], color=np.where(s["rsi"] < 0, "#C44E52", "#4C72B0"))
        ax.axvline(0, color="grey", lw=0.5)
        ax.set_xlim(-1, 1)
        ax.set_xlabel("RSI (speakers with >= 5 passages)")
        fig.tight_layout()
        fig.savefig(os.path.join(out, "fig2_speakers.png"), dpi=200)
        plt.close(fig)

    if mk_d is not None and len(mk_d):
        x = pd.PeriodIndex(mk_d["month"], freq="M").to_timestamp()
        fig, ax1 = plt.subplots(figsize=(9, 3.5))
        ax1.plot(x, mk_d["rsi_ffill"], color="#C44E52", label="ECB RSI")
        ax1.set_ylabel("ECB RSI")
        ax2 = ax1.twinx()
        ax2.plot(x, mk_d["eu_share"] * 100, color="#4C72B0", label="EU/EEA share of stablecoin value (%)")
        ax2.set_ylabel("EU/EEA share (%)")
        fig.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "fig3_stance_market.png"), dpi=200)
        plt.close(fig)


# ----------------------------------------------------------------------------- main
def md_table(df, digits=3):
    if df is None or len(df) == 0:
        return "_(not available)_\n"
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.{digits}f}")
    head = "| " + " | ".join(map(str, d.columns)) + " |\n|" + "---|" * len(d.columns) + "\n"
    return head + "".join("| " + " | ".join(map(str, r)) + " |\n" for r in d.itertuples(index=False))


def main():
    a = parse_args()
    root = a.root
    cfg = json.load(open(os.path.join(root, "config", "config.json"), encoding="utf-8"))
    out = os.path.join(root, "outputs", "python")
    os.makedirs(out, exist_ok=True)

    sp = load_speeches(cfg, root)
    sp, ps = extract_passages(sp, cfg)
    ps = tag_focus(ps, cfg)
    log(f"{len(sp)} speeches, {len(ps)} stablecoin passages in {ps['speech_id'].nunique()} speeches")

    ps = dictionary_stance(ps, cfg)
    stance_source = "dictionary"
    if a.models == "nli":
        try:
            ps = nli_stance(ps, cfg, a.batch)
            stance_source = "nli"
        except Exception as e:  # no internet / no transformers
            log(f"NLI model unavailable ({type(e).__name__}: {e}); falling back to dictionary stance")
        try:
            ps = finbert_tone(ps, cfg, a.batch)
        except Exception as e:
            log(f"FinBERT unavailable ({type(e).__name__}: {e}); tone not computed")
    if a.llm:
        try:
            ps = llm_stance(ps, cfg)
        except Exception as e:
            log(f"LLM unavailable ({type(e).__name__}: {e})")
    ps["stance"] = ps["stance_nli"] if stance_source == "nli" else ps["stance_dict"]
    if "tone" not in ps:
        ps["tone"] = np.nan

    val = validation(ps, cfg, root)
    agree = method_agreement(ps)
    mi = monthly_indices(sp, ps, cfg)
    spk = speaker_table(ps)
    st = stance_tone_table(ps)
    foc = focus_table(ps)
    terms = top_terms(ps, cfg)
    mst = milestone_tests(ps, cfg)

    first = mi["rsi"].first_valid_index()
    bp_months, bp_tab, h = [], None, None
    if first is not None:
        y = mi.loc[first:, "rsi_ffill"].values
        bp_tab, h = bai_perron_mean(y, cfg["break_trim"], cfg["max_breaks"])
        best = bp_tab.loc[bp_tab["bic"].idxmin()]
        months = mi.loc[first:, "month"].tolist()
        bp_months = [months[i] for i in best["breaks"]]
        bp_tab["breaks"] = bp_tab["breaks"].map(lambda b: ",".join(months[i] for i in b))

    mk, check = load_market(cfg, root)
    adf_rows = []
    for nm, ser in [("rsi_ffill", mi.loc[first:, "rsi_ffill"] if first is not None else pd.Series(dtype=float)),
                    ("attention", mi["attention"])]:
        if ser.notna().sum() > 10:
            adf_rows.append(dict(series=nm, **adf(ser)))
    reg = gr = mk_d = None
    if mk is not None:
        for nm in ["g_total", "g_eu_eea", "d_eu_share", "r_btc"]:
            if mk[nm].replace([np.inf, -np.inf], np.nan).notna().sum() > 10:
                adf_rows.append(dict(series=nm, **adf(mk[nm].replace([np.inf, -np.inf], np.nan))))
        reg, gr, mk_d = market_models(mi, mk, cfg)
        mk.to_csv(os.path.join(out, "market_monthly.csv"), index=False)
    adf_tab = pd.DataFrame(adf_rows)

    # ---- write outputs
    ps.to_csv(os.path.join(out, "passages_labelled.csv"), index=False)
    mi.to_csv(os.path.join(out, "monthly_indices.csv"), index=False)
    spk.to_csv(os.path.join(out, "speakers.csv"), index=False)
    foc.to_csv(os.path.join(out, "focus.csv"), index=False)
    terms.to_csv(os.path.join(out, "top_terms.csv"), index=False)
    mst.to_csv(os.path.join(out, "milestones_before_after.csv"), index=False)
    agree.to_csv(os.path.join(out, "method_agreement.csv"), index=False)
    adf_tab.to_csv(os.path.join(out, "adf.csv"), index=False)
    if st is not None:
        st.to_csv(os.path.join(out, "stance_by_tone.csv"))
    if bp_tab is not None:
        bp_tab.to_csv(os.path.join(out, "breaks.csv"), index=False)
    if val is not None:
        val.to_csv(os.path.join(out, "validation_metrics.csv"), index=False)
    if reg is not None:
        reg.to_csv(os.path.join(out, "market_regressions.csv"), index=False)
        gr.to_csv(os.path.join(out, "granger.csv"), index=False)
    figures(mi, ps, spk, bp_months, mk_d, cfg, out)

    dist = ps["stance"].map(STANCE_NAMES).value_counts().reindex(["restrictive", "neutral", "supportive"], fill_value=0)
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write("# ECB stablecoin stance monitor -- summary (Python)\n\n")
        f.write(f"- Speeches {cfg['period']['start']} to {cfg['period']['end']}: **{len(sp)}**; "
                f"speeches with stablecoin passages: **{ps['speech_id'].nunique()}**; passages: **{len(ps)}**\n")
        f.write(f"- Main stance measure: **{stance_source}**; stance distribution: "
                + ", ".join(f"{k} {v}" for k, v in dist.items()) + f"; overall RSI = {index_from(ps['stance']):.3f}\n")
        if ps["tone"].notna().any():
            f.write(f"- Overall tone index = {index_from(ps['tone']):.3f}\n")
        if check:
            f.write(f"- Market file check: max |Total - sum(jurisdictions)|/Total = {check['max_rel_diff_total_vs_sum']:.4f}\n")
        f.write(f"- Structural breaks in monthly RSI (BIC, trim {cfg['break_trim']}, h = {h}): "
                f"{', '.join(bp_months) if bp_months else 'none'}\n\n")
        for title, tab in [("Validation against human labels", val), ("Agreement between methods", agree),
                           ("Speakers", spk), ("Stance x tone", None if st is None else st.reset_index()),
                           ("USD vs EUR focus", foc), ("Before/after milestones (passage-level, +/-12 months)", mst),
                           ("Breaks", bp_tab), ("ADF tests (constant + trend)", adf_tab),
                           ("Market regressions (Newey-West)", reg), ("Granger tests", gr),
                           ("Distinctive terms by stance", terms)]:
            f.write(f"## {title}\n\n{md_table(tab)}\n")
    log(f"done -- outputs in {out}")


if __name__ == "__main__":
    main()
