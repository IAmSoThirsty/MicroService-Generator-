"""
Core microservice generator engine
Delegates generation to the canonical Genesis Microservices Generator (genesis.py).
"""
import io
import sys
import zipfile
from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader
from .models import MicroserviceConfig, Language
import logging

logger = logging.getLogger(__name__)

# Make the repo root importable so that genesis.py can be used as a module
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from genesis import (
        GenesisGenerator,
        ServiceSpec,
        Criticality,
        Language as GenesisLanguage,
        DatabaseType as GenesisDatabaseType,
    )
    _GENESIS_AVAILABLE = True
except ImportError:
    _GENESIS_AVAILABLE = False
    logger.warning("genesis.py not found; falling back to template-based generator")


def _map_language(lang: Language) -> "GenesisLanguage":
    """Map backend Language enum to genesis Language enum."""
    mapping = {
        Language.PYTHON_FASTAPI: GenesisLanguage.PYTHON,
        Language.GO_FIBER: GenesisLanguage.GO,
        Language.NODEJS_NESTJS: GenesisLanguage.NODEJS,
        Language.RUST_ACTIX: GenesisLanguage.RUST,
    }
    return mapping.get(lang, GenesisLanguage.PYTHON)


def _map_database(db_type) -> "GenesisDatabaseType":
    """Map backend DatabaseType to genesis DatabaseType."""
    from .models import DatabaseType
    mapping = {
        DatabaseType.POSTGRESQL: GenesisDatabaseType.POSTGRESQL,
        DatabaseType.MONGODB: GenesisDatabaseType.MONGODB,
        DatabaseType.REDIS: GenesisDatabaseType.REDIS,
        DatabaseType.IN_MEMORY: GenesisDatabaseType.NONE,
    }
    return mapping.get(db_type, GenesisDatabaseType.POSTGRESQL)


class MicroserviceGenerator:
    """
    Main generator class for creating production-ready microservices.
    Delegates to the Genesis Microservices Generator (genesis.py) when available,
    falling back to the Jinja2 template-based generator otherwise.
    """

    def __init__(self):
        self.templates_dir = Path(__file__).parent / "templates"
        if _GENESIS_AVAILABLE:
            self._genesis = GenesisGenerator()
            logger.info("Genesis generator active (v%s, %d components)",
                        self._genesis.VERSION, self._genesis.COMPONENTS)
        else:
            self._genesis = None
        self._legacy_generators = {
            Language.PYTHON_FASTAPI: PythonFastAPIGenerator(self.templates_dir),
        }

    def generate(self, config: MicroserviceConfig) -> bytes:
        """
        Generate a complete microservice based on configuration.
        Returns ZIP file as bytes.

        Uses the Genesis generator (genesis.py) when available; falls back
        to the Jinja2 template-based generator for unsupported configurations.
        """
        logger.info("Generating microservice: %s", config.metadata.name)

        if self._genesis is not None:
            spec = ServiceSpec(
                name=config.metadata.name,
                language=_map_language(config.language),
                database=_map_database(config.database.database_type),
                port=config.metadata.port,
                version=config.metadata.version,
                description=config.metadata.description,
                author=config.metadata.author,
                enable_terraform=True,
                enable_cicd=(config.cicd.platform.value in ("github_actions", "both")),
                enable_argocd=True,
                enable_pact=True,
                enable_pre_commit=True,
                enable_drift_detection=True,
                criticality=Criticality.HIGH if config.kubernetes.max_replicas >= 10 else Criticality.MEDIUM,
            )
            logger.info("Delegating to Genesis generator v%s", self._genesis.VERSION)
            return self._genesis.generate_zip(spec)

        # Legacy Jinja2 fallback
        generator = self._legacy_generators.get(config.language)
        if not generator:
            raise ValueError(f"Unsupported language: {config.language}")

        logger.info("Using legacy template generator for: %s", config.language)
        files = generator.generate_all(config)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_path, content in files.items():
                zip_file.writestr(file_path, content)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def info(self) -> Dict[str, Any]:
        """Return generator capability information."""
        if self._genesis is not None:
            return self._genesis.info()
        return {
            "name": "Maximal Microservice Generator (Legacy)",
            "version": "1.0.0",
            "note": "genesis.py not found; operating in legacy mode",
        }


