"""
Tests for the Genesis Microservices Generator (genesis.py)
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest

# Ensure genesis.py is importable from repo root
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from genesis import (
    ArgoCDGenerator,
    CICDPipelineGenerator,
    Criticality,
    DatabaseType,
    DriftDetectionGenerator,
    GenesisGenerator,
    HPAGenerator,
    HPA_PROFILES,
    Language,
    PDBGenerator,
    PDB_PROFILES,
    PactContractGenerator,
    PreCommitGenerator,
    PrometheusAlertGenerator,
    RBACGenerator,
    SLO_PROFILES,
    SacredZonePreserver,
    ServiceSpec,
    SurgicalRegen,
    TerraformGenerator,
    VaultPolicyGenerator,
    KubernetesGenerator,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def spec_medium():
    return ServiceSpec(
        name="test-service",
        criticality=Criticality.MEDIUM,
        language=Language.PYTHON,
        database=DatabaseType.POSTGRESQL,
        port=8000,
    )


@pytest.fixture
def spec_critical():
    return ServiceSpec(
        name="payment-service",
        criticality=Criticality.CRITICAL,
        language=Language.PYTHON,
        database=DatabaseType.POSTGRESQL,
        port=8080,
    )


@pytest.fixture
def genesis():
    return GenesisGenerator()


# ─── ServiceSpec Tests ────────────────────────────────────────────────────────

class TestServiceSpec:
    def test_slug(self):
        s = ServiceSpec(name="My Service")
        assert s.slug == "my-service"

    def test_snake(self):
        s = ServiceSpec(name="my-service")
        assert s.snake == "my_service"

    def test_pascal(self):
        s = ServiceSpec(name="my-service")
        assert s.pascal == "MyService"

    def test_default_namespace(self):
        s = ServiceSpec(name="my-service")
        assert s.namespace == "my-service"

    def test_default_description(self):
        s = ServiceSpec(name="foo")
        assert "foo" in s.description

    def test_hpa_profiles_by_criticality(self):
        for crit in Criticality:
            s = ServiceSpec(name="svc", criticality=crit)
            hpa = s.hpa
            assert "min" in hpa
            assert "max" in hpa
            assert "cpu_target" in hpa
            assert hpa["min"] <= hpa["max"]

    def test_slo_profiles_by_criticality(self):
        for crit in Criticality:
            s = ServiceSpec(name="svc", criticality=crit)
            slo = s.slo
            assert slo["availability_target"] >= 99.0
            assert slo["latency_target_ms"] > 0

    def test_pdb_profiles(self):
        for crit in Criticality:
            s = ServiceSpec(name="svc", criticality=crit)
            assert s.pdb_min_available in ("0", "1", "2")

    def test_critical_higher_replicas_than_low(self):
        low = ServiceSpec(name="svc", criticality=Criticality.LOW)
        crit = ServiceSpec(name="svc", criticality=Criticality.CRITICAL)
        assert crit.hpa["min"] > low.hpa["min"]
        assert crit.hpa["max"] > low.hpa["max"]

    def test_from_dict(self):
        d = {"name": "foo", "criticality": "high", "language": "python"}
        s = ServiceSpec.from_dict(d)
        assert s.slug == "foo"
        assert s.criticality == Criticality.HIGH
        assert s.language == Language.PYTHON


# ─── Genesis Generator Tests ─────────────────────────────────────────────────

class TestGenesisGenerator:
    def test_version(self, genesis):
        assert genesis.VERSION == "2.0.0"

    def test_component_count(self, genesis):
        assert genesis.COMPONENTS == 15

    def test_generate_returns_dict(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        assert isinstance(files, dict)
        assert len(files) > 0

    def test_generate_zip_returns_bytes(self, genesis, spec_medium):
        zip_bytes = genesis.generate_zip(spec_medium)
        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0

    def test_zip_is_valid(self, genesis, spec_medium):
        zip_bytes = genesis.generate_zip(spec_medium)
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert len(names) > 0

    def test_generates_kubernetes_files(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        k8s_files = [k for k in files if "kubernetes/" in k]
        assert len(k8s_files) > 0

    def test_generates_terraform_files(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        tf_files = [k for k in files if k.endswith(".tf")]
        assert len(tf_files) > 0

    def test_generates_cicd_files(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        cicd_files = [k for k in files if ".github/workflows" in k]
        assert len(cicd_files) > 0

    def test_generates_argocd_files(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        argocd_files = [k for k in files if "argocd/" in k]
        assert len(argocd_files) > 0

    def test_generates_vault_policies(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        vault_files = [k for k in files if "vault/policies" in k]
        assert len(vault_files) > 0

    def test_generates_prometheus_rules(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        prom_files = [k for k in files if "monitoring/rules" in k]
        assert len(prom_files) > 0

    def test_service_spec_yaml_included(self, genesis, spec_medium):
        files = genesis.generate(spec_medium)
        assert "service-spec.yaml" in files

    def test_info_returns_dict(self, genesis):
        info = genesis.info()
        assert info["name"] == "Genesis Microservices Generator"
        assert info["version"] == "2.0.0"
        assert info["components"] == 15
        assert len(info["component_inventory"]) == 15

    def test_info_cicd_gates(self, genesis):
        info = genesis.info()
        gates = info["cicd_gates"]
        assert len(gates) == 5
        assert any("Constitutional" in g for g in gates)
        assert any("Pact" in g for g in gates)
        assert any("ArgoCD" in g for g in gates)
        assert any("Drift" in g for g in gates)

    def test_critical_generates_more_tf_replicas(self, genesis, spec_critical):
        files = genesis.generate(spec_critical)
        tfvars = next((v for k, v in files.items() if "terraform.tfvars" in k), None)
        assert tfvars is not None

    def test_no_terraform_flag(self, genesis):
        spec = ServiceSpec(name="lean-svc", enable_terraform=False)
        files = genesis.generate(spec)
        tf_files = [k for k in files if k.endswith(".tf")]
        assert len(tf_files) == 0

    def test_no_cicd_flag(self, genesis):
        spec = ServiceSpec(name="lean-svc", enable_cicd=False)
        files = genesis.generate(spec)
        cicd_files = [k for k in files if ".github/workflows" in k]
        assert len(cicd_files) == 0

    def test_no_argocd_flag(self, genesis):
        spec = ServiceSpec(name="lean-svc", enable_argocd=False)
        files = genesis.generate(spec)
        argocd_files = [k for k in files if "argocd/" in k]
        assert len(argocd_files) == 0


# ─── Component Tests ──────────────────────────────────────────────────────────

class TestTerraformGenerator:
    def test_generates_five_modules(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        # Path structure: terraform/services/<slug>/modules/<module>/...
        modules = {k.split("/")[4] for k in files if "/modules/" in k}
        assert {"namespace", "deployment", "rbac", "vault", "monitoring"}.issubset(modules)

    def test_root_main_tf_exists(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        assert f"terraform/services/{spec_medium.slug}/main.tf" in files

    def test_versions_tf_exists(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        assert f"terraform/services/{spec_medium.slug}/versions.tf" in files

    def test_backend_tf_exists(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        assert f"terraform/services/{spec_medium.slug}/backend.tf" in files

    def test_env_files_generated(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        for env in spec_medium.environments:
            assert f"terraform/envs/{env}/main.tf" in files

    def test_criticality_reflected_in_variables(self, spec_critical):
        gen = TerraformGenerator()
        files = gen.generate(spec_critical)
        var_tf = files[f"terraform/services/{spec_critical.slug}/variables.tf"]
        assert "critical" in var_tf

    def test_scripts_generated(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        assert "terraform/scripts/plan.sh" in files
        assert "terraform/scripts/apply.sh" in files
        assert "terraform/scripts/destroy.sh" in files

    def test_file_count(self, spec_medium):
        gen = TerraformGenerator()
        files = gen.generate(spec_medium)
        # 6 root + 15 module files + 4 shared + 3 scripts + 2*3 env = >= 30
        assert len(files) >= 30


class TestKubernetesGenerator:
    def test_generates_all_manifests(self, spec_medium):
        gen = KubernetesGenerator()
        files = gen.generate(spec_medium)
        base = f"kubernetes/{spec_medium.slug}"
        assert f"{base}/namespace.yaml" in files
        assert f"{base}/deployment.yaml" in files
        assert f"{base}/service.yaml" in files
        assert f"{base}/configmap.yaml" in files
        assert f"{base}/serviceaccount.yaml" in files
        assert f"{base}/network-policy.yaml" in files

    def test_deployment_has_probes(self, spec_medium):
        gen = KubernetesGenerator()
        files = gen.generate(spec_medium)
        deployment = files[f"kubernetes/{spec_medium.slug}/deployment.yaml"]
        assert "livenessProbe" in deployment
        assert "readinessProbe" in deployment
        assert "startupProbe" in deployment


class TestRBACGenerator:
    def test_generates_clusterrole_and_binding(self, spec_medium):
        gen = RBACGenerator()
        files = gen.generate(spec_medium)
        base = f"kubernetes/{spec_medium.slug}"
        assert f"{base}/clusterrole.yaml" in files
        assert f"{base}/clusterrolebinding.yaml" in files


class TestVaultPolicyGenerator:
    def test_generates_per_environment(self, spec_medium):
        gen = VaultPolicyGenerator()
        files = gen.generate(spec_medium)
        for env in spec_medium.environments:
            assert f"vault/policies/{spec_medium.slug}-{env}.hcl" in files

    def test_policy_contains_service_name(self, spec_medium):
        gen = VaultPolicyGenerator()
        files = gen.generate(spec_medium)
        policy = files[f"vault/policies/{spec_medium.slug}-dev.hcl"]
        assert spec_medium.slug in policy

    def test_policy_scoped_deny(self, spec_medium):
        gen = VaultPolicyGenerator()
        files = gen.generate(spec_medium)
        policy = files[f"vault/policies/{spec_medium.slug}-dev.hcl"]
        assert "deny" in policy

    def test_common_policy_generated(self, spec_medium):
        gen = VaultPolicyGenerator()
        files = gen.generate(spec_medium)
        assert f"vault/policies/{spec_medium.slug}-common.hcl" in files


class TestPrometheusAlertGenerator:
    def test_generates_slo_and_infra_rules(self, spec_medium):
        gen = PrometheusAlertGenerator()
        files = gen.generate(spec_medium)
        slug = spec_medium.slug
        assert f"monitoring/rules/{slug}-slo-alerts.yaml" in files
        assert f"monitoring/rules/{slug}-infra-alerts.yaml" in files

    def test_slo_alert_contains_availability_target(self, spec_critical):
        gen = PrometheusAlertGenerator()
        files = gen.generate(spec_critical)
        slo_yaml = files[f"monitoring/rules/{spec_critical.slug}-slo-alerts.yaml"]
        assert "99.99" in slo_yaml

    def test_critical_severity_is_critical(self, spec_critical):
        gen = PrometheusAlertGenerator()
        files = gen.generate(spec_critical)
        slo_yaml = files[f"monitoring/rules/{spec_critical.slug}-slo-alerts.yaml"]
        assert "critical" in slo_yaml


class TestHPAGenerator:
    def test_generates_hpa(self, spec_medium):
        gen = HPAGenerator()
        files = gen.generate(spec_medium)
        assert f"kubernetes/{spec_medium.slug}/hpa.yaml" in files

    def test_hpa_reflects_criticality_min_max(self, spec_critical):
        gen = HPAGenerator()
        files = gen.generate(spec_critical)
        hpa_yaml = files[f"kubernetes/{spec_critical.slug}/hpa.yaml"]
        hpa = HPA_PROFILES[Criticality.CRITICAL]
        assert str(hpa["min"]) in hpa_yaml
        assert str(hpa["max"]) in hpa_yaml


class TestPDBGenerator:
    def test_generates_pdb(self, spec_medium):
        gen = PDBGenerator()
        files = gen.generate(spec_medium)
        assert f"kubernetes/{spec_medium.slug}/pdb.yaml" in files

    def test_pdb_min_available_for_critical(self, spec_critical):
        gen = PDBGenerator()
        files = gen.generate(spec_critical)
        pdb_yaml = files[f"kubernetes/{spec_critical.slug}/pdb.yaml"]
        assert PDB_PROFILES[Criticality.CRITICAL] in pdb_yaml


class TestArgoCDGenerator:
    def test_generates_applicationset_and_project(self, spec_medium):
        gen = ArgoCDGenerator()
        files = gen.generate(spec_medium)
        assert f"argocd/{spec_medium.slug}-applicationset.yaml" in files
        assert f"argocd/{spec_medium.slug}-app-project.yaml" in files

    def test_applicationset_has_self_heal(self, spec_medium):
        gen = ArgoCDGenerator()
        files = gen.generate(spec_medium)
        appset = files[f"argocd/{spec_medium.slug}-applicationset.yaml"]
        assert "selfHeal" in appset

    def test_applicationset_has_auto_prune(self, spec_medium):
        gen = ArgoCDGenerator()
        files = gen.generate(spec_medium)
        appset = files[f"argocd/{spec_medium.slug}-applicationset.yaml"]
        assert "prune" in appset


class TestCICDPipelineGenerator:
    def test_generates_six_workflow_files(self, spec_medium):
        gen = CICDPipelineGenerator()
        files = gen.generate(spec_medium)
        wf_files = [k for k in files if ".github/workflows" in k]
        assert len(wf_files) == 6

    def test_full_pipeline_has_five_gates(self, spec_medium):
        gen = CICDPipelineGenerator()
        files = gen.generate(spec_medium)
        pipeline = files[".github/workflows/genesis-pipeline.yml"]
        assert "Gate 1" in pipeline
        assert "Gate 2" in pipeline
        assert "Gate 3" in pipeline
        assert "Gate 4" in pipeline
        assert "Gate 5" in pipeline

    def test_pipeline_has_argocd_deploy(self, spec_medium):
        gen = CICDPipelineGenerator()
        files = gen.generate(spec_medium)
        pipeline = files[".github/workflows/genesis-pipeline.yml"]
        assert "argocd-deploy" in pipeline

    def test_pipeline_has_pact(self, spec_medium):
        gen = CICDPipelineGenerator()
        files = gen.generate(spec_medium)
        pipeline = files[".github/workflows/genesis-pipeline.yml"]
        assert "pact" in pipeline.lower()


class TestPreCommitGenerator:
    def test_generates_config_and_script(self, spec_medium):
        gen = PreCommitGenerator()
        files = gen.generate(spec_medium)
        assert ".pre-commit-config.yaml" in files
        assert "scripts/pre-commit-sacred-check.py" in files

    def test_config_has_genesis_hook(self, spec_medium):
        gen = PreCommitGenerator()
        files = gen.generate(spec_medium)
        config = files[".pre-commit-config.yaml"]
        assert "genesis-sacred-zone-check" in config

    def test_config_has_gitleaks(self, spec_medium):
        gen = PreCommitGenerator()
        files = gen.generate(spec_medium)
        config = files[".pre-commit-config.yaml"]
        assert "gitleaks" in config

    def test_config_has_terraform_fmt(self, spec_medium):
        gen = PreCommitGenerator()
        files = gen.generate(spec_medium)
        config = files[".pre-commit-config.yaml"]
        assert "terraform_fmt" in config


class TestPactContractGenerator:
    def test_generates_three_files(self, spec_medium):
        gen = PactContractGenerator()
        files = gen.generate(spec_medium)
        assert len(files) == 3

    def test_provider_test_exists(self, spec_medium):
        gen = PactContractGenerator()
        files = gen.generate(spec_medium)
        assert f"tests/pact/test_{spec_medium.snake}_provider.py" in files

    def test_consumer_test_exists(self, spec_medium):
        gen = PactContractGenerator()
        files = gen.generate(spec_medium)
        assert f"tests/pact/test_{spec_medium.snake}_consumer.py" in files


class TestDriftDetectionGenerator:
    def test_generates_script_and_cronjob(self, spec_medium):
        gen = DriftDetectionGenerator()
        files = gen.generate(spec_medium)
        assert f"scripts/drift-check-{spec_medium.slug}.sh" in files
        assert f"kubernetes/{spec_medium.slug}/drift-cronjob.yaml" in files

    def test_script_has_terraform_check(self, spec_medium):
        gen = DriftDetectionGenerator()
        files = gen.generate(spec_medium)
        script = files[f"scripts/drift-check-{spec_medium.slug}.sh"]
        assert "terraform plan" in script


# ─── Sacred Zone Preserver Tests ─────────────────────────────────────────────

class TestSacredZonePreserver:
    def test_extract_empty(self):
        preserver = SacredZonePreserver()
        zones = preserver.extract("no sacred zones here")
        assert zones == {}

    def test_extract_single_zone(self):
        preserver = SacredZonePreserver()
        content = "before\n# <<<SACRED_ZONE_BEGIN>>> my-zone\ncustom code\n# <<<SACRED_ZONE_END>>>\nafter"
        zones = preserver.extract(content)
        assert "my-zone" in zones
        assert "custom code" in zones["my-zone"]

    def test_inject_preserves_zone(self):
        preserver = SacredZonePreserver()
        original = "before\n# <<<SACRED_ZONE_BEGIN>>> z\nold code\n# <<<SACRED_ZONE_END>>>\nafter"
        zones = {"z": "old code"}
        new_template = "before\n# <<<SACRED_ZONE_BEGIN>>> z\nnew generated code\n# <<<SACRED_ZONE_END>>>\nafter"
        result = preserver.inject(new_template, zones)
        assert "old code" in result
        assert "new generated code" not in result

    def test_roundtrip(self):
        preserver = SacredZonePreserver()
        content = "# <<<SACRED_ZONE_BEGIN>>> zone1\nmy custom logic\n# <<<SACRED_ZONE_END>>>"
        zones = preserver.extract(content)
        result = preserver.inject(content, zones)
        assert "my custom logic" in result


# ─── Surgical Regen Tests ─────────────────────────────────────────────────────

class TestSurgicalRegen:
    def test_regen_terraform_only(self, spec_medium, tmp_path):
        preserver = SacredZonePreserver()
        surgical = SurgicalRegen(preserver)
        files = surgical.regen(spec_medium, ["terraform"], str(tmp_path))
        assert all(k.startswith("terraform/") for k in files)

    def test_regen_kubernetes_only(self, spec_medium, tmp_path):
        preserver = SacredZonePreserver()
        surgical = SurgicalRegen(preserver)
        files = surgical.regen(spec_medium, ["kubernetes"], str(tmp_path))
        assert all("kubernetes/" in k for k in files)

    def test_regen_unknown_component_logs_warning(self, spec_medium, tmp_path):
        preserver = SacredZonePreserver()
        surgical = SurgicalRegen(preserver)
        # Unknown component should not raise
        files = surgical.regen(spec_medium, ["unknown-component"], str(tmp_path))
        assert files == {}

    def test_regen_multi_component(self, spec_medium, tmp_path):
        preserver = SacredZonePreserver()
        surgical = SurgicalRegen(preserver)
        files = surgical.regen(spec_medium, ["terraform", "argocd"], str(tmp_path))
        tf_files = [k for k in files if k.endswith(".tf")]
        argocd_files = [k for k in files if "argocd/" in k]
        assert len(tf_files) > 0
        assert len(argocd_files) > 0
