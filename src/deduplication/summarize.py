#!/usr/bin/env python3
"""
summarize.py <findings_dir> <out.jsonl>

– Same targets as before, but fires up to 300 concurrent workers.
– Uses the *sync* OpenAI client in a ThreadPoolExecutor; no asyncio/import churn.
– Idempotent: SHA-1 cache against out.jsonl.
"""

import hashlib, json, pathlib, re, sys, openai
from concurrent.futures import ThreadPoolExecutor, as_completed

MODEL = "gpt-4.1"
MAX_WORKERS = 300

SYSTEM_PROMPT = (
    "You are a senior compiler engineer. One paragraph ≤55 words: "
    "start with construct, state fault and misleading symptom; tiny code in back-ticks, "
    "use `...` to trim, no fillers, no bullets, no IDs/paths."
)

# ————————————————————————————————————————————————————————————————————————


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def compress(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


client = openai.OpenAI()  # global, safe for threads


def summarise(md_text: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": md_text[:10000]},
        ],
    )
    return compress(resp.choices[0].message.content)


# ————————————————————————————————————————————————————————————————————————


def load_done(jsonl_path: pathlib.Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    with jsonl_path.open() as f:
        return {json.loads(line)["id"] for line in f}


def main(src_dir: str, out_jsonl: str):
    src = pathlib.Path(src_dir)
    out = pathlib.Path(out_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)

    done_ids = load_done(out)
    tasks = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for md in sorted(src.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            h = sha1(text)
            if h in done_ids:
                continue
            tasks.append(pool.submit(summarise, text))
            tasks[-1].md_name = md.name
            tasks[-1].hash = h

        new_cnt = 0
        for fut in as_completed(tasks):
            try:
                summary = fut.result()
            except Exception as e:
                print(f"⚠️  {getattr(fut,'md_name','?')} failed: {e}")
                continue
            rec = {"id": fut.hash, "path": fut.md_name, "summary": summary}
            with out.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            new_cnt += 1
            print(f"{fut.md_name} ✔")

    print(f"new summaries written: {new_cnt}")


# ————————————————————————————————————————————————————————————————————————

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python summarize.py <findings_dir> <out.jsonl>")
    main(sys.argv[1], sys.argv[2])
