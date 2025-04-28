#!/usr/bin/env python3
"""
filter.py  INPUT.jsonl  OUTPUT.jsonl

Pipeline
--------
1. Embed every summary with an OpenAI embedding model (default: text-embedding-3-large).
   • Vectors cached to <cache_dir>/<fingerprint>.npy  (fingerprint = SHA-1 of ids).
2. Normalize vectors to unit length.
3. Cluster with HDBSCAN (density-based, deterministic).
4. Keep one representative per cluster (earliest numeric path); keep all noise.
5. Write representatives to OUTPUT.jsonl (sorted by path).
6. Save labels to <cache_dir>/<fingerprint>.labels.npy for later inspection.

Resumable: if cache entry for the exact input fingerprint exists, embedding is skipped.
"""

import argparse, hashlib, json, os, pathlib, time
import random, numpy as np
import hdbscan
from tqdm import tqdm
from openai import OpenAI

# ─── defaults ───────────────────────────────────────────────────────────────
DEF_MODEL = "text-embedding-3-large"
DEF_BATCH = 256
DEF_MIN_CL = 2
DEF_EPS = 0.0
DEF_CACHE = ".embed_cache"
# ────────────────────────────────────────────────────────────────────────────


def load_jsonl(p):  # -> list[dict]
    return [json.loads(line) for line in pathlib.Path(p).open()]


# ─── caching helpers ────────────────────────────────────────────────────────
def fingerprint(ids):
    return hashlib.sha1("\n".join(ids).encode()).hexdigest()


def cache_paths(cache_dir, fp):
    d = pathlib.Path(cache_dir)
    return d / f"{fp}.npy", d / f"{fp}.order", d / f"{fp}.labels.npy"


def try_load_cache(cache_dir, fp, n_expected):
    emb_p, ord_p, _ = cache_paths(cache_dir, fp)
    if emb_p.exists() and ord_p.exists():
        order = json.loads(ord_p.read_text())
        if len(order) == n_expected:
            return np.load(emb_p), order
    return None, None


def save_cache(cache_dir, fp, vecs, order, labels):
    pathlib.Path(cache_dir).mkdir(exist_ok=True, parents=True)
    emb_p, ord_p, lab_p = cache_paths(cache_dir, fp)
    np.save(emb_p, vecs)
    ord_p.write_text(json.dumps(order))
    np.save(lab_p, labels)


# ─── embedding ──────────────────────────────────────────────────────────────
def embed_texts(texts, model, batch):
    client, vecs = OpenAI(), []
    for i in tqdm(range(0, len(texts), batch), desc="embedding"):
        while True:
            try:
                resp = client.embeddings.create(model=model, input=texts[i : i + batch])
                break
            except:
                time.sleep(2)
        vecs.extend([d.embedding for d in resp.data])
    return np.array(vecs, dtype="float32")


def normalize(v):
    return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-8)


# ─── main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_jsonl")
    ap.add_argument("output_jsonl")
    ap.add_argument("--model", default=DEF_MODEL)
    ap.add_argument("--batch", type=int, default=DEF_BATCH)
    ap.add_argument("--min-cluster", type=int, default=DEF_MIN_CL)
    ap.add_argument("--epsilon", type=float, default=DEF_EPS)
    ap.add_argument("--cache-dir", default=DEF_CACHE)
    args = ap.parse_args()

    records = load_jsonl(args.input_jsonl)
    records.sort(key=lambda r: int(r["path"].split(".")[0]))  # deterministic
    ids = [r["id"] for r in records]
    fp = fingerprint(ids)

    vecs, order = try_load_cache(args.cache_dir, fp, len(records))
    if vecs is None:
        summaries = [r["summary"] for r in records]
        vecs = embed_texts(summaries, args.model, args.batch)
        order = ids

    vecs = normalize(vecs)

    random.seed(42)
    np.random.seed(42)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=args.min_cluster,
        metric="euclidean",
        cluster_selection_epsilon=args.epsilon,
        prediction_data=False,
    ).fit(vecs)
    labels = clusterer.labels_

    label_to_indices = {}
    for idx, lab in enumerate(labels):
        label_to_indices.setdefault(lab, []).append(idx)

    keep_mask = np.zeros(len(records), dtype=bool)
    for lab, idxs in label_to_indices.items():
        if lab == -1:  # noise
            keep_mask[idxs] = True
        else:
            chosen = min(idxs, key=lambda i: int(records[i]["path"].split(".")[0]))
            keep_mask[chosen] = True

    uniques = [rec for rec, keep in zip(records, keep_mask) if keep]

    out_p = pathlib.Path(args.output_jsonl)
    out_p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uniques))
    save_cache(args.cache_dir, fp, vecs, order, labels)

    print(f"kept {len(uniques)} of {len(records)} → {out_p}")


if __name__ == "__main__":
    main()
