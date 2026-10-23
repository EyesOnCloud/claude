"""Draw a reproducible stratified random sample of high-confidence production extractions."""
import argparse, json, random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--confidence', type=float, default=0.90)
    p.add_argument('--per-stratum', type=int, default=2)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--data', default=str(HERE / 'extraction_records.jsonl'))
    p.add_argument('--output', default=str(HERE / 'high_confidence_review_sample.jsonl'))
    a = p.parse_args()
    if a.per_stratum < 1: raise SystemExit('--per-stratum must be at least 1')
    rows = [json.loads(x) for x in Path(a.data).read_text().splitlines() if x.strip()]
    high = [r for r in rows if r['split'] == 'production' and r['confidence'] >= a.confidence]
    strata = defaultdict(list)
    for r in high: strata[(r['document_type'], r['field'])].append(r)
    rng = random.Random(a.seed)
    sample = []
    print(f"High-confidence production records (confidence >= {a.confidence:.2f}): {len(high)}")
    print(f"Sampling up to {a.per_stratum} per document-type/field stratum; seed={a.seed}")
    for key, items in sorted(strata.items()):
        chosen = rng.sample(items, min(a.per_stratum, len(items)))
        print(f"  {key[0]} / {key[1]}: {len(items)} eligible, {len(chosen)} sampled")
        for r in chosen:
            # Keep expected_value and error_pattern out of the reviewer-facing file.
            sample.append({k: r[k] for k in (
                'extraction_id','document_id','document_type','field','predicted_value',
                'confidence','ambiguous_source','contradictory_source','source_excerpt'
            )})
    Path(a.output).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in sample))
    print(f"\nSaved reviewer-facing sample: {a.output}")
    print(f"Sample size: {len(sample)}")
    print('Expected values are intentionally omitted so the review remains blind.')

if __name__ == '__main__': main()
