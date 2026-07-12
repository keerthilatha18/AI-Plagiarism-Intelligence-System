"""
scripts/seed_data.py
---------------------
Inserts ~15 synthetic submissions into Cloudant for local testing and demo purposes.

Mix of submission types:
  - 5 clean submissions (well-written, unique)
  - 5 lightly paraphrased (similar content, slightly reworded)
  - 5 obviously AI-generated (uniform structure, generic phrasing)

Usage:
    cd backend
    python ../scripts/seed_data.py

Requires a valid .env file with CLOUDANT_URL, CLOUDANT_APIKEY, and
optionally WATSONX_* for live embedding generation.  If watsonx is not
configured, synthetic embedding vectors are used instead.
"""
from __future__ import annotations

import os
import sys
import random
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Allow importing backend modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from services.cloudant_service import CloudantService
from services.stylometrics import compute_style_fingerprint, compute_readability_score

# ── Synthetic text corpus ─────────────────────────────────────────────────────

CLEAN_TEXTS = [
    """The French Revolution fundamentally altered the political landscape of Europe.
Rooted in Enlightenment ideals of liberty, equality, and fraternity, it challenged
the absolute authority of the monarchy and aristocracy. The storming of the Bastille
in 1789 symbolized popular resistance against tyranny and sparked a decade of radical
political and social transformation. Thinkers such as Rousseau had laid the intellectual
groundwork for the uprising, arguing that legitimate authority derives from the consent
of the governed rather than divine right.""",

    """Climate change represents one of the most pressing scientific and policy challenges
of the twenty-first century. Human activities, particularly the combustion of fossil fuels,
have elevated atmospheric CO2 concentrations to levels not seen in over 800,000 years.
The resulting warming triggers cascading effects: rising sea levels, intensifying storm
systems, shifting agricultural zones, and accelerated biodiversity loss. Effective responses
require both rapid decarbonization of energy systems and substantial adaptation investments
in vulnerable regions.""",

    """Shakespeare's Hamlet explores the paralysing effect of excessive reflection on action.
The prince's famous soliloquies reveal a mind perpetually interrogating its own motives,
unable to commit to vengeance despite clear evidence of his father's murder. Critics have
debated whether this hesitation stems from moral scrupulousness, Oedipal conflict, or
a broader philosophical scepticism. What is certain is that Hamlet's delay drives the
tragedy forward and gives the play its distinctive psychological depth.""",

    """Machine learning systems trained on biased historical data risk perpetuating and
amplifying existing social inequities. When algorithmic decision-making governs access
to credit, employment, or criminal sentencing, systemic biases embedded in training
corpora can lead to discriminatory outcomes at scale. Addressing this requires not only
technical interventions such as re-sampling and adversarial debiasing but also
institutional accountability mechanisms and meaningful community input into system design.""",

    """The human microbiome—the trillions of microorganisms inhabiting the gut, skin, and
oral cavity—plays a far larger role in health than previously appreciated. Recent research
implicates gut microbial composition in conditions ranging from inflammatory bowel disease
to depression and autism spectrum disorder. The microbiome develops in early childhood,
is shaped by diet, antibiotics, and environmental exposures, and can be modulated through
targeted interventions including probiotics and faecal microbiota transplantation.""",
]

PARAPHRASED_TEXTS = [
    """The French Revolution dramatically changed Europe's political map. Based on
Enlightenment concepts of freedom, equality, and brotherhood, it opposed the complete
power of kings and nobles. The capture of the Bastille fortress in 1789 stood for
people standing up against oppression and started ten years of major political and
social change. Philosophers like Rousseau had prepared the intellectual foundation
for the revolt, saying that real authority comes from the agreement of the people
rather than from God.""",

    """Global warming is among the most urgent scientific and governmental issues of
the 2000s. Human actions, especially burning oil and coal, have raised the amount of
CO2 in the air to the highest level in more than 800,000 years. The warming that follows
causes a chain of effects: higher ocean levels, stronger hurricanes, moving farm areas,
and faster loss of animal species. Solving this problem demands quick removal of carbon
from energy production and large spending on preparing at-risk communities.""",

    """In Shakespeare's Hamlet, too much thinking stops the hero from taking action.
The prince's well-known speeches show a mind that keeps questioning its own reasons
and cannot decide on revenge even though the proof of his father's killing is obvious.
Scholars have argued about whether this waiting comes from moral care, psychological
issues, or a deep doubt about knowledge. What is clear is that Hamlet's delay moves
the tragedy ahead and makes the play uniquely deep in psychological terms.""",

    """AI systems that learn from unfair past data risk continuing and growing existing
social unfairness. When computer programs decide who gets loans, jobs, or how criminals
are sentenced, unfairness baked into training data can cause harmful results on a large
scale. Fixing this needs both technical solutions like changing data sets and fighting
bias, and also organisational oversight and real input from affected communities into
how these systems are built.""",

    """The microbiome—the huge number of tiny organisms living in the gut, on skin, and
in mouths—has a much bigger effect on health than scientists once thought. New studies
connect the bacteria in the gut to conditions including bowel disease, sadness, and
developmental disorders. The microbiome forms in the first years of life and is affected
by what we eat, medicines, and our environment, and can be changed through methods
including friendly bacteria supplements and transplants of intestinal material.""",
]

