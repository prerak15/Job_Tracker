"""The starting skill catalogue — data, not logic.

Read out of the fifteen job descriptions stored in data/jobs.json on
2026-09-07, checked against the master resume. `skills.py` owns the behaviour;
this file only supplies rows, the same way company_seed.py and pattern_seed.py
do for their boards.

Three things to keep in mind when editing:

**Aliases are the join, and a careless one is silently wrong.** They are what
matches a skill against a job description, so a too-broad alias invents demand
that was never there and a too-narrow one hides demand that was. Never add a
two-letter alias, never add a word that is also ordinary English, and check a
new alias against the corpus before committing it — `skills.mentions` is a pure
function, so that costs nothing. An alias prefixed `re:` is a raw regex, matched
case-sensitively; each one below says which false positive it exists to kill.

**Skills already held belong here too.** The catalogue is the denominator for
`stats()["coverage"]`, so a file containing only gaps would report 0% forever
and say nothing. Rows with `level` at or above `target_level` drop out of the
queue on their own.

**`level` is the honest one.** 0 none · 1 aware · 2 used · 3 built · 4 shipped.
"Used" means touched it, "built" means made something non-trivial with it,
"shipped" means other people depend on it. A level inflated here becomes a
question that cannot be answered in an interview, which is the exact failure
the `exposed` state exists to catch.
"""

from __future__ import annotations

from typing import Any

# Guards, written out so the reason survives longer than the memory of the bug.
#
#   _GO      "Go ahead, apply anyway" (UiPath) is a word-boundary match on the
#            language name. Nothing else separates the verb from the language,
#            so the following word has to be excluded explicitly — the same
#            shape as discover.guess_seniority's `(?<!technical )staff`.
#   _VOICE   "voice pipeline" saw none of the Weekday posting, which writes
#            "voice pipelines" and "voice agents" throughout. Plurals are
#            handled generally by the matcher now, but the two-word forms still
#            need spelling out, and a bare "voice" would match any mention of
#            a phone call.
#   _STREAM  "SSE Streaming" sits in the skills row of seven tailored resumes.
#            Server-sent events are not Kafka, and matching them reported the
#            data-streaming gap as already claimed on most of the pipeline.
#   _R       "R" as a language is unusable as an alias at all: one letter, and
#            it collides with everything. Left out rather than guessed at.
_GO = r"re:\bGo\b(?!\s+(?:ahead|to|back|through|live|forward|beyond|deep|hand))"
_VOICE = r"re:(?i)\bvoice[ -](?:agent|pipeline|bot|assistant)s?\b"
_STREAMING = r"re:(?i)(?<!sse )\bstreaming\b"

