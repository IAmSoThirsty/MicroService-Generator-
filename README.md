# Genesis Microservices Generator

Production-grade microservices infrastructure generator — **15 components, complete pipeline**.

> **📖 Canonical Architecture & Design Guide:** [`docs/GENESIS.md`](docs/GENESIS.md) — complete
> documentation of the Genesis system: architecture, compiler pipeline, all 15 components,
> criticality profiles, sacred-zone governance, CI/CD gates, and full API reference.

## Overview

The **Genesis Microservices Generator** replaces the prior template-based generator with a unified,
authoritative implementation covering the full infrastructure stack: Terraform, Kubernetes, CI/CD,
ArgoCD, Vault, Prometheus, HPA, PDB, RBAC, pre-commit hooks, Pact contract tests, and drift detection.

### Component Inventory

| # | Component | Description |
|---|-----------|-------------|
| 1 | `SystemPipeline` | Orchestrates all generation phases |
| 2 | `TerraformGenerator` | 32 files across 5 modules (namespace, deployment, RBAC, Vault, monitoring) |
| 3 | `KubernetesGenerator` | Namespace, Deployment, Service, ConfigMap, NetworkPolicy |
| 4 | `RBACGenerator` | ClusterRole + RoleBinding per service |
| 5 | `VaultPolicyGenerator` | Scoped secret paths per service and environment |
| 6 | `PrometheusAlertGenerator` | SLO burn-rate alerts calibrated to criticality |
| 7 | `HPAGenerator` | HPA with criticality-driven min/max replicas |
| 8 | `PDBGenerator` | PodDisruptionBudget per service |
| 9 | `ArgoCDGenerator` | ApplicationSet with self-heal + auto-prune |
| 10 | `CICDPipelineGenerator` | 5-gate GitHub Actions pipeline |
| 11 | `PreCommitGenerator` | Sacred-zone integrity hooks |
| 12 | `PactContractGenerator` | Consumer-driven contract test stubs |
| 13 | `DriftDetectionGenerator` | Terraform + live-state drift detection |
| 14 | `SacredZonePreserver` | Protects manually maintained sections |
| 15 | `SurgicalRegen` | Component-level selective regeneration |

### Terraform Modules (5)

- **namespace** — Kubernetes namespace with ResourceQuota + LimitRange
- **deployment** — Deployment + Service with probes and rolling updates
- **rbac** — ServiceAccount + ClusterRole + ClusterRoleBinding
- **vault** — Vault policy + Kubernetes auth role
- **monitoring** — ServiceMonitor + Prometheus SLO alert rules

### CI/CD Gates (5)

1. **Constitutional Validation** — Schema, sacred zones, Terraform fmt, Kubernetes dry-run
2. **Build & Test** — Language-aware matrix: lint, test (85%+ coverage), container build, SBOM, signing
3. **Pact Contract Tests** — Provider verification against Pact Broker
4. **Drift Detection** — `terraform plan -detailed-exitcode` + Kubernetes manifest diff
5. **ArgoCD Deploy** — Progressive env promotion: dev → staging → production

### Criticality Profiles

| Criticality | HPA min | HPA max | CPU target | SLO availability | SLO p99 latency | PDB minAvailable |
|-------------|---------|---------|------------|-----------------|-----------------|------------------|
| low | 1 | 3 | 80% | 99.0% | 500ms | 0 |
| medium | 2 | 6 | 70% | 99.5% | 300ms | 1 |
| high | 3 | 10 | 65% | 99.9% | 200ms | 1 |
| critical | 5 | 20 | 60% | 99.99% | 100ms | 2 |

## Quick Start

### CLI

```bash
# Generate with defaults (medium criticality, Python, PostgreSQL)
python genesis.py generate --name my-service

# Generate with full options
python genesis.py generate \
  --name payment-service \
  --criticality critical \
  --language python \
  --database postgresql \
  --port 8080

# Generate from a spec file
python genesis.py generate --config service-spec.yaml

# Output as ZIP
python genesis.py generate --name my-service --zip

# Surgically regenerate specific components
python genesis.py regen --config service-spec.yaml --components terraform,cicd,argocd

# Check for infrastructure drift
python genesis.py drift-check --service my-service --all-envs

# Validate sacred zone integrity (use in CI)
python genesis.py validate-sacred --base-ref origin/main

# Show generator info
python genesis.py info
```

### Python API

```python
from genesis import GenesisGenerator, ServiceSpec, Criticality, Language

gen = GenesisGenerator()

spec = ServiceSpec(
    name="payment-service",
    criticality=Criticality.CRITICAL,
    language=Language.PYTHON,
    port=8080,
    github_owner="IAmSoThirsty",
)

# Generate all files to disk
written = gen.write_to_disk(spec, output_dir="./output")

# Generate as ZIP bytes (e.g. for API response)
zip_bytes = gen.generate_zip(spec)
```

### REST API

The FastAPI backend exposes these endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/generate` | Legacy generate (MicroserviceConfig payload) |
| `POST` | `/api/genesis/generate` | Genesis generate (ServiceSpec payload) |
| `GET` | `/api/generator/info` | Generator capabilities and metadata |

```bash
# Genesis generate
curl -X POST http://localhost:8001/api/genesis/generate \
  -H "Content-Type: application/json" \
  -d '{"name": "my-service", "criticality": "high", "language": "python"}' \
  -o my-service-genesis.zip
