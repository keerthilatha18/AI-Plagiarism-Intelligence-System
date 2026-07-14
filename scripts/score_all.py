"""
scripts/score_all.py
---------------------
Score all seeded submissions so flags appear in the UI immediately.
Run from project root after the backend is started:
    python scripts/score_all.py
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from services.cloudant_service import CloudantService
from services.granite_client import GraniteClient
from services.scoring import run_scoring_pipeline
from config import get_settings

settings = get_settings()
cloudant = CloudantService(url=settings.cloudant_url, apikey=settings.cloudant_apikey)
granite  = GraniteClient(api_key=settings.watsonx_api_key,
                         project_id=settings.watsonx_project_id,
                         url=settings.watsonx_url)

# Fetch all submissions
all_subs = cloudant.query_submissions({"submission_id": {"$gt": ""}})
print(f"Found {len(all_subs)} submissions\n")

total_flags = 0
for sub in all_subs:
    sid = sub['submission_id']
    try:
        flags = run_scoring_pipeline(sub, cloudant, granite,
                                     settings.paraphrase_cosine_threshold,
                                     settings.style_drift_threshold)
        n = len(flags)
        total_flags += n
        flag_types = [f.flag_type for f in flags]
        print(f"  {sid:30s}  {n} flag(s)  {flag_types}")
    except Exception as e:
        print(f"  {sid:30s}  ERROR: {e}")

print(f"\nDone. Total flags created: {total_flags}")
