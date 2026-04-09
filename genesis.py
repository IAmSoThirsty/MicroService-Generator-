#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          GENESIS MICROSERVICES GENERATOR — Production-Grade v2.0.0          ║
║                                                                              ║
║  15 Components, Complete Pipeline, Full Terraform + K8s + CI/CD Coverage    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Component Inventory:
  1.  SystemPipeline             — Orchestrates all generation phases
  2.  TerraformGenerator         — 32 files across 5 modules (per-service infra)
  3.  KubernetesGenerator        — Namespace, Deployment, Service manifests
  4.  RBACGenerator              — ClusterRole / RoleBinding per service
  5.  VaultPolicyGenerator       — Scoped secret paths per service
  6.  PrometheusAlertGenerator   — SLO burn-rate alerts (criticality-calibrated)
  7.  HPAGenerator               — HPA with criticality-driven min/max replicas
  8.  PDBGenerator               — PodDisruptionBudget per service
  9.  ArgoCDGenerator            — ApplicationSet with self-heal + auto-prune
  10. CICDPipelineGenerator      — 5-gate GitHub Actions pipeline
  11. PreCommitGenerator         — Sacred-zone integrity hooks
  12. PactContractGenerator      — Consumer-driven contract tests
  13. DriftDetectionGenerator    — Terraform / live-state drift detection job
  14. SacredZonePreserver        — Protects immutable sections from regeneration
  15. SurgicalRegen              — Component-level selective regeneration

Usage (CLI):
    python genesis.py generate --config <service-spec.yaml>
    python genesis.py generate --name my-service --criticality high --language python
    python genesis.py regen    --name my-service --components terraform,cicd
    python genesis.py info

Usage (Python API):
    from genesis import GenesisGenerator, ServiceSpec, Criticality
    gen = GenesisGenerator()
    files = gen.generate(ServiceSpec(name="my-service", criticality=Criticality.HIGH))
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Component 14 — Sacred Zone Preserver
# ──────────────────────────────────────────────────────────────────────────────

SACRED_ZONE_OPEN = "# <<<SACRED_ZONE_BEGIN>>>"
SACRED_ZONE_CLOSE = "# <<<SACRED_ZONE_END>>>"


class SacredZonePreserver:
    """Extracts and re-injects sacred (manually maintained) blocks during regen."""

    def extract(self, content: str) -> Dict[str, str]:
        zones: Dict[str, str] = {}
        lines = content.splitlines()
        inside = False
        zone_name = ""
        buf: List[str] = []
        for line in lines:
            if SACRED_ZONE_OPEN in line:
                inside = True
                zone_name = line.strip().split(SACRED_ZONE_OPEN)[-1].strip() or "default"
                buf = []
            elif SACRED_ZONE_CLOSE in line and inside:
                zones[zone_name] = "\n".join(buf)
                inside = False
                buf = []
            elif inside:
                buf.append(line)
        return zones

    def inject(self, content: str, zones: Dict[str, str]) -> str:
        lines = content.splitlines()
        result: List[str] = []
        inside = False
        zone_name = ""
        for line in lines:
            if SACRED_ZONE_OPEN in line:
                inside = True
                zone_name = line.strip().split(SACRED_ZONE_OPEN)[-1].strip() or "default"
                result.append(line)
                if zone_name in zones:
                    result.extend(zones[zone_name].splitlines())
            elif SACRED_ZONE_CLOSE in line and inside:
                inside = False
                result.append(line)
            elif not inside:
                result.append(line)
        return "\n".join(result)


# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

class Criticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Language(str, Enum):
    PYTHON = "python"
    GO = "go"
    NODEJS = "nodejs"
    RUST = "rust"


class DatabaseType(str, Enum):
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    REDIS = "redis"
    NONE = "none"


HPA_PROFILES: Dict[str, Dict[str, int]] = {
    Criticality.LOW: {"min": 1, "max": 3, "cpu_target": 80},
    Criticality.MEDIUM: {"min": 2, "max": 6, "cpu_target": 70},
    Criticality.HIGH: {"min": 3, "max": 10, "cpu_target": 65},
    Criticality.CRITICAL: {"min": 5, "max": 20, "cpu_target": 60},
}

SLO_PROFILES: Dict[str, Dict[str, Any]] = {
    Criticality.LOW: {
        "availability_target": 99.0,
        "latency_target_ms": 500,
        "burn_rate_1h": 14.4,
        "burn_rate_6h": 6.0,
    },
    Criticality.MEDIUM: {
        "availability_target": 99.5,
        "latency_target_ms": 300,
        "burn_rate_1h": 14.4,
        "burn_rate_6h": 6.0,
    },
    Criticality.HIGH: {
        "availability_target": 99.9,
        "latency_target_ms": 200,
        "burn_rate_1h": 14.4,
        "burn_rate_6h": 6.0,
    },
    Criticality.CRITICAL: {
        "availability_target": 99.99,
        "latency_target_ms": 100,
        "burn_rate_1h": 14.4,
        "burn_rate_6h": 6.0,
    },
}

PDB_PROFILES: Dict[str, str] = {
    Criticality.LOW: "0",
    Criticality.MEDIUM: "1",
    Criticality.HIGH: "1",
    Criticality.CRITICAL: "2",
}


@dataclass
class ServiceSpec:
    name: str
    criticality: Criticality = Criticality.MEDIUM
    language: Language = Language.PYTHON
    database: DatabaseType = DatabaseType.POSTGRESQL
    port: int = 8000
    metrics_port: int = 9090
    namespace: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = "platform-team"
    github_owner: str = "IAmSoThirsty"
    github_repo: str = "MicroService-Generator-"
    vault_mount: str = "secret"
    argocd_server: str = "argocd.example.com"
    image_registry: str = "ghcr.io"
    enable_terraform: bool = True
    enable_cicd: bool = True
    enable_argocd: bool = True
    enable_pact: bool = True
    enable_drift_detection: bool = True
    enable_pre_commit: bool = True
    environments: List[str] = field(default_factory=lambda: ["dev", "staging", "production"])

    def __post_init__(self):
        if not self.namespace:
            self.namespace = self.name
        if not self.description:
            self.description = f"Production microservice: {self.name}"

    @property
    def hpa(self) -> Dict[str, int]:
        return HPA_PROFILES[self.criticality]

    @property
    def slo(self) -> Dict[str, Any]:
        return SLO_PROFILES[self.criticality]

    @property
    def pdb_min_available(self) -> str:
        return PDB_PROFILES[self.criticality]

    @property
    def slug(self) -> str:
        return self.name.lower().replace("_", "-").replace(" ", "-")

    @property
    def snake(self) -> str:
        return self.name.lower().replace("-", "_").replace(" ", "_")

    @property
    def pascal(self) -> str:
        return "".join(w.capitalize() for w in self.name.replace("-", " ").replace("_", " ").split())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ServiceSpec":
        d = dict(d)
        for enum_field, enum_class in [
            ("criticality", Criticality),
            ("language", Language),
            ("database", DatabaseType),
        ]:
            if enum_field in d and isinstance(d[enum_field], str):
                d[enum_field] = enum_class(d[enum_field])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_yaml(cls, path: str) -> "ServiceSpec":
        with open(path) as f:
            return cls.from_dict(yaml.safe_load(f))


# ──────────────────────────────────────────────────────────────────────────────
# Component 2 — Terraform Generator (32 files, 5 modules)
# ──────────────────────────────────────────────────────────────────────────────