```

## Repository Structure

```
MicroService-Generator-/
├── run.sh                        # ← One-command build & run (logically gated)
├── genesis.py                    # ← Canonical Genesis generator (15 components)
├── service-spec.yaml             # Example service specification
├── Dockerfile                    # Multi-stage build (frontend + backend)
├── docker-compose.yml            # Full-stack compose (app + MongoDB)
├── .dockerignore
├── docs/
│   └── GENESIS.md                # ← Canonical architecture & design guide
├── backend/
│   ├── server.py                 # FastAPI server (uses genesis.py, serves UI)
│   ├── requirements.txt
│   └── generator/
│       ├── engine.py             # Delegates to genesis.py
│       ├── models.py             # Pydantic models
│       └── templates/            # Legacy Jinja2 templates (fallback)
├── frontend/                     # React UI
├── tests/
│   ├── test_genesis.py           # Genesis generator tests
│   └── pact/                     # Pact contract test stubs
├── .github/
│   └── workflows/
│       ├── genesis-ci.yml        # 5-gate CI pipeline
│       └── docker-release.yml    # Docker build & GHCR release
├── .pre-commit-config.yaml       # Pre-commit hooks
└── README.md
```

## Sacred Zones

Files managed by Genesis may contain protected sections:

```python
# <<<SACRED_ZONE_BEGIN>>> custom-logic
# Your manually maintained code here
# <<<SACRED_ZONE_END>>>
```

Sacred zones are preserved during `regen` operations and protected by pre-commit hooks.

## Documentation

| Document | Description |
|----------|-------------|
| **[`docs/GENESIS.md`](docs/GENESIS.md)** | **Canonical architecture & design guide** — complete system design, compiler pipeline, all 15 components, criticality profiles, sacred-zone governance, CI/CD gate architecture, and full API reference |
| [`service-spec.yaml`](service-spec.yaml) | Example `ServiceSpec` in YAML format |

## One-Command Deployment

```bash
./run.sh
```

That's it. The script is **logically gated** — every prerequisite, path, port, build step, and
health check must pass before the next one starts. If anything is wrong, it stops immediately with
a clear message telling you exactly what failed and how to fix it.

```
Gate 0 — Preflight      Bash 4+, Docker daemon, docker compose plugin
Gate 1 — Repo integrity All required source files present
Gate 2 — Port check     Ports 8001 and 27017 are free
Gate 3 — Build          docker compose build (multi-stage: frontend + backend)
Gate 4 — Launch & wait  Containers started; health-check loop with timeout
Gate 5 — Smoke tests    /api/ and /api/generator/info return HTTP 200
```

Once all five gates pass the terminal prints:

```
  ✓  Genesis Microservices Generator is UP

     App  →  http://localhost:8001
     API  →  http://localhost:8001/api/
     Docs →  http://localhost:8001/api/docs
```

### Sub-commands

| Command | Action |
|---------|--------|
| `./run.sh` | build + start (default) |
| `./run.sh --stop` | stop all services and remove containers |
| `./run.sh --clean` | stop + remove volumes + prune build cache |
| `./run.sh --logs` | tail live logs from the running stack |
| `./run.sh --status` | print container health status |
| `./run.sh --help` | usage message |

---

## Docker Deployment

The easiest way to run Genesis as a fully self-contained app (backend + React UI + all
dependencies) is via Docker.

### Quick start — docker compose (recommended)

```bash
# Clone and start the full stack (app + MongoDB)
git clone https://github.com/IAmSoThirsty/MicroService-Generator-.git
cd MicroService-Generator-
docker compose up --build
```

Open **http://localhost:8001** — the React UI is served directly by the FastAPI backend.

### Build the image yourself

```bash
docker build -t microservice-generator:latest .
docker run --rm -p 8001:8001 \
  -e MONGO_URL=mongodb://your-mongo:27017 \
  -e DB_NAME=genesis \
  microservice-generator:latest
```

### Pull a pre-built release from GitHub Container Registry

```bash
# Replace <version> with e.g. "v1.0.0" or use "latest"
docker pull ghcr.io/iamsothirsty/microservice-generator:<version>
docker run --rm -p 8001:8001 \
  -e MONGO_URL=mongodb://your-mongo:27017 \
  ghcr.io/iamsothirsty/microservice-generator:<version>
```

### Download a standalone tarball (from GitHub Releases)

Each tagged release publishes a self-contained Docker image tarball for linux/amd64:

```bash
# Download the tarball from the GitHub Releases page, then:
gunzip -c microservice-generator-<version>-linux-amd64.tar.gz | docker load
docker run --rm -p 8001:8001 \
  -e MONGO_URL=mongodb://localhost:27017 \
  ghcr.io/iamsothirsty/microservice-generator:<version>
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `DB_NAME` | `genesis` | MongoDB database name |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |

## Development

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run tests
pytest tests/ -v

# Start API server
cd backend && uvicorn server:app --reload --port 8001

# Run genesis CLI
python genesis.py info
```

