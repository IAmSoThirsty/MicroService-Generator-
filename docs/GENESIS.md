# Genesis Microservices Generator — Canonical Architecture & Design Guide

> **This is the authoritative reference for Genesis design, compiler pipeline, and governance
> philosophy.** All architectural decisions, component contracts, and operational patterns are
> documented here. For quick-start usage see the [project README](../README.md).

---

## Table of Contents

1. [Overview & Design Philosophy](#1-overview--design-philosophy)
2. [Architecture](#2-architecture)
   - 2.1 [System Pipeline](#21-system-pipeline)
   - 2.2 [Component Inventory](#22-component-inventory)
   - 2.3 [Data Models](#23-data-models)
   - 2.4 [Criticality Profiles](#24-criticality-profiles)
3. [Compiler Pipeline](#3-compiler-pipeline)
   - 3.1 [Generation Phases](#31-generation-phases)
   - 3.2 [Component Contracts](#32-component-contracts)
4. [Infrastructure Components](#4-infrastructure-components)
   - 4.1 [TerraformGenerator](#41-terraformgenerator)
   - 4.2 [KubernetesGenerator](#42-kubernetesgenerator)
   - 4.3 [RBACGenerator](#43-rbacgenerator)
   - 4.4 [VaultPolicyGenerator](#44-vaultpolicygenerator)
   - 4.5 [PrometheusAlertGenerator](#45-prometheusalertgenerator)
   - 4.6 [HPAGenerator](#46-hpagenerator)
   - 4.7 [PDBGenerator](#47-pdbgenerator)
5. [Delivery & Operations Components](#5-delivery--operations-components)
   - 5.1 [ArgoCDGenerator](#51-argocdgenerator)
   - 5.2 [CICDPipelineGenerator](#52-cicdpipelinegenerator)
   - 5.3 [PreCommitGenerator](#53-precommitgenerator)
   - 5.4 [PactContractGenerator](#54-pactcontractgenerator)
   - 5.5 [DriftDetectionGenerator](#55-driftdetectiongenerator)
6. [Governance: Sacred Zones](#6-governance-sacred-zones)
   - 6.1 [SacredZonePreserver](#61-sacredzonepreserver)
   - 6.2 [SurgicalRegen](#62-surgicalregen)
7. [CI/CD Pipeline — The 5 Gates](#7-cicd-pipeline--the-5-gates)
8. [Configuration Reference](#8-configuration-reference)
   - 8.1 [ServiceSpec Fields](#81-servicespec-fields)
   - 8.2 [service-spec.yaml Format](#82-service-specyaml-format)
9. [CLI Reference](#9-cli-reference)
10. [Python API Reference](#10-python-api-reference)
11. [REST API Reference](#11-rest-api-reference)
12. [Output Structure](#12-output-structure)
13. [Operational Runbook](#13-operational-runbook)

---

## 1. Overview & Design Philosophy

Genesis is a **production-grade infrastructure compiler** — not a templating engine. It treats
every microservice as a specification-driven artefact that must satisfy invariants across:

- **Security** (RBAC, Vault, NetworkPolicy, image signing, SBOM)
- **Reliability** (HPA, PDB, SLO alerting, readiness/liveness/startup probes)
- **Observability** (Prometheus SLO burn-rate alerts, ServiceMonitor, structured logging)
- **Governance** (Sacred zones, pre-commit guards, schema validation, drift detection)
- **Delivery** (5-gate CI/CD, ArgoCD progressive promotion, contract testing)

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Specification-first** | A single `ServiceSpec` is the sole source of truth; all artefacts are deterministic derivations |
| **Criticality-driven** | Every tunable (HPA replicas, SLO targets, PDB budgets, burn-rate thresholds) is a function of the service's criticality level |
| **Sacred-zone governance** | Manually maintained sections are protected by cryptographic extraction/re-injection during regeneration |
| **Full-stack coverage** | One invocation produces Terraform, Kubernetes, RBAC, Vault, Prometheus, HPA, PDB, ArgoCD, CI/CD, pre-commit, Pact stubs, and drift-detection in a single atomic pass |
| **Surgical regeneration** | Any single component can be regenerated in isolation without disturbing adjacent artefacts or sacred zones |
| **Zero-drift enforcement** | Terraform plan and Kubernetes manifest diff are mandatory CI gates, blocking promotion on detected drift |

---

## 2. Architecture

### 2.1 System Pipeline

Genesis executes a deterministic, ordered pipeline:

```
ServiceSpec
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        GenesisGenerator                             │
│  (Component 1 — SystemPipeline / Orchestrator)                      │
│                                                                     │
│  Phase 1 — Core Kubernetes artefacts                                │
│    ├─ KubernetesGenerator   (Namespace, Deployment, Service, …)     │
│    ├─ RBACGenerator         (ClusterRole, RoleBinding, SA)          │
│    ├─ HPAGenerator          (HPA, criticality-scaled)               │
│    ├─ PDBGenerator          (PodDisruptionBudget)                   │
│    ├─ VaultPolicyGenerator  (HCL policy, K8s auth role)             │
│    └─ PrometheusAlertGenerator (SLO burn-rate rules)                │
│                                                                     │
│  Phase 2 — Optional but recommended artefacts                       │
│    ├─ TerraformGenerator    (32 files, 5 modules)   [enable_terraform]│
│    ├─ CICDPipelineGenerator (6 workflow files)      [enable_cicd]   │
│    ├─ ArgoCDGenerator       (ApplicationSet)        [enable_argocd] │
│    ├─ PreCommitGenerator    (.pre-commit-config.yaml) [enable_pre_commit]│
│    ├─ PactContractGenerator (consumer + provider)   [enable_pact]   │
│    └─ DriftDetectionGenerator (CronJob + script)   [enable_drift_detection]│
│                                                                     │
│  Phase 3 — Manifest                                                 │
│    └─ service-spec.yaml     (serialised ServiceSpec)                │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
Dict[str, str]   →   ZIP archive  /  write_to_disk()
```

### 2.2 Component Inventory

| # | Component | Phase | Responsibility |
|---|-----------|-------|----------------|
| 1 | `SystemPipeline` (`GenesisGenerator`) | Orchestrator | Coordinates all generation phases; owns the canonical generate/regen/validate lifecycle |
| 2 | `TerraformGenerator` | Phase 2 | 32 files across 5 Terraform modules (namespace, deployment, rbac, vault, monitoring) |
| 3 | `KubernetesGenerator` | Phase 1 | Namespace, Deployment, Service, ConfigMap, ServiceAccount, NetworkPolicy |
| 4 | `RBACGenerator` | Phase 1 | ClusterRole + ClusterRoleBinding per service; principle of least privilege |
| 5 | `VaultPolicyGenerator` | Phase 1 | Scoped HCL secret paths (`secret/{service}/{env}/*`) with explicit deny; Kubernetes auth role |
| 6 | `PrometheusAlertGenerator` | Phase 1 | Fast/slow burn-rate SLO alerts + latency p99 rules calibrated to criticality |
| 7 | `HPAGenerator` | Phase 1 | HorizontalPodAutoscaler with criticality-driven min/max replicas and CPU scale-stabilisation |
| 8 | `PDBGenerator` | Phase 1 | PodDisruptionBudget with criticality-driven `minAvailable` |
| 9 | `ArgoCDGenerator` | Phase 2 | ApplicationSet with self-heal, auto-prune, and per-environment progressive promotion |
| 10 | `CICDPipelineGenerator` | Phase 2 | 6 GitHub Actions workflow files implementing the 5-gate pipeline |
| 11 | `PreCommitGenerator` | Phase 2 | Sacred-zone pre-commit hook + quality hooks (Black, isort, flake8, gitleaks, terraform fmt) |
| 12 | `PactContractGenerator` | Phase 2 | Consumer-driven contract test stubs (provider + consumer); Pact Broker integration |
| 13 | `DriftDetectionGenerator` | Phase 2 | `terraform plan -detailed-exitcode` CronJob + Kubernetes manifest diff script |
| 14 | `SacredZonePreserver` | Cross-cutting | Extracts named sacred blocks before regeneration; re-injects them after |
| 15 | `SurgicalRegen` | Cross-cutting | Component-level selective regeneration preserving all sacred zones |

### 2.3 Data Models

#### `ServiceSpec`

The canonical input to every generator. All fields have safe defaults.

```python
@dataclass
class ServiceSpec:
    # Identity
    name: str                           # Service name (slug-ified internally)
    criticality: Criticality            # low | medium | high | critical
    language: Language                  # python | go | nodejs | rust
    database: DatabaseType              # postgresql | mongodb | redis | none
    port: int                           # Application port (default: 8000)
    metrics_port: int                   # Prometheus metrics port (default: 9090)
    namespace: str                      # K8s namespace (defaults to <name>)
    version: str                        # Semantic version (default: "1.0.0")
    description: str                    # Human description
    author: str                         # Team / owner (default: "platform-team")

    # GitHub integration
    github_owner: str                   # GitHub username / org
    github_repo: str                    # GitHub repo name

    # Vault
    vault_mount: str                    # Vault KV mount path (default: "secret")

    # ArgoCD
    argocd_server: str                  # ArgoCD API server hostname

    # Registry
    image_registry: str                 # OCI registry (default: "ghcr.io")

    # Feature flags
    enable_terraform: bool              # Include Terraform (default: True)
    enable_cicd: bool                   # Include CI/CD workflows (default: True)
    enable_argocd: bool                 # Include ArgoCD ApplicationSet (default: True)
    enable_pact: bool                   # Include Pact stubs (default: True)
    enable_drift_detection: bool        # Include drift-detection CronJob (default: True)
    enable_pre_commit: bool             # Include pre-commit config (default: True)

    # Environments
    environments: List[str]             # Promotion environments (default: [dev, staging, production])
```

#### Enumerations

```python
class Criticality(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

class Language(str, Enum):
    PYTHON = "python"
    GO     = "go"
    NODEJS = "nodejs"
    RUST   = "rust"

class DatabaseType(str, Enum):
    POSTGRESQL = "postgresql"
    MONGODB    = "mongodb"
    REDIS      = "redis"
    NONE       = "none"
```

### 2.4 Criticality Profiles

Criticality is the single dial that tunes all reliability, scalability, and observability
knobs simultaneously.

#### HPA Profiles

| Criticality | `minReplicas` | `maxReplicas` | CPU Target | Scale-down stabilisation |
|-------------|:---:|:---:|:---:|:---|
| `low` | 1 | 3 | 80% | default |
| `medium` | 2 | 6 | 70% | default |
| `high` | 3 | 10 | 65% | 300 s window |
| `critical` | 5 | 20 | 60% | 600 s window |

#### SLO Profiles

| Criticality | Availability target | p99 latency | 1-hour burn-rate | 6-hour burn-rate |
|-------------|:---:|:---:|:---:|:---:|
| `low` | 99.0% | 500 ms | 14.4× | 6.0× |
| `medium` | 99.5% | 300 ms | 14.4× | 6.0× |
| `high` | 99.9% | 200 ms | 14.4× | 6.0× |
| `critical` | 99.99% | 100 ms | 14.4× | 6.0× |

#### PDB Profiles

| Criticality | `minAvailable` |
|-------------|:---:|
| `low` | 0 |
| `medium` | 1 |
| `high` | 1 |
| `critical` | 2 |

---

## 3. Compiler Pipeline

### 3.1 Generation Phases

Genesis is structured as a two-pass compiler:

**Pass 1 — Emission**

Each generator's `generate(spec: ServiceSpec) -> Dict[str, str]` method is a pure function
mapping a `ServiceSpec` to a dict of `{relative_path: file_content}`. Generators are stateless
and deterministic; calling them twice with the same spec produces identical output.

**Pass 2 — Sacred-zone reconciliation (regen only)**

During surgical regeneration (`genesis regen`), the `SacredZonePreserver` runs between passes:

```
Existing file on disk
    │
    ├─ extract()  ──►  Dict[zone_name, zone_content]
    │
    │   [generator emits new file]
    │
    └─ inject()   ◄──  Dict[zone_name, zone_content]
         │
         ▼
    New file with sacred zones preserved
```

### 3.2 Component Contracts

Every generator implements the same interface:

```python
class <Name>Generator:
    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        """
        Returns a mapping of relative output paths to file contents.
        Must be:
          - Pure (no side effects)
          - Deterministic (same spec → same output)
          - Complete (all paths fully qualified relative to output root)
        """
```

The `GenesisGenerator` orchestrator calls each generator in the prescribed order and merges
all outputs into a single flat `Dict[str, str]`. Duplicate keys are last-writer-wins (later
phases override earlier ones), though in practice no two generators emit the same path.

---

## 4. Infrastructure Components

### 4.1 TerraformGenerator

**Files emitted: 32** across 5 modules + shared infrastructure.

```
terraform/
├── shared/
│   ├── providers.tf          # Provider pinning (kubernetes, vault, helm)
│   ├── data.tf               # Remote state data sources
│   ├── locals.tf             # Common locals
│   └── variables.tf          # Shared variable declarations
├── scripts/
│   ├── plan.sh               # CI-safe plan script (detailed-exitcode)
│   ├── apply.sh              # Auto-approved apply with state locking
│   └── destroy.sh            # Guarded destroy with confirmation
└── services/<slug>/
    ├── main.tf               # Root module wiring all 5 child modules
    ├── variables.tf          # Per-service variable declarations
    ├── outputs.tf            # Service-level outputs
    ├── versions.tf           # Terraform + provider version constraints
    ├── terraform.tfvars      # Default variable values
    ├── backend.tf            # Remote state backend configuration
    └── modules/
        ├── namespace/        # Namespace + ResourceQuota + LimitRange
        │   ├── main.tf
        │   ├── variables.tf
        │   └── outputs.tf
        ├── deployment/       # Deployment + Service with probes + rolling updates
        │   ├── main.tf
        │   ├── variables.tf
        │   └── outputs.tf
        ├── rbac/             # ServiceAccount + ClusterRole + ClusterRoleBinding
        │   ├── main.tf
        │   ├── variables.tf
        │   └── outputs.tf
        ├── vault/            # Vault policy + Kubernetes auth role
        │   ├── main.tf
        │   ├── variables.tf
        │   └── outputs.tf
        └── monitoring/       # ServiceMonitor + Prometheus SLO alert rules
            ├── main.tf
            ├── variables.tf
            └── outputs.tf
```

**Root module dependency ordering:** `namespace → rbac → vault → deployment → monitoring`.
Each module explicitly depends on its predecessor to prevent race conditions during `apply`.

### 4.2 KubernetesGenerator

**Files emitted: 6** per service.

```
kubernetes/<slug>/
├── namespace.yaml        # Namespace with criticality + managed-by labels
├── deployment.yaml       # Deployment with RollingUpdate (maxUnavailable=0, maxSurge=1)
├── service.yaml          # ClusterIP Service
├── configmap.yaml        # Environment configuration ConfigMap
├── serviceaccount.yaml   # ServiceAccount with genesis.io/managed annotation
└── network-policy.yaml   # NetworkPolicy: ingress from ingress-nginx only; egress to DNS + HTTPS
```

**Deployment features:**
- Image pulled from `{image_registry}/{github_owner}/{slug}:latest`
- Three-probe readiness contract: `liveness (/health/live)`, `readiness (/health/ready)`, `startup (/health/startup)`
- Prometheus scrape annotations on pod template
- `terminationGracePeriodSeconds: 60` for clean shutdown

**NetworkPolicy default:**
- Ingress: only from `ingress-nginx` namespace, on `spec.port`
- Egress: only to TCP 443 (HTTPS) and UDP/TCP 53 (DNS)

### 4.3 RBACGenerator

**Files emitted: 2** per service.

```
kubernetes/<slug>/
├── clusterrole.yaml      # ClusterRole with minimal permissions
└── clusterrolebinding.yaml
```

Role binds to the ServiceAccount emitted by `KubernetesGenerator`. Permissions follow
principle of least privilege: read-only access to the service's own namespace resources.

### 4.4 VaultPolicyGenerator

**Files emitted: 2** per service.

```
vault/<slug>/
├── policy.hcl            # HCL policy: path "secret/<slug>/<env>/*" { capabilities = [...] }
└── auth-role.yaml        # Kubernetes auth role binding SA to Vault policy
```

**Path structure:**
```hcl
# Read/list own secrets
path "secret/data/<slug>/+/*" { capabilities = ["read", "list"] }

# Explicit deny for other services
path "secret/data/+/+/*" { capabilities = ["deny"] }
```

Environments are looped: policy is per-environment (`dev`, `staging`, `production`).

### 4.5 PrometheusAlertGenerator

**Files emitted: 1** per service.

```
kubernetes/<slug>/
└── prometheus-alerts.yaml   # PrometheusRule with SLO burn-rate + latency alerts
```

**Alert architecture:**

Fast/slow burn-rate multi-window alerting (Google SRE Workbook pattern):

| Alert | Window | Burn rate | Severity | Fires when |
|-------|--------|-----------|----------|-----------|
| `<slug>FastBurnRate` | 1 h | `> burn_rate_1h × (1 - slo_target)` | critical | ~2% budget consumed in 1 hour |
| `<slug>SlowBurnRate` | 6 h | `> burn_rate_6h × (1 - slo_target)` | warning | budget being steadily eroded |
| `<slug>LatencyP99High` | 5 m | p99 > threshold ms | warning | latency SLO at risk |

All thresholds (`burn_rate_1h`, `burn_rate_6h`, `latency_target_ms`) are derived from the
`SLO_PROFILES` mapping keyed by `Criticality`.

### 4.6 HPAGenerator

**Files emitted: 1** per service.

```
kubernetes/<slug>/
└── hpa.yaml    # HorizontalPodAutoscaler
```

**Scaling algorithm:**
- CPU-based autoscaling via `targetCPUUtilizationPercentage` (from `HPA_PROFILES`)
- `minReplicas` / `maxReplicas` from `HPA_PROFILES` keyed by criticality
- `high` and `critical` services include `scaleDown.stabilizationWindowSeconds` to prevent
  flapping under bursty load

### 4.7 PDBGenerator

**Files emitted: 1** per service.

```
kubernetes/<slug>/
└── pdb.yaml    # PodDisruptionBudget
```

`minAvailable` is `PDB_PROFILES[criticality]` (0, 1, or 2). For `low` criticality services
(development / background workers) PDB is still emitted but allows zero minimum to avoid
blocking cluster maintenance.

---

## 5. Delivery & Operations Components

### 5.1 ArgoCDGenerator

**Files emitted: 2** per service.

```
argocd/
├── appset-<slug>.yaml     # ApplicationSet with multi-environment matrix
└── project-<slug>.yaml    # AppProject with destination namespace restriction
```

**ApplicationSet strategy:**
- Matrix generator: `[environments] × [clusters]`
- `syncPolicy.automated.selfHeal: true` — ArgoCD reconciles drift on every sync
- `syncPolicy.automated.prune: true` — removes resources deleted from Git
- Progressive promotion: `dev` → `staging` → `production`; each step requires the prior
  sync to succeed (enforced by the CI/CD Gate 5 job sequencing)

### 5.2 CICDPipelineGenerator

**Files emitted: 6** GitHub Actions workflow files.

```
.github/workflows/
├── genesis-pipeline.yml      # Main 5-gate pipeline (push to main / release/**)
├── genesis-pr-check.yml      # Fast PR validation (constitutional + unit tests)
├── genesis-drift-detect.yml  # Scheduled drift detection CronJob
├── genesis-release.yml       # Release workflow (tag → image + helm chart)
├── genesis-rollback.yml      # Manual rollback trigger
└── genesis-security-scan.yml # Periodic security scan (Trivy, Grype, Semgrep)
```

See [Section 7](#7-cicd-pipeline--the-5-gates) for full gate documentation.

### 5.3 PreCommitGenerator

**Files emitted: 2**.

```
.pre-commit-config.yaml              # Pre-commit hook configuration
scripts/pre-commit-sacred-check.py   # Sacred zone integrity hook script
```

**Hook inventory:**

| Hook | Tool | Purpose |
|------|------|---------|
| `trailing-whitespace` | pre-commit-hooks | Normalise whitespace |
| `end-of-file-fixer` | pre-commit-hooks | Ensure newline at EOF |
| `check-yaml` / `check-json` / `check-toml` | pre-commit-hooks | Syntax validation |
| `check-merge-conflict` | pre-commit-hooks | Prevent accidental merge marker commits |
| `detect-private-key` | pre-commit-hooks | Block accidental credential commits |
| `no-commit-to-branch` | pre-commit-hooks | Prevent direct commits to `main` / `release` |
| `black` | PSF Black | Python formatting (line length 120) |
| `isort` | isort | Import ordering (Black-compatible) |
| `flake8` | Flake8 | PEP 8 lint (line length 120) |
| `gitleaks` | Gitleaks v8 | Secret scanning |
| `terraform_fmt` | antonbabenko | Terraform formatting |
| `terraform_validate` | antonbabenko | Terraform schema validation |
| `terraform_docs` | antonbabenko | Auto-update module README |
| `yamllint` | yamllint | YAML style enforcement |
| `genesis-sacred-zone-check` | local | Sacred zone integrity (blocks modifications) |

### 5.4 PactContractGenerator

**Files emitted: 2** per service.

```
tests/pact/
├── test_provider_<slug>.py    # Provider-side contract verification
└── test_consumer_<slug>.py    # Consumer-side contract test stub
```

Stubs are pre-wired to connect to a Pact Broker. Provider tests use `pytest-pact` to verify
published consumer contracts; consumer tests generate pact files to be published.

### 5.5 DriftDetectionGenerator

**Files emitted: 2** per service.

```
scripts/
└── drift-check-<slug>.sh        # Terraform plan + K8s manifest diff script

kubernetes/<slug>/
└── drift-detection-cronjob.yaml # Kubernetes CronJob running drift check hourly
```

**Drift detection algorithm:**

1. `terraform plan -detailed-exitcode` — exit code `2` indicates plan with changes (drift)
2. `kubectl diff -f kubernetes/<slug>/` — exits non-zero if live state diverges from manifests
3. On drift: emits Prometheus metric `genesis_drift_detected{service="<slug>"}` and optionally
   pages via AlertManager

---

## 6. Governance: Sacred Zones

Sacred zones are the **governance contract** between Genesis (the generator) and the service
team (the operator). They define regions of generated files that Genesis will never overwrite.

### 6.1 SacredZonePreserver

**Syntax:**

```python
# <<<SACRED_ZONE_BEGIN>>> <zone-name>
# ... manually maintained content ...
# <<<SACRED_ZONE_END>>>
```

`<zone-name>` is an arbitrary identifier; each file may contain multiple named zones.
Zone names must be unique within a single file.

**Lifecycle:**

```
regen invoked
    │
    ├─ SacredZonePreserver.extract(existing_file_content)
    │      → Dict[zone_name, zone_content]
    │
    ├─ Generator.generate(spec)
    │      → new_file_content (sacred zones contain empty/default placeholders)
    │
    └─ SacredZonePreserver.inject(new_file_content, extracted_zones)
           → final_file_content (sacred zones restored verbatim)
```

**Pre-commit protection:**

The `genesis-sacred-zone-check` hook runs on every `git commit`. It:
1. Identifies genesis-managed files (marked with `# genesis-managed: true` header comment)
2. Compares staged sacred zone content against HEAD
3. Aborts the commit if any sacred zone has been manually modified outside of `genesis regen`

**Validation in CI:**

Gate 1 (Constitutional Validation) runs:
```bash
python genesis.py validate-sacred --base-ref origin/main
```

This checks that no sacred zone has been altered in the current diff. The check is
non-bypassable for PRs targeting `main` or `release/**`.

### 6.2 SurgicalRegen

`SurgicalRegen` provides component-level selective regeneration:

```python
class SurgicalRegen:
    def regen(
        self,
        spec: ServiceSpec,
        components: List[str],   # e.g. ["terraform", "cicd", "argocd"]
        output_dir: str = ".",
    ) -> Dict[str, str]:
```

**Available component keys:**

| Key | Generator |
|-----|-----------|
| `terraform` | `TerraformGenerator` |
| `kubernetes` | `KubernetesGenerator` |
| `rbac` | `RBACGenerator` |
| `vault` | `VaultPolicyGenerator` |
| `prometheus` | `PrometheusAlertGenerator` |
| `hpa` | `HPAGenerator` |
| `pdb` | `PDBGenerator` |
| `argocd` | `ArgoCDGenerator` |
| `cicd` | `CICDPipelineGenerator` |
| `pre-commit` | `PreCommitGenerator` |
| `pact` | `PactContractGenerator` |
| `drift` | `DriftDetectionGenerator` |

Sacred zones are automatically preserved for any component that touches an existing file.

---

## 7. CI/CD Pipeline — The 5 Gates

The Genesis pipeline is a **sequential, blocking gate architecture**. No gate may start
until all prior gates succeed. Failure in any gate terminates the pipeline and prevents
deployment.

### Gate 1 — Constitutional Validation

**Trigger:** every push to `main` / `release/**`; every PR

**Jobs:**
1. **Sacred zone integrity** — `python genesis.py validate-sacred --base-ref origin/main`
2. **Service spec schema validation** — validates `service-spec.yaml` against the
   `ServiceSpec` schema
3. **Terraform format** — `terraform fmt -check -recursive`
4. **Kubernetes dry-run** — `kubectl apply --dry-run=server -f kubernetes/<slug>/`

**Failure policy:** immediate pipeline abort; no subsequent gates execute.

### Gate 2 — Build & Test

**Trigger:** success of Gate 1

**Matrix:** language-aware matrix over `[python, go, nodejs, rust]` (only active for
configured `spec.language`)

**Jobs:**
1. **Lint** — language-specific linter (flake8, golangci-lint, eslint, clippy)
2. **Unit tests** — `pytest / go test / jest / cargo test` — minimum **85% coverage**
3. **Container build** — `docker build` with build args
4. **SBOM generation** — `syft` produces a CycloneDX SBOM artefact
5. **Image signing** — `cosign sign` with keyless OIDC signing (Sigstore)

**Failure policy:** pipeline abort; image not pushed to registry.

### Gate 3 — Pact Contract Tests

**Trigger:** success of Gate 2

**Jobs:**
1. **Provider verification** — fetches consumer pacts from Pact Broker; verifies provider
   against each pact
2. **Consumer contract publication** — runs consumer tests; publishes generated pact files
   to Pact Broker with commit SHA tag

**Failure policy:** pipeline abort; prevents integration-breaking API changes from propagating.

### Gate 4 — Drift Detection

**Trigger:** success of Gate 3

**Jobs:**
1. **Terraform plan** — `terraform plan -detailed-exitcode` in each environment; exit code `2`
   is a drift failure
2. **Kubernetes manifest diff** — `kubectl diff -f kubernetes/<slug>/`; non-zero exit is a
   drift failure

**Failure policy:** pipeline abort; promotes only when infrastructure state matches
the declared specification.

### Gate 5 — ArgoCD Deploy

**Trigger:** success of Gate 4

**Jobs (sequential per environment):**
1. `dev` — `argocd app sync <slug>-dev --timeout 300`
2. `staging` — `argocd app sync <slug>-staging --timeout 300` (requires dev healthy ≥ 5 min)
3. `production` — `argocd app sync <slug>-production --timeout 600` (requires staging healthy ≥ 15 min)

**Health check:** each promotion step waits for `argocd app wait --health` before proceeding
to the next environment.

**Rollback:** the `genesis-rollback.yml` workflow reverts the ArgoCD application to the
previous revision and re-runs health checks.

---

## 8. Configuration Reference

### 8.1 ServiceSpec Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Service name; slug-ified (`my-service` → `my-service`) |
| `criticality` | `Criticality` | `medium` | Reliability tier; drives HPA, SLO, PDB |
| `language` | `Language` | `python` | Primary implementation language |
| `database` | `DatabaseType` | `postgresql` | Backing store type |
| `port` | `int` | `8000` | Container application port |
| `metrics_port` | `int` | `9090` | Prometheus metrics endpoint port |
| `namespace` | `str` | `<name>` | Kubernetes namespace (defaults to service name) |
| `version` | `str` | `1.0.0` | Semantic version |
| `description` | `str` | `""` | Human-readable description |
| `author` | `str` | `platform-team` | Team / owner identifier |
| `github_owner` | `str` | `IAmSoThirsty` | GitHub username or organisation |
| `github_repo` | `str` | `MicroService-Generator-` | GitHub repository name |
| `vault_mount` | `str` | `secret` | Vault KV engine mount path |
| `argocd_server` | `str` | `argocd.example.com` | ArgoCD API server FQDN |
| `image_registry` | `str` | `ghcr.io` | OCI image registry hostname |
| `enable_terraform` | `bool` | `True` | Emit Terraform modules |
| `enable_cicd` | `bool` | `True` | Emit GitHub Actions workflows |
| `enable_argocd` | `bool` | `True` | Emit ArgoCD ApplicationSet |
| `enable_pact` | `bool` | `True` | Emit Pact contract test stubs |
| `enable_drift_detection` | `bool` | `True` | Emit drift-detection CronJob and script |
| `enable_pre_commit` | `bool` | `True` | Emit pre-commit configuration |
| `environments` | `List[str]` | `[dev, staging, production]` | Promotion environment list |

### 8.2 service-spec.yaml Format

```yaml
name: payment-service
criticality: critical
language: python
database: postgresql
port: 8080
metrics_port: 9090
namespace: payment-service
version: 1.2.0
description: "Handles all payment processing and billing"
author: payments-team
github_owner: IAmSoThirsty
github_repo: MicroService-Generator-
vault_mount: secret
argocd_server: argocd.internal.example.com
image_registry: ghcr.io
enable_terraform: true
enable_cicd: true
enable_argocd: true
enable_pact: true
enable_drift_detection: true
enable_pre_commit: true
environments:
  - dev
  - staging
  - production
```

---

## 9. CLI Reference

```
genesis <command> [options]
```

### `generate` — Full generation pass

```bash
# From flags
python genesis.py generate \
  --name <service-name> \
  --criticality <low|medium|high|critical> \
  --language <python|go|nodejs|rust> \
  --database <postgresql|mongodb|redis|none> \
  --port <port> \
  --output-dir <path>

# From spec file
python genesis.py generate --config service-spec.yaml

# Output as ZIP archive
python genesis.py generate --config service-spec.yaml --zip
python genesis.py generate --name my-service --zip --output-dir ./dist
```

### `regen` — Surgical component regeneration

```bash
# Regenerate specific components (preserves sacred zones)
python genesis.py regen \
  --config service-spec.yaml \
  --components terraform,cicd,argocd

# Available component keys: terraform, kubernetes, rbac, vault,
#   prometheus, hpa, pdb, argocd, cicd, pre-commit, pact, drift
```

### `drift-check` — Manual drift detection

```bash
# Check dev environment
python genesis.py drift-check --service payment-service

# Check all environments
python genesis.py drift-check --service payment-service --all-envs
```

### `validate-sacred` — Sacred zone integrity check

```bash
# Validate against origin/main (used in CI Gate 1)
python genesis.py validate-sacred --base-ref origin/main

# Validate against a specific commit
python genesis.py validate-sacred --base-ref HEAD~1
```

### `info` — Generator metadata

```bash
python genesis.py info
# Outputs JSON: version, components, criticality profiles, supported languages, etc.
```

---

## 10. Python API Reference

```python
from genesis import (
    GenesisGenerator,
    ServiceSpec,
    Criticality,
    Language,
    DatabaseType,
)

gen = GenesisGenerator()

spec = ServiceSpec(
    name="payment-service",
    criticality=Criticality.CRITICAL,
    language=Language.PYTHON,
    database=DatabaseType.POSTGRESQL,
    port=8080,
    github_owner="IAmSoThirsty",
    environments=["dev", "staging", "production"],
)
```

### `generate(spec) → Dict[str, str]`

Returns a flat mapping of `{relative_path: file_content}` for all enabled components.
Does not write to disk.

```python
files = gen.generate(spec)
# files["kubernetes/payment-service/deployment.yaml"] → "apiVersion: apps/v1\n..."
```

### `generate_zip(spec) → bytes`

Calls `generate()` and packs all files into a ZIP archive. Suitable for API responses.

```python
zip_bytes = gen.generate_zip(spec)
with open("payment-service.zip", "wb") as f:
    f.write(zip_bytes)
```

### `write_to_disk(spec, output_dir=".") → List[str]`

Calls `generate()` and writes all files to `output_dir`, creating parent directories as
needed. Returns the list of relative paths written.

```python
written = gen.write_to_disk(spec, output_dir="./generated/payment-service")
# written → ["kubernetes/payment-service/deployment.yaml", ...]
```

### `regen(spec, components, output_dir=".") → Dict[str, str]`

Surgically regenerates the listed components in `output_dir`, preserving sacred zones.

```python
regenerated = gen.regen(
    spec,
    components=["terraform", "cicd"],
    output_dir="./generated/payment-service",
)
```

### `validate_sacred_zones(base_ref="HEAD") → bool`

Returns `True` if no sacred zones have been modified since `base_ref`. Returns `False`
and logs all violations otherwise.

```python
ok = gen.validate_sacred_zones(base_ref="origin/main")
if not ok:
    raise RuntimeError("Sacred zone violations detected")
```

### `drift_check(service, all_envs=False) → bool`

Runs the drift-detection shell scripts for the named service. Returns `True` if no drift
detected, `False` otherwise.

```python
clean = gen.drift_check("payment-service", all_envs=True)
```

### `info() → Dict[str, Any]`

Returns generator metadata: version, component inventory, criticality profiles, supported
languages and databases, Terraform modules, CI/CD gates.

```python
import json
print(json.dumps(gen.info(), indent=2))
```

---

## 11. REST API Reference

The FastAPI backend (at `backend/server.py`) exposes the Genesis generator over HTTP.

### `POST /api/genesis/generate`

Generate a complete microservice infrastructure package, returned as a ZIP archive.

**Request body** (`application/json`):

```json
{
  "name": "payment-service",
  "criticality": "critical",
  "language": "python",
  "database": "postgresql",
  "port": 8080,
  "github_owner": "IAmSoThirsty"
}
```

All fields correspond to `ServiceSpec` fields. `name` is required; all others have defaults.

**Response:** `application/zip` — binary ZIP archive.

```bash
curl -X POST http://localhost:8001/api/genesis/generate \
  -H "Content-Type: application/json" \
  -d '{"name": "payment-service", "criticality": "critical", "language": "python"}' \
  -o payment-service.zip
```

### `POST /api/generate`

Legacy endpoint. Accepts `MicroserviceConfig` payload and delegates to the Genesis generator.

### `GET /api/generator/info`

Returns the `GenesisGenerator.info()` payload as JSON.

```bash
curl http://localhost:8001/api/generator/info | jq .
```

---

## 12. Output Structure

A full generation pass for a service named `payment-service` with all features enabled
produces the following directory tree:

```
output/
├── service-spec.yaml
│
├── kubernetes/payment-service/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── serviceaccount.yaml
│   ├── network-policy.yaml
│   ├── clusterrole.yaml
│   ├── clusterrolebinding.yaml
│   ├── hpa.yaml
│   ├── pdb.yaml
│   ├── prometheus-alerts.yaml
│   └── drift-detection-cronjob.yaml
│
├── vault/payment-service/
│   ├── policy.hcl
│   └── auth-role.yaml
│
├── terraform/
│   ├── shared/
│   │   ├── providers.tf
│   │   ├── data.tf
│   │   ├── locals.tf
│   │   └── variables.tf
│   ├── scripts/
│   │   ├── plan.sh
│   │   ├── apply.sh
│   │   └── destroy.sh
│   └── services/payment-service/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── versions.tf
│       ├── terraform.tfvars
│       ├── backend.tf
│       └── modules/
│           ├── namespace/{main,variables,outputs}.tf
│           ├── deployment/{main,variables,outputs}.tf
│           ├── rbac/{main,variables,outputs}.tf
│           ├── vault/{main,variables,outputs}.tf
│           └── monitoring/{main,variables,outputs}.tf
│
├── argocd/
│   ├── appset-payment-service.yaml
│   └── project-payment-service.yaml
│
├── .github/workflows/
│   ├── genesis-pipeline.yml
│   ├── genesis-pr-check.yml
│   ├── genesis-drift-detect.yml
│   ├── genesis-release.yml
│   ├── genesis-rollback.yml
│   └── genesis-security-scan.yml
│
├── .pre-commit-config.yaml
│
├── scripts/
│   ├── pre-commit-sacred-check.py
│   └── drift-check-payment-service.sh
│
└── tests/pact/
    ├── test_provider_payment_service.py
    └── test_consumer_payment_service.py
```

---

## 13. Operational Runbook

### Adding a new service

```bash
# 1. Create a spec file
cat > my-service-spec.yaml <<EOF
name: my-service
criticality: high
language: python
database: postgresql
port: 8000
github_owner: IAmSoThirsty
EOF

# 2. Generate all artefacts
python genesis.py generate --config my-service-spec.yaml --output-dir ./generated/my-service

# 3. Review generated files
ls generated/my-service/

# 4. Commit and push — CI will validate constitutional constraints
git add generated/my-service/
git commit -m "feat: add my-service infrastructure"
git push
```

### Updating a single component after spec change

```bash
# Edit the spec, then surgically regenerate only what changed
python genesis.py regen \
  --config my-service-spec.yaml \
  --components terraform,hpa \
  --output-dir ./generated/my-service

# Review the diff — sacred zones are untouched
git diff generated/my-service/
```

### Responding to a sacred zone violation in CI

A sacred zone violation means a manually maintained block was changed without going through
the proper update mechanism. To resolve:

1. Identify the violated zone:
   ```
   python genesis.py validate-sacred --base-ref origin/main
   ```
2. If the change was intentional, use `genesis regen` to update the generated portion and
   preserve your change inside the zone delimiters.
3. If the change was accidental, revert it:
   ```bash
   git checkout origin/main -- <file>
   ```

### Handling detected infrastructure drift

1. Examine the drift report in the CI Gate 4 log
2. For Terraform drift:
   - If expected (manual hotfix applied): run `terraform apply` from the generated config to
     bring state back in sync, then commit
   - If unexpected: investigate who changed the live infrastructure and correct it
3. For Kubernetes drift:
   - Trigger an ArgoCD sync manually: `argocd app sync <slug>-<env>`

### Rolling back a failed deployment

```bash
# Via the rollback workflow
gh workflow run genesis-rollback.yml \
  -f service=payment-service \
  -f environment=production \
  -f revision=previous
```

Or directly via ArgoCD:
```bash
argocd app rollback payment-service-production
```

---

*This document is the canonical reference for Genesis design, compiler pipeline, and governance
philosophy. For implementation details, see [`genesis.py`](../genesis.py) in the repository root.
For quick-start instructions and REST API usage, see the [project README](../README.md).*
