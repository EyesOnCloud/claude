"""Score a review sample against the synthetic labels after the review exercise."""
import argparse, json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(HERE / 'extraction_records.jsonl'))
    p.add_argument('--sample', default=str(HERE / 'high_confidence_review_sample.jsonl'))
    a = p.parse_args()
    all_rows = {r['extraction_id']: r for r in read_jsonl(a.data)}
    sample = read_jsonl(a.sample)
    if not sample: raise SystemExit('Sample is empty. Run review_sampling.py first.')
    groups = defaultdict(list); incorrect_patterns = defaultdict(int); wrong = 0
    for s in sample:
        r = all_rows.get(s['extraction_id'])
        if not r: raise SystemExit(f"Sample ID not found in source data: {s['extraction_id']}")
        is_correct = r['predicted_value'] == r['expected_value']
        groups[(r['document_type'], r['field'])].append(is_correct)
        if not is_correct:
            wrong += 1
            incorrect_patterns[r.get('error_pattern') or 'unclassified'] += 1
    print(f"Reviewed sample: {len(sample)} | Incorrect: {wrong} | Sample error rate: {wrong/len(sample):.1%}")
    print('\n=== SAMPLE ERROR RATE BY STRATUM ===')
    for (doc, field), outcomes in sorted(groups.items()):
        errors = len(outcomes) - sum(outcomes)
        print(f"{doc} / {field}: {errors}/{len(outcomes)} errors ({errors/len(outcomes):.1%})")
    print('\n=== ERROR PATTERNS FOUND ===')
    if incorrect_patterns:
        for pattern, count in sorted(incorrect_patterns.items()): print(f"{pattern}: {count}")
    else:
        print('No errors were found in this sample. Continue sampling; zero observed errors does not prove zero risk.')
    print('\nNote: These labels are synthetic ground truth for the exercise. Real reviews must be adjudicated by reviewers.')

if __name__ == '__main__': main()