AI_GENERATED_TEXTS = [
    """The French Revolution was a significant event in European history. It occurred
in 1789 and had many important consequences. The revolution was caused by a variety of
factors including economic hardship, social inequality, and political instability.
The key outcomes of the French Revolution include the abolition of the monarchy, the
establishment of a republic, and the spread of democratic ideals throughout Europe.
These developments had lasting impacts on the political landscape of the continent.
Overall, the French Revolution was a pivotal moment in world history.""",

    """Climate change is a major issue that affects the entire planet. It is caused by
greenhouse gas emissions from human activities. The effects of climate change include
rising temperatures, melting ice caps, and extreme weather events. Many scientists and
policymakers agree that urgent action is needed to address this problem. Solutions
include transitioning to renewable energy, improving energy efficiency, and implementing
carbon pricing mechanisms. International cooperation is essential to effectively combat
climate change and its consequences.""",

    """Shakespeare wrote many famous plays and sonnets during his lifetime. Hamlet is
considered one of his greatest works. The play explores themes of revenge, mortality,
and existential doubt. The main character, Prince Hamlet, must decide whether to avenge
his father's murder. Throughout the play, he struggles with this decision. The play
contains many famous quotes that are still widely known today. Hamlet is frequently
performed in theaters around the world and is studied in academic settings internationally.""",

    """Artificial intelligence and machine learning have become increasingly important
in modern society. These technologies are used in a wide range of applications including
healthcare, finance, transportation, and entertainment. While AI offers many benefits,
it also raises important ethical concerns. Issues such as privacy, bias, and job
displacement must be carefully considered. Researchers and policymakers are working
to develop frameworks to ensure that AI is developed and deployed responsibly. This
is an important area that will continue to evolve in the coming years.""",

    """The human body contains many different types of microorganisms. These include
bacteria, viruses, and fungi. The collection of microorganisms in the human body is
called the microbiome. Research has shown that the microbiome plays an important role
in human health. It affects digestion, immunity, and even mental health. Scientists are
studying the microbiome to better understand how it influences disease. This research
may lead to new treatments and therapies in the future. The microbiome is a fascinating
area of scientific inquiry with many potential applications.""",
]

# ── Synthetic embedding generation ────────────────────────────────────────────

def _synthetic_embedding(text: str, dims: int = 128) -> list[float]:
    """
    Generate a deterministic pseudo-embedding based on character frequencies.
    Not semantically meaningful — for local testing only.
    """
    vec = [0.0] * dims
    for i, ch in enumerate(text[:dims * 4]):
        vec[i % dims] += ord(ch) / 10000.0
    # Normalize
    mag = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / mag, 6) for v in vec]


def _days_ago(n: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=n)
    return dt.isoformat()


# ── Main seeding logic ────────────────────────────────────────────────────────

def seed(cloudant_url: str, cloudant_apikey: str) -> None:
    print("Connecting to Cloudant...")
    service = CloudantService(url=cloudant_url, apikey=cloudant_apikey)

    # Two instructors, two assignments
    instructors = ["inst-alice", "inst-bob"]
    assignments = ["asgn-history-101", "asgn-cs-201"]

    all_submissions = (
        [(t, "clean") for t in CLEAN_TEXTS]
        + [(t, "paraphrased") for t in PARAPHRASED_TEXTS]
        + [(t, "ai_generated") for t in AI_GENERATED_TEXTS]
    )

    created = []
    for idx, (raw_text, label) in enumerate(all_submissions):
        sub_id = f"seed-{label[:4]}-{str(uuid4())[:8]}"
        instructor_id = instructors[idx % 2]
        assignment_id = assignments[idx % 2]

        fp = compute_style_fingerprint(raw_text)
        readability = compute_readability_score(raw_text)
        embedding = _synthetic_embedding(raw_text)

        doc = {
            "submission_id": sub_id,
            "student_id": f"student-{(idx + 1):03d}",
            "assignment_id": assignment_id,
            "instructor_id": instructor_id,
            "raw_text": raw_text.strip(),
            "file_url": "",
            "submitted_at": _days_ago(random.randint(1, 60)),
            "embedding_vector": embedding,
            "readability_score": readability,
            "style_fingerprint": fp,
            "seed_label": label,  # Metadata for test verification
        }

        try:
            service.create_submission(doc)
            created.append(sub_id)
            print(f"  [{idx+1:2d}/15] Created {label:12s} submission: {sub_id}")
        except Exception as exc:
            print(f"  [{idx+1:2d}/15] FAILED ({label}): {exc}")

    print(f"\nDone. Seeded {len(created)}/15 submissions.")
    print(f"Instructors: {instructors}")
    print(f"Assignments: {assignments}")
    print("\nTo rebuild a baseline, call:")
    print(f"  POST /api/v1/instructors/{instructors[0]}/baseline/rebuild?assignment_id={assignments[0]}")


if __name__ == "__main__":
    cloudant_url = os.getenv("CLOUDANT_URL")
    cloudant_apikey = os.getenv("CLOUDANT_APIKEY")

    if not cloudant_url or not cloudant_apikey:
        print("ERROR: CLOUDANT_URL and CLOUDANT_APIKEY must be set in your environment or .env file.")
        sys.exit(1)

    seed(cloudant_url, cloudant_apikey)
