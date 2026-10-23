"""Analyze aggregate accuracy and accuracy by document type and field."""
import argparse, json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def report(title, groups):
    print(f"\n=== {title} ===")
    print(f"{'SEGMENT':38} {'N':>4} {'CORRECT':>8} {'ACCURACY':>9}")
    for label, items in sorted(groups.items()):
        correct = sum(r['predicted_value'] == r['expected_value'] for r in items)
        accuracy = correct / len(items) if items else 0
        print(f"{label:38} {len(items):4d} {correct:8d} {accuracy:8.1%}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--split', choices=['all', 'validation', 'production'], default='all')
    p.add_argument('--data', default=str(HERE / 'extraction_records.jsonl'))
    a = p.parse_args()
    rows = load(a.data)
    if a.split != 'all': rows = [r for r in rows if r['split'] == a.split]
    if not rows: raise SystemExit('No records matched the selected split.')
    correct = sum(r['predicted_value'] == r['expected_value'] for r in rows)
    print(f"Records: {len(rows)} | Correct: {correct} | Overall accuracy: {correct/len(rows):.1%}")
    by_doc = defaultdict(list); by_field = defaultdict(list); by_segment = defaultdict(list)
    for r in rows:
        by_doc[r['document_type']].append(r)
        by_field[r['field']].append(r)
        by_segment[f"{r['document_type']} / {r['field']}"].append(r)
    report('ACCURACY BY DOCUMENT TYPE', by_doc)
    report('ACCURACY BY FIELD', by_field)
    report('ACCURACY BY DOCUMENT TYPE AND FIELD', by_segment)
    if a.split == 'all':
        print('\nInfo: Compare overall accuracy with each segment. A strong aggregate can hide a weak field/document-type combination.')

if __name__ == '__main__': main()