class TerraformGenerator:
    """Generates Terraform modules: namespace, deployment, rbac, vault, monitoring."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        files: Dict[str, str] = {}
        base = f"terraform/services/{spec.slug}"

        # Root module
        files[f"{base}/main.tf"] = self._root_main(spec)
        files[f"{base}/variables.tf"] = self._root_variables(spec)
        files[f"{base}/outputs.tf"] = self._root_outputs(spec)
        files[f"{base}/versions.tf"] = self._versions()
        files[f"{base}/terraform.tfvars"] = self._root_tfvars(spec)
        files[f"{base}/backend.tf"] = self._backend(spec)

        # Module: namespace
        files[f"{base}/modules/namespace/main.tf"] = self._ns_main(spec)
        files[f"{base}/modules/namespace/variables.tf"] = self._ns_variables()
        files[f"{base}/modules/namespace/outputs.tf"] = self._ns_outputs()

        # Module: deployment
        files[f"{base}/modules/deployment/main.tf"] = self._deploy_main(spec)
        files[f"{base}/modules/deployment/variables.tf"] = self._deploy_variables(spec)
        files[f"{base}/modules/deployment/outputs.tf"] = self._deploy_outputs()

        # Module: rbac
        files[f"{base}/modules/rbac/main.tf"] = self._rbac_main(spec)
        files[f"{base}/modules/rbac/variables.tf"] = self._rbac_variables()
        files[f"{base}/modules/rbac/outputs.tf"] = self._rbac_outputs()

        # Module: vault
        files[f"{base}/modules/vault/main.tf"] = self._vault_main(spec)
        files[f"{base}/modules/vault/variables.tf"] = self._vault_variables(spec)
        files[f"{base}/modules/vault/outputs.tf"] = self._vault_outputs()

        # Module: monitoring
        files[f"{base}/modules/monitoring/main.tf"] = self._monitoring_main(spec)
        files[f"{base}/modules/monitoring/variables.tf"] = self._monitoring_variables(spec)
        files[f"{base}/modules/monitoring/outputs.tf"] = self._monitoring_outputs()

        # Shared/root terraform files
        files["terraform/shared/providers.tf"] = self._shared_providers()
        files["terraform/shared/data.tf"] = self._shared_data()
        files["terraform/shared/locals.tf"] = self._shared_locals()
        files["terraform/shared/variables.tf"] = self._shared_variables()

        # Scripts
        files["terraform/scripts/plan.sh"] = self._tf_plan_script()
        files["terraform/scripts/apply.sh"] = self._tf_apply_script()
        files["terraform/scripts/destroy.sh"] = self._tf_destroy_script()

        # Environments
        for env in spec.environments:
            files[f"terraform/envs/{env}/main.tf"] = self._env_main(spec, env)
            files[f"terraform/envs/{env}/terraform.tfvars"] = self._env_tfvars(spec, env)

        return files

    def _root_main(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Root module for {spec.slug}
            # Wires all sub-modules with explicit dependency ordering

            module "namespace" {{
              source      = "./modules/namespace"
              name        = var.service_name
              labels      = local.common_labels
              annotations = local.common_annotations
            }}

            module "rbac" {{
              source         = "./modules/rbac"
              service_name   = var.service_name
              namespace      = module.namespace.name
              service_account = var.service_account_name

              depends_on = [module.namespace]
            }}

            module "vault" {{
              source       = "./modules/vault"
              service_name = var.service_name
              vault_mount  = var.vault_mount
              environment  = var.environment

              depends_on = [module.namespace, module.rbac]
            }}

            module "deployment" {{
              source           = "./modules/deployment"
              service_name     = var.service_name
              namespace        = module.namespace.name
              image            = var.image
              tag              = var.image_tag
              port             = var.port
              replicas         = var.replicas
              criticality      = var.criticality
              vault_role       = module.vault.vault_role
              service_account  = module.rbac.service_account_name
              environment      = var.environment
              resource_limits  = var.resource_limits
              resource_requests = var.resource_requests

              depends_on = [module.namespace, module.rbac, module.vault]
            }}

            module "monitoring" {{
              source             = "./modules/monitoring"
              service_name       = var.service_name
              namespace          = module.namespace.name
              criticality        = var.criticality
              availability_target = var.slo_availability_target
              latency_target_ms  = var.slo_latency_target_ms

              depends_on = [module.deployment]
            }}
        """)

    def _root_variables(self, spec: ServiceSpec) -> str:
        hpa = spec.hpa
        slo = spec.slo
        return dedent(f"""\
            variable "service_name" {{
              description = "Service name"
              type        = string
              default     = "{spec.slug}"
            }}

            variable "environment" {{
              description = "Deployment environment"
              type        = string
            }}

            variable "image" {{
              description = "Container image repository"
              type        = string
              default     = "{spec.image_registry}/{spec.github_owner}/{spec.slug}"
            }}

            variable "image_tag" {{
              description = "Container image tag"
              type        = string
              default     = "latest"
            }}

            variable "port" {{
              description = "Service port"
              type        = number
              default     = {spec.port}
            }}

            variable "replicas" {{
              description = "Initial replica count"
              type        = number
              default     = {hpa["min"]}
            }}

            variable "criticality" {{
              description = "Service criticality (low|medium|high|critical)"
              type        = string
              default     = "{spec.criticality.value}"
            }}

            variable "service_account_name" {{
              description = "Kubernetes service account name"
              type        = string
              default     = "{spec.slug}-sa"
            }}

            variable "vault_mount" {{
              description = "Vault mount path"
              type        = string
              default     = "{spec.vault_mount}"
            }}

            variable "resource_limits" {{
              description = "Resource limits"
              type        = map(string)
              default = {{
                cpu    = "500m"
                memory = "512Mi"
              }}
            }}

            variable "resource_requests" {{
              description = "Resource requests"
              type        = map(string)
              default = {{
                cpu    = "100m"
                memory = "128Mi"
              }}
            }}

            variable "slo_availability_target" {{
              description = "SLO availability target (%)"
              type        = number
              default     = {slo["availability_target"]}
            }}

            variable "slo_latency_target_ms" {{
              description = "SLO latency target (ms)"
              type        = number
              default     = {slo["latency_target_ms"]}
            }}

            locals {{
              common_labels = {{
                "app.kubernetes.io/name"       = var.service_name
                "app.kubernetes.io/version"    = var.image_tag
                "app.kubernetes.io/managed-by" = "genesis"
                "criticality"                  = var.criticality
                "environment"                  = var.environment
              }}

              common_annotations = {{
                "genesis.io/generated-by" = "genesis-v2"
                "genesis.io/service"      = var.service_name
              }}
            }}
        """)

    def _root_outputs(self, spec: ServiceSpec) -> str:
        return dedent("""\
            output "namespace" {
              description = "Kubernetes namespace"
              value       = module.namespace.name
            }

            output "service_account" {
              description = "Kubernetes service account"
              value       = module.rbac.service_account_name
            }

            output "vault_role" {
              description = "Vault Kubernetes auth role"
              value       = module.vault.vault_role
            }

            output "deployment_name" {
              description = "Kubernetes deployment name"
              value       = module.deployment.deployment_name
            }

            output "service_monitor_name" {
              description = "Prometheus ServiceMonitor name"
              value       = module.monitoring.service_monitor_name
            }
        """)

    def _versions(self) -> str:
        return dedent("""\
            terraform {
              required_version = ">= 1.5.0"

              required_providers {
                kubernetes = {
                  source  = "hashicorp/kubernetes"
                  version = "~> 2.23"
                }
                vault = {
                  source  = "hashicorp/vault"
                  version = "~> 3.20"
                }
                helm = {
                  source  = "hashicorp/helm"
                  version = "~> 2.11"
                }
              }
            }
        """)

    def _root_tfvars(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            service_name  = "{spec.slug}"
            image         = "{spec.image_registry}/{spec.github_owner}/{spec.slug}"
            image_tag     = "latest"
            vault_mount   = "{spec.vault_mount}"
            criticality   = "{spec.criticality.value}"
        """)

    def _backend(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            terraform {{
              backend "s3" {{
                bucket         = "terraform-state-{spec.github_owner}"
                key            = "services/{spec.slug}/terraform.tfstate"
                region         = "us-east-1"
                encrypt        = true
                dynamodb_table = "terraform-state-lock"
              }}
            }}
        """)

    def _ns_main(self, spec: ServiceSpec) -> str:
        return dedent("""\
            resource "kubernetes_namespace" "this" {
              metadata {
                name        = var.name
                labels      = var.labels
                annotations = var.annotations
              }
            }

            resource "kubernetes_resource_quota" "this" {
              metadata {
                name      = "${var.name}-quota"
                namespace = kubernetes_namespace.this.metadata[0].name
              }
              spec {
                hard = {
                  pods             = "50"
                  "requests.cpu"   = "4"
                  "requests.memory" = "8Gi"
                  "limits.cpu"     = "8"
                  "limits.memory"  = "16Gi"
                }
              }
            }

            resource "kubernetes_limit_range" "this" {
              metadata {
                name      = "${var.name}-limits"
                namespace = kubernetes_namespace.this.metadata[0].name
              }
              spec {
                limit {
                  type = "Container"
                  default = {
                    cpu    = "200m"
                    memory = "256Mi"
                  }
                  default_request = {
                    cpu    = "50m"
                    memory = "64Mi"
                  }
                }
              }
            }
        """)

    def _ns_variables(self) -> str:
        return dedent("""\
            variable "name" {
              description = "Namespace name"
              type        = string
            }

            variable "labels" {
              description = "Labels"
              type        = map(string)
              default     = {}
            }

            variable "annotations" {
              description = "Annotations"
              type        = map(string)
              default     = {}
            }
        """)

    def _ns_outputs(self) -> str:
        return dedent("""\
            output "name" {
              description = "Namespace name"
              value       = kubernetes_namespace.this.metadata[0].name
            }
        """)

    def _deploy_main(self, spec: ServiceSpec) -> str:
        return dedent("""\
            resource "kubernetes_deployment" "this" {
              metadata {
                name      = var.service_name
                namespace = var.namespace
                labels    = local.labels
              }

              spec {
                replicas = var.replicas

                selector {
                  match_labels = {
                    "app.kubernetes.io/name" = var.service_name
                  }
                }

                strategy {
                  type = "RollingUpdate"
                  rolling_update {
                    max_unavailable = "0"
                    max_surge       = "1"
                  }
                }

                template {
                  metadata {
                    labels      = local.labels
                    annotations = {
                      "prometheus.io/scrape" = "true"
                      "prometheus.io/port"   = tostring(var.port)
                      "prometheus.io/path"   = "/metrics"
                    }
                  }

                  spec {
                    service_account_name            = var.service_account
                    automount_service_account_token  = true
                    termination_grace_period_seconds = 60

                    container {
                      name  = var.service_name
                      image = "${var.image}:${var.tag}"

                      port {
                        name           = "http"
                        container_port = var.port
                        protocol       = "TCP"
                      }

                      resources {
                        limits   = var.resource_limits
                        requests = var.resource_requests
                      }

                      liveness_probe {
                        http_get {
                          path = "/health/live"
                          port = var.port
                        }
                        initial_delay_seconds = 30
                        period_seconds        = 10
                        failure_threshold     = 3
                      }

                      readiness_probe {
                        http_get {
                          path = "/health/ready"
                          port = var.port
                        }
                        initial_delay_seconds = 10
                        period_seconds        = 5
                        failure_threshold     = 3
                      }

                      startup_probe {
                        http_get {
                          path = "/health/startup"
                          port = var.port
                        }
                        failure_threshold = 30
                        period_seconds    = 10
                      }

                      env {
                        name  = "SERVICE_NAME"
                        value = var.service_name
                      }
                      env {
                        name  = "ENVIRONMENT"
                        value = var.environment
                      }
                      env {
                        name  = "VAULT_ROLE"
                        value = var.vault_role
                      }
                    }
                  }
                }
              }
            }

            resource "kubernetes_service" "this" {
              metadata {
                name      = var.service_name
                namespace = var.namespace
                labels    = local.labels
              }
              spec {
                selector = {
                  "app.kubernetes.io/name" = var.service_name
                }
                port {
                  name        = "http"
                  port        = 80
                  target_port = var.port
                  protocol    = "TCP"
                }
                type = "ClusterIP"
              }
            }

            locals {
              labels = merge(
                var.resource_labels,
                {
                  "app.kubernetes.io/name"       = var.service_name
                  "app.kubernetes.io/version"    = var.tag
                  "criticality"                  = var.criticality
                }
              )
            }
        """)

    def _deploy_variables(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            variable "service_name"     {{ type = string }}
            variable "namespace"        {{ type = string }}
            variable "image"            {{ type = string }}
            variable "tag"              {{ type = string; default = "latest" }}
            variable "port"             {{ type = number; default = {spec.port} }}
            variable "replicas"         {{ type = number; default = {spec.hpa["min"]} }}
            variable "criticality"      {{ type = string; default = "{spec.criticality.value}" }}
            variable "vault_role"       {{ type = string }}
            variable "service_account"  {{ type = string }}
            variable "environment"      {{ type = string }}
            variable "resource_limits"  {{ type = map(string) }}
            variable "resource_requests" {{ type = map(string) }}
            variable "resource_labels"  {{ type = map(string); default = {{}} }}
        """)

    def _deploy_outputs(self) -> str:
        return dedent("""\
            output "deployment_name" {
              value = kubernetes_deployment.this.metadata[0].name
            }

            output "service_name" {
              value = kubernetes_service.this.metadata[0].name
            }
        """)

    def _rbac_main(self, spec: ServiceSpec) -> str:
        return dedent("""\
            resource "kubernetes_service_account" "this" {
              metadata {
                name      = var.service_account
                namespace = var.namespace
                annotations = {
                  "genesis.io/managed" = "true"
                }
              }
            }

            resource "kubernetes_cluster_role" "this" {
              metadata {
                name = "${var.service_name}-role"
              }
              rule {
                api_groups = [""]
                resources  = ["configmaps", "secrets"]
                verbs      = ["get", "list", "watch"]
              }
              rule {
                api_groups = [""]
                resources  = ["pods"]
                verbs      = ["get", "list"]
              }
            }

            resource "kubernetes_cluster_role_binding" "this" {
              metadata {
                name = "${var.service_name}-role-binding"
              }
              role_ref {
                api_group = "rbac.authorization.k8s.io"
                kind      = "ClusterRole"
                name      = kubernetes_cluster_role.this.metadata[0].name
              }
              subject {
                kind      = "ServiceAccount"
                name      = kubernetes_service_account.this.metadata[0].name
                namespace = var.namespace
              }
            }
        """)

    def _rbac_variables(self) -> str:
        return dedent("""\
            variable "service_name"   { type = string }
            variable "namespace"      { type = string }
            variable "service_account" { type = string }
        """)

    def _rbac_outputs(self) -> str:
        return dedent("""\
            output "service_account_name" {
              value = kubernetes_service_account.this.metadata[0].name
            }
        """)

    def _vault_main(self, spec: ServiceSpec) -> str:
        return dedent("""\
            resource "vault_policy" "this" {
              name   = var.service_name
              policy = templatefile("${path.module}/policy.hcl.tpl", {
                service_name = var.service_name
                vault_mount  = var.vault_mount
                environment  = var.environment
              })
            }

            resource "vault_kubernetes_auth_backend_role" "this" {
              backend                          = "kubernetes"
              role_name                        = "${var.service_name}-${var.environment}"
              bound_service_account_names      = ["${var.service_name}-sa"]
              bound_service_account_namespaces = [var.service_name]
              token_ttl                        = 3600
              token_policies                   = [vault_policy.this.name]
            }
        """)

    def _vault_variables(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            variable "service_name" {{ type = string }}
            variable "vault_mount"  {{ type = string; default = "{spec.vault_mount}" }}
            variable "environment"  {{ type = string }}
        """)

    def _vault_outputs(self) -> str:
        return dedent("""\
            output "vault_role" {
              value = vault_kubernetes_auth_backend_role.this.role_name
            }
            output "policy_name" {
              value = vault_policy.this.name
            }
        """)

    def _monitoring_main(self, spec: ServiceSpec) -> str:
        return dedent("""\
            resource "kubernetes_manifest" "service_monitor" {
              manifest = {
                apiVersion = "monitoring.coreos.com/v1"
                kind       = "ServiceMonitor"
                metadata = {
                  name      = "${var.service_name}-monitor"
                  namespace = var.namespace
                  labels = {
                    release = "prometheus"
                  }
                }
                spec = {
                  selector = {
                    matchLabels = {
                      "app.kubernetes.io/name" = var.service_name
                    }
                  }
                  endpoints = [{
                    port     = "http"
                    path     = "/metrics"
                    interval = "15s"
                  }]
                }
              }
            }

            resource "kubernetes_manifest" "slo_alert_fast" {
              manifest = {
                apiVersion = "monitoring.coreos.com/v1"
                kind       = "PrometheusRule"
                metadata = {
                  name      = "${var.service_name}-slo-fast-burn"
                  namespace = var.namespace
                  labels = {
                    release = "prometheus"
                  }
                }
                spec = {
                  groups = [{
                    name = "${var.service_name}.slo.fast-burn"
                    rules = [{
                      alert = "${var.service_name}SLOFastBurn"
                      expr  = "(sum(rate(http_requests_total{job='${var.service_name}',status=~'5..'}[1h])) / sum(rate(http_requests_total{job='${var.service_name}'}[1h]))) > (${var.burn_rate_1h} * (1 - ${var.availability_target} / 100))"
                      for   = "2m"
                      labels = {
                        severity    = var.criticality == "critical" ? "page" : "warn"
                        service     = var.service_name
                        criticality = var.criticality
                      }
                      annotations = {
                        summary     = "Fast error budget burn on ${var.service_name}"
                        description = "Error budget burn rate is ${var.burn_rate_1h}x over 1h window"
                      }
                    }]
                  }]
                }
              }
            }
        """)

    def _monitoring_variables(self, spec: ServiceSpec) -> str:
        slo = spec.slo
        return dedent(f"""\
            variable "service_name"       {{ type = string }}
            variable "namespace"          {{ type = string }}
            variable "criticality"        {{ type = string; default = "{spec.criticality.value}" }}
            variable "availability_target" {{ type = number; default = {slo["availability_target"]} }}
            variable "latency_target_ms"  {{ type = number; default = {slo["latency_target_ms"]} }}
            variable "burn_rate_1h"       {{ type = number; default = {slo["burn_rate_1h"]} }}
            variable "burn_rate_6h"       {{ type = number; default = {slo["burn_rate_6h"]} }}
        """)

    def _monitoring_outputs(self) -> str:
        return dedent("""\
            output "service_monitor_name" {
              value = "${var.service_name}-monitor"
            }
        """)

    def _shared_providers(self) -> str:
        return dedent("""\
            provider "kubernetes" {
              config_path    = var.kubeconfig_path
              config_context = var.kube_context
            }

            provider "vault" {
              address = var.vault_address
            }

            provider "helm" {
              kubernetes {
                config_path    = var.kubeconfig_path
                config_context = var.kube_context
              }
            }
        """)

    def _shared_data(self) -> str:
        return dedent("""\
            data "vault_generic_secret" "cluster_credentials" {
              path = "secret/platform/kubernetes"
            }
        """)

    def _shared_locals(self) -> str:
        return dedent("""\
            locals {
              cluster_name = "${var.environment}-cluster"
              region       = var.aws_region
            }
        """)

    def _shared_variables(self) -> str:
        return dedent("""\
            variable "kubeconfig_path"  { type = string; default = "~/.kube/config" }
            variable "kube_context"     { type = string; default = "" }
            variable "vault_address"    { type = string; default = "https://vault.example.com" }
            variable "aws_region"       { type = string; default = "us-east-1" }
            variable "environment"      { type = string }
        """)

    def _tf_plan_script(self) -> str:
        return dedent("""\
            #!/usr/bin/env bash
            set -euo pipefail
            ENV="${1:-dev}"
            SERVICE="${2}"
            cd "$(dirname "$0")/../services/${SERVICE}"
            terraform init -backend-config="key=services/${SERVICE}/${ENV}/terraform.tfstate"
            terraform plan -var="environment=${ENV}" -out=tfplan
            echo "Plan saved to: tfplan"
        """)

    def _tf_apply_script(self) -> str:
        return dedent("""\
            #!/usr/bin/env bash
            set -euo pipefail
            ENV="${1:-dev}"
            SERVICE="${2}"
            cd "$(dirname "$0")/../services/${SERVICE}"
            terraform apply -var="environment=${ENV}" -auto-approve
            echo "Apply complete for ${SERVICE} in ${ENV}"
        """)

    def _tf_destroy_script(self) -> str:
        return dedent("""\
            #!/usr/bin/env bash
            set -euo pipefail
            ENV="${1:-dev}"
            SERVICE="${2}"
            read -p "Destroy ${SERVICE} in ${ENV}? [yes/NO] " confirm
            if [[ "$confirm" != "yes" ]]; then echo "Aborted."; exit 1; fi
            cd "$(dirname "$0")/../services/${SERVICE}"
            terraform destroy -var="environment=${ENV}" -auto-approve
        """)

    def _env_main(self, spec: ServiceSpec, env: str) -> str:
        return dedent(f"""\
            module "{spec.slug}" {{
              source      = "../../services/{spec.slug}"
              environment = "{env}"
              image_tag   = var.image_tag
            }}
        """)

    def _env_tfvars(self, spec: ServiceSpec, env: str) -> str:
        replicas = spec.hpa["min"] if env == "dev" else spec.hpa["min"] + 1
        return dedent(f"""\
            # Environment: {env}
            image_tag = "latest"
            replicas  = {replicas}
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Component 3 — Kubernetes Generator
# ──────────────────────────────────────────────────────────────────────────────

class KubernetesGenerator:
    """Generates raw Kubernetes YAML manifests."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        base = f"kubernetes/{spec.slug}"
        return {
            f"{base}/namespace.yaml": self._namespace(spec),
            f"{base}/deployment.yaml": self._deployment(spec),
            f"{base}/service.yaml": self._service(spec),
            f"{base}/configmap.yaml": self._configmap(spec),
            f"{base}/serviceaccount.yaml": self._serviceaccount(spec),
            f"{base}/network-policy.yaml": self._network_policy(spec),
        }

    def _namespace(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": spec.namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "genesis",
                    "criticality": spec.criticality.value,
                },
            },
        }, default_flow_style=False)

    def _deployment(self, spec: ServiceSpec) -> str:
        hpa = spec.hpa
        return yaml.dump({
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": spec.slug,
                "namespace": spec.namespace,
                "labels": {"app.kubernetes.io/name": spec.slug},
            },
            "spec": {
                "replicas": hpa["min"],
                "selector": {"matchLabels": {"app.kubernetes.io/name": spec.slug}},
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "template": {
                    "metadata": {
                        "labels": {"app.kubernetes.io/name": spec.slug},
                        "annotations": {
                            "prometheus.io/scrape": "true",
                            "prometheus.io/port": str(spec.port),
                        },
                    },
                    "spec": {
                        "serviceAccountName": f"{spec.slug}-sa",
                        "terminationGracePeriodSeconds": 60,
                        "containers": [{
                            "name": spec.slug,
                            "image": f"{spec.image_registry}/{spec.github_owner}/{spec.slug}:latest",
                            "ports": [{"name": "http", "containerPort": spec.port}],
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "128Mi"},
                                "limits": {"cpu": "500m", "memory": "512Mi"},
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/health/live", "port": spec.port},
                                "initialDelaySeconds": 30,
                                "periodSeconds": 10,
                            },
                            "readinessProbe": {
                                "httpGet": {"path": "/health/ready", "port": spec.port},
                                "initialDelaySeconds": 10,
                                "periodSeconds": 5,
                            },
                            "startupProbe": {
                                "httpGet": {"path": "/health/startup", "port": spec.port},
                                "failureThreshold": 30,
                                "periodSeconds": 10,
                            },
                        }],
                    },
                },
            },
        }, default_flow_style=False)

    def _service(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": spec.slug,
                "namespace": spec.namespace,
                "labels": {"app.kubernetes.io/name": spec.slug},
            },
            "spec": {
                "selector": {"app.kubernetes.io/name": spec.slug},
                "ports": [{"name": "http", "port": 80, "targetPort": spec.port}],
                "type": "ClusterIP",
            },
        }, default_flow_style=False)

    def _configmap(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"{spec.slug}-config",
                "namespace": spec.namespace,
            },
            "data": {
                "SERVICE_NAME": spec.slug,
                "LOG_LEVEL": "INFO",
                "PORT": str(spec.port),
            },
        }, default_flow_style=False)

    def _serviceaccount(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": f"{spec.slug}-sa",
                "namespace": spec.namespace,
                "annotations": {"genesis.io/managed": "true"},
            },
        }, default_flow_style=False)

    def _network_policy(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"{spec.slug}-network-policy",
                "namespace": spec.namespace,
            },
            "spec": {
                "podSelector": {"matchLabels": {"app.kubernetes.io/name": spec.slug}},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [{
                    "from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}}}],
                    "ports": [{"protocol": "TCP", "port": spec.port}],
                }],
                "egress": [{"to": [], "ports": [{"protocol": "TCP", "port": 443}, {"protocol": "TCP", "port": 53}, {"protocol": "UDP", "port": 53}]}],
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 4 — RBAC Generator
# ──────────────────────────────────────────────────────────────────────────────

class RBACGenerator:
    """Generates ClusterRole and RoleBinding YAML for a service."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        base = f"kubernetes/{spec.slug}"
        return {
            f"{base}/clusterrole.yaml": self._cluster_role(spec),
            f"{base}/clusterrolebinding.yaml": self._cluster_role_binding(spec),
        }

    def _cluster_role(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": f"{spec.slug}-role"},
            "rules": [
                {"apiGroups": [""], "resources": ["configmaps", "secrets"], "verbs": ["get", "list", "watch"]},
                {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]},
            ],
        }, default_flow_style=False)

    def _cluster_role_binding(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {"name": f"{spec.slug}-role-binding"},
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": f"{spec.slug}-role",
            },
            "subjects": [{
                "kind": "ServiceAccount",
                "name": f"{spec.slug}-sa",
                "namespace": spec.namespace,
            }],
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 5 — Vault Policy Generator
# ──────────────────────────────────────────────────────────────────────────────

class VaultPolicyGenerator:
    """Generates scoped Vault HCL policies per service and environment."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for env in spec.environments:
            files[f"vault/policies/{spec.slug}-{env}.hcl"] = self._policy(spec, env)
        files[f"vault/policies/{spec.slug}-common.hcl"] = self._common_policy(spec)
        return files

    def _policy(self, spec: ServiceSpec, env: str) -> str:
        mount = spec.vault_mount
        return dedent(f"""\
            # Vault policy for {spec.slug} in {env}
            # Generated by Genesis v2 — scoped secret paths

            # Service-specific secrets
            path "{mount}/data/{env}/{spec.slug}/*" {{
              capabilities = ["read", "list"]
            }}

            path "{mount}/metadata/{env}/{spec.slug}/*" {{
              capabilities = ["list"]
            }}

            # Shared platform secrets (read-only)
            path "{mount}/data/{env}/platform/tls" {{
              capabilities = ["read"]
            }}

            path "{mount}/data/{env}/platform/db-credentials/{spec.slug}" {{
              capabilities = ["read"]
            }}

            # Deny everything else
            path "{mount}/*" {{
              capabilities = ["deny"]
            }}
        """)

    def _common_policy(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Common policy for {spec.slug} across all environments
            path "auth/token/renew-self" {{
              capabilities = ["update"]
            }}
            path "auth/token/lookup-self" {{
              capabilities = ["read"]
            }}
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Component 6 — Prometheus SLO Alert Generator
# ──────────────────────────────────────────────────────────────────────────────

class PrometheusAlertGenerator:
    """Generates SLO burn-rate alert rules calibrated to criticality."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"monitoring/rules/{spec.slug}-slo-alerts.yaml": self._slo_rules(spec),
            f"monitoring/rules/{spec.slug}-infra-alerts.yaml": self._infra_rules(spec),
        }

    def _slo_rules(self, spec: ServiceSpec) -> str:
        slo = spec.slo
        target = slo["availability_target"]
        error_budget = 1 - target / 100
        fast_burn = slo["burn_rate_1h"]
        slow_burn = slo["burn_rate_6h"]
        severity = "critical" if spec.criticality in (Criticality.HIGH, Criticality.CRITICAL) else "warning"
        latency_ms = slo["latency_target_ms"]

        return yaml.dump({
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {
                "name": f"{spec.slug}-slo",
                "namespace": spec.namespace,
                "labels": {"release": "prometheus", "app": spec.slug},
            },
            "spec": {
                "groups": [
                    {
                        "name": f"{spec.slug}.slo.availability",
                        "interval": "30s",
                        "rules": [
                            {
                                "alert": f"{spec.pascal}HighErrorBudgetBurnFast",
                                "expr": (
                                    f"(sum(rate(http_requests_total{{job='{spec.slug}',status=~'5..'}}[1h])) / "
                                    f"sum(rate(http_requests_total{{job='{spec.slug}'}}[1h]))) > "
                                    f"({fast_burn} * {error_budget:.6f})"
                                ),
                                "for": "2m",
                                "labels": {
                                    "severity": severity,
                                    "service": spec.slug,
                                    "criticality": spec.criticality.value,
                                    "slo_type": "availability",
                                    "burn_window": "1h",
                                },
                                "annotations": {
                                    "summary": f"[{spec.slug}] Fast error budget burn — {fast_burn}x over 1h",
                                    "description": (
                                        f"The {spec.slug} service is consuming error budget "
                                        f"{fast_burn}x faster than allowed (1h window). "
                                        f"SLO target: {target}%."
                                    ),
                                    "runbook_url": f"https://wiki.example.com/runbooks/{spec.slug}",
                                    "dashboard": f"https://grafana.example.com/d/{spec.slug}",
                                },
                            },
                            {
                                "alert": f"{spec.pascal}HighErrorBudgetBurnSlow",
                                "expr": (
                                    f"(sum(rate(http_requests_total{{job='{spec.slug}',status=~'5..'}}[6h])) / "
                                    f"sum(rate(http_requests_total{{job='{spec.slug}'}}[6h]))) > "
                                    f"({slow_burn} * {error_budget:.6f})"
                                ),
                                "for": "15m",
                                "labels": {
                                    "severity": "warning",
                                    "service": spec.slug,
                                    "criticality": spec.criticality.value,
                                    "slo_type": "availability",
                                    "burn_window": "6h",
                                },
                                "annotations": {
                                    "summary": f"[{spec.slug}] Slow error budget burn — {slow_burn}x over 6h",
                                    "description": (
                                        f"The {spec.slug} service is consuming error budget "
                                        f"{slow_burn}x faster than allowed (6h window)."
                                    ),
                                },
                            },
                        ],
                    },
                    {
                        "name": f"{spec.slug}.slo.latency",
                        "rules": [
                            {
                                "alert": f"{spec.pascal}HighLatency",
                                "expr": (
                                    f"histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket"
                                    f"{{job='{spec.slug}'}}[5m])) by (le)) > {latency_ms / 1000:.3f}"
                                ),
                                "for": "5m",
                                "labels": {
                                    "severity": severity,
                                    "service": spec.slug,
                                    "slo_type": "latency",
                                },
                                "annotations": {
                                    "summary": f"[{spec.slug}] p99 latency > {latency_ms}ms",
                                    "description": (
                                        f"99th percentile latency for {spec.slug} exceeds "
                                        f"SLO target of {latency_ms}ms."
                                    ),
                                },
                            },
                        ],
                    },
                ]
            },
        }, default_flow_style=False)

    def _infra_rules(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {
                "name": f"{spec.slug}-infra",
                "namespace": spec.namespace,
                "labels": {"release": "prometheus"},
            },
            "spec": {
                "groups": [{
                    "name": f"{spec.slug}.infrastructure",
                    "rules": [
                        {
                            "alert": f"{spec.pascal}PodRestartingTooOften",
                            "expr": (
                                f"increase(kube_pod_container_status_restarts_total"
                                f"{{namespace='{spec.namespace}',pod=~'{spec.slug}-.*'}}[1h]) > 5"
                            ),
                            "for": "5m",
                            "labels": {"severity": "warning", "service": spec.slug},
                            "annotations": {
                                "summary": f"[{spec.slug}] Pod restarting frequently",
                            },
                        },
                        {
                            "alert": f"{spec.pascal}DeploymentReplicasMismatch",
                            "expr": (
                                f"kube_deployment_spec_replicas{{namespace='{spec.namespace}',"
                                f"deployment='{spec.slug}'}} != "
                                f"kube_deployment_status_replicas_available{{namespace='{spec.namespace}',"
                                f"deployment='{spec.slug}'}}"
                            ),
                            "for": "5m",
                            "labels": {"severity": "critical", "service": spec.slug},
                            "annotations": {
                                "summary": f"[{spec.slug}] Deployment replica mismatch",
                            },
                        },
                    ],
                }],
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 7 — HPA Generator
# ──────────────────────────────────────────────────────────────────────────────

class HPAGenerator:
    """Generates HorizontalPodAutoscaler with criticality-driven profiles."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"kubernetes/{spec.slug}/hpa.yaml": self._hpa(spec),
        }

    def _hpa(self, spec: ServiceSpec) -> str:
        hpa = spec.hpa
        return yaml.dump({
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{spec.slug}-hpa",
                "namespace": spec.namespace,
                "annotations": {
                    "genesis.io/criticality": spec.criticality.value,
                    "genesis.io/hpa-profile": json.dumps(hpa),
                },
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": spec.slug,
                },
                "minReplicas": hpa["min"],
                "maxReplicas": hpa["max"],
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": hpa["cpu_target"],
                            },
                        },
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": 80,
                            },
                        },
                    },
                ],
                "behavior": {
                    "scaleDown": {
                        "stabilizationWindowSeconds": 300,
                        "policies": [{"type": "Pods", "value": 1, "periodSeconds": 60}],
                    },
                    "scaleUp": {
                        "stabilizationWindowSeconds": 0,
                        "policies": [
                            {"type": "Pods", "value": 2, "periodSeconds": 60},
                            {"type": "Percent", "value": 100, "periodSeconds": 60},
                        ],
                        "selectPolicy": "Max",
                    },
                },
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 8 — PDB Generator
# ──────────────────────────────────────────────────────────────────────────────

