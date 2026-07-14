# Plagiarism Intelligence

An AI-driven academic integrity tool that detects paraphrased and AI-generated
plagiarism, learns instructor-specific style baselines over time, and enforces a
human-in-the-loop review step before any academic action is taken.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        IBM Code Engine                                   │
│                                                                          │
│  ┌──────────────────────┐          ┌───────────────────────────────────┐ │
│  │   Frontend           │  HTTPS   │   Backend (FastAPI / uvicorn)     │ │
│  │   React + Vite       │ ──────▶  │                                   │ │
│  │   nginx:80           │          │  /api/v1/submissions               │ │
│  └──────────────────────┘          │  /api/v1/flags                    │ │
│                                    │  /api/v1/instructors               │ │
│                                    └───────────┬───────────────────────┘ │
└────────────────────────────────────────────────│─────────────────────────┘
                                                 │
          ┌──────────────────────────────────────┼──────────────────────┐
          │                                      │                      │
          ▼                                      ▼                      ▼
  ┌───────────────────┐              ┌───────────────────┐   ┌─────────────────┐
  │  IBM Cloudant     │              │  IBM watsonx.ai   │   │  IBM Cloud COS  │
  │  (NoSQL)          │              │  Granite models   │   │  Raw files      │
  │                   │              │                   │   │                 │
  │  • submissions    │              │  • Slate-125M     │   │  submissions/   │
  │  • flags          │              │    (embeddings)   │   │  {id}/{file}    │
  │  • baselines      │              │  • Granite-13B    │   │                 │
  │  • audit_log      │              │    (classify +    │   └─────────────────┘
  └───────────────────┘              │     explain)      │
                                     └───────────────────┘
```

### Data flow for a new submission

1. **Upload** → `POST /submissions/upload` extracts text, stores file in COS,
   writes Submission doc to Cloudant.
2. **Process** → `POST /submissions/{id}/process` runs spaCy stylometrics and
   Granite embedding; updates the Cloudant doc.
3. **Score** → `POST /submissions/{id}/score` runs the full scoring pipeline:
   paraphrase detection, AI-text classification, style drift analysis. Each
   concern is written as a Flag doc with confidence + explanation.
4. **Review** → Instructor sees flags in the UI, reads the Granite explanation,
   then calls `PATCH /flags/{id}/decision` with `confirmed` or `dismissed`.
   This also nudges the instructor's threshold for future runs.

---

## IBM Cloud Lite Services Required

| Service | Purpose | Lite plan sufficient? |
|---|---|---|
| **IBM watsonx.ai** | Granite embeddings + text generation | Yes (rate-limited) |
| **IBM Cloudant** | Document storage for all 4 collections | Yes (1 GB free) |
| **IBM Cloud Object Storage** | Raw file storage | Yes (25 GB free) |
| **IBM Code Engine** | Container hosting for backend + frontend | Yes (100K vCPU-s free/mo) |

---

## Environment Variables

Copy `.env.example` to `backend/.env` and fill in your credentials.

| Variable | Required | Description |
|---|---|---|
| `WATSONX_API_KEY` | Yes | IBM Cloud API key with watsonx.ai access |
| `WATSONX_PROJECT_ID` | Yes | watsonx.ai project GUID |
| `WATSONX_URL` | Yes | watsonx.ai region URL (e.g. `https://us-south.ml.cloud.ibm.com`) |
| `CLOUDANT_URL` | Yes | Your Cloudant instance URL |
| `CLOUDANT_APIKEY` | Yes | Cloudant IAM API key |
| `COS_API_KEY` | Yes | COS IAM API key |
| `COS_INSTANCE_CRN` | Yes | COS resource instance CRN |
| `COS_BUCKET` | Yes | Bucket name for raw file storage |
| `COS_ENDPOINT_URL` | No | COS endpoint (default: `us-south`) |
| `PARAPHRASE_COSINE_THRESHOLD` | No | Default `0.82` |
| `STYLE_DRIFT_THRESHOLD` | No | Default `0.40` |
| `VITE_API_BASE_URL` | Frontend | Backend URL for the React app |

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- An IBM Cloud account with the four services provisioned

### Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

# Copy and fill in credentials
cp ../.env.example .env
# Edit .env with your IBM Cloud credentials

# Start the API server
uvicorn main:app --reload --port 8080
```

The API will be available at `http://localhost:8080`.
Interactive docs: `http://localhost:8080/docs`

### Frontend

```bash
cd frontend

npm install

# Create .env from example
echo "VITE_API_BASE_URL=http://localhost:8080" > .env

npm run dev
```

The UI will be available at `http://localhost:5173`.

### Seed sample data

```bash
# From the project root, with backend/.env populated:
cd backend
python ../scripts/seed_data.py
```

