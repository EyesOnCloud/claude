"""Route production extractions to human review using calibrated thresholds and source risk."""
import argparse, json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load_jsonl(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(HERE / 'extraction_records.jsonl'))
    p.add_argument('--calibration', default=str(HERE / 'calibrated_thresholds.json'))
    p.add_argument('--capacity', type=int, default=10)
    p.add_argument('--output', default=str(HERE / 'human_review_queue.jsonl'))
    a = p.parse_args()
    if a.capacity < 1: raise SystemExit('--capacity must be at least 1')
    calibration = json.loads(Path(a.calibration).read_text())
    thresholds = calibration['thresholds']
    rows = [r for r in load_jsonl(a.data) if r['split'] == 'production']
    queue = []
    for r in rows:
        key = f"{r['document_type']}|{r['field']}"
        segment = thresholds.get(key)
        threshold = segment.get('auto_accept_threshold') if segment else None
        reasons = []
        priority = 0
        if r['contradictory_source']:
            reasons.append('contradictory_source'); priority = max(priority, 100)
        if r['ambiguous_source']:
            reasons.append('ambiguous_source'); priority = max(priority, 90)
        if threshold is None:
            reasons.append('no_validated_threshold'); priority = max(priority, 85)
        elif r['confidence'] < threshold:
            reasons.append('below_calibrated_threshold')
            priority = max(priority, 70 + min(14, round((threshold - r['confidence']) * 100)))
        if reasons:
            q = {k: r[k] for k in (
                'extraction_id','document_id','document_type','field','predicted_value',
                'confidence','ambiguous_source','contradictory_source','source_excerpt'
            )}
            q.update({'review_reasons': reasons, 'priority': priority,
                      'calibrated_threshold': threshold})
            queue.append(q)
    queue.sort(key=lambda r: (-r['priority'], r['confidence'], r['extraction_id']))
    selected = queue[:a.capacity]
    Path(a.output).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in selected))
    print(f"Production extractions: {len(rows)}")
    print(f"Candidates routed to review: {len(queue)}")
    print(f"Reviewer capacity: {a.capacity} | Items prioritized into queue: {len(selected)}")
    print('\n=== PRIORITIZED HUMAN REVIEW QUEUE ===')
    for r in selected:
        print(f"priority={r['priority']:3d} confidence={r['confidence']:.2f} {r['document_type']}/{r['field']} {r['extraction_id']} reasons={','.join(r['review_reasons'])}")
    print(f"\nSaved queue to {a.output}")
    if len(queue) > a.capacity:
        print(f"Overflow: {len(queue)-a.capacity} items remain pending because reviewer capacity is limited.")
    print('Note: Do not auto-accept fields from segments with no validated threshold or conflicting/ambiguous source evidence.')

if __name__ == '__main__': main()
