"""
Configuration models for microservice generation
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from enum import Enum


class Language(str, Enum):
    PYTHON_FASTAPI = "python_fastapi"
    GO_FIBER = "go_fiber"
    NODEJS_NESTJS = "nodejs_nestjs"
    RUST_ACTIX = "rust_actix"


class DatabaseType(str, Enum):
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    REDIS = "redis"
    IN_MEMORY = "in_memory"


class AuthType(str, Enum):
    JWT = "jwt"
    API_KEY = "api_key"
    BOTH = "both"


class CICDPlatform(str, Enum):
    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    BOTH = "both"


class DeploymentTarget(str, Enum):
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    BOTH = "both"


class SecurityConfig(BaseModel):
    """Security configuration"""
    auth_type: AuthType = AuthType.API_KEY
    enable_rbac: bool = True
    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 200
    enable_cors: bool = True
    cors_origins: List[str] = ["*"]
    jwt_expiry_hours: int = 24
    api_key_header: str = "X-API-Key"


class ObservabilityConfig(BaseModel):
    """Observability configuration"""
    enable_prometheus: bool = True
    enable_structured_logging: bool = True
    enable_tracing: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    metrics_port: int = 9090


class DatabaseConfig(BaseModel):
    """Database configuration"""
    database_type: DatabaseType = DatabaseType.POSTGRESQL
    enable_migrations: bool = True
    enable_backup_scripts: bool = True
    enable_integrity_checks: bool = True
    connection_pool_size: int = 20
    connection_timeout: int = 30


class CICDConfig(BaseModel):
    """CI/CD configuration"""
    platform: CICDPlatform = CICDPlatform.GITHUB_ACTIONS
    enable_sbom: bool = True
    enable_signing: bool = True
    enable_security_scan: bool = True
    coverage_threshold: int = 85
    enable_fuzz_testing: bool = True
    environments: List[str] = ["dev", "staging", "production"]


class KubernetesConfig(BaseModel):
    """Kubernetes configuration"""
    enable_hpa: bool = True
    enable_pdb: bool = True
    enable_network_policy: bool = True
    enable_service_monitor: bool = True
    min_replicas: int = 2
    max_replicas: int = 10
    target_cpu_utilization: int = 70
    resource_requests_cpu: str = "100m"
    resource_requests_memory: str = "128Mi"
    resource_limits_cpu: str = "500m"
    resource_limits_memory: str = "512Mi"


class ServiceMetadata(BaseModel):
    """Service metadata"""
    name: str = Field(..., description="Service name (lowercase, hyphen-separated)")
    version: str = Field(default="1.0.0", description="Semantic version")
    description: str = Field(..., description="Service description")
    author: str = Field(default="Your Team", description="Author or team name")
    port: int = Field(default=8000, description="Service port")
    api_prefix: str = Field(default="/api/v1", description="API route prefix")


class MicroserviceConfig(BaseModel):
    """Complete microservice configuration"""
    metadata: ServiceMetadata
    language: Language = Language.PYTHON_FASTAPI
    database: DatabaseConfig = DatabaseConfig()
    security: SecurityConfig = SecurityConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
    cicd: CICDConfig = CICDConfig()
    kubernetes: KubernetesConfig = KubernetesConfig()
    deployment_target: DeploymentTarget = DeploymentTarget.BOTH
    enable_helm: bool = False
    enable_api_docs: bool = True
    enable_health_checks: bool = True
    enable_graceful_shutdown: bool = True
