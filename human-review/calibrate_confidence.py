"""Calibrate field-level auto-accept thresholds on labeled validation data."""
import argparse, json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]

def accuracy(rows):
    return sum(r['predicted_value'] == r['expected_value'] for r in rows) / len(rows) if rows else 0.0

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(HERE / 'extraction_records.jsonl'))
    p.add_argument('--target-accuracy', type=float, default=0.95)
    p.add_argument('--min-support', type=int, default=5,
                   help='Minimum number of validation extractions accepted at a threshold')
    p.add_argument('--output', default=str(HERE / 'calibrated_thresholds.json'))
    a = p.parse_args()
    if not 0 < a.target_accuracy <= 1: raise SystemExit('--target-accuracy must be in (0, 1]')
    rows = [r for r in load(a.data) if r['split'] == 'validation']
    groups = defaultdict(list)
    for r in rows: groups[(r['document_type'], r['field'])].append(r)
    thresholds = {}
    print(f"Target validation accuracy: {a.target_accuracy:.1%}; minimum accepted validation records: {a.min_support}")
    print(f"{'SEGMENT':38} {'N':>4} {'ACC':>7} {'THRESHOLD':>11}  DECISION")
    for (doc, field), items in sorted(groups.items()):
        overall = accuracy(items)
        # Require the set of all examples at or above a candidate threshold to meet target accuracy and support.
        candidates = sorted({round(float(r['confidence']), 4) for r in items})
        selected = None
        for threshold in candidates:
            accepted = [r for r in items if r['confidence'] >= threshold]
            if len(accepted) >= a.min_support and accuracy(accepted) >= a.target_accuracy:
                selected = threshold
                break
        key = f"{doc}|{field}"
        thresholds[key] = {
            'document_type': doc,
            'field': field,
            'validation_count': len(items),
            'validation_accuracy': round(overall, 4),
            'target_accuracy': a.target_accuracy,
            'minimum_support': a.min_support,
            'auto_accept_threshold': selected,
            'auto_accept_enabled': selected is not None,
        }
        value = f"{selected:.2f}" if selected is not None else 'NONE'
        decision = 'calibrated' if selected is not None else 'REVIEW ALL: threshold unsupported'
        print(f"{doc + ' / ' + field:38} {len(items):4d} {overall:6.1%} {value:>11}  {decision}")
    result = {
        'target_accuracy': a.target_accuracy,
        'minimum_support': a.min_support,
        'source_split': 'validation',
        'thresholds': thresholds,
        'warning': 'Small synthetic validation samples are instructional only; do not use these thresholds in production.'
    }
    Path(a.output).write_text(json.dumps(result, indent=2) + '\n')
    print(f"\nSaved calibration results to {a.output}")
    print('Thresholds are segment-specific. Segments without sufficient evidence are not auto-accepted.')

if __name__ == '__main__': main()