This inserts 15 synthetic submissions (5 clean, 5 paraphrased, 5 AI-generated)
across two instructors and two assignments.

### Run tests

```bash
cd backend
# Tests use mocked Granite — no live API calls required
pytest ../tests/ -v
```

---

## Deployment to IBM Code Engine

### 1. Authenticate and set up container registry

```bash
# Log in to IBM Cloud
ibmcloud login --apikey YOUR_IBMCLOUD_API_KEY -r us-south

# Target your resource group
ibmcloud target -g Default

# Log in to IBM Container Registry
ibmcloud cr login

# Create a namespace (if you don't have one)
ibmcloud cr namespace-add plagiarism-intel
```

### 2. Build and push images

```bash
# Backend
docker build -t us.icr.io/plagiarism-intel/backend:latest ./backend
docker push us.icr.io/plagiarism-intel/backend:latest

# Frontend (pass your backend Code Engine URL)
docker build \
  --build-arg VITE_API_BASE_URL=https://your-backend.us-south.codeengine.appdomain.cloud \
  -t us.icr.io/plagiarism-intel/frontend:latest \
  ./frontend
docker push us.icr.io/plagiarism-intel/frontend:latest
```

### 3. Create Code Engine project and applications

```bash
# Create project
ibmcloud ce project create --name plagiarism-intelligence

# Target project
ibmcloud ce project select --name plagiarism-intelligence

# Create a registry secret for IBM Container Registry
ibmcloud ce secret create --format registry \
  --name icr-secret \
  --server us.icr.io \
  --username iamapikey \
  --password YOUR_IBMCLOUD_API_KEY

# Deploy backend with all env vars
ibmcloud ce application create \
  --name pi-backend \
  --image us.icr.io/plagiarism-intel/backend:latest \
  --registry-secret icr-secret \
  --port 8080 \
  --min-scale 1 \
  --env WATSONX_API_KEY=YOUR_KEY \
  --env WATSONX_PROJECT_ID=YOUR_PROJECT_ID \
  --env WATSONX_URL=https://us-south.ml.cloud.ibm.com \
  --env CLOUDANT_URL=YOUR_CLOUDANT_URL \
  --env CLOUDANT_APIKEY=YOUR_CLOUDANT_KEY \
  --env COS_API_KEY=YOUR_COS_KEY \
  --env COS_INSTANCE_CRN=YOUR_CRN \
  --env COS_BUCKET=YOUR_BUCKET

# Get the backend URL
BACKEND_URL=$(ibmcloud ce application get --name pi-backend --output json | \
  python -c "import sys,json; print(json.load(sys.stdin)['status']['url'])")

# Deploy frontend pointing at backend
ibmcloud ce application create \
  --name pi-frontend \
  --image us.icr.io/plagiarism-intel/frontend:latest \
  --registry-secret icr-secret \
  --port 80
```

---

## Ethical Guardrails (implemented in code)

1. **No bare booleans** — every API response containing a flag includes
   `confidence` (0-1) and `granite_explanation` (human-readable evidence).
   See [`routers/submissions.py`](backend/routers/submissions.py).

2. **Human-in-the-loop required** — flags are never acted on automatically.
   `PATCH /flags/{id}/decision` is the only path to recording a decision, and
   it explicitly notes "no automatic action taken" in the response.
   See [`routers/flags.py`](backend/routers/flags.py).

3. **Audit log** — every scoring run writes to the `audit_log` Cloudant
   collection with timestamp, submission ID, and exact thresholds used.
   See [`services/scoring.py`](backend/services/scoring.py).

4. **Adaptive learning is transparent** — threshold nudges are stored
   numerically in the InstructorBaseline document and visible in the
   Instructor Baseline UI page.

---

## Project Structure

```
plagiarism-intelligence/
├── backend/
│   ├── main.py                  FastAPI app factory
│   ├── config.py                Pydantic v2 settings from env vars
│   ├── models/                  Pydantic data models
│   ├── routers/                 FastAPI route handlers
│   ├── services/                Business logic (scoring, Granite, Cloudant, COS)
│   └── utils/                   Text extraction helpers
├── tests/                       pytest tests (Granite is mocked)
├── scripts/seed_data.py         15 synthetic submissions for local testing
├── frontend/
│   ├── src/
│   │   ├── api/client.js        Centralised fetch wrapper
│   │   ├── pages/               Login, AssignmentList, SubmissionList,
│   │   │                        SubmissionDetail, InstructorBaseline
│   │   └── components/          FlagCard, ParagraphHighlight, ConfidenceBadge
│   └── Dockerfile               Multi-stage node → nginx
├── backend/Dockerfile
├── .env.example
└── README.md
```
#   A I - P l a g i a r i s m - I n t e l l i g e n c e - S y s t e m  
 #   A I - P l a g i a r i s m - I n t e l l i g e n c e - S y s t e m  
 