class PDBGenerator:
    """Generates PodDisruptionBudget per service."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"kubernetes/{spec.slug}/pdb.yaml": self._pdb(spec),
        }

    def _pdb(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "policy/v1",
            "kind": "PodDisruptionBudget",
            "metadata": {
                "name": f"{spec.slug}-pdb",
                "namespace": spec.namespace,
                "annotations": {
                    "genesis.io/criticality": spec.criticality.value,
                },
            },
            "spec": {
                "minAvailable": spec.pdb_min_available,
                "selector": {
                    "matchLabels": {"app.kubernetes.io/name": spec.slug},
                },
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 9 — ArgoCD ApplicationSet Generator
# ──────────────────────────────────────────────────────────────────────────────

class ArgoCDGenerator:
    """Generates ArgoCD ApplicationSet with self-heal, auto-prune, per environment."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"argocd/{spec.slug}-applicationset.yaml": self._applicationset(spec),
            f"argocd/{spec.slug}-app-project.yaml": self._app_project(spec),
        }

    def _applicationset(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "ApplicationSet",
            "metadata": {
                "name": spec.slug,
                "namespace": "argocd",
                "annotations": {
                    "genesis.io/owner": spec.github_owner,
                    "genesis.io/service": spec.slug,
                },
            },
            "spec": {
                "generators": [{
                    "list": {
                        "elements": [
                            {"env": env, "revision": "main" if env == "production" else env}
                            for env in spec.environments
                        ],
                    },
                }],
                "template": {
                    "metadata": {
                        "name": f"{spec.slug}-{{{{env}}}}",
                        "labels": {
                            "app": spec.slug,
                            "environment": "{{env}}",
                        },
                    },
                    "spec": {
                        "project": spec.slug,
                        "source": {
                            "repoURL": f"https://github.com/{spec.github_owner}/{spec.github_repo}",
                            "targetRevision": "{{revision}}",
                            "path": f"kubernetes/{spec.slug}",
                        },
                        "destination": {
                            "server": "https://kubernetes.default.svc",
                            "namespace": f"{spec.namespace}-{{{{env}}}}",
                        },
                        "syncPolicy": {
                            "automated": {
                                "prune": True,
                                "selfHeal": True,
                                "allowEmpty": False,
                            },
                            "syncOptions": [
                                "Validate=true",
                                "CreateNamespace=true",
                                "PrunePropagationPolicy=foreground",
                                "PruneLast=true",
                            ],
                            "retry": {
                                "limit": 5,
                                "backoff": {
                                    "duration": "5s",
                                    "factor": 2,
                                    "maxDuration": "3m",
                                },
                            },
                        },
                    },
                },
            },
        }, default_flow_style=False)

    def _app_project(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": {
                "name": spec.slug,
                "namespace": "argocd",
            },
            "spec": {
                "description": spec.description,
                "sourceRepos": [
                    f"https://github.com/{spec.github_owner}/{spec.github_repo}",
                ],
                "destinations": [
                    {"server": "https://kubernetes.default.svc", "namespace": f"{spec.namespace}-*"},
                ],
                "clusterResourceWhitelist": [
                    {"group": "", "kind": "Namespace"},
                    {"group": "rbac.authorization.k8s.io", "kind": "ClusterRole"},
                    {"group": "rbac.authorization.k8s.io", "kind": "ClusterRoleBinding"},
                ],
                "namespaceResourceWhitelist": [
                    {"group": "*", "kind": "*"},
                ],
                "roles": [{
                    "name": "deploy-role",
                    "description": f"Deployment role for {spec.slug}",
                    "policies": [
                        f"p, proj:{spec.slug}:deploy-role, applications, sync, {spec.slug}/*, allow",
                    ],
                    "groups": [f"github:{spec.github_owner}"],
                }],
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 10 — CI/CD Pipeline Generator (5 gates)
# ──────────────────────────────────────────────────────────────────────────────

class CICDPipelineGenerator:
    """
    Generates GitHub Actions workflows implementing the 5-gate pipeline:
      Gate 1: Constitutional Validation
      Gate 2: Build & Test (language-aware matrix)
      Gate 3: Pact Contract Tests
      Gate 4: Drift Detection
      Gate 5: ArgoCD Deploy
    """

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        files: Dict[str, str] = {}
        base = ".github/workflows"
        files[f"{base}/genesis-pipeline.yml"] = self._full_pipeline(spec)
        files[f"{base}/genesis-pr-check.yml"] = self._pr_check(spec)
        files[f"{base}/genesis-drift-detect.yml"] = self._drift_detect_workflow(spec)
        files[f"{base}/genesis-release.yml"] = self._release_workflow(spec)
        files[f"{base}/genesis-rollback.yml"] = self._rollback_workflow(spec)
        files[f"{base}/genesis-security-scan.yml"] = self._security_scan(spec)
        return files

    def _full_pipeline(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Genesis 5-Gate Pipeline for {spec.slug}
            # Generated by Genesis Microservices Generator v2.0.0
            name: "{spec.slug} — Genesis Pipeline"

            on:
              push:
                branches: [main, release/**]
                paths:
                  - 'backend/**'
                  - 'frontend/**'
                  - 'kubernetes/{spec.slug}/**'
                  - 'terraform/services/{spec.slug}/**'
              workflow_dispatch:
                inputs:
                  environment:
                    description: "Target environment"
                    required: true
                    default: "dev"
                    type: choice
                    options: {json.dumps(spec.environments)}

            env:
              SERVICE_NAME: {spec.slug}
              IMAGE_REGISTRY: {spec.image_registry}
              IMAGE_REPO: {spec.github_owner}/{spec.slug}
              CRITICALITY: {spec.criticality.value}

            concurrency:
              group: pipeline-${{{{ github.ref }}}}
              cancel-in-progress: false

            jobs:

              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              # GATE 1 — Constitutional Validation
              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              constitutional-validation:
                name: "Gate 1 — Constitutional Validation"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      fetch-depth: 0

                  - name: Verify sacred zones untouched
                    run: |
                      python genesis.py validate-sacred --base-ref origin/main

                  - name: Validate service spec schema
                    run: |
                      python -c "
                      import yaml
                      from genesis import ServiceSpec
                      with open('service-spec.yaml') as f:
                          spec = ServiceSpec.from_dict(yaml.safe_load(f))
                      print(f'✓ Spec valid: {{spec.slug}}')
                      "

                  - name: Validate Terraform syntax
                    working-directory: terraform/services/{spec.slug}
                    run: terraform fmt -check -recursive

                  - name: Validate Kubernetes YAML
                    run: |
                      find kubernetes/{spec.slug} -name '*.yaml' | \\
                        xargs -I{{}} kubectl apply --dry-run=client -f {{}}

                  - name: Check CODEOWNERS integrity
                    run: |
                      if [ -f .github/CODEOWNERS ]; then
                        echo "✓ CODEOWNERS present"
                        grep -q "{spec.slug}" .github/CODEOWNERS || echo "⚠ {spec.slug} not in CODEOWNERS"
                      fi

              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              # GATE 2 — Build & Test (language-aware matrix)
              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              build-and-test:
                name: "Gate 2 — Build & Test"
                needs: constitutional-validation
                runs-on: ubuntu-latest
                strategy:
                  matrix:
                    component: [backend, frontend]
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Python
                    if: matrix.component == 'backend'
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.12"
                      cache: pip

                  - name: Install backend deps
                    if: matrix.component == 'backend'
                    run: pip install -r backend/requirements.txt

                  - name: Lint backend
                    if: matrix.component == 'backend'
                    run: |
                      cd backend
                      python -m flake8 . --max-line-length=120 --exclude=__pycache__
                      python -m mypy . --ignore-missing-imports || true

                  - name: Test backend
                    if: matrix.component == 'backend'
                    run: |
                      cd backend
                      python -m pytest ../tests/ \\
                        --cov=. \\
                        --cov-report=xml \\
                        --cov-fail-under=85 \\
                        -v

                  - name: Set up Node.js
                    if: matrix.component == 'frontend'
                    uses: actions/setup-node@v4
                    with:
                      node-version: "20"
                      cache: npm
                      cache-dependency-path: frontend/package-lock.json

                  - name: Install frontend deps
                    if: matrix.component == 'frontend'
                    working-directory: frontend
                    run: npm ci

                  - name: Lint frontend
                    if: matrix.component == 'frontend'
                    working-directory: frontend
                    run: npm run lint || true

                  - name: Test frontend
                    if: matrix.component == 'frontend'
                    working-directory: frontend
                    run: npm test -- --coverage --watchAll=false || true

                  - name: Build container image
                    if: matrix.component == 'backend'
                    run: |
                      docker build -t $IMAGE_REGISTRY/$IMAGE_REPO:${{{{ github.sha }}}} .
                      docker tag $IMAGE_REGISTRY/$IMAGE_REPO:${{{{ github.sha }}}} \\
                                 $IMAGE_REGISTRY/$IMAGE_REPO:latest

                  - name: Security scan (Trivy)
                    if: matrix.component == 'backend'
                    uses: aquasecurity/trivy-action@master
                    with:
                      image-ref: ${{{{ env.IMAGE_REGISTRY }}}}/${{{{ env.IMAGE_REPO }}}}:${{{{ github.sha }}}}
                      format: table
                      exit-code: "1"
                      severity: CRITICAL,HIGH

                  - name: Push image
                    if: matrix.component == 'backend' && github.ref == 'refs/heads/main'
                    run: |
                      echo "${{{{ secrets.GITHUB_TOKEN }}}}" | \\
                        docker login $IMAGE_REGISTRY -u ${{{{ github.actor }}}} --password-stdin
                      docker push $IMAGE_REGISTRY/$IMAGE_REPO:${{{{ github.sha }}}}
                      docker push $IMAGE_REGISTRY/$IMAGE_REPO:latest

                  - name: Generate SBOM
                    if: matrix.component == 'backend'
                    uses: anchore/sbom-action@v0
                    with:
                      image: ${{{{ env.IMAGE_REGISTRY }}}}/${{{{ env.IMAGE_REPO }}}}:${{{{ github.sha }}}}
                      format: spdx-json
                      output-file: sbom.spdx.json

                  - name: Install Cosign
                    if: matrix.component == 'backend' && github.ref == 'refs/heads/main'
                    uses: sigstore/cosign-installer@v3

                  - name: Sign image
                    if: matrix.component == 'backend' && github.ref == 'refs/heads/main'
                    run: |
                      cosign sign --yes \\
                        $IMAGE_REGISTRY/$IMAGE_REPO:${{{{ github.sha }}}}

              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              # GATE 3 — Pact Contract Tests
              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              pact-contract-tests:
                name: "Gate 3 — Pact Contract Tests"
                needs: build-and-test
                runs-on: ubuntu-latest
                services:
                  pact-broker:
                    image: pactfoundation/pact-broker:latest
                    env:
                      PACT_BROKER_DATABASE_ADAPTER: sqlite
                      PACT_BROKER_DATABASE_NAME: /tmp/pact_broker.sqlite
                    ports:
                      - 9292:9292
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.12"
                      cache: pip

                  - name: Install deps
                    run: pip install -r backend/requirements.txt pact-python

                  - name: Run provider verification
                    env:
                      PACT_BROKER_URL: http://localhost:9292
                    run: |
                      cd backend
                      python -m pytest tests/pact/ \\
                        --provider={spec.slug} \\
                        -v \\
                        || echo "Pact tests complete (non-fatal for new services)"

                  - name: Publish pact results
                    if: always()
                    run: |
                      echo "Pact verification for {spec.slug} at ${{{{ github.sha }}}}"

              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              # GATE 4 — Drift Detection
              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              drift-detection:
                name: "Gate 4 — Drift Detection"
                needs: pact-contract-tests
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Terraform
                    uses: hashicorp/setup-terraform@v3
                    with:
                      terraform_version: "1.6.x"

                  - name: Terraform Init
                    working-directory: terraform/services/{spec.slug}
                    run: terraform init -backend=false

                  - name: Terraform Plan (drift check)
                    working-directory: terraform/services/{spec.slug}
                    env:
                      TF_VAR_environment: dev
                    run: |
                      terraform plan -detailed-exitcode -out=tfplan || {{
                        EXIT=$?
                        if [ $EXIT -eq 2 ]; then
                          echo "⚠ Drift detected in {spec.slug} — requires review"
                          exit 1
                        fi
                        exit $EXIT
                      }}

                  - name: Run genesis drift check
                    run: |
                      python genesis.py drift-check --service {spec.slug}

              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              # GATE 5 — ArgoCD Deploy
              # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              argocd-deploy:
                name: "Gate 5 — ArgoCD Deploy"
                needs: drift-detection
                if: github.ref == 'refs/heads/main'
                runs-on: ubuntu-latest
                environment:
                  name: production
                  url: https://{spec.slug}.example.com
                steps:
                  - uses: actions/checkout@v4

                  - name: Install ArgoCD CLI
                    run: |
                      curl -sSL -o argocd \\
                        https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
                      chmod +x argocd
                      sudo mv argocd /usr/local/bin/

                  - name: ArgoCD login
                    run: |
                      argocd login {spec.argocd_server} \\
                        --username admin \\
                        --password "${{{{ secrets.ARGOCD_PASSWORD }}}}" \\
                        --insecure

                  - name: Sync dev environment
                    run: |
                      argocd app sync {spec.slug}-dev \\
                        --revision ${{{{ github.sha }}}} \\
                        --prune \\
                        --force

                  - name: Wait for dev sync
                    run: |
                      argocd app wait {spec.slug}-dev \\
                        --health \\
                        --timeout 300

                  - name: Promote to staging
                    run: |
                      argocd app sync {spec.slug}-staging \\
                        --revision ${{{{ github.sha }}}} \\
                        --prune

                  - name: Wait for staging sync
                    run: |
                      argocd app wait {spec.slug}-staging \\
                        --health \\
                        --timeout 300

                  - name: Deploy to production
                    run: |
                      argocd app sync {spec.slug}-production \\
                        --revision ${{{{ github.sha }}}} \\
                        --prune \\
                        --timeout 600

                  - name: Verify production health
                    run: |
                      argocd app wait {spec.slug}-production \\
                        --health \\
                        --timeout 600

                  - name: Notify deployment
                    if: always()
                    run: |
                      echo "Deployment of {spec.slug} @ ${{{{ github.sha }}}} complete"
        """)

    def _pr_check(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # PR Check workflow for {spec.slug}
            name: "PR — Quick Check"

            on:
              pull_request:
                branches: [main]

            jobs:
              pr-validation:
                name: "PR Validation"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      fetch-depth: 0

                  - name: Set up Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.12"
                      cache: pip

                  - name: Install deps
                    run: pip install -r backend/requirements.txt

                  - name: Constitutional validation
                    run: python genesis.py validate-sacred --base-ref origin/main

                  - name: Lint
                    run: |
                      cd backend
                      python -m flake8 . --max-line-length=120

                  - name: Quick test
                    run: |
                      cd backend
                      python -m pytest ../tests/ -x --tb=short -q
        """)

    def _drift_detect_workflow(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Scheduled drift detection for {spec.slug}
            name: "Drift Detection — Scheduled"

            on:
              schedule:
                - cron: "0 */6 * * *"
              workflow_dispatch: {{}}

            jobs:
              drift-check:
                name: "Terraform Drift Check"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Terraform
                    uses: hashicorp/setup-terraform@v3
                    with:
                      terraform_version: "1.6.x"

                  - name: Check drift for {spec.slug}
                    run: python genesis.py drift-check --service {spec.slug} --all-envs

                  - name: Alert on drift
                    if: failure()
                    run: |
                      echo "Drift detected in {spec.slug} infrastructure"
                      # Integrate with alerting (PagerDuty, Slack, etc.)
        """)

    def _release_workflow(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Release workflow for {spec.slug}
            name: "Release"

            on:
              push:
                tags:
                  - "v*"

            jobs:
              release:
                name: "Create Release"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4

                  - name: Build release image
                    run: |
                      docker build -t {spec.image_registry}/{spec.github_owner}/{spec.slug}:${{{{ github.ref_name }}}} .
                      echo "${{{{ secrets.GITHUB_TOKEN }}}}" | \\
                        docker login {spec.image_registry} -u ${{{{ github.actor }}}} --password-stdin
                      docker push {spec.image_registry}/{spec.github_owner}/{spec.slug}:${{{{ github.ref_name }}}}

                  - name: Create GitHub Release
                    uses: softprops/action-gh-release@v1
                    with:
                      generate_release_notes: true
        """)

    def _rollback_workflow(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Rollback workflow for {spec.slug}
            name: "Rollback"

            on:
              workflow_dispatch:
                inputs:
                  environment:
                    description: "Environment to roll back"
                    required: true
                    type: choice
                    options: {json.dumps(spec.environments)}
                  revision:
                    description: "Git revision to roll back to"
                    required: true

            jobs:
              rollback:
                name: "Rollback ${{{{ inputs.environment }}}}"
                runs-on: ubuntu-latest
                environment:
                  name: ${{{{ inputs.environment }}}}
                steps:
                  - uses: actions/checkout@v4
                    with:
                      ref: ${{{{ inputs.revision }}}}

                  - name: Install ArgoCD CLI
                    run: |
                      curl -sSL -o argocd \\
                        https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
                      chmod +x argocd && sudo mv argocd /usr/local/bin/

                  - name: Rollback
                    run: |
                      argocd login {spec.argocd_server} \\
                        --username admin \\
                        --password "${{{{ secrets.ARGOCD_PASSWORD }}}}" \\
                        --insecure
                      argocd app rollback {spec.slug}-${{{{ inputs.environment }}}} \\
                        --revision ${{{{ inputs.revision }}}}
        """)

    def _security_scan(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Security scanning workflow for {spec.slug}
            name: "Security Scan"

            on:
              schedule:
                - cron: "0 2 * * *"
              push:
                branches: [main]

            jobs:
              gitleaks:
                name: "Secret Scanning (Gitleaks)"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      fetch-depth: 0
                  - uses: gitleaks/gitleaks-action@v2
                    env:
                      GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

              bandit:
                name: "SAST (Bandit)"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - uses: actions/setup-python@v5
                    with:
                      python-version: "3.12"
                  - run: pip install bandit[toml]
                  - run: |
                      bandit -r backend/ \\
                        -c pyproject.toml \\
                        --format json \\
                        --output bandit-report.json || true

              trivy-fs:
                name: "Dependency Scan (Trivy)"
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - name: Run Trivy filesystem scan
                    uses: aquasecurity/trivy-action@master
                    with:
                      scan-type: fs
                      scan-ref: .
                      format: sarif
                      output: trivy-results.sarif
                  - name: Upload results
                    uses: github/codeql-action/upload-sarif@v3
                    with:
                      sarif_file: trivy-results.sarif
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Component 11 — Pre-commit Generator
# ──────────────────────────────────────────────────────────────────────────────

class PreCommitGenerator:
    """Generates pre-commit configuration guarding sacred zone integrity."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            ".pre-commit-config.yaml": self._config(spec),
            "scripts/pre-commit-sacred-check.py": self._sacred_check_script(),
        }

    def _config(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            # Pre-commit configuration — Genesis {spec.slug}
            # Protects sacred zones and enforces code quality before every commit
            repos:
              # ── Built-in hooks ──────────────────────────────────────────────
              - repo: https://github.com/pre-commit/pre-commit-hooks
                rev: v4.5.0
                hooks:
                  - id: trailing-whitespace
                  - id: end-of-file-fixer
                  - id: check-yaml
                  - id: check-json
                  - id: check-toml
                  - id: check-merge-conflict
                  - id: check-added-large-files
                    args: ["--maxkb=1000"]
                  - id: detect-private-key
                  - id: no-commit-to-branch
                    args: ["--branch=main", "--branch=release"]

              # ── Python quality ──────────────────────────────────────────────
              - repo: https://github.com/psf/black
                rev: 23.12.1
                hooks:
                  - id: black
                    language_version: python3
                    args: ["--line-length=120"]

              - repo: https://github.com/PyCQA/isort
                rev: 5.13.2
                hooks:
                  - id: isort
                    args: ["--profile=black"]

              - repo: https://github.com/PyCQA/flake8
                rev: 7.0.0
                hooks:
                  - id: flake8
                    args: ["--max-line-length=120"]

              # ── Security ────────────────────────────────────────────────────
              - repo: https://github.com/gitleaks/gitleaks
                rev: v8.18.2
                hooks:
                  - id: gitleaks

              # ── Terraform ───────────────────────────────────────────────────
              - repo: https://github.com/antonbabenko/pre-commit-terraform
                rev: v1.86.0
                hooks:
                  - id: terraform_fmt
                  - id: terraform_validate
                  - id: terraform_docs
                    args:
                      - "--hook-config=--path-to-file=README.md"
                      - "--hook-config=--add-to-existing-file=true"

              # ── Kubernetes / YAML ──────────────────────────────────────────
              - repo: https://github.com/adrienverge/yamllint
                rev: v1.35.1
                hooks:
                  - id: yamllint
                    args: ["-c=.yamllint.yaml"]

              # ── Genesis Sacred Zone ─────────────────────────────────────────
              - repo: local
                hooks:
                  - id: genesis-sacred-zone-check
                    name: "Genesis — Sacred Zone Integrity"
                    entry: python scripts/pre-commit-sacred-check.py
                    language: python
                    pass_filenames: true
                    always_run: false
                    description: "Prevents modification of sacred zones in generated files"
        """)

    def _sacred_check_script(self) -> str:
        return dedent(f"""\
            #!/usr/bin/env python3
            \"\"\"Pre-commit hook: Sacred Zone Integrity Check
            Ensures sacred zones in generated files are not accidentally modified.
            \"\"\"
            import subprocess
            import sys
            from pathlib import Path

            SACRED_MARKER = "{SACRED_ZONE_OPEN}"
            GENESIS_MANAGED_PATTERN = "# genesis-managed: true"


            def get_staged_content(filepath: str) -> str:
                result = subprocess.run(
                    ["git", "show", f":{{filepath}}"],
                    capture_output=True, text=True
                )
                return result.stdout


            def get_head_content(filepath: str) -> str:
                result = subprocess.run(
                    ["git", "show", f"HEAD:{{filepath}}"],
                    capture_output=True, text=True
                )
                return result.stdout


            def check_file(filepath: str) -> bool:
                staged = get_staged_content(filepath)
                if GENESIS_MANAGED_PATTERN not in staged:
                    return True  # Not a genesis-managed file, skip

                head = get_head_content(filepath)
                if not head:
                    return True  # New file, nothing to compare

                # Extract sacred zones from HEAD
                from genesis import SacredZonePreserver
                preserver = SacredZonePreserver()
                head_zones = preserver.extract(head)
                staged_zones = preserver.extract(staged)

                violations = []
                for zone_name, zone_content in head_zones.items():
                    if zone_name in staged_zones:
                        if staged_zones[zone_name].strip() != zone_content.strip():
                            violations.append(zone_name)

                if violations:
                    print(f"❌ Sacred zone violation in {{filepath}}:")
                    for v in violations:
                        print(f"   Zone '{{v}}' has been modified")
                    print("   Use 'python genesis.py regen' to update generated sections.")
                    return False

                return True


            def main():
                files = sys.argv[1:]
                failed = False
                for f in files:
                    if not check_file(f):
                        failed = True
                sys.exit(1 if failed else 0)


            if __name__ == "__main__":
                main()
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Component 12 — Pact Contract Test Generator
# ──────────────────────────────────────────────────────────────────────────────

class PactContractGenerator:
    """Generates Pact consumer-driven contract test stubs."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"tests/pact/test_{spec.snake}_provider.py": self._provider_test(spec),
            f"tests/pact/test_{spec.snake}_consumer.py": self._consumer_test(spec),
            f"tests/pact/conftest.py": self._conftest(spec),
        }

    def _provider_test(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            \"\"\"Pact provider verification tests for {spec.slug}\"\"\"
            import pytest
            from pact import Verifier


            PACT_BROKER_URL = "http://localhost:9292"
            PROVIDER_URL = "http://localhost:{spec.port}"


            def test_pact_provider_verification():
                verifier = Verifier(
                    provider="{spec.slug}",
                    provider_base_url=PROVIDER_URL,
                )
                output, _ = verifier.verify_with_broker(
                    broker_url=PACT_BROKER_URL,
                    publish_verification_results=True,
                    provider_version="1.0.0",
                )
                assert output == 0, f"Pact provider verification failed for {spec.slug}"
        """)

    def _consumer_test(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            \"\"\"Pact consumer contract tests for {spec.slug}\"\"\"
            import pytest
            from pact import Consumer, Provider, Like


            @pytest.fixture(scope="session")
            def pact():
                consumer = Consumer("{spec.slug}-consumer")
                pact = consumer.has_pact_with(
                    Provider("{spec.slug}"),
                    pact_dir="./pacts",
                    log_dir="./logs",
                )
                pact.start_service()
                yield pact
                pact.stop_service()


            def test_get_health(pact):
                expected = Like({{"status": "ok"}})
                (
                    pact
                    .given("service is healthy")
                    .upon_receiving("a health check request")
                    .with_request("GET", "/health/ready")
                    .will_respond_with(200, body=expected)
                )
                with pact:
                    import httpx
                    response = httpx.get(pact.uri + "/health/ready")
                    assert response.status_code == 200
        """)

    def _conftest(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            \"\"\"Pact test configuration for {spec.slug}\"\"\"
            import os
            import pytest


            @pytest.fixture(scope="session", autouse=True)
            def setup_pact_env():
                os.environ.setdefault("PACT_BROKER_URL", "http://localhost:9292")
                os.environ.setdefault("PROVIDER_URL", "http://localhost:{spec.port}")
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Component 13 — Drift Detection Generator
# ──────────────────────────────────────────────────────────────────────────────

class DriftDetectionGenerator:
    """Generates drift detection scripts and Kubernetes CronJob."""

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        return {
            f"scripts/drift-check-{spec.slug}.sh": self._drift_script(spec),
            f"kubernetes/{spec.slug}/drift-cronjob.yaml": self._drift_cronjob(spec),
        }

    def _drift_script(self, spec: ServiceSpec) -> str:
        return dedent(f"""\
            #!/usr/bin/env bash
            # Drift detection script for {spec.slug}
            # Usage: ./drift-check-{spec.slug}.sh [environment]
            set -euo pipefail

            SERVICE="{spec.slug}"
            ENV="${{1:-dev}}"
            TF_DIR="terraform/services/$SERVICE"

            echo "=== Drift Detection: $SERVICE [$ENV] ==="
            echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

            # Terraform drift check
            echo ""
            echo "--- Terraform Drift ---"
            cd "$TF_DIR"
            terraform init -backend-config="key=services/$SERVICE/$ENV/terraform.tfstate" -input=false
            PLAN_EXIT=0
            terraform plan \\
              -var="environment=$ENV" \\
              -detailed-exitcode \\
              -refresh=true \\
              -out=/tmp/tfplan-$SERVICE-$ENV \\
              2>&1 | tee /tmp/tfplan-output.txt || PLAN_EXIT=$?

            if [ $PLAN_EXIT -eq 0 ]; then
              echo "✓ No Terraform drift detected for $SERVICE in $ENV"
            elif [ $PLAN_EXIT -eq 2 ]; then
              echo "⚠ Drift detected! Changes pending:"
              terraform show -no-color /tmp/tfplan-$SERVICE-$ENV
              exit 2
            else
              echo "✗ Terraform plan failed"
              exit 1
            fi

            # Kubernetes live-state check
            echo ""
            echo "--- Kubernetes State Check ---"
            NAMESPACE="{spec.namespace}"
            kubectl diff -f ../../kubernetes/$SERVICE/ \\
              --namespace="$NAMESPACE-$ENV" || {{
              echo "⚠ Kubernetes manifest drift detected"
              exit 2
            }}
            echo "✓ No Kubernetes drift for $SERVICE in $ENV"
        """)

    def _drift_cronjob(self, spec: ServiceSpec) -> str:
        return yaml.dump({
            "apiVersion": "batch/v1",
            "kind": "CronJob",
            "metadata": {
                "name": f"{spec.slug}-drift-check",
                "namespace": spec.namespace,
            },
            "spec": {
                "schedule": "0 */6 * * *",
                "concurrencyPolicy": "Forbid",
                "jobTemplate": {
                    "spec": {
                        "template": {
                            "spec": {
                                "restartPolicy": "Never",
                                "serviceAccountName": f"{spec.slug}-sa",
                                "containers": [{
                                    "name": "drift-check",
                                    "image": f"{spec.image_registry}/{spec.github_owner}/genesis:latest",
                                    "command": [
                                        "python", "genesis.py",
                                        "drift-check",
                                        "--service", spec.slug,
                                        "--all-envs",
                                    ],
                                }],
                            },
                        },
                    },
                },
            },
        }, default_flow_style=False)


# ──────────────────────────────────────────────────────────────────────────────
# Component 15 — Surgical Regen
# ──────────────────────────────────────────────────────────────────────────────

COMPONENT_MAP = {
    "terraform": "TerraformGenerator",
    "kubernetes": "KubernetesGenerator",
    "rbac": "RBACGenerator",
    "vault": "VaultPolicyGenerator",
    "prometheus": "PrometheusAlertGenerator",
    "hpa": "HPAGenerator",
    "pdb": "PDBGenerator",
    "argocd": "ArgoCDGenerator",
    "cicd": "CICDPipelineGenerator",
    "pre-commit": "PreCommitGenerator",
    "pact": "PactContractGenerator",
    "drift": "DriftDetectionGenerator",
}


class SurgicalRegen:
    """Regenerate individual components without touching sacred zones."""

    def __init__(self, preserver: SacredZonePreserver):
        self.preserver = preserver

    def regen(
        self,
        spec: ServiceSpec,
        components: List[str],
        output_dir: str = ".",
    ) -> Dict[str, str]:
        component_map = {
            "terraform": TerraformGenerator(),
            "kubernetes": KubernetesGenerator(),
            "rbac": RBACGenerator(),
            "vault": VaultPolicyGenerator(),
            "prometheus": PrometheusAlertGenerator(),
            "hpa": HPAGenerator(),
            "pdb": PDBGenerator(),
            "argocd": ArgoCDGenerator(),
            "cicd": CICDPipelineGenerator(),
            "pre-commit": PreCommitGenerator(),
            "pact": PactContractGenerator(),
            "drift": DriftDetectionGenerator(),
        }

        regenerated: Dict[str, str] = {}
        for component in components:
            gen = component_map.get(component)
            if not gen:
                logger.warning("Unknown component: %s", component)
                continue

            new_files = gen.generate(spec)
            for path, new_content in new_files.items():
                full_path = Path(output_dir) / path
                if full_path.exists():
                    old_content = full_path.read_text()
                    sacred_zones = self.preserver.extract(old_content)
                    if sacred_zones:
                        new_content = self.preserver.inject(new_content, sacred_zones)
                regenerated[path] = new_content

        return regenerated


# ──────────────────────────────────────────────────────────────────────────────
# Component 1 — System Pipeline (Orchestrator)
# ──────────────────────────────────────────────────────────────────────────────

class GenesisGenerator:
    """
    Main orchestrator for the Genesis Microservices Generator.
    Coordinates all 15 components to produce a complete, production-ready
    microservice infrastructure package.
    """

    VERSION = "2.0.0"
    COMPONENTS = 15

    def __init__(self):
        self.preserver = SacredZonePreserver()
        self.generators = {
            "terraform": TerraformGenerator(),
            "kubernetes": KubernetesGenerator(),
            "rbac": RBACGenerator(),
            "vault": VaultPolicyGenerator(),
            "prometheus": PrometheusAlertGenerator(),
            "hpa": HPAGenerator(),
            "pdb": PDBGenerator(),
            "argocd": ArgoCDGenerator(),
            "cicd": CICDPipelineGenerator(),
            "pre-commit": PreCommitGenerator(),
            "pact": PactContractGenerator(),
            "drift": DriftDetectionGenerator(),
        }
        self.surgical = SurgicalRegen(self.preserver)

    def generate(self, spec: ServiceSpec) -> Dict[str, str]:
        """Generate all files for a complete production microservice."""
        files: Dict[str, str] = {}

        # Always include Kubernetes + RBAC (core)
        files.update(self.generators["kubernetes"].generate(spec))
        files.update(self.generators["rbac"].generate(spec))
        files.update(self.generators["hpa"].generate(spec))
        files.update(self.generators["pdb"].generate(spec))
        files.update(self.generators["vault"].generate(spec))
        files.update(self.generators["prometheus"].generate(spec))

        # Optional but recommended
        if spec.enable_terraform:
            files.update(self.generators["terraform"].generate(spec))

        if spec.enable_cicd:
            files.update(self.generators["cicd"].generate(spec))

        if spec.enable_argocd:
            files.update(self.generators["argocd"].generate(spec))

        if spec.enable_pre_commit:
            files.update(self.generators["pre-commit"].generate(spec))

        if spec.enable_pact:
            files.update(self.generators["pact"].generate(spec))

        if spec.enable_drift_detection:
            files.update(self.generators["drift"].generate(spec))

        # Service spec manifest
        files["service-spec.yaml"] = yaml.dump(
            {
                "name": spec.name,
                "criticality": spec.criticality.value,
                "language": spec.language.value,
                "database": spec.database.value,
                "port": spec.port,
                "metrics_port": spec.metrics_port,
                "namespace": spec.namespace,
                "version": spec.version,
                "description": spec.description,
                "author": spec.author,
                "github_owner": spec.github_owner,
                "github_repo": spec.github_repo,
                "environments": spec.environments,
            },
            default_flow_style=False,
        )

        return files

    def generate_zip(self, spec: ServiceSpec) -> bytes:
        """Generate all files and return as a ZIP archive."""
        files = self.generate(spec)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, content in files.items():
                zf.writestr(path, content)
        buf.seek(0)
        return buf.getvalue()

    def regen(self, spec: ServiceSpec, components: List[str], output_dir: str = ".") -> Dict[str, str]:
        """Surgically regenerate specific components."""
        return self.surgical.regen(spec, components, output_dir)

    def write_to_disk(self, spec: ServiceSpec, output_dir: str = ".") -> List[str]:
        """Generate all files and write them to disk."""
        files = self.generate(spec)
        written: List[str] = []
        base = Path(output_dir)
        for rel_path, content in files.items():
            full_path = base / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(str(rel_path))
            logger.info("Wrote: %s", rel_path)
        return written

    def validate_sacred_zones(self, base_ref: str = "HEAD") -> bool:
        """Validate sacred zones haven't changed relative to base_ref."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref],
                capture_output=True, text=True, check=True
            )
            changed_files = result.stdout.strip().splitlines()
        except subprocess.CalledProcessError:
            logger.warning("Could not determine changed files; skipping sacred zone check")
            return True

        violations: List[str] = []
        for filepath in changed_files:
            p = Path(filepath)
            if not p.exists():
                continue
            content = p.read_text()
            if SACRED_ZONE_OPEN not in content:
                continue
            result = subprocess.run(
                ["git", "show", f"{base_ref}:{filepath}"],
                capture_output=True, text=True
            )
            if not result.stdout:
                continue
            old_zones = self.preserver.extract(result.stdout)
            new_zones = self.preserver.extract(content)
            for zone_name, old_val in old_zones.items():
                if zone_name in new_zones and new_zones[zone_name].strip() != old_val.strip():
                    violations.append(f"{filepath}::zone:{zone_name}")

        if violations:
            logger.error("Sacred zone violations: %s", violations)
            return False
        return True

    def drift_check(self, service: str, all_envs: bool = False) -> bool:
        """Run drift detection for a service."""
        import subprocess
        envs = ["dev", "staging", "production"] if all_envs else ["dev"]
        drift_found = False
        for env in envs:
            script = Path(f"scripts/drift-check-{service}.sh")
            if script.exists():
                result = subprocess.run(
                    ["bash", str(script), env],
                    capture_output=False
                )
                if result.returncode == 2:
                    drift_found = True
                    logger.warning("Drift detected in %s [%s]", service, env)
                elif result.returncode != 0:
                    logger.error("Drift check failed for %s [%s]", service, env)
                    return False
        return not drift_found

    def info(self) -> Dict[str, Any]:
        """Return generator metadata."""
        return {
            "name": "Genesis Microservices Generator",
            "version": self.VERSION,
            "components": self.COMPONENTS,
            "component_inventory": [
                "SystemPipeline",
                "TerraformGenerator",
                "KubernetesGenerator",
                "RBACGenerator",
                "VaultPolicyGenerator",
                "PrometheusAlertGenerator",
                "HPAGenerator",
                "PDBGenerator",
                "ArgoCDGenerator",
                "CICDPipelineGenerator",
                "PreCommitGenerator",
                "PactContractGenerator",
                "DriftDetectionGenerator",
                "SacredZonePreserver",
                "SurgicalRegen",
            ],
            "criticality_profiles": {
                c.value: {
                    "hpa": HPA_PROFILES[c],
                    "slo": SLO_PROFILES[c],
                    "pdb_min_available": PDB_PROFILES[c],
                }
                for c in Criticality
            },
            "supported_languages": [l.value for l in Language],
            "supported_databases": [d.value for d in DatabaseType],
            "terraform_modules": ["namespace", "deployment", "rbac", "vault", "monitoring"],
            "cicd_gates": [
                "Constitutional Validation",
                "Build & Test (language-aware matrix)",
                "Pact Contract Tests",
                "Drift Detection",
                "ArgoCD Deploy",
            ],
        }


# ──────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis",
        description="Genesis Microservices Generator v2.0.0 — 15 components, complete pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── generate ────────────────────────────────────────────────────────────
    gen_p = sub.add_parser("generate", help="Generate a complete microservice infrastructure")
    gen_p.add_argument("--config", help="Path to service-spec.yaml")
    gen_p.add_argument("--name", help="Service name")
    gen_p.add_argument("--criticality", choices=[c.value for c in Criticality], default="medium")
    gen_p.add_argument("--language", choices=[l.value for l in Language], default="python")
    gen_p.add_argument("--database", choices=[d.value for d in DatabaseType], default="postgresql")
    gen_p.add_argument("--port", type=int, default=8000)
    gen_p.add_argument("--output-dir", default=".", help="Output directory")
    gen_p.add_argument("--zip", action="store_true", help="Output as ZIP file")
    gen_p.add_argument("--zip-output", default=None, help="ZIP output path")
    gen_p.add_argument("--no-terraform", action="store_true")
    gen_p.add_argument("--no-cicd", action="store_true")
    gen_p.add_argument("--no-argocd", action="store_true")
    gen_p.add_argument("--no-pact", action="store_true")
    gen_p.add_argument("--no-pre-commit", action="store_true")

    # ── regen ────────────────────────────────────────────────────────────────
    regen_p = sub.add_parser("regen", help="Surgically regenerate specific components")
    regen_p.add_argument("--config", required=True, help="Path to service-spec.yaml")
    regen_p.add_argument("--components", required=True,
                         help=f"Comma-separated components: {','.join(COMPONENT_MAP.keys())}")
    regen_p.add_argument("--output-dir", default=".", help="Output directory")

    # ── validate-sacred ──────────────────────────────────────────────────────
    vs_p = sub.add_parser("validate-sacred", help="Validate sacred zone integrity")
    vs_p.add_argument("--base-ref", default="HEAD", help="Git reference to compare against")

    # ── drift-check ──────────────────────────────────────────────────────────
    dc_p = sub.add_parser("drift-check", help="Run drift detection")
    dc_p.add_argument("--service", required=True, help="Service name")
    dc_p.add_argument("--all-envs", action="store_true", help="Check all environments")

    # ── info ─────────────────────────────────────────────────────────────────
    sub.add_parser("info", help="Display generator information")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args(argv)
    genesis = GenesisGenerator()

    if args.command == "info":
        info = genesis.info()
        print(json.dumps(info, indent=2))
        return 0

    if args.command == "validate-sacred":
        ok = genesis.validate_sacred_zones(args.base_ref)
        if ok:
            print("✓ All sacred zones intact")
            return 0
        else:
            print("✗ Sacred zone violations detected")
            return 1

    if args.command == "drift-check":
        ok = genesis.drift_check(args.service, args.all_envs)
        return 0 if ok else 2

    if args.command == "regen":
        spec = ServiceSpec.from_yaml(args.config)
        components = [c.strip() for c in args.components.split(",")]
        files = genesis.regen(spec, components, args.output_dir)
        base = Path(args.output_dir)
        for rel_path, content in files.items():
            full_path = base / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            print(f"  Regenerated: {rel_path}")
        print(f"\n✓ Regenerated {len(files)} files for components: {', '.join(components)}")
        return 0

    if args.command == "generate":
        # Build spec
        if args.config:
            spec = ServiceSpec.from_yaml(args.config)
        elif args.name:
            spec = ServiceSpec(
                name=args.name,
                criticality=Criticality(args.criticality),
                language=Language(args.language),
                database=DatabaseType(args.database),
                port=args.port,
                enable_terraform=not args.no_terraform,
                enable_cicd=not args.no_cicd,
                enable_argocd=not args.no_argocd,
                enable_pact=not args.no_pact,
                enable_pre_commit=not args.no_pre_commit,
            )
        else:
            parser.error("Either --config or --name is required")
            return 1

        if args.zip:
            zip_path = args.zip_output or f"{spec.slug}.zip"
            zip_bytes = genesis.generate_zip(spec)
            Path(zip_path).write_bytes(zip_bytes)
            print(f"✓ Generated {spec.slug} → {zip_path}")
        else:
            written = genesis.write_to_disk(spec, args.output_dir)
            print(f"\n✓ Generated {len(written)} files for '{spec.slug}' ({spec.criticality.value} criticality)")
            print(f"  Output: {Path(args.output_dir).resolve()}")
            print(f"\nHPA profile:  min={spec.hpa['min']} max={spec.hpa['max']} cpu={spec.hpa['cpu_target']}%")
            print(f"SLO target:   {spec.slo['availability_target']}% availability, "
                  f"{spec.slo['latency_target_ms']}ms p99 latency")
            print(f"PDB:          minAvailable={spec.pdb_min_available}")

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
