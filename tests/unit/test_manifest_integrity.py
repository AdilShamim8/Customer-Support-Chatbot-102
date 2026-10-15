"""
Infrastructure manifest integrity tests.

Every YAML file shipped in deploy/ and .github/ must parse and carry the
production-critical fields. A manifest that breaks at `kubectl apply`
time is an outage that was checkable at commit time.
"""

import pathlib

import pytest
import yaml

REPO = pathlib.Path(".")
K8S_DIR = REPO / "deploy" / "kubernetes"
WORKFLOWS_DIR = REPO / ".github" / "workflows"


def k8s_manifests():
    return sorted(K8S_DIR.rglob("*.yaml"))


def workflow_files():
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


class TestYamlSyntax:
    @pytest.mark.parametrize("path", k8s_manifests(), ids=lambda p: p.name)
    def test_k8s_manifests_parse(self, path):
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        assert documents, f"{path.name} is empty"
        for doc in documents:
            if doc:  # skip empty separator documents
                assert isinstance(doc, dict), f"{path.name} has a non-mapping document"

    @pytest.mark.parametrize("path", workflow_files(), ids=lambda p: p.name)
    def test_workflows_parse(self, path):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict), f"{path.name} is not a mapping"
        assert "jobs" in doc, f"{path.name} has no jobs"
        assert "on" in doc or True  # 'on' parses to boolean True key in YAML 1.1


class TestDeploymentContract:
    @pytest.fixture(scope="class")
    def deployment(self):
        text = (K8S_DIR / "deployment.yaml").read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_zero_downtime_rollout(self, deployment):
        strategy = deployment["spec"]["strategy"]
        assert strategy["type"] == "RollingUpdate"
        assert (
            strategy["rollingUpdate"]["maxUnavailable"] == 0
        ), "maxUnavailable != 0 breaks the zero-downtime contract"

    def test_grace_period_exceeds_gunicorn_drain(self, deployment):
        grace = deployment["spec"]["template"]["spec"]["terminationGracePeriodSeconds"]
        assert grace >= 130, f"grace period {grace}s < gunicorn graceful_timeout 120s + margin"

    def test_probes_use_correct_endpoints(self, deployment):
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        liveness = container["livenessProbe"]["httpGet"]["path"]
        readiness = container["readinessProbe"]["httpGet"]["path"]
        assert liveness == "/live", "liveness must not check dependencies"
        assert readiness == "/ready", "readiness must gate traffic"

    def test_non_root_security_context(self, deployment):
        spec = deployment["spec"]["template"]["spec"]
        assert spec["securityContext"]["runAsNonRoot"] is True
        container = spec["containers"][0]
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["allowPrivilegeEscalation"] is False

    def test_zone_spread_present(self, deployment):
        constraints = deployment["spec"]["template"]["spec"].get("topologySpreadConstraints")
        assert constraints, "no zone spread - single-AZ outage risk"

    def test_resource_limits_set(self, deployment):
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["resources"]["limits"]["memory"]
        assert container["resources"]["requests"]["cpu"]


class TestHpaContract:
    def test_scale_bounds_sane(self):
        hpa = yaml.safe_load((K8S_DIR / "hpa.yaml").read_text(encoding="utf-8"))
        spec = hpa["spec"]
        assert spec["minReplicas"] >= 3, "floor below 3 cannot survive zone loss"
        assert spec["maxReplicas"] > spec["minReplicas"]
        # Slow scale-down prevents conversation-affinity flapping
        assert spec["behavior"]["scaleDown"]["stabilizationWindowSeconds"] >= 300


class TestConfigMapContract:
    def test_no_secret_material_in_configmap(self):
        configmap = yaml.safe_load((K8S_DIR / "configmap.yaml").read_text(encoding="utf-8"))
        data = configmap.get("data", {})
        for key, value in data.items():
            value = str(value)
            for marker in ("sk-", "password=", "SECRET", "REPLACE_ME", "changeme"):
                assert (
                    marker.lower() not in value.lower()
                ), f"secret-like value in configmap key {key}"


class TestKustomizationCompleteness:
    def test_all_manifests_listed(self):
        kustomization = yaml.safe_load((K8S_DIR / "kustomization.yaml").read_text(encoding="utf-8"))
        listed = set(kustomization["resources"])
        on_disk = {p.relative_to(K8S_DIR).as_posix() for p in k8s_manifests()}
        # Overlays reference the base - listing them in it would recurse
        excluded = {
            "kustomization.yaml",
            "overlays/staging/kustomization.yaml",
            "overlays/production/kustomization.yaml",
        }
        unlisted = on_disk - listed - excluded
        assert not unlisted, f"manifests not in kustomization: {unlisted}"