class BaseGenerator:
    """Base class for language-specific generators"""
    
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.env = None
    
    def setup_jinja_env(self, template_subdir: str):
        """Setup Jinja2 environment"""
        template_path = self.templates_dir / template_subdir
        self.env = Environment(
            loader=FileSystemLoader(str(template_path)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        # Add custom filters
        self.env.filters['snake_case'] = self.to_snake_case
        self.env.filters['pascal_case'] = self.to_pascal_case
        self.env.filters['kebab_case'] = self.to_kebab_case
    
    @staticmethod
    def to_snake_case(text: str) -> str:
        """Convert to snake_case"""
        return text.lower().replace('-', '_').replace(' ', '_')
    
    @staticmethod
    def to_pascal_case(text: str) -> str:
        """Convert to PascalCase"""
        return ''.join(word.capitalize() for word in text.replace('-', ' ').replace('_', ' ').split())
    
    @staticmethod
    def to_kebab_case(text: str) -> str:
        """Convert to kebab-case"""
        return text.lower().replace('_', '-').replace(' ', '-')
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a template with context"""
        template = self.env.get_template(template_name)
        return template.render(**context)
    
    def generate_all(self, config: MicroserviceConfig) -> Dict[str, str]:
        """Generate all files for the microservice"""
        raise NotImplementedError("Subclasses must implement generate_all()")


class PythonFastAPIGenerator(BaseGenerator):
    """Generator for Python + FastAPI microservices"""
    
    def __init__(self, templates_dir: Path):
        super().__init__(templates_dir)
        self.setup_jinja_env("python_fastapi")
    
    def generate_all(self, config: MicroserviceConfig) -> Dict[str, str]:
        """Generate all files for Python/FastAPI microservice"""
        files = {}
        service_name = config.metadata.name
        context = self.build_context(config)
        
        # Application files
        files.update(self.generate_app_files(service_name, context))
        
        # CI/CD files
        files.update(self.generate_cicd_files(service_name, context))
        
        # Database files
        if config.database.enable_migrations:
            files.update(self.generate_database_files(service_name, context))
        
        # Kubernetes files
        if config.deployment_target.value in ["kubernetes", "both"]:
            files.update(self.generate_kubernetes_files(service_name, context))
        
        # Docker files
        files.update(self.generate_docker_files(service_name, context))
        
        # Documentation files
        files.update(self.generate_documentation_files(service_name, context))
        
        # Configuration files
        files.update(self.generate_config_files(service_name, context))
        
        return files
    
    def build_context(self, config: MicroserviceConfig) -> Dict[str, Any]:
        """Build template context from configuration"""
        return {
            "config": config,
            "service_name": config.metadata.name,
            "service_name_snake": self.to_snake_case(config.metadata.name),
            "service_name_pascal": self.to_pascal_case(config.metadata.name),
            "version": config.metadata.version,
            "description": config.metadata.description,
            "author": config.metadata.author,
            "port": config.metadata.port,
            "api_prefix": config.metadata.api_prefix,
        }
    
    def generate_app_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate application source files"""
        files = {}
        base_path = f"{service_name}/app"
        
        templates = [
            ("main.py.j2", f"{base_path}/main.py"),
            ("config.py.j2", f"{base_path}/config.py"),
            ("models.py.j2", f"{base_path}/models.py"),
            ("routes.py.j2", f"{base_path}/routes.py"),
            ("services.py.j2", f"{base_path}/services.py"),
            ("repository.py.j2", f"{base_path}/repository.py"),
            ("errors.py.j2", f"{base_path}/errors.py"),
            ("middleware.py.j2", f"{base_path}/middleware.py"),
            ("security.py.j2", f"{base_path}/security.py"),
            ("metrics.py.j2", f"{base_path}/metrics.py"),
            ("logging_config.py.j2", f"{base_path}/logging_config.py"),
            ("health.py.j2", f"{base_path}/health.py"),
            ("__init__.py.j2", f"{base_path}/__init__.py"),
        ]
        
        for template_name, file_path in templates:
            files[file_path] = self.render_template(template_name, context)
        
        # Tests
        files.update(self.generate_test_files(service_name, context))
        
        return files
    
    def generate_test_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate test files"""
        files = {}
        base_path = f"{service_name}/tests"
        
        templates = [
            ("test_main.py.j2", f"{base_path}/test_main.py"),
            ("test_routes.py.j2", f"{base_path}/test_routes.py"),
            ("test_services.py.j2", f"{base_path}/test_services.py"),
            ("test_security.py.j2", f"{base_path}/test_security.py"),
            ("conftest.py.j2", f"{base_path}/conftest.py"),
            ("__init__.py.j2", f"{base_path}/__init__.py"),
        ]
        
        for template_name, file_path in templates:
            files[file_path] = self.render_template(template_name, context)
        
        return files
    
    def generate_cicd_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate CI/CD pipeline files"""
        files = {}
        config = context["config"]
        
        if config.cicd.platform.value in ["github_actions", "both"]:
            files[f"{service_name}/.github/workflows/ci.yml"] = self.render_template("github_ci.yml.j2", context)
            files[f"{service_name}/.github/workflows/cd.yml"] = self.render_template("github_cd.yml.j2", context)
        
        if config.cicd.platform.value in ["gitlab_ci", "both"]:
            files[f"{service_name}/.gitlab-ci.yml"] = self.render_template("gitlab_ci.yml.j2", context)
        
        return files
    
    def generate_database_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate database migration and management files"""
        files = {}
        base_path = f"{service_name}/database"
        
        templates = [
            ("migrations_init.py.j2", f"{base_path}/migrations/__init__.py"),
            ("migration_001.py.j2", f"{base_path}/migrations/001_initial_schema.py"),
            ("backup.sh.j2", f"{base_path}/scripts/backup.sh"),
            ("restore.sh.j2", f"{base_path}/scripts/restore.sh"),
            ("integrity_check.py.j2", f"{base_path}/scripts/integrity_check.py"),
            ("rollback.py.j2", f"{base_path}/scripts/rollback.py"),
        ]
        
        for template_name, file_path in templates:
            content = self.render_template(template_name, context)
            files[file_path] = content
            # Make scripts executable
            if file_path.endswith('.sh'):
                files[file_path] = content
        
        return files
    
    def generate_kubernetes_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate Kubernetes manifests"""
        files = {}
        base_path = f"{service_name}/kubernetes"
        
        templates = [
            ("deployment.yaml.j2", f"{base_path}/deployment.yaml"),
            ("service.yaml.j2", f"{base_path}/service.yaml"),
            ("configmap.yaml.j2", f"{base_path}/configmap.yaml"),
            ("secret.yaml.j2", f"{base_path}/secret.yaml"),
            ("hpa.yaml.j2", f"{base_path}/hpa.yaml"),
            ("pdb.yaml.j2", f"{base_path}/pdb.yaml"),
            ("network_policy.yaml.j2", f"{base_path}/network-policy.yaml"),
            ("service_monitor.yaml.j2", f"{base_path}/service-monitor.yaml"),
        ]
        
        for template_name, file_path in templates:
            files[file_path] = self.render_template(template_name, context)
        
        return files
    
    def generate_docker_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate Docker files"""
        files = {}
        
        files[f"{service_name}/Dockerfile"] = self.render_template("Dockerfile.j2", context)
        files[f"{service_name}/.dockerignore"] = self.render_template("dockerignore.j2", context)
        
        return files
    
    def generate_documentation_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate documentation files"""
        files = {}
        base_path = f"{service_name}/docs"
        
        templates = [
            ("README.md.j2", f"{service_name}/README.md"),
            ("API.md.j2", f"{base_path}/API.md"),
            ("ARCHITECTURE.md.j2", f"{base_path}/ARCHITECTURE.md"),
            ("FAILURE_MODES.md.j2", f"{base_path}/FAILURE_MODES.md"),
            ("RUNBOOK.md.j2", f"{base_path}/RUNBOOK.md"),
            ("PERFORMANCE.md.j2", f"{base_path}/PERFORMANCE.md"),
            ("SECURITY.md.j2", f"{base_path}/SECURITY.md"),
        ]
        
        for template_name, file_path in templates:
            files[file_path] = self.render_template(template_name, context)
        
        return files
    
    def generate_config_files(self, service_name: str, context: Dict) -> Dict[str, str]:
        """Generate configuration files"""
        files = {}
        
        templates = [
            ("requirements.txt.j2", f"{service_name}/requirements.txt"),
            ("pyproject.toml.j2", f"{service_name}/pyproject.toml"),
            (".env.example.j2", f"{service_name}/.env.example"),
            ("setup.py.j2", f"{service_name}/setup.py"),
            (".gitignore.j2", f"{service_name}/.gitignore"),
        ]
        
        for template_name, file_path in templates:
            files[file_path] = self.render_template(template_name, context)
        
        return files