SKILLS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # Cheap, recurring, and currently zero. Ordered first so a fresh board
    # reads as a work queue rather than an inventory.
    # ------------------------------------------------------------------
    {
        "key": "kubernetes",
        "name": "Kubernetes",
        "area": "infra",
        "order": 10,
        "aliases": ["Kubernetes", "K8s", "EKS", "GKE", "AKS", "container orchestration"],
        "level": 0,
        "effort": "days",
        "plan": "Both the tracker and Kestrel are already Dockerised. Deploy them to a "
        "local kind or k3s cluster, then once to a managed one.",
    },
    {
        "key": "airflow",
        "name": "Airflow / workflow orchestration",
        "area": "infra",
        "order": 11,
        "aliases": [
            "Airflow",
            "Cloud Composer",
            "Dagster",
            "Prefect",
            "workflow orchestration",
            "Flyte",
        ],
        "level": 0,
        "effort": "days",
        "plan": "One real DAG on Kestrel: ingest to embed to evaluate. Redis/BullMQ is a "
        "job queue, not a scheduler, and that substitution will not survive a follow-up.",
    },
    {
        "key": "observability",
        "name": "Observability",
        "area": "infra",
        "order": 12,
        "aliases": [
            "OpenTelemetry",
            "OTel",
            "distributed tracing",
            "structured logging",
            "observability",
            "Prometheus",
            "Grafana",
            "monitoring and alerting",
        ],
        "level": 0,
        "effort": "days",
        "plan": "Instrument the tracker with OpenTelemetry and Prometheus. It currently "
        "reports nothing measurable about itself.",
    },
    {
        "key": "terraform",
        "name": "Terraform / IaC",
        "area": "infra",
        "order": 13,
        "aliases": [
            "Terraform",
            "CloudFormation",
            "infrastructure-as-code",
            "infrastructure as code",
            "Pulumi",
            "GitOps",
        ],
        "level": 0,
        "effort": "days",
        "plan": "Provision the Kubernetes cluster from Terraform instead of a console. "
        "Rides along free with the Kubernetes work.",
    },
    {
        "key": "agent-frameworks",
        "name": "LangGraph / named agent frameworks",
        "area": "ml",
        "order": 14,
        "aliases": ["LangGraph", "LangChain", "LlamaIndex", "CrewAI", "Strands", "Google ADK"],
        "level": 0,
        "effort": "days",
        "plan": "Port one existing agent to LangGraph and carry both. MCP and the Agent "
        "SDK are the same competence and arguably deeper, but nothing screens on them.",
        "notes": "Token matching, not capability — treat it as a resume line, not a skill "
        "to learn from scratch.",
    },
    {
        "key": "grpc",
        "name": "gRPC / protobuf",
        "area": "backend",
        "order": 15,
        "aliases": ["gRPC", "protobuf", "protocol buffers"],
        "level": 0,
        "effort": "days",
        "plan": "One service in the tracker exposed over gRPC alongside its REST route.",
    },
    {
        "key": "ai-safety",
        "name": "AI safety (injection, PII, filtering)",
        "area": "ml",
        "order": 16,
        "aliases": [
            "prompt injection",
            "OWASP",
            "MITRE ATLAS",
            "NIST AI RMF",
            "content filtering",
            "toxicity",
            "AI safety",
            "PII handling",
            "guardrail",
        ],
        "level": 1,
        "effort": "days",
        "plan": "Kestrel already has evaluation infrastructure — add a prompt-injection "
        "and PII suite to the tracker's agent and write up what it catches.",
    },
    # ------------------------------------------------------------------
    # The expensive, recurring ones.
    # ------------------------------------------------------------------
    {
        "key": "mlops",
        "name": "Production ML lifecycle / MLOps",
        "area": "ml",
        "order": 20,
        "aliases": [
            "MLOps",
            "model registry",
            "experiment tracking",
            "MLflow",
            "training pipeline",
            "inference pipeline",
            "model monitoring",
            "model deployment",
            "feature store",
            "CI/CD for ML",
            "production machine learning",
            "end-to-end ML",
        ],
        "level": 0,
        "effort": "months",
        "plan": "Kestrel owns the evaluation half already. Automate train, evaluate, "
        "register, serve — one pipeline closes most of this and every JD that asks for it.",
    },
    {
        "key": "spark",
        "name": "Spark / distributed data processing",
        "area": "data",
        "order": 21,
        "aliases": ["Spark", "PySpark", "Scala", "Databricks", "big data", "MapReduce"],
        "level": 0,
        "effort": "months",
        "plan": "A PySpark stage over a real dataset in the Kestrel pipeline. PostgreSQL "
        "is currently the only data system on the resume.",
    },
    {
        "key": "lakehouse",
        "name": "Lakehouse / warehouse",
        "area": "data",
        "order": 22,
        "aliases": [
            "Iceberg",
            "Snowflake",
            "Hive",
            "Delta Lake",
            "lakehouse",
            "dbt",
            "data warehouse",
            "data warehousing",
            "dimensional",
            "BigQuery",
        ],
        "level": 0,
        "effort": "months",
        "plan": "Land the Kestrel corpus as Iceberg tables and query them, rather than "
        "reading Snowflake documentation.",
    },
    {
        "key": "streaming",
        "name": "Streaming / Kafka",
        "area": "data",
        "order": 23,
        "aliases": [
            "Kafka",
            "Kinesis",
            "Flink",
            "near real-time",
            "Pub/Sub",
            "stream processing",
            _STREAMING,
        ],
        "level": 0,
        "effort": "weeks",
        "plan": "Move the tracker's refresh loop onto a real event stream instead of a "
        "30-second poll.",
    },
    {
        "key": "statistics",
        "name": "Statistics and experimentation",
        "area": "ml",
        "order": 24,
        "aliases": [
            "statistics",
            "statistical",
            "hypothesis testing",
            "probability",
            "A/B test",
            "A/B testing",
            "causal inference",
            "experimentation",
        ],
        "level": 1,
        "effort": "weeks",
        "plan": "The cheapest of the expensive rows — it is reading, not infrastructure. "
        "Work through hypothesis testing, A/B design and causal inference, then apply "
        "them to Kestrel's evaluation numbers.",
    },
    {
        "key": "pytorch",
        "name": "PyTorch",
        "area": "ml",
        "order": 25,
        "aliases": ["PyTorch", "torch.nn"],
        "level": 0,
        "effort": "weeks",
        "plan": "Rebuild the Siamese network in PyTorch. Keras traces to 2023 and reads "
        "that way; PyTorch is what the JDs name.",
    },
    {
        "key": "fine-tuning",
        "name": "Fine-tuning and model training",
        "area": "ml",
        "order": 26,
        "aliases": [
            "fine-tuning",
            "fine-tune",
            "LoRA",
            "PEFT",
            "distributed training",
            "pre-training",
            "RLHF",
        ],
        "level": 0,
        "effort": "months",
        "plan": "One LoRA fine-tune of a small open-weight model on a real task, with "
        "before-and-after numbers. Everything on the resume today is LLM consumption.",
    },
    {
        "key": "boosted-models",
        "name": "Classical ML at production scale",
        "area": "ml",
        "order": 27,
        "aliases": [
            "XGBoost",
            "LightGBM",
            "gradient boosting",
            "boosted",
            "anomaly detection",
            "random forest",
        ],
        "level": 1,
        "effort": "weeks",
        "plan": "The tabular half of the ML-coded JDs. One boosted model end to end with "
        "a held-out evaluation, not a notebook.",
    },
    {
        "key": "distributed-systems",
        "name": "Distributed systems",
        "area": "backend",
        "order": 28,
        "aliases": [
            "distributed systems",
            "fault tolerance",
            "fault-tolerant",
            "sharding",
            "replication",
            # "consensus" alone matched UiPath's "drive consensus" — team
            # agreement, not Raft. Name the distributed thing instead.
            "distributed consensus",
            "Raft",
            "Paxos",
            "high availability",
            "horizontal scaling",
            "distributed computing",
        ],
        "level": 1,
        "effort": "months",
        "plan": "Already the top row of the gap assessment. Load-test the tracker, find "
        "where the JSON store breaks under concurrent writers, then fix it.",
    },
    {
        "key": "golang",
        "name": "Go",
        "area": "language",
        "order": 29,
        "aliases": ["Golang", _GO],
        "level": 0,
        "effort": "months",
        "plan": "The second production language worth having: it appears in the infra and "
        "AI-infra postings actually being applied to, and it pairs with the Kubernetes work.",
    },
    {
        "key": "java",
        "name": "Java",
        "area": "language",
        "order": 30,
        "aliases": ["Java"],
        "level": 1,
        "effort": "months",
        "plan": "Only worth the months if Amazon and the enterprise track become the "
        "primary target. Otherwise Go covers the same 'second language' box for less.",
    },
    {
        "key": "cpp",
        "name": "C++",
        "area": "language",
        "order": 31,
        "aliases": ["C++", "CPP"],
        "level": 1,
        "effort": "months",
        "plan": "Academic only. Relevant to Google and the systems track, not to the "
        "AI-infra postings that make up most of the pipeline.",
    },
    {
        "key": "rust",
        "name": "Rust",
        "area": "language",
        "order": 32,
        "aliases": ["Rust"],
        "level": 1,
        "effort": "months",
        "evidence": "Kestrel's serving layer, in progress.",
        "status": "learning",
        "plan": "Finish Kestrel's serving layer. Stays out of the resume's Languages row "
        "until it is written.",
    },
    # ------------------------------------------------------------------
    # Cloud. AWS is claimed on the resume already, which is the point of
    # tracking the three separately rather than as one "cloud" row.
    # ------------------------------------------------------------------
    {
        "key": "aws",
        "name": "AWS",
        "area": "cloud",
        "order": 40,
        "aliases": ["AWS", "Amazon Web Services", "EC2", "Bedrock", "SageMaker", "Lambda"],
        "level": 2,
        "effort": "weeks",
        "evidence": "Lambda, Bedrock, S3 and DynamoDB on the Jack In The Box engagement.",
        "plan": "EC2 and S3 are on the resume and have never been personally deployed. "
        "Stand up one instance and one bucket under your own account.",
    },
    {
        "key": "gcp",
        "name": "GCP",
        "area": "cloud",
        "order": 41,
        "aliases": ["GCP", "Google Cloud", "Vertex AI", "Stackdriver", "Cloud Run"],
        "level": 0,
        "effort": "weeks",
        "plan": "Only if the Kubernetes work lands on GKE. Otherwise one cloud done "
        "properly beats three listed.",
    },
    {
        "key": "azure",
        "name": "Azure",
        "area": "cloud",
        "order": 42,
        "aliases": ["Azure"],
        "level": 0,
        "effort": "weeks",
        "plan": "Lowest-yield of the three. Nothing in the pipeline requires it alone.",
    },
    # ------------------------------------------------------------------
    # Not learnable from a side project. Tracked anyway, because they are
    # screened on as hard as anything above and pretending otherwise makes
    # the board optimistic.
    # ------------------------------------------------------------------
    {
        "key": "scale-numbers",
        "name": "Scale numbers (QPS, p99)",
        "area": "practice",
        "order": 50,
        "aliases": ["QPS", "p99", "throughput", "latency", "requests per second"],
        "level": 0,
        "target_level": 2,
        "effort": "weeks",
        "plan": "Load-test the tracker and Kestrel. One honest measured number beats "
        "every adjective on the resume.",
    },
    {
        "key": "oncall",
        "name": "On-call and incident response",
        "area": "practice",
        "order": 51,
        "aliases": [
            "on-call",
            "oncall",
            "incident response",
            "site reliability",
            "SRE",
            "production support",
            "pager",
        ],
        "level": 0,
        "target_level": 2,
        "effort": "months",
        "plan": "Not obtainable from a side project. This is what the two-step path — a "
        "product company first — is actually for.",
    },
    {
        "key": "design-docs",
        "name": "Written design (specs, RFCs)",
        "area": "practice",
        "order": 52,
        "aliases": [
            "design document",
            "functional specification",
            "technical design",
            "RFC",
            "low level design",
            "high level design",
            "architecture and design",
        ],
        "level": 1,
        "target_level": 2,
        "effort": "days",
        "plan": "The study guide in data/ is most of one already. Write a real design doc "
        "for Kestrel's serving layer before building it.",
    },
    {
        "key": "mentoring",
        "name": "Mentoring and code review",
        "area": "practice",
        "order": 53,
        "aliases": ["mentor", "mentoring", "peer review", "code review"],
        "level": 1,
        "target_level": 2,
        "effort": "months",
        "evidence": "SME at PwC within six months; consulted by engineers with 10+ years.",
        "plan": "Real evidence exists but is not on the resume. Open-source review "
        "comments are the closest public proxy.",
    },
    # ------------------------------------------------------------------
    # Held. These are the denominator: without them `coverage` is a
    # percentage of nothing and the board says only that everything is bad.
    # ------------------------------------------------------------------
    {
        "key": "python",
        "name": "Python",
        "area": "language",
        "order": 60,
        "aliases": ["Python"],
        "level": 4,
        "effort": "months",
        "evidence": "FastAPI services at Mphasis, PwC data science work, the tracker, Kestrel.",
    },
    {
        "key": "sql",
        "name": "SQL",
        "area": "data",
        "order": 61,
        "aliases": ["SQL", "PostgreSQL", "Postgres", "relational database"],
        "level": 3,
        "effort": "weeks",
        "evidence": "Postgres schema design behind the lifecycle platform and the ITSM tool.",
    },
    {
        "key": "apis",
        "name": "REST APIs and services",
        "area": "backend",
        "order": 62,
        "aliases": ["REST", "REST API", "FastAPI", "API design", "microservice"],
        "level": 4,
        "effort": "weeks",
        "evidence": "NestJS and FastAPI services in production at Mphasis; the tracker's API.",
    },
    {
        "key": "docker",
        "name": "Docker",
        "area": "infra",
        "order": 63,
        "aliases": ["Docker", "containerised", "containerized", "containerisation"],
        "level": 3,
        "effort": "days",
        "evidence": "The FastAPI microservice and Kestrel are both containerised.",
    },
    {
        "key": "cicd",
        "name": "CI/CD",
        "area": "infra",
        "order": 64,
        "aliases": ["CI/CD", "GitHub Actions", "GitLab", "Jenkins", "continuous integration"],
        "level": 3,
        "effort": "days",
        "evidence": "GitHub Actions running lint and tests on the lifecycle platform and Kestrel.",
    },
    {
        "key": "rag",
        "name": "RAG, embeddings and vector search",
        "area": "ml",
        "order": 65,
        "aliases": [
            "RAG",
            "retrieval augmented",
            "vector database",
            "vector search",
            "embedding",
            "embeddings",
            "semantic search",
            "pgvector",
        ],
        "level": 3,
        "effort": "weeks",
        "evidence": "pgvector semantic search in the FastAPI microservice; Kestrel is a "
        "distributed vector retrieval engine with reproducible evaluation.",
    },
    {
        "key": "llm-apps",
        "name": "LLM application engineering",
        "area": "ml",
        "order": 66,
        "aliases": [
            "LLM",
            "large language model",
            "GenAI",
            "generative AI",
            "prompt engineering",
            "OpenAI",
            "Claude",
            "agentic",
            "AI agent",
            "MCP",
        ],
        "level": 4,
        "effort": "weeks",
        "evidence": "Conversational assistants at PwC; the tracker's Agent SDK assistant "
        "with ~60 in-process tools over MCP.",
    },
    {
        "key": "nlp",
        "name": "NLP",
        "area": "ml",
        "order": 67,
        "aliases": ["NLP", "natural language processing"],
        "level": 3,
        "effort": "weeks",
        "evidence": "Resume-to-JD matching engine at Reslink using embeddings and similarity ranking.",
    },
    {
        "key": "frontend",
        "name": "Frontend (React/TypeScript)",
        "area": "backend",
        "order": 68,
        "aliases": ["React", "TypeScript", "JavaScript", "Angular", "Next.js", "front-end", "frontend"],
        "level": 3,
        "effort": "weeks",
        "evidence": "React/TypeScript ITSM tool, Angular 18 + AG Grid lifecycle platform, "
        "the tracker's dashboard.",
    },
    {
        "key": "testing",
        "name": "Testing",
        "area": "practice",
        "order": 69,
        "aliases": [
            "testing",
            "unit test",
            "integration test",
            "TDD",
            "test coverage",
            "pytest",
            "automated test",
        ],
        "level": 3,
        "effort": "days",
        "evidence": "Hermetic self-test suite covering every domain of the tracker.",
    },
    # ------------------------------------------------------------------
    # Declined. Each appeared in exactly one JD; learning any of them
    # optimises for a posting that has already resolved. Demand keeps
    # updating underneath the decision, so a fourth mention will show up.
    # ------------------------------------------------------------------
    {
        "key": "fhe-web3",
        "name": "FHE, ZK and Web3",
        "area": "ml",
        "order": 80,
        "aliases": [
            "homomorphic",
            "FHE",
            "zero-knowledge",
            "zero knowledge",
            "Solidity",
            "blockchain",
            "Web3",
            "smart contract",
        ],
        "status": "declined",
        "effort": "months",
        "notes": "Mind Network only. Months of cryptography for one inbound posting.",
    },
    {
        "key": "embedded",
        "name": "Embedded and firmware",
        "area": "language",
        "order": 81,
        "aliases": ["embedded", "uboot", "coreboot", "device driver", "RTOS", "bare metal", "firmware"],
        "status": "declined",
        "effort": "months",
        "notes": "Nokia Optical only, and that application was already rejected.",
    },
    {
        "key": "voice-ai",
        "name": "Voice AI (ASR/TTS)",
        "area": "ml",
        "order": 82,
        "aliases": [
            "ASR",
            "TTS",
            "speech recognition",
            "speech synthesis",
            "telephony",
            "barge-in",
            # "voice pipeline" missed "voice pipelines" and "voice agents" — the
            # whole posting is written in the plural.
            _VOICE,
        ],
        "status": "declined",
        "effort": "months",
        "notes": "The Weekday voice-agent role only. A whole subfield for one posting.",
    },
    {
        "key": "dotnet",
        "name": ".NET / C# / RPA",
        "area": "language",
        "order": 83,
        "aliases": [".NET", "C#", "RPA", "robotic process automation"],
        "status": "declined",
        "effort": "months",
        "notes": "UiPath only, and it was not even in their stated requirements.",
    },
    {
        "key": "knowledge-graphs",
        "name": "Knowledge graphs and ontologies",
        "area": "data",
        "order": 84,
        "aliases": ["knowledge graph", "ontology", "ontologies", "SPARQL", "RDF"],
        "status": "declined",
        "effort": "weeks",
        "notes": "Mopid only.",
    },
    {
        "key": "computer-vision",
        "name": "Computer vision",
        "area": "ml",
        "order": 85,
        "aliases": ["computer vision", "OpenCV", "object detection", "image classification"],
        "status": "declined",
        "effort": "months",
        "notes": "Clicksoft only, and listed as good-to-have.",
    },
]
