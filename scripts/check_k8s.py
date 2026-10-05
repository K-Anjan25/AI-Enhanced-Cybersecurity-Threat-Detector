#!/usr/bin/env python3
"""Static consistency checks for the Kubernetes manifests (T-001).

There is no cluster and no ``kubectl`` in the development sandbox, so nothing
here applies a manifest. What it does check is everything that can be decided
from the YAML plus the real application code — the same discipline
``check_compose.py`` uses for the compose stack:

* the YAML parses and every document is shaped like a Kubernetes object;
* every probe path is a route the application actually serves;
* every ``AEGIS_*`` variable is a real ``Settings`` field, so a typo cannot
  reach production as a silently ignored environment variable;
* no secret value is inlined — secrets arrive by reference only;
* every container is non-root, cannot escalate, and has a read-only root
  filesystem with all capabilities dropped;
* every image is pinned, because ``:latest`` makes a rollback meaningless;
* every HPA targets a Deployment that exists, and every Ingress backend names a
  Service that exists.

Route discovery reuses :func:`check_compose.served_paths` so that "what does
this app serve" has one definition across both checkers.
"""

from __future__ import annotations

import glob
import os
import sys
from typing import Any, cast

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_compose import ROOT, served_paths, settings_fields  # noqa: E402

K8S_DIR = os.path.join(ROOT, "k8s")
NAMESPACE = "aegis"

#: Container port and expected uid per workload. The uid must match the USER
#: line in the image, or the pod is rejected by the runtime.
WORKLOADS: dict[str, tuple[int, int]] = {
    "backend": (8000, 10001),
    "ml-service": (8001, 10001),
    "dashboard": (8080, 101),
}

#: Environment variables that must never carry a literal value in a manifest.
SECRET_ONLY = ("AEGIS_SECRET_KEY", "AEGIS_DATABASE_URL")

MIN_REPLICAS = 2


def fail(problems: list[str], message: str) -> None:
    """Record one problem."""
    problems.append(message)


def load_documents(problems: list[str]) -> list[dict[str, Any]]:
    """Parse every manifest and return the documents that carry content."""
    documents: list[dict[str, Any]] = []
    paths = sorted(glob.glob(os.path.join(K8S_DIR, "*.yaml")))
    if not paths:
        fail(problems, f"no manifests found in {K8S_DIR}")
        return documents
    for path in paths:
        relative = os.path.relpath(path, ROOT)
        try:
            with open(path, encoding="utf-8") as handle:
                parsed = list(yaml.safe_load_all(handle))
        except yaml.YAMLError as exc:
            fail(problems, f"{relative}: invalid YAML: {exc}")
            continue
        for index, document in enumerate(parsed):
            if document is None:
                continue
            if not isinstance(document, dict):
                fail(problems, f"{relative}: document {index} is not a mapping")
                continue
            for field in ("apiVersion", "kind"):
                if not document.get(field):
                    fail(problems, f"{relative}: document {index} has no {field}")
            name = document.get("metadata", {}).get("name")
            if not name:
                fail(problems, f"{relative}: document {index} has no metadata.name")
            elif (
                document.get("kind") != "Namespace"
                and document.get("metadata", {}).get("namespace") != NAMESPACE
            ):
                fail(
                    problems,
                    f"{relative}: {name} is not in the {NAMESPACE} namespace",
                )
            documents.append(cast("dict[str, Any]", document))
    return documents


def check_deployment(
    document: dict[str, Any], problems: list[str], fields: set[str]
) -> None:
    """Validate one Deployment against the app it runs."""
    name = document["metadata"]["name"]
    if name not in WORKLOADS:
        fail(problems, f"{name}: unexpected Deployment, add it to WORKLOADS")
        return
    port, uid = WORKLOADS[name]
    spec = document.get("spec", {})

    if spec.get("replicas", 0) < MIN_REPLICAS:
        fail(problems, f"{name}: replicas must be at least {MIN_REPLICAS}")

    pod = spec.get("template", {}).get("spec", {})
    pod_security = pod.get("securityContext", {})
    if pod_security.get("runAsNonRoot") is not True:
        fail(problems, f"{name}: pod securityContext must set runAsNonRoot: true")
    if pod_security.get("runAsUser") != uid:
        fail(
            problems,
            f"{name}: runAsUser is {pod_security.get('runAsUser')}, "
            f"but the image runs as {uid}",
        )

    containers = pod.get("containers", [])
    if len(containers) != 1:
        fail(problems, f"{name}: expected exactly one container, got {len(containers)}")
        return
    container = containers[0]

    resources = container.get("resources", {})
    for section in ("requests", "limits"):
        for resource in ("cpu", "memory"):
            if resource not in resources.get(section, {}):
                fail(problems, f"{name}: resources.{section}.{resource} is not set")

    security = container.get("securityContext", {})
    if security.get("allowPrivilegeEscalation") is not False:
        fail(problems, f"{name}: allowPrivilegeEscalation must be false")
    if security.get("readOnlyRootFilesystem") is not True:
        fail(problems, f"{name}: readOnlyRootFilesystem must be true")
    if "ALL" not in security.get("capabilities", {}).get("drop", []):
        fail(problems, f"{name}: capabilities must drop ALL")

    image = container.get("image", "")
    if image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1]:
        fail(problems, f"{name}: image {image!r} is not pinned to a tag")

    check_probes(name, container, port, problems)
    check_env(name, container, problems, fields)


