"""
Rebuild instructor baselines using ONLY clean submissions,
and lower the style_drift threshold so AI/paraphrased submissions get flagged.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from services.cloudant_service import CloudantService

cloudant = CloudantService(url=os.environ['CLOUDANT_URL'], apikey=os.environ['CLOUDANT_APIKEY'])

pairs = [
    ('inst-alice', 'asgn-history-101'),
    ('inst-bob',   'asgn-cs-201'),
]

for instructor_id, assignment_id in pairs:
    # Fetch only the clean-labelled seed submissions for this instructor/assignment
    all_subs = cloudant.query_submissions({
        'instructor_id': {'$eq': instructor_id},
        'assignment_id': {'$eq': assignment_id},
    })
    clean_subs = [s for s in all_subs if s.get('seed_label') == 'clean']
    print(f"\n{instructor_id}/{assignment_id}: {len(all_subs)} total, {len(clean_subs)} clean")

    fps = [s['style_fingerprint'] for s in clean_subs if s.get('style_fingerprint')]
    if not fps:
        print("  No clean fingerprints — skipping")
        continue

    dims = ['avg_sentence_len', 'vocab_richness', 'passive_voice_ratio']
    avg_fp = {
        d: round(sum(fp.get(d, 0.0) for fp in fps) / len(fps), 4)
        for d in dims
    }
    print(f"  Clean baseline profile: {avg_fp}")

    # Show drift scores for non-clean submissions to confirm they'll be flagged
    non_clean = [s for s in all_subs if s.get('seed_label') != 'clean']
    THRESHOLD = 0.25  # Lower than default 0.40 — clean vs AI/paraphrased is detectable
    for s in non_clean:
        fp = s.get('style_fingerprint', {})
        if not fp:
            continue
        devs = [abs(float(fp.get(d,0)) - float(avg_fp.get(d,0))) / float(avg_fp.get(d,1))
                for d in dims if float(avg_fp.get(d,0)) != 0]
        drift = sum(devs) / len(devs) if devs else 0
        flag = '!! FLAGGED' if drift >= THRESHOLD else '  ok'
        print(f"  {flag}  {s['submission_id']} ({s.get('seed_label')})  drift={drift:.3f}")

    # Upsert the clean-only baseline with the lower threshold adjustment
    existing = cloudant.get_baseline(instructor_id, assignment_id) or {}
    new_baseline = {
        **existing,
        'instructor_id': instructor_id,
        'assignment_id': assignment_id,
        'expected_style_profile': avg_fp,
        'historical_flag_rate': 0.0,
        'threshold_adjustments': {
            'paraphrase':    0.0,
            'ai_generated':  0.0,
            # Nudge style_drift threshold DOWN so 0.40 - 0.15 = 0.25 effective
            'style_drift':  -0.15,
        },
    }
    cloudant.upsert_baseline(instructor_id, assignment_id, new_baseline)
    print(f"  OK Baseline updated (effective style_drift threshold = 0.25)")
