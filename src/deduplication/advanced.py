#!/usr/bin/env python3
"""
accurate_deduplication.py – incremental & resumable (file **or** directory)
---------------------------------------------------------------------------
* **Single Markdown file** → split on "## Reported Issue by Agent" headers.
* **Directory**            → treat each `*.md` / `*.txt` file as one finding **or**
  only the files listed in a JSON-Lines *index* (see below).
* Streams findings one-by-one to **gemini-2.5-flash** via OpenRouter, using
  the structured-output feature (strict JSON schema).
* Writes / appends to `decisions.jsonl` and `unique_findings.txt` *after every
  finding*, so you can stop & restart safely.

**Index file** – selective processing
------------------------------------
If the directory contains an `f.jsonl` file (or you pass `--index my.jsonl`)
whose lines are JSON objects with a `path` field, **only** those files are
processed.  Paths are taken as *relative to the directory*.

```jsonl
{"id": "…", "path": "12564.md", "summary": "…"}
{"id": "…", "path": "12572.md", "summary": "…"}
```

Usage
-----
```bash
# monolithic file
python accurate_deduplication.py findings.md

# whole directory (all md/txt)
python accurate_deduplication.py analysis/data/findings

# directory but only files mentioned in index.jsonl
python accurate_deduplication.py analysis/data/findings --index analysis/data/f.jsonl
```
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv
import openai
from tqdm import tqdm
import numpy as np

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.5-flash"

if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not found in .env")

client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL)

JSON_SCHEMA = {
    "name": "dedup_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "duplicate": {"type": "string", "enum": ["YES", "NOT SURE", "NO"]},
            "duplicate_of": {"type": ["integer", "null"]},
        },
        "required": ["duplicate"],
        "additionalProperties": False,
    },
}

HEADER_RE = re.compile(
    r"^##\s*Reported\s+Issue\s+by\s+Agent\s+(\d+)[^\n]*$", re.I | re.M
)

DECISIONS_FILE = Path("decisions.jsonl")
UNIQUE_FILE = Path("unique_findings.txt")

# ──────────────────────────────────────────────
# EMBEDDING CONFIGURATION
# ──────────────────────────────────────────────
EMB_CACHE_DIR = ".embed_cache"
EMB_MODEL = "text-embedding-3-large"
K_NEAREST = 10
SIM_THRESHOLD = 0.0


def fingerprint(ids):
    import hashlib

    return hashlib.sha1("\n".join(ids).encode()).hexdigest()


def cache_paths(cache_dir, fp):
    d = Path(cache_dir)
    return d / f"{fp}.npy", d / f"{fp}.order", d / f"{fp}.labels.npy"


def load_embedding_matrix(ids: list[str]):
    fp = fingerprint(ids)
    vec_p, order_p, _ = cache_paths(EMB_CACHE_DIR, fp)
    if not vec_p.exists() or not order_p.exists():
        raise RuntimeError(
            "Pre-computed embedding cache not found – run dedupe_embeddings_cluster.py first"
        )
    V = np.load(vec_p)
    order = json.loads(order_p.read_text())
    id2row = {str(i): r for r, i in enumerate(order)}
    return V, id2row, fp


def embed_texts(texts, model, batch):
    import time

    cli, vecs = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL), []
    for i in range(0, len(texts), batch):
        while True:
            try:
                resp = cli.embeddings.create(model=model, input=texts[i : i + batch])
                break
            except:
                time.sleep(2)
        vecs.extend([d.embedding for d in resp.data])
    return np.array(vecs, dtype="float32")


def normalize(v):
    return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-8)


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────


def split_monolithic(raw: str) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    last = 0
    for m in HEADER_RE.finditer(raw):
        if findings:
            findings[-1]["text"] = raw[last : m.start()].strip()
        findings.append({"tag": m.group(1), "text": ""})
        last = m.end()
    if findings:
        findings[-1]["text"] = raw[last:].strip()
    return findings


# ──────────────────────────────────────────────
# PROGRESS LOADING
# ──────────────────────────────────────────────


def load_progress() -> Tuple[int, List[Tuple[int, str]]]:
    """Return (count processed, list of unique (id, text))."""
    if not DECISIONS_FILE.exists():
        return 0, []
    processed = 0
    uniques: List[Tuple[int, str]] = []
    with DECISIONS_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            processed += 1
            rec = json.loads(line)
            if rec.get("duplicate") == "NO":
                uniques.append((rec["id"], rec["text"]))
    return processed, uniques


def ensure_json(txt: str) -> Dict:
    try:
        return json.loads(txt.strip())
    except Exception as exc:
        raise ValueError("Model returned invalid JSON") from exc


# ──────────────────────────────────────────────
# k-NN HELPERS
# ──────────────────────────────────────────────


def nearest_unique_rows(query_row: int, k: int, rows: List[int]) -> List[int]:
    if not rows:
        return []
    sims = V[rows] @ V[query_row]
    if SIM_THRESHOLD > 0:
        mask = sims >= SIM_THRESHOLD
        rows_filt = [r for s, r, in zip(sims, rows) if s >= SIM_THRESHOLD]
    else:
        rows_filt = rows
    if not rows_filt:
        return []
    sims = [V[r] @ V[query_row] for r in rows_filt]
    idxs = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:k]
    return [rows_filt[i] for i in idxs]


def ask_model(idx, cur_text, query_row, context_texts: List[str]):
    # build single user prompt
    ctx_block = "\n\n".join(context_texts) if context_texts else "NONE"
    user_content = (
        f"Previous unique findings:\n{ctx_block}\n\n"
        f"Evaluate finding #{idx}:\n```\n{cur_text}\n```"
    )
    print(f"Context for finding #{idx}: {len(context_texts)}")
    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior bug-triage assistant. Decide if the NEW finding "
                "duplicates any previous UNIQUE finding and reply with JSON matching schema."
            ),
        },
        {"role": "user", "content": user_content},
    ]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
        reasoning_effort="high",
    )
    return ensure_json(resp.choices[0].message.content)


# ──────────────────────────────────────────────
# GATHER FINDINGS
# ──────────────────────────────────────────────


def gather_findings(src: Path, *, index: Path | None = None) -> List[Dict[str, str]]:
    if src.is_file():
        return split_monolithic(src.read_text("utf-8"))
    if not src.is_dir():
        raise ValueError(f"{src} is neither file nor directory")
    if index is None:
        cand = src / "f.jsonl"
        if cand.exists():
            index = cand
    if index and index.exists():
        files = []
        with index.open("r", encoding="utf-8") as fh:
            for ln in fh:
                rec = json.loads(ln)
                p = rec.get("path")
                if p:
                    files.append(src / p)
        files = sorted(files, key=lambda f: int(Path(f).stem))
    else:
        files = sorted(
            (p for p in src.iterdir() if p.suffix in {".md", ".txt"}),
            key=lambda f: int(f.stem),
        )
    return [
        {"tag": f.stem, "text": f.read_text("utf-8").strip()}
        for f in files
        if f.exists()
    ]


# ──────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────


def process(src: Path, *, index: Path | None = None):
    findings = gather_findings(src, index=index)
    ids = [f["tag"] for f in findings]
    global V, id2row, embedding_fp
    V, id2row, embedding_fp = load_embedding_matrix(ids)

    done, uniques = load_progress()
    # rebuild unique_rows and context_texts
    unique_rows: List[int] = []
    context_texts: List[str] = []
    for uid, utxt in uniques:
        tag = findings[uid - 1]["tag"]
        row = id2row.get(str(tag))
        if row is not None:
            unique_rows.append(row)
            context_texts.append(f"{uid}. {utxt.replace('\n',' ')}")

    total = len(findings)
    if done >= total:
        print("All findings already processed – nothing to do.")
        return
    print(f"Resuming at {done}/{total}; unique so far: {len(unique_rows)}")

    dec_f = DECISIONS_FILE.open("a", encoding="utf-8")
    uniq_f = UNIQUE_FILE.open("a" if UNIQUE_FILE.exists() else "w", encoding="utf-8")

    with tqdm(total=total, initial=done, unit="finding") as bar:
        for idx in range(done + 1, total + 1):
            entry = findings[idx - 1]
            print(f"\n\n── Finding #{idx} ({entry['tag']}) ──")

            # ensure vector
            qr = id2row.get(entry["tag"])
            if qr is None:
                vec = embed_texts([entry["text"][:8192]], EMB_MODEL, 1)[0]
                vec = vec / np.linalg.norm(vec)
                V = np.vstack([V, vec])
                qr = len(V) - 1
                id2row[entry["tag"]] = qr
                # flush new cache
                vp, op, _ = cache_paths(EMB_CACHE_DIR, embedding_fp)
                np.save(vp, V)
                Path(op).write_text(json.dumps(list(id2row.keys())))

            nbrs = nearest_unique_rows(qr, K_NEAREST, unique_rows)
            ctx = [context_texts[i] for i, r in enumerate(unique_rows) if r in nbrs]
            verdict = ask_model(idx, entry["text"], qr, ctx)
            flag = verdict.get("duplicate", "NOT SURE")
            dup = verdict.get("duplicate_of")

            rec = {
                "id": idx,
                "duplicate": flag,
                "duplicate_of": dup,
                "text": entry["text"],
            }
            dec_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            dec_f.flush()

            if flag == "NO":
                new_no = len(context_texts) + 1
                uniq_f.write(f"Finding #{new_no}\n{entry['text']}\n\n")
                uniq_f.flush()
                unique_rows.append(qr)
                context_texts.append(f"{idx}. {entry['text'].replace('\n',' ')}")
                print(f"✓ UNIQUE  (stored as #{new_no})")
                # flush cache again
                vp, op, _ = cache_paths(EMB_CACHE_DIR, embedding_fp)
                np.save(vp, V)
                Path(op).write_text(json.dumps(list(id2row.keys())))
            else:
                print(f"≈ DUPLICATE of {dup} ({flag})")
            bar.update(1)

    dec_f.close()
    uniq_f.close()
    print(f"\nAll done. Total unique findings: {len(unique_rows)}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Deduplicate findings via gemini-2.5-flash / OpenRouter with embedding filter"
    )
    p.add_argument("path", type=Path, help="File OR directory containing findings")
    p.add_argument(
        "--index", type=Path, help="JSONL index listing which files should be processed"
    )
    p.add_argument(
        "--k",
        type=int,
        default=K_NEAREST,
        help="Top-k nearest uniques for prompt context",
    )
    p.add_argument(
        "--sim-threshold",
        type=float,
        default=SIM_THRESHOLD,
        help="Min cosine sim for context (0 disables)",
    )
    args = p.parse_args()
    K_NEAREST = args.k
    SIM_THRESHOLD = args.sim_threshold
    process(args.path, index=args.index)