def check_probes(
    name: str, container: dict[str, Any], port: int, problems: list[str]
) -> None:
    """Both probes must exist and point at a route the app really serves."""
    if name == "dashboard":
        return  # nginx serves static files; its routes are not introspectable
    routes = served_paths(name)
    for probe in ("livenessProbe", "readinessProbe"):
        spec = container.get(probe)
        if not spec:
            fail(problems, f"{name}: {probe} is missing")
            continue
        path = spec.get("httpGet", {}).get("path")
        if path not in routes:
            fail(
                problems, f"{name}: {probe} targets {path}, which is not a served route"
            )
        if spec.get("httpGet", {}).get("port") != port:
            fail(problems, f"{name}: {probe} targets the wrong port")


def check_env(
    name: str, container: dict[str, Any], problems: list[str], fields: set[str]
) -> None:
    """Every AEGIS_* variable must be real, and secrets must come by reference."""
    for entry in container.get("env", []) or []:
        variable = entry.get("name", "")
        if not variable.startswith("AEGIS_"):
            continue
        if variable not in fields:
            fail(problems, f"{name}: {variable} is not a field on Settings")
        if variable in SECRET_ONLY and "value" in entry:
            fail(
                problems, f"{name}: {variable} must come from a secretRef, not a value"
            )

    for source in container.get("envFrom", []) or []:
        if "secretRef" in source:
            continue
        if "configMapRef" in source:
            continue
        fail(
            problems,
            f"{name}: envFrom entry has neither a configMapRef nor a secretRef",
        )


def check_configmap(
    document: dict[str, Any], problems: list[str], fields: set[str]
) -> None:
    """Every AEGIS_* key in the ConfigMap must be a real Settings field.

    These become environment variables through ``envFrom``, so an unrecognised
    key is not a harmless extra — it is a setting the application silently
    ignores while the operator believes it applied.
    """
    name = document["metadata"]["name"]
    for key in document.get("data", {}) or {}:
        if key.startswith("AEGIS_") and key not in fields:
            fail(problems, f"configmap {name}: {key} is not a field on Settings")


def check_service(
    document: dict[str, Any], deployments: set[str], problems: list[str]
) -> None:
    """A Service must select a workload that exists and expose its port."""
    name = document["metadata"]["name"]
    selector = document.get("spec", {}).get("selector", {})
    target = selector.get("app.kubernetes.io/name")
    if target not in deployments:
        fail(
            problems,
            f"service {name}: selects {target!r}, which is not a Deployment here",
        )
        return
    port, _uid = WORKLOADS[target]
    ports = document.get("spec", {}).get("ports", [])
    exposed = [entry.get("port") for entry in ports]
    if exposed != [port]:
        fail(problems, f"service {name}: exposes {exposed}, expected [{port}]")


def check_hpa(
    document: dict[str, Any], deployments: set[str], problems: list[str]
) -> None:
    """An HPA must target a real Deployment and never scale below the minimum."""
    name = document["metadata"]["name"]
    spec = document.get("spec", {})
    target = spec.get("scaleTargetRef", {})
    if target.get("kind") != "Deployment" or target.get("name") not in deployments:
        fail(
            problems,
            f"hpa {name}: targets {target.get('name')!r}, which is not a Deployment here",
        )
    if spec.get("minReplicas", 0) < MIN_REPLICAS:
        fail(problems, f"hpa {name}: minReplicas must be at least {MIN_REPLICAS}")
    if spec.get("maxReplicas", 0) < spec.get("minReplicas", 0):
        fail(problems, f"hpa {name}: maxReplicas is below minReplicas")


def check_ingress(
    document: dict[str, Any], services: set[str], problems: list[str]
) -> None:
    """TLS must be configured and every backend must name a real Service."""
    name = document["metadata"]["name"]
    spec = document.get("spec", {})
    tls = spec.get("tls", [])
    if not tls or not all(entry.get("secretName") for entry in tls):
        fail(problems, f"ingress {name}: TLS must be configured with a secretName")
    for rule in spec.get("rules", []):
        for path in rule.get("http", {}).get("paths", []):
            backend = path.get("backend", {}).get("service", {})
            if backend.get("name") not in services:
                fail(
                    problems,
                    f"ingress {name}: routes to {backend.get('name')!r}, "
                    "which is not a Service here",
                )


def main() -> int:
    """Run every static check. Returns a process exit code."""
    problems: list[str] = []
    if not os.path.isdir(K8S_DIR):
        print(f"FATAL: {K8S_DIR} not found", file=sys.stderr)
        return 2

    documents = load_documents(problems)
    fields = settings_fields()

    deployments = {
        document["metadata"]["name"]
        for document in documents
        if document.get("kind") == "Deployment"
    }
    services = {
        document["metadata"]["name"]
        for document in documents
        if document.get("kind") == "Service"
    }

    for document in documents:
        kind = document.get("kind")
        if kind == "Deployment":
            check_deployment(document, problems, fields)
        elif kind == "ConfigMap":
            check_configmap(document, problems, fields)
        elif kind == "Service":
            check_service(document, deployments, problems)
        elif kind == "HorizontalPodAutoscaler":
            check_hpa(document, deployments, problems)
        elif kind == "Ingress":
            check_ingress(document, services, problems)

    if not any(document.get("kind") == "NetworkPolicy" for document in documents):
        fail(problems, "no NetworkPolicy: the namespace has no default-deny rule")

    print(
        f"checked {len(documents)} manifest documents: "
        f"{len(deployments)} deployments, {len(services)} services"
    )
    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  FAIL {problem}", file=sys.stderr)
        return 1

    print("k8s static consistency: all checks passed")
    print("note: this does not apply anything — there is no cluster here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
