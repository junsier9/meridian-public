from __future__ import annotations

import ast
import compileall
from datetime import UTC, date, datetime, timedelta
import gzip
import importlib
import inspect
import math
from pathlib import Path, PurePosixPath
import json
import re
import tempfile
import unittest

import pandas as pd

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _read_assignment_literal(path: str, name: str) -> object:
    tree = ast.parse(_read(path), filename=path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{path} does not assign {name}")


def _read_with_name_assignment(path: str, name: str) -> str:
    pattern = re.compile(
        rf"{re.escape(name)}\s*=\s*Path\(__file__\)\.with_name\(\"([^\"]+)\"\)"
    )
    match = pattern.search(_read(path))
    if match is None:
        raise AssertionError(f"{path} does not assign {name} with Path(__file__).with_name(...)")
    return match.group(1)


def _add_target_names(symbols: set[str], target: ast.AST) -> None:
    if isinstance(target, ast.Name):
        symbols.add(target.id)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            _add_target_names(symbols, item)


def _read_module_level_symbols(path: str) -> set[str]:
    tree = ast.parse(_read(path), filename=path)
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _add_target_names(symbols, target)
        elif isinstance(node, ast.AnnAssign):
            _add_target_names(symbols, node.target)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    symbols.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.asname or alias.name.split(".")[0])
    return symbols


def _attribute_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return []


def _sorted_mapping(mapping: dict[str, set[str]]) -> dict[str, list[str]]:
    return {key: sorted(values) for key, values in sorted(mapping.items())}


def _scan_hypothesis_batch_external_compatibility(scan_roots: list[str]) -> dict[str, dict[str, list[str]]]:
    module_name = "enhengclaw.quant_research" + ".hypothesis_batch"
    module_parts = module_name.split(".")
    package_name = "enhengclaw.quant_research"
    module_prefix = module_name + "."
    mutable_globals: dict[str, set[str]] = {}
    read_globals: dict[str, set[str]] = {}
    private_helpers: dict[str, set[str]] = {}
    string_patch_targets: dict[str, set[str]] = {}

    def add(mapping: dict[str, set[str]], name: str, rel_path: str) -> None:
        mapping.setdefault(name, set()).add(rel_path)

    def classify_name(name: str, rel_path: str) -> None:
        if name.startswith("_"):
            add(private_helpers, name, rel_path)
        elif (
            name.isupper()
            or name.startswith("HYPOTHESIS_BATCH")
            or name.startswith("EXPECTED_")
            or name.endswith("CONTRACT_VERSION")
        ):
            add(read_globals, name, rel_path)

    def attribute_name(node: ast.Attribute, aliases: set[str]) -> str | None:
        chain = _attribute_chain(node)
        if len(chain) == 2 and chain[0] in aliases:
            return chain[1]
        if len(chain) == len(module_parts) + 1 and chain[:-1] == module_parts:
            return chain[-1]
        return None

    for scan_root in scan_roots:
        for path in (ROOT / scan_root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel_path = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
            aliases: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == module_name:
                            aliases.add(alias.asname or alias.name.split(".")[-1])
                elif isinstance(node, ast.ImportFrom):
                    if node.module == package_name:
                        for alias in node.names:
                            if alias.name == "hypothesis_batch":
                                aliases.add(alias.asname or alias.name)
                    elif node.module == module_name:
                        for alias in node.names:
                            classify_name(alias.name, rel_path)

            for node in ast.walk(tree):
                targets: list[ast.AST] = []
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                elif isinstance(node, ast.AugAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute):
                        name = attribute_name(target, aliases)
                        if name is not None:
                            add(mutable_globals, name, rel_path)

                if isinstance(node, ast.Attribute):
                    name = attribute_name(node, aliases)
                    if name is not None:
                        classify_name(name, rel_path)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith(module_prefix):
                        add(string_patch_targets, node.value.removeprefix(module_prefix), rel_path)

    return {
        "mutable_global_patch_targets": _sorted_mapping(mutable_globals),
        "global_read_targets": _sorted_mapping(read_globals),
        "private_helper_targets": _sorted_mapping(private_helpers),
        "string_patch_targets": _sorted_mapping(string_patch_targets),
    }


def _scan_lab_external_compatibility(scan_roots: list[str]) -> dict[str, dict[str, list[str]]]:
    module_name = "enhengclaw.quant_research.lab"
    module_parts = module_name.split(".")
    package_name = "enhengclaw.quant_research"
    module_prefix = module_name + "."
    mutable_globals: dict[str, set[str]] = {}
    public_facade: dict[str, set[str]] = {}
    private_helpers: dict[str, set[str]] = {}
    string_patch_targets: dict[str, set[str]] = {}

    def add(mapping: dict[str, set[str]], name: str, rel_path: str) -> None:
        mapping.setdefault(name, set()).add(rel_path)

    def classify_name(name: str, rel_path: str) -> None:
        if name.startswith("_"):
            add(private_helpers, name, rel_path)
        else:
            add(public_facade, name, rel_path)

    def attribute_name(node: ast.Attribute, aliases: set[str]) -> str | None:
        chain = _attribute_chain(node)
        if len(chain) == 2 and chain[0] in aliases:
            return chain[1]
        if len(chain) == len(module_parts) + 1 and chain[:-1] == module_parts:
            return chain[-1]
        return None

    for scan_root in scan_roots:
        for path in (ROOT / scan_root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel_path = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
            aliases: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == module_name:
                            aliases.add(alias.asname or alias.name.split(".")[-1])
                elif isinstance(node, ast.ImportFrom):
                    if node.module == package_name:
                        for alias in node.names:
                            if alias.name == "lab":
                                aliases.add(alias.asname or alias.name)
                    elif node.module == module_name:
                        for alias in node.names:
                            classify_name(alias.name, rel_path)

            for node in ast.walk(tree):
                targets: list[ast.AST] = []
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                elif isinstance(node, ast.AugAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute):
                        name = attribute_name(target, aliases)
                        if name is not None:
                            add(mutable_globals, name, rel_path)

                if isinstance(node, ast.Attribute):
                    name = attribute_name(node, aliases)
                    if name is not None:
                        classify_name(name, rel_path)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith(module_prefix):
                        add(string_patch_targets, node.value.removeprefix(module_prefix), rel_path)

    return {
        "mutable_global_patch_targets": _sorted_mapping(mutable_globals),
        "public_facade_targets": _sorted_mapping(public_facade),
        "private_helper_targets": _sorted_mapping(private_helpers),
        "string_patch_targets": _sorted_mapping(string_patch_targets),
    }


def _scan_features_utility_external_compatibility(
    scan_roots: list[str],
    helper_names: set[str],
) -> dict[str, list[str]]:
    module_name = "enhengclaw.quant_research.features"
    helper_targets: dict[str, set[str]] = {}

    def add(name: str, rel_path: str) -> None:
        helper_targets.setdefault(name, set()).add(rel_path)

    for scan_root in scan_roots:
        for path in (ROOT / scan_root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel_path = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.module != module_name:
                    continue
                for alias in node.names:
                    if alias.name in helper_names:
                        add(alias.name, rel_path)

    return _sorted_mapping(helper_targets)


def _function_signature_contract(function: object) -> dict[str, object]:
    signature = inspect.signature(function)
    parameters = []
    for parameter in signature.parameters.values():
        required = parameter.default is inspect.Parameter.empty
        annotation = None
        if parameter.annotation is not inspect.Parameter.empty:
            annotation = str(parameter.annotation)
        parameters.append(
            {
                "annotation": annotation,
                "default_repr": None if required else repr(parameter.default),
                "kind": parameter.kind.name,
                "name": parameter.name,
                "required": required,
            }
        )

    return_annotation = None
    if signature.return_annotation is not inspect.Signature.empty:
        return_annotation = str(signature.return_annotation)
    return {
        "parameters": parameters,
        "return_annotation": return_annotation,
    }


def _read_markdown_tables(path: str, *, required_headers: set[str] | None = None) -> list[list[dict[str, str]]]:
    lines = [line.strip() for line in _read(path).splitlines() if line.strip()]
    tables: list[list[dict[str, str]]] = []
    for index, line in enumerate(lines):
        if not (line.startswith("|") and line.endswith("|")):
            continue
        if index + 1 >= len(lines):
            continue
        separator = lines[index + 1]
        separator_body = set(separator.replace("|", "").strip())
        if not (
            separator.startswith("|")
            and separator.endswith("|")
            and separator_body <= {"-", ":", " "}
        ):
            continue
        headers = [cell.strip() for cell in line.strip("|").split("|")]
        if required_headers and not required_headers.issubset(set(headers)):
            continue
        rows: list[dict[str, str]] = []
        for row_line in lines[index + 2 :]:
            if not (row_line.startswith("|") and row_line.endswith("|")):
                break
            cells = [cell.strip() for cell in row_line.strip("|").split("|")]
            if len(cells) != len(headers):
                raise AssertionError(f"{path} has a malformed row: {row_line}")
            rows.append(dict(zip(headers, cells)))
        tables.append(rows)
    return tables


def _read_markdown_table(path: str, *, required_headers: set[str] | None = None) -> list[dict[str, str]]:
    tables = _read_markdown_tables(path, required_headers=required_headers)
    if tables:
        return tables[0]
    raise AssertionError(f"{path} does not contain a parseable markdown table")


class StaticContractTests(unittest.TestCase):
    def test_checked_in_governance_manifest_and_registry_stay_consistent(self) -> None:
        governance = evaluate_agent_layer_governance()

        self.assertEqual(governance["status"], "enabled")
        self.assertEqual(governance["blockers"], [])
        self.assertTrue(governance["broad_agent_layer_ready"])
        self.assertFalse(governance["broad_agent_layer_enabled"])

    def test_runtime_ownership_contract_aligns_with_docs(self) -> None:
        runtime_contract = _read_json("config/project_governance/runtime_ownership_contract.json")
        state_text = _read("PROJECT_STATE.md")
        instructions_text = _read("PROJECT_INSTRUCTIONS.md")
        agent_text = _read("docs/README_FOR_AGENT.md")
        owner_text = _read("docs/agents/OWNER_AGENT_ARCHITECTURE.md")

        self.assertEqual(runtime_contract["contract_version"], "runtime_ownership_contract.v1")
        self.assertEqual(runtime_contract["runtime_ownership_phase"], "partial")
        self.assertTrue(runtime_contract["owner_verification_required"])
        self.assertTrue(runtime_contract["owner_verification_enforced_in_boundary_gates"])
        for text in (state_text, instructions_text, agent_text, owner_text):
            self.assertIn("config/project_governance/runtime_ownership_contract.json", text)
        self.assertIn("runtime_ownership_phase = partial", state_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", state_text)
        self.assertIn("runtime_ownership_phase = partial", agent_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", agent_text)
        self.assertIn("runtime ownership phase is `partial`", owner_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", owner_text)

    def test_boundary_gates_include_owner_verification_step_when_contract_enabled(self) -> None:
        runtime_contract = _read_json("config/project_governance/runtime_ownership_contract.json")
        gate_text = _read("scripts/verify/run_boundary_gates.py")

        if runtime_contract["owner_verification_enforced_in_boundary_gates"]:
            self.assertIn("phase5 owner verification boundary", gate_text)
            self.assertIn("phase5_owner_verification_boundary.py", gate_text)

    def test_project_profile_declares_dual_track_stage_contract(self) -> None:
        profile = json.loads((ROOT / "config" / "project_governance" / "project_profile.json").read_text(encoding="utf-8"))
        stage_contract = json.loads((ROOT / "config" / "project_governance" / "stage_contract.json").read_text(encoding="utf-8"))
        broad_unlock_contract = json.loads((ROOT / "config" / "agent_layer_governance" / "broad_unlock_contract.json").read_text(encoding="utf-8"))
        publication_contract = json.loads((ROOT / "config" / "quant_research" / "publication_contract.json").read_text(encoding="utf-8"))

        self.assertEqual(profile["contract_version"], "project_profile.v1")
        self.assertEqual(profile["display_name"], "Meridian Alpha Platform")
        self.assertEqual(profile["slug"], "meridian_alpha")
        self.assertEqual(profile["env_prefix"], "MERIDIAN_ALPHA_")
        self.assertEqual(profile["legacy_identity"]["display_name"], "EnhengClaw")
        self.assertEqual(profile["legacy_identity"]["env_prefix"], "ENHENGCLAW_")
        self.assertEqual(profile["tracks"], ["framework", "research_platform"])
        self.assertEqual(profile["current_stage"], "stage_4_automated_execution")
        self.assertEqual(profile["target_stage"], "stage_4_automated_execution")
        self.assertEqual(profile["operator_host_contract"], "windows_wsl_single_host")
        self.assertFalse(profile["dependency_rules"]["framework_may_depend_on_research_platform"])
        self.assertEqual(stage_contract["contract_version"], "project_stage_contract.v1")
        self.assertEqual(
            broad_unlock_contract["minimum_project_stage_for_manual_unlock"],
            stage_contract["unlock_minimum_stages"]["broad_agent_layer_manual_unlock"],
        )
        self.assertEqual(publication_contract["contract_version"], "quant_publication_contract.v2")
        self.assertEqual(publication_contract["minimum_stage_for_incoming"], "stage_2_manual_export_human_review")
        self.assertNotIn(profile["current_stage"], publication_contract["archive_only_stages"])
        self.assertTrue(publication_contract["backend_modes"]["live"]["publishable"])
        self.assertFalse(publication_contract["backend_modes"]["deterministic"]["publishable"])
        self.assertTrue(publication_contract["contract_guardrails"]["thresholds_not_derivable_from_pipeline_output"])
        for threshold_name, threshold_payload in publication_contract["thresholds"].items():
            self.assertIsInstance(threshold_payload, dict, threshold_name)
            self.assertIn("value", threshold_payload)
            self.assertIn("rationale", threshold_payload)
            self.assertIn("last_reviewed_utc", threshold_payload)
            self.assertTrue(str(threshold_payload["rationale"]).strip())
            self.assertTrue(str(threshold_payload["last_reviewed_utc"]).strip())

    def test_gitignore_whitelists_governance_critical_quant_artifacts(self) -> None:
        gitignore = _read(".gitignore")
        self.assertIn("!artifacts/quant_research/assessments/", gitignore)
        self.assertIn("!artifacts/quant_research/bridge_exports/", gitignore)
        self.assertIn("!artifacts/quant_research/assessments/**/*.md", gitignore)
        self.assertIn("!artifacts/quant_research/cycles/**/research_quality_summary.json", gitignore)
        self.assertIn("!artifacts/quant_research/governance/daily_alpha_manifests/", gitignore)
        self.assertIn("!artifacts/quant_research/governance/leakage_audits/", gitignore)
        self.assertIn("!artifacts/quant_research/governance/promotion_decisions/", gitignore)
        self.assertIn("!artifacts/quant_research/ops/", gitignore)
        self.assertIn("!artifacts/quant_research/ops/**/*.json", gitignore)
        self.assertIn("!artifacts/quant_research/registry/alpha_registry.json", gitignore)
        self.assertIn("!artifacts/quant_research/experiments/**/alpha_card.json", gitignore)
        self.assertIn("!artifacts/quant_research/experiments/**/falsification_audit.json", gitignore)

    def test_threshold_provenance_covers_every_publication_threshold(self) -> None:
        publication_contract = _read_json("config/quant_research/publication_contract.json")
        rows = _read_markdown_table(
            "config/quant_research/threshold_provenance.md",
            required_headers={
                "threshold_key",
                "value",
                "source_type",
                "source_reference",
                "evidence_basis",
                "review_status",
                "owner",
                "next_review_action",
            },
        )
        threshold_keys = sorted(publication_contract["thresholds"].keys())
        row_keys = sorted(row["threshold_key"] for row in rows)

        self.assertEqual(row_keys, threshold_keys)
        allowed_source_types = {
            "literature",
            "empirical_distribution",
            "engineering_default_pending_review",
        }
        for row in rows:
            with self.subTest(threshold_key=row["threshold_key"]):
                self.assertIn(row["source_type"], allowed_source_types)
                self.assertTrue(row["source_reference"].strip())
                self.assertTrue(row["evidence_basis"].strip())
                self.assertTrue(row["review_status"].strip())
                self.assertTrue(row["owner"].strip())
                self.assertTrue(row["next_review_action"].strip())

    def test_quant_research_script_catalog_covers_every_script(self) -> None:
        catalog_path = "docs/quant_research/00_roadmap_state/quant_research_script_catalog.md"
        catalog_text = _read(catalog_path)
        readme_text = _read("scripts/quant_research/README.md")
        script_root = ROOT / "scripts" / "quant_research"
        actual_scripts = sorted(
            path.relative_to(ROOT).as_posix()
            for path in script_root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".ps1"} and "__pycache__" not in path.parts
        )

        required_catalog_headers = {
            "script path",
            "category",
            "status",
            "run priority",
            "purpose",
            "primary inputs",
            "primary outputs",
            "related roadmap/doc",
            "safe-to-move",
        }
        catalog_rows: list[dict[str, str]] = []
        for table in _read_markdown_tables(catalog_path, required_headers=required_catalog_headers):
            for row in table:
                if "[scripts/quant_research/" in row["script path"]:
                    catalog_rows.append(row)

        catalog_scripts: list[str] = []
        catalog_path_obj = ROOT / catalog_path
        allowed_categories = {
            "scheduled_wrappers",
            "data_foundation_sync",
            "canonical_h10d_and_binance_pit",
            "coinglass_foundation_and_r_lanes",
            "parallel_1h",
            "m3_mf_spk_legacy_candidates",
            "utilities_and_reports",
        }
        allowed_statuses = {
            "active",
            "scheduled_entrypoint",
            "supporting",
            "historical",
            "quarantined",
            "deprecated_candidate",
        }
        allowed_run_priorities = {
            "default_entrypoint",
            "scheduled_only",
            "quarantined_falsification",
            "historical_do_not_start_here",
            "supporting_tool",
        }
        allowed_safe_to_move = {"no", "yes", "yes-with-wrapper"}

        for row in catalog_rows:
            match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", row["script path"].strip())
            self.assertIsNotNone(match, row["script path"])
            assert match is not None
            script_label = match.group(1)
            script_target = match.group(2)
            catalog_scripts.append(script_label)
            self.assertTrue((catalog_path_obj.parent / script_target).resolve().exists(), script_target)
            self.assertEqual(script_label, script_target.replace("../../../", ""))

            category = row["category"].strip("`")
            status = row["status"].strip("`")
            run_priority = row["run priority"].strip("`")
            safe_to_move = row["safe-to-move"].strip("`")
            self.assertIn(category, allowed_categories, script_label)
            self.assertIn(status, allowed_statuses, script_label)
            self.assertIn(run_priority, allowed_run_priorities, script_label)
            self.assertIn(safe_to_move, allowed_safe_to_move, script_label)

            if status == "scheduled_entrypoint":
                self.assertEqual(run_priority, "scheduled_only", script_label)
                self.assertEqual(safe_to_move, "no", script_label)
            if status == "quarantined":
                self.assertEqual(run_priority, "quarantined_falsification", script_label)
            if status in {"historical", "deprecated_candidate"}:
                self.assertEqual(run_priority, "historical_do_not_start_here", script_label)
            if run_priority == "scheduled_only":
                self.assertEqual(status, "scheduled_entrypoint", script_label)

        self.assertEqual(len(catalog_scripts), len(set(catalog_scripts)))
        self.assertEqual(sorted(catalog_scripts), actual_scripts)
        self.assertIn(f"`Coverage: {len(actual_scripts)} script files", catalog_text)
        for marker in (
            "Default Entrypoints",
            "Scheduled-only Entrypoints",
            "Quarantined Falsification Scripts",
            "Historical / Do-not-start-here Scripts",
        ):
            self.assertIn(marker, readme_text)
        for run_priority in allowed_run_priorities:
            self.assertIn(f"`{run_priority}`", readme_text)
            self.assertIn(f"`{run_priority}`", catalog_text)

    def test_quant_research_markdown_root_stays_consolidated(self) -> None:
        quant_doc_root = ROOT / "docs" / "quant_research"
        self.assertEqual(
            sorted(path.name for path in quant_doc_root.glob("*.md")),
            ["quant_research_roadmap_state_2026_05_12.md"],
        )

        allowed_root_refs = {"docs/quant_research/quant_research_roadmap_state_2026_05_12.md"}
        immediate_root_ref = re.compile(r"docs[/\\]quant_research[/\\][A-Za-z0-9_-]+\.md")
        offenders: list[str] = []
        for base_name in ("config", "docs", "scripts", "src", "tests"):
            for path in (ROOT / base_name).rglob("*"):
                if not path.is_file() or path.suffix not in {".json", ".md", ".ps1", ".py", ".toml", ".yaml", ".yml"}:
                    continue
                relative_path = path.relative_to(ROOT).as_posix()
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    for match in immediate_root_ref.finditer(line):
                        ref = match.group(0).replace("\\", "/")
                        if ref not in allowed_root_refs:
                            offenders.append(f"{relative_path}:{line_number}: {ref}")

        self.assertEqual(offenders, [])

    def test_quant_research_markdown_docs_are_indexed(self) -> None:
        quant_doc_root = ROOT / "docs" / "quant_research"
        index_paths = {
            "docs/quant_research/quant_research_roadmap_state_2026_05_12.md",
            "docs/quant_research/00_roadmap_state/quant_research_script_catalog.md",
            "docs/quant_research/00_roadmap_state/research_doc_governance_index.md",
        }
        index_text = "\n".join(_read(path).replace("\\", "/") for path in sorted(index_paths))

        missing: list[str] = []
        for path in sorted(quant_doc_root.rglob("*.md")):
            relative_path = path.relative_to(ROOT).as_posix()
            if relative_path in index_paths:
                continue
            quant_relative_path = path.relative_to(quant_doc_root).as_posix()
            if relative_path not in index_text and quant_relative_path not in index_text:
                missing.append(relative_path)

        self.assertEqual(
            missing,
            [],
            "Every docs/quant_research Markdown document must be discoverable "
            "from the main roadmap, script catalog, or governance index.",
        )

    def test_quant_research_entry_language_is_shared(self) -> None:
        roadmap_text = _read("docs/quant_research/quant_research_roadmap_state_2026_05_12.md")
        readme_text = _read("scripts/quant_research/README.md")

        shared_markers = (
            "Current Entry Contract",
            "current Binance PIT h10d hardening",
            "data-foundation refresh",
            "CoinGlass sidecar/catalog work",
            "scheduled automation",
            "quarantined falsification",
            "historical audit or rediscovery",
            "one-off diagnostic/report writing",
            "roadmap state\n-> script catalog\n-> default_entrypoint rows in canonical_h10d_and_binance_pit",
        )
        for marker in shared_markers:
            self.assertIn(marker, roadmap_text)
            self.assertIn(marker, readme_text)
        for run_priority in (
            "default_entrypoint",
            "scheduled_only",
            "quarantined_falsification",
            "historical_do_not_start_here",
            "supporting_tool",
        ):
            self.assertIn(f"`{run_priority}`", roadmap_text)
            self.assertIn(f"`{run_priority}`", readme_text)

    def test_quant_research_lazy_public_exports_stay_stable(self) -> None:
        init_path = "src/enhengclaw/quant_research/__init__.py"
        expected_exports = (
            "run_baseline_alpha_proof",
            "run_baseline_alpha_survival",
            "run_eth_shadow_grid_daily_sample",
            "run_eth_shadow_grid_survival",
            "run_quant_hypothesis_batch_cycle",
            "run_quant_deterministic_daily_sample",
            "run_quantagent_shadow_proposal_cycle",
            "run_quant_research_cycle",
        )
        expected_lazy_exports = {
            "run_baseline_alpha_proof": (".baseline_alpha_proof", "run_baseline_alpha_proof"),
            "run_baseline_alpha_survival": (".deterministic_survival", "run_baseline_alpha_survival"),
            "run_eth_shadow_grid_daily_sample": (".shadow_proposals", "run_eth_shadow_grid_daily_sample"),
            "run_eth_shadow_grid_survival": (".shadow_proposals", "run_eth_shadow_grid_survival"),
            "run_quant_hypothesis_batch_cycle": (".hypothesis_batch", "run_quant_hypothesis_batch_cycle"),
            "run_quant_deterministic_daily_sample": (".deterministic_survival", "run_quant_deterministic_daily_sample"),
            "run_quantagent_shadow_proposal_cycle": (".shadow_proposals", "run_quantagent_shadow_proposal_cycle"),
            "run_quant_research_cycle": (".lab", "run_quant_research_cycle"),
        }

        actual_exports = tuple(_read_assignment_literal(init_path, "__all__"))
        actual_lazy_exports = _read_assignment_literal(init_path, "_LAZY_EXPORTS")

        self.assertEqual(actual_exports, expected_exports)
        self.assertEqual(actual_lazy_exports, expected_lazy_exports)
        self.assertEqual(set(actual_exports), set(expected_lazy_exports))
        for module_name, _attribute_name in expected_lazy_exports.values():
            module_path = module_name.removeprefix(".").replace(".", "/") + ".py"
            self.assertTrue((ROOT / "src" / "enhengclaw" / "quant_research" / module_path).exists(), module_path)

    def test_quant_research_architecture_frozen_root_surfaces_exist(self) -> None:
        quant_root = ROOT / "src" / "enhengclaw" / "quant_research"
        plan_text = _read(
            "docs/quant_research/00_roadmap_state/src_quant_research_architecture_governance_plan_2026_05_14.md"
        )
        frozen_root_surfaces = (
            "contracts.py",
            "features.py",
            "lab.py",
            "hypothesis_batch.py",
            "legacy_surface.py",
            "bridge.py",
        )

        self.assertIn("## Do Not Move Without Redesign", plan_text)
        for surface in frozen_root_surfaces:
            with self.subTest(surface=surface):
                self.assertTrue((quant_root / surface).is_file(), surface)
                self.assertIn(f"`{surface}`", plan_text)

    def test_quant_research_path_sensitive_manifests_remain_documented(self) -> None:
        quant_root = ROOT / "src" / "enhengclaw" / "quant_research"
        plan_text = _read(
            "docs/quant_research/00_roadmap_state/src_quant_research_architecture_governance_plan_2026_05_14.md"
        )
        archive_readme = _read("src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/README.md")
        root_manifests = (
            "cross_sectional_hypothesis_batch_manifest_v83.json",
            "deterministic_strategy_manifest.json",
            "strategy_library_thesis_seed.json",
        )

        for manifest_name in root_manifests:
            with self.subTest(manifest_name=manifest_name):
                self.assertTrue((quant_root / manifest_name).is_file(), manifest_name)
                self.assertIn(manifest_name, plan_text)
        self.assertIn("root JSON manifests", plan_text)
        self.assertIn("manifest path loading remains valid", plan_text)
        self.assertIn("cross_sectional_hypothesis_batch_manifest_v83.json", archive_readme)
        self.assertIn("hypothesis_batch.py:HYPOTHESIS_BATCH_MANIFEST_PATH", archive_readme)
        self.assertIn("not the current `hypothesis_batch.py` runtime default", archive_readme)
        self.assertIn("cross_sectional_hypothesis_batch_manifest_v97.json", archive_readme)
        self.assertIn("not current runtime loading", archive_readme)

    def test_quant_research_manifest_lifecycle_catalog_covers_root_json(self) -> None:
        quant_root = ROOT / "src" / "enhengclaw" / "quant_research"
        catalog = _read_json("config/quant_research/src_quant_research_manifest_lifecycle_catalog.json")
        entries = list(catalog["entries"])
        entry_by_file = {str(entry["file"]): entry for entry in entries}
        actual_root_json = sorted(path.name for path in quant_root.glob("*.json"))
        allowed_lifecycle_classes = set(catalog["allowed_lifecycle_classes"])
        allowed_move_stances = set(catalog["allowed_move_stances"])

        self.assertEqual(catalog["contract_version"], "src_quant_research_manifest_lifecycle_catalog.v1")
        self.assertEqual(len(entries), len(entry_by_file))
        self.assertEqual(sorted(entry_by_file), actual_root_json)
        for file_name, entry in entry_by_file.items():
            with self.subTest(file_name=file_name):
                self.assertTrue((quant_root / file_name).is_file(), file_name)
                self.assertIn(entry["lifecycle_class"], allowed_lifecycle_classes)
                self.assertIn(entry["move_stance"], allowed_move_stances)
                self.assertTrue(str(entry.get("evidence") or "").strip())
                if entry["lifecycle_class"] == "unknown_pending_owner":
                    self.assertEqual(entry["move_stance"], "catalog_only")
                if entry["move_stance"] == "owner_gated_dry_run_only":
                    self.assertEqual(entry["lifecycle_class"], "historical_archive_candidate")

        hypothesis_manifest = _read_with_name_assignment(
            "src/enhengclaw/quant_research/hypothesis_batch.py",
            "HYPOTHESIS_BATCH_MANIFEST_PATH",
        )
        deterministic_manifest = _read_with_name_assignment(
            "src/enhengclaw/quant_research/deterministic_core.py",
            "DETERMINISTIC_STRATEGY_MANIFEST_PATH",
        )
        thesis_seed = _read_assignment_literal(
            "src/enhengclaw/quant_research/governance.py",
            "THESIS_TASK_SEED_FILENAME",
        )
        active_h10d_registry = _read_json("config/quant_research/active_h10d_registry.json")
        active_h10d_manifest = Path(active_h10d_registry["canonical_parent"]["manifest_path"]).name

        protected_classes = {
            hypothesis_manifest: "active_runtime_loaded",
            deterministic_manifest: "active_runtime_loaded",
            str(thesis_seed): "source_truth",
            active_h10d_manifest: "runtime_path_sensitive",
        }
        for file_name, lifecycle_class in protected_classes.items():
            with self.subTest(protected_file=file_name):
                self.assertIn(file_name, entry_by_file)
                self.assertEqual(entry_by_file[file_name]["lifecycle_class"], lifecycle_class)
                self.assertEqual(entry_by_file[file_name]["move_stance"], "do_not_move")

    def test_quant_research_binance_h10d_root_surface_classification_contract_stays_complete(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_root_surface_classification_contract.json"
        )
        required_groups = {
            "config_and_provider_entrypoints",
            "score_surface_and_feature_manifest",
            "archive_data_foundation_and_feature_panel",
            "pit_universe_and_eligibility",
            "funding_facade_entrypoints",
            "validation_orchestration_and_artifacts",
            "backtest_and_gap_policy",
            "attribution_and_paper_shadow",
            "ablations_and_feature_subset_rescore",
            "risk_brake_behavior",
            "falsification_and_holdout",
            "reporting_metric_sanitation",
            "root_local_partition_boundary",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_root_surface_classification_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "ast_root_function_classification_only")
        self.assertIn("owner-gated root-surface classification baseline", _read(contract["approved_by_matrix"]))

        tree = ast.parse(_read(contract["source_path"]), filename=contract["source_path"])
        source_functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(len(source_functions), contract["expected_root_function_count"])

        groups = contract["root_surface_groups"]
        self.assertEqual(set(groups), required_groups)
        seen_by_function: dict[str, str] = {}
        duplicate_functions: dict[str, list[str]] = {}
        for group_name, function_names in groups.items():
            self.assertRegex(group_name, r"^[a-z0-9_]+$")
            self.assertTrue(function_names)
            for function_name in function_names:
                if function_name in seen_by_function:
                    duplicate_functions.setdefault(function_name, [seen_by_function[function_name]]).append(group_name)
                seen_by_function[function_name] = group_name

        self.assertEqual(duplicate_functions, {})
        self.assertEqual(set(source_functions), set(seen_by_function))
        self.assertEqual(len(seen_by_function), contract["expected_root_function_count"])
        self.assertTrue(
            set(contract["owner_approval_required_before_source_move_groups"]).issubset(groups)
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("inspect.signature freeze", contract["excluded_surfaces"])
        self.assertIn("formula behavior", contract["excluded_surfaces"])
        self.assertIn("runtime execution", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])
        self.assertIn("line numbers", contract["excluded_surfaces"])
        self.assertIn("artifact schemas", contract["excluded_surfaces"])
        self.assertIn("markdown report content", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("backtest output", contract["excluded_surfaces"])
        self.assertIn("strategy pass/fail status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_config_provider_entrypoints_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_config_provider_entrypoints_contract.json"
        )
        expected_targets = {
            "load_strategy_config",
            "default_strategy_config",
            "discover_usdm_perp_symbols",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_config_provider_entrypoints_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_only_no_runtime_calls")
        self.assertIn("signature-only dry-run", _read(contract["approved_by_dry_run"]))
        self.assertEqual(set(contract["config_provider_entrypoint_targets"]), expected_targets)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        self.assertEqual(
            set(classification_contract["root_surface_groups"][classification_spec["required_group"]]),
            expected_targets,
        )

        cli_anchor = contract["required_cli_import_anchor"]
        self.assertIn(cli_anchor["import_text"], _read(cli_anchor["path"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for function_name, function_contract in contract["config_provider_entrypoint_targets"].items():
            with self.subTest(function_name=function_name):
                self.assertIn(function_name, source_symbols)
                function = getattr(module, function_name)
                self.assertEqual(_function_signature_contract(function), function_contract["signature"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("default config payload contents", contract["excluded_surfaces"])
        self.assertIn("DEFAULT_CONFIG_PATH changes", contract["excluded_surfaces"])
        self.assertIn("DEFAULT_STORE_ROOT changes", contract["excluded_surfaces"])
        self.assertIn("provider store scan behavior", contract["excluded_surfaces"])
        self.assertIn("real filesystem IO", contract["excluded_surfaces"])
        self.assertIn("runtime execution", contract["excluded_surfaces"])
        self.assertIn("strategy validation behavior", contract["excluded_surfaces"])
        self.assertIn("feature scoring behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_assertion_helpers_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_assertion_helpers_contract.json"
        )
        expected_targets = {
            "assert_alpha_feature_purity",
            "assert_alpha_feature_subset_purity",
            "_allow_feature_subset",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_assertion_helpers_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_tiny_assertion_samples")
        self.assertIn("tiny behavior dry-run", _read(contract["approved_by_dry_run"]))
        self.assertEqual(set(contract["assertion_helper_targets"]), expected_targets)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        classified = set(classification_contract["root_surface_groups"][classification_spec["required_group"]])
        self.assertTrue(expected_targets.issubset(classified))

        score_spec = contract["required_score_surface_contract"]
        score_contract = _read_json(score_spec["path"])
        self.assertEqual(score_contract["contract_version"], score_spec["contract_version"])
        self.assertIn(score_spec["required_validator_target"], score_contract["function_targets"])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["assertion_helper_targets"]
        for function_name, function_contract in targets.items():
            with self.subTest(function_name=function_name):
                self.assertIn(function_name, source_symbols)
                function = getattr(module, function_name)
                self.assertEqual(_function_signature_contract(function), function_contract["signature"])

        alpha_feature_purity = getattr(module, "assert_alpha_feature_purity")
        alpha_feature_purity(targets["assert_alpha_feature_purity"]["no_raise_feature_columns"])
        with self.assertRaisesRegex(
            ValueError,
            targets["assert_alpha_feature_purity"]["expected_error_substring"],
        ):
            alpha_feature_purity(targets["assert_alpha_feature_purity"]["raise_feature_columns"])

        subset_purity = getattr(module, "assert_alpha_feature_subset_purity")
        subset_purity(targets["assert_alpha_feature_subset_purity"]["no_raise_feature_columns"])
        with self.assertRaisesRegex(
            ValueError,
            targets["assert_alpha_feature_subset_purity"]["expected_error_substring"],
        ):
            subset_purity(targets["assert_alpha_feature_subset_purity"]["raise_feature_columns"])

        allow_feature_subset = getattr(module, "_allow_feature_subset")
        for sample in targets["_allow_feature_subset"]["sample_cases"]:
            with self.subTest(config=sample["config"]):
                self.assertEqual(allow_feature_subset(sample["config"]), sample["expected"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full score formula behavior", contract["excluded_surfaces"])
        self.assertIn("feature weights", contract["excluded_surfaces"])
        self.assertIn("feature allowlist edits", contract["excluded_surfaces"])
        self.assertIn("forbidden pattern edits", contract["excluded_surfaces"])
        self.assertIn("full score output snapshots", contract["excluded_surfaces"])
        self.assertIn("default config payload contents", contract["excluded_surfaces"])
        self.assertIn("feature_manifest_hash identity", contract["excluded_surfaces"])
        self.assertIn("backtest metrics", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("features.py scorer formulas", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_aggregate_1m_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_aggregate_1m_contract.json"
        )

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_aggregate_1m_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_tiny_in_memory_aggregation_samples",
        )
        self.assertIn("aggregate_1m_klines only", _read(contract["approved_by_plan"]))

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        self.assertIn(
            contract["aggregate_target"]["helper_name"],
            classification_contract["root_surface_groups"][classification_spec["required_group"]],
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["aggregate_target"]
        aggregate_1m_klines = getattr(module, target["helper_name"])
        self.assertIn(target["helper_name"], source_symbols)
        self.assertEqual(_function_signature_contract(aggregate_1m_klines), target["signature"])

        def minute_frame(sample: dict[str, object], minute_count: int) -> pd.DataFrame:
            start_ms = int(sample["start_open_time_ms"])
            rows = []
            for index in range(minute_count):
                open_time_ms = start_ms + index * 60_000
                rows.append(
                    {
                        "exchange": "binance",
                        "market_type": "usdm_perp",
                        "symbol": sample["symbol"],
                        "open_time_ms": open_time_ms,
                        "close_time_ms": open_time_ms + 59_999,
                        "open": 100.0 + index,
                        "high": 101.0 + index,
                        "low": 99.0 + index,
                        "close": 100.5 + index,
                        "volume": 1.0,
                        "quote_volume": 10.0,
                        "trade_count": 1,
                        "taker_buy_base_volume": 0.5,
                        "taker_buy_quote_volume": 5.0,
                    }
                )
            return pd.DataFrame(rows)

        complete_sample = target["complete_1h_sample"]
        complete_frame = minute_frame(complete_sample, int(complete_sample["minute_count"]))
        aggregated = aggregate_1m_klines(complete_frame, interval=complete_sample["interval"])
        self.assertEqual(len(aggregated), complete_sample["expected_row_count"])
        row = aggregated.iloc[0]
        self.assertEqual(int(row["open_time_ms"]), complete_sample["expected_open_time_ms"])
        self.assertEqual(int(row["close_time_ms"]), complete_sample["expected_close_time_ms"])
        self.assertEqual(float(row["open"]), complete_sample["expected_open"])
        self.assertEqual(float(row["high"]), complete_sample["expected_high"])
        self.assertEqual(float(row["low"]), complete_sample["expected_low"])
        self.assertEqual(float(row["close"]), complete_sample["expected_close"])
        self.assertEqual(float(row["volume"]), complete_sample["expected_volume"])
        self.assertEqual(float(row["quote_volume"]), complete_sample["expected_quote_volume"])
        self.assertEqual(int(row["trade_count"]), complete_sample["expected_trade_count"])
        self.assertEqual(float(row["taker_buy_base_volume"]), complete_sample["expected_taker_buy_base_volume"])
        self.assertEqual(float(row["taker_buy_quote_volume"]), complete_sample["expected_taker_buy_quote_volume"])
        self.assertEqual(int(row["expected_minute_count"]), complete_sample["expected_minute_count"])
        self.assertEqual(
            int(row["observed_minute_row_count"]),
            complete_sample["expected_observed_minute_row_count"],
        )
        self.assertEqual(int(row["unique_open_time_count"]), complete_sample["expected_unique_open_time_count"])
        self.assertEqual(bool(row["bar_complete"]), complete_sample["expected_bar_complete"])

        incomplete_sample = target["incomplete_1h_sample"]
        incomplete_count = int(complete_sample["minute_count"]) - int(incomplete_sample["drop_trailing_minutes"])
        incomplete_frame = minute_frame(complete_sample, incomplete_count)
        self.assertEqual(
            len(aggregate_1m_klines(incomplete_frame, interval=complete_sample["interval"])),
            incomplete_sample["expected_drop_incomplete_row_count"],
        )
        audited = aggregate_1m_klines(
            incomplete_frame,
            interval=complete_sample["interval"],
            drop_incomplete=False,
        )
        self.assertEqual(len(audited), incomplete_sample["expected_audit_row_count"])
        audit_row = audited.iloc[0]
        self.assertEqual(
            int(audit_row["observed_minute_row_count"]),
            incomplete_sample["expected_observed_minute_row_count"],
        )
        self.assertEqual(
            int(audit_row["unique_open_time_count"]),
            incomplete_sample["expected_unique_open_time_count"],
        )
        self.assertEqual(bool(audit_row["bar_complete"]), incomplete_sample["expected_bar_complete"])

        unsupported_sample = target["unsupported_interval_sample"]
        with self.assertRaisesRegex(ValueError, unsupported_sample["expected_error_substring"]):
            aggregate_1m_klines(complete_frame, interval=unsupported_sample["interval"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full OHLCV aggregation schema", contract["excluded_surfaces"])
        self.assertIn("all interval behavior", contract["excluded_surfaces"])
        self.assertIn("local archive path discovery", contract["excluded_surfaces"])
        self.assertIn("parquet or csv.gz reader behavior", contract["excluded_surfaces"])
        self.assertIn("build_symbol_feature_frame behavior", contract["excluded_surfaces"])
        self.assertIn("daily feature-panel behavior", contract["excluded_surfaces"])
        self.assertIn("build_binance_canonical_dataset behavior", contract["excluded_surfaces"])
        self.assertIn("feature formulas", contract["excluded_surfaces"])
        self.assertIn("target label construction", contract["excluded_surfaces"])
        self.assertIn("funding attachment", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_intraday_settlement_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_intraday_settlement_contract.json"
        )
        expected_targets = {"_intraday_realized_vol_by_day", "_settlement_premium_by_day"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_intraday_settlement_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_tiny_in_memory_intraday_settlement_samples",
        )
        self.assertIn("prior 4h close", _read(contract["approved_by_plan"]))
        self.assertIn("prior 1h close", _read(contract["approved_by_plan"]))

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        classified = set(classification_contract["root_surface_groups"][classification_spec["required_group"]])
        self.assertTrue(expected_targets.issubset(classified))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        intraday_target = contract["intraday_target"]
        settlement_target = contract["settlement_target"]
        intraday_helper = getattr(module, intraday_target["helper_name"])
        settlement_helper = getattr(module, settlement_target["helper_name"])
        for target in (intraday_target, settlement_target):
            with self.subTest(helper_name=target["helper_name"]):
                self.assertIn(target["helper_name"], source_symbols)
                self.assertEqual(
                    _function_signature_contract(getattr(module, target["helper_name"])),
                    target["signature"],
                )

        intraday_empty = intraday_helper(pd.DataFrame())
        self.assertEqual(list(intraday_empty.columns), intraday_target["empty_expected_columns"])
        settlement_empty = settlement_helper(pd.DataFrame())
        self.assertEqual(list(settlement_empty.columns), settlement_target["empty_expected_columns"])

        intraday_sample = intraday_target["complete_day_sample"]
        target_start = datetime.fromisoformat(intraday_sample["target_day_start_utc"]).astimezone(UTC)

        def four_h_frame(target_bar_count: int) -> pd.DataFrame:
            close = float(intraday_sample["initial_close"])
            rows = []
            anchor_time = target_start - timedelta(hours=int(intraday_sample["prior_anchor_hours"]))
            rows.append({"open_time_ms": int(anchor_time.timestamp() * 1000), "close": close})
            for index in range(target_bar_count):
                close *= math.exp(float(intraday_sample["log_return_per_bar"]))
                ts = target_start + timedelta(hours=4 * index)
                rows.append({"open_time_ms": int(ts.timestamp() * 1000), "close": close})
            return pd.DataFrame(rows)

        intraday_output = intraday_helper(four_h_frame(int(intraday_sample["target_bar_count"])))
        prior_row = intraday_output.loc[
            intraday_output["date_utc"].astype(str).eq(intraday_sample["expected_prior_date"])
        ].iloc[0]
        target_row = intraday_output.loc[
            intraday_output["date_utc"].astype(str).eq(intraday_sample["expected_target_date"])
        ].iloc[0]
        self.assertTrue(pd.isna(prior_row["intraday_realized_vol_4h_to_1d"]))
        self.assertAlmostEqual(
            float(target_row["intraday_realized_vol_4h_to_1d"]),
            float(intraday_sample["expected_target_value"]),
            places=15,
        )

        incomplete_sample = intraday_target["incomplete_day_sample"]
        incomplete_output = intraday_helper(four_h_frame(int(incomplete_sample["target_bar_count"])))
        incomplete_row = incomplete_output.loc[
            incomplete_output["date_utc"].astype(str).eq(incomplete_sample["expected_target_date"])
        ].iloc[0]
        self.assertTrue(pd.isna(incomplete_row["intraday_realized_vol_4h_to_1d"]))

        settlement_sample = settlement_target["rolling_sample"]
        settlement_start = datetime.fromisoformat(settlement_sample["target_start_utc"]).astimezone(UTC)
        settlement_hours = {int(item) for item in settlement_sample["settlement_hours_utc"]}
        close = float(settlement_sample["initial_close"])
        rows = [
            {
                "open_time_ms": int((settlement_start - timedelta(hours=1)).timestamp() * 1000),
                "close": close,
            }
        ]
        for hour_index in range(int(settlement_sample["day_count"]) * 24):
            ts = settlement_start + timedelta(hours=hour_index)
            log_return = (
                float(settlement_sample["settlement_log_return"])
                if ts.hour in settlement_hours
                else float(settlement_sample["other_hour_log_return"])
            )
            close *= math.exp(log_return)
            rows.append({"open_time_ms": int(ts.timestamp() * 1000), "close": close})
        settlement_output = settlement_helper(pd.DataFrame(rows))
        self.assertEqual(len(settlement_output), settlement_sample["expected_output_row_count"])
        self.assertEqual(
            int(settlement_output["settlement_cycle_premium_60d"].notna().sum()),
            settlement_sample["expected_non_null_count"],
        )
        self.assertTrue(
            pd.isna(
                settlement_output.loc[
                    settlement_output["date_utc"].astype(str).eq(settlement_sample["expected_prior_date"]),
                    "settlement_cycle_premium_60d",
                ].iloc[0]
            )
        )
        self.assertTrue(
            pd.isna(
                settlement_output.loc[
                    settlement_output["date_utc"].astype(str).eq(settlement_sample["expected_first_target_date"]),
                    "settlement_cycle_premium_60d",
                ].iloc[0]
            )
        )
        final_row = settlement_output.loc[
            settlement_output["date_utc"].astype(str).eq(settlement_sample["expected_final_date"])
        ].iloc[0]
        self.assertAlmostEqual(
            float(final_row["settlement_cycle_premium_60d"]),
            float(settlement_sample["expected_final_rolling_60d_premium"]),
            places=15,
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full feature-panel schema", contract["excluded_surfaces"])
        self.assertIn("add_binance_ohlcv_core_features behavior", contract["excluded_surfaces"])
        self.assertIn("score output", contract["excluded_surfaces"])
        self.assertIn("target label construction", contract["excluded_surfaces"])
        self.assertIn("local archive path discovery", contract["excluded_surfaces"])
        self.assertIn("archive reader behavior", contract["excluded_surfaces"])
        self.assertIn("funding attachment", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("build_symbol_feature_frame behavior", contract["excluded_surfaces"])
        self.assertIn("build_binance_canonical_dataset behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_archive_helpers_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_archive_helpers_contract.json"
        )
        expected_helpers = {
            "_read_kline_path",
            "_coerce_kline_frame",
            "symbol_to_subject",
            "_summarize_symbol_audits",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_archive_helpers_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_archive")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_archive.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_signature_tiny_archive_samples",
        )
        for implementation_plan in contract["implementation_plans"]:
            with self.subTest(implementation_plan=implementation_plan):
                self.assertIn("implementation plan", _read(implementation_plan).lower())
        self.assertIn("_read_kline_path", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])

        for constant_name, expected_values in contract["constant_targets"].items():
            with self.subTest(constant_name=constant_name):
                self.assertIn(constant_name, source_symbols)
                self.assertIn(constant_name, facade_symbols)
                source_value = getattr(source_module, constant_name)
                facade_value = getattr(facade_module, constant_name)
                self.assertIs(facade_value, source_value)
                self.assertEqual(list(source_value), expected_values)

        targets = contract["archive_helper_targets"]
        self.assertEqual(set(targets), expected_helpers)
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(_function_signature_contract(source_helper), helper_contract["signature"])

        read_kline_path = getattr(source_module, "_read_kline_path")
        csv_sample = targets["_read_kline_path"]["csv_gz_sample"]
        with tempfile.TemporaryDirectory() as temp_root:
            sample_path = Path(temp_root) / csv_sample["file_name"]
            with gzip.open(sample_path, "wt", encoding="utf-8", newline="") as handle:
                handle.write(csv_sample["csv_text"])
            actual_frame = read_kline_path(sample_path)
            expected_frame = pd.DataFrame(csv_sample["expected_records"])
            pd.testing.assert_frame_equal(actual_frame, expected_frame)

            unsupported_path = Path(temp_root) / targets["_read_kline_path"]["unsupported_file_name"]
            unsupported_path.write_text("not a supported archive", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                targets["_read_kline_path"]["unsupported_error_substring"],
            ):
                read_kline_path(unsupported_path)

        coerce_kline_frame = getattr(source_module, "_coerce_kline_frame")
        coerce_sample = targets["_coerce_kline_frame"]["coerce_sample"]
        frame = pd.DataFrame(coerce_sample["records"])
        self.assertIsNone(coerce_kline_frame(frame))
        for column, expected_values in coerce_sample["expected_numeric_values"].items():
            for row_index, expected_value in enumerate(expected_values):
                with self.subTest(column=column, row_index=row_index):
                    actual_value = frame.loc[row_index, column]
                    if expected_value is None:
                        self.assertTrue(pd.isna(actual_value))
                    else:
                        self.assertAlmostEqual(actual_value, expected_value)
        self.assertEqual(frame["unchanged"].tolist(), coerce_sample["expected_unchanged_values"])

        symbol_to_subject = getattr(source_module, "symbol_to_subject")
        for sample_name, sample in targets["symbol_to_subject"]["sample_cases"].items():
            with self.subTest(symbol_sample=sample_name):
                self.assertEqual(symbol_to_subject(sample["symbol"]), sample["expected_subject"])

        summarize_symbol_audits = getattr(source_module, "_summarize_symbol_audits")
        summary_sample = targets["_summarize_symbol_audits"]["summary_sample"]
        self.assertEqual(
            summarize_symbol_audits(summary_sample["symbol_audits"]),
            summary_sample["expected_summary"],
        )

        self.assertEqual(
            contract["deferred_targets"],
            [
                "_partition_month",
                "_symbol_partition_paths",
                "aggregate_1m_klines",
                "build_symbol_feature_frame",
                "build_binance_canonical_dataset",
                "funding loaders",
                "PIT universe helpers",
            ],
        )
        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("_partition_month archive/funding boundary", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("funding load behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("full archive schemas", contract["excluded_surfaces"])
        self.assertIn("parquet engine behavior", contract["excluded_surfaces"])
        self.assertIn("archive partition discovery", contract["excluded_surfaces"])
        self.assertIn("aggregate_1m_klines behavior", contract["excluded_surfaces"])
        self.assertIn("build_symbol_feature_frame behavior", contract["excluded_surfaces"])
        self.assertIn("build_binance_canonical_dataset behavior", contract["excluded_surfaces"])
        self.assertIn("gap-audit field expansion", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_partition_boundary_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_partition_boundary_contract.json"
        )
        expected_targets = {"_partition_month", "_symbol_partition_paths"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_partition_boundary_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["archive_module"], "enhengclaw.quant_research._binance_canonical_archive")
        self.assertEqual(contract["archive_path"], "src/enhengclaw/quant_research/_binance_canonical_archive.py")
        self.assertEqual(contract["validation_mode"], "root_local_signature_partition_samples")
        self.assertIn("_partition_month", _read(contract["approved_by_dry_run"]))
        self.assertIn("root-local freeze", _read(contract["owner_decision"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        archive_symbols = _read_module_level_symbols(str(contract["archive_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["root_local_targets"]
        self.assertEqual(set(targets), expected_targets)
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertNotIn(helper_name, archive_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        partition_month = getattr(module, "_partition_month")
        for sample_name, sample in targets["_partition_month"]["sample_cases"].items():
            with self.subTest(partition_month_sample=sample_name):
                self.assertEqual(
                    partition_month(Path(sample["path_name"])),
                    sample["expected_month"],
                )

        symbol_partition_paths = getattr(module, "_symbol_partition_paths")
        window_sample = targets["_symbol_partition_paths"]["window_sample"]
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            archive_root = (
                temp_path
                / "data"
                / getattr(module, "MARKET_TYPE")
                / window_sample["symbol"].upper()
                / getattr(module, "INTERVAL_1M")
            )
            archive_root.mkdir(parents=True)
            for file_name in window_sample["created_file_names"]:
                (archive_root / file_name).touch()
            actual_names = [
                path.name
                for path in symbol_partition_paths(
                    store_root=temp_path,
                    symbol=window_sample["symbol"],
                    start_month=window_sample["start_month"],
                    end_month=window_sample["end_month"],
                )
            ]
            self.assertEqual(actual_names, window_sample["expected_file_names"])

        for forbidden_symbol in contract["forbidden_archive_symbols"]:
            with self.subTest(forbidden_archive_symbol=forbidden_symbol):
                self.assertNotIn(forbidden_symbol, archive_symbols)

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        archive_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_archive_helpers_contract.json"
        ]
        archive_contract = _read_json(archive_spec["path"])
        self.assertEqual(archive_contract["contract_version"], archive_spec["contract_version"])
        self.assertIn(archive_spec["must_defer_target"], archive_contract["deferred_targets"])
        self.assertIn(archive_spec["must_exclude_surface"], archive_contract["excluded_surfaces"])

        funding_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_funding_facade_contract.json"
        ]
        funding_contract = _read_json(funding_spec["path"])
        self.assertEqual(funding_contract["contract_version"], funding_spec["contract_version"])
        self.assertIn(funding_spec["must_exclude_surface"], funding_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("neutral partition helper implementation", contract["excluded_surfaces"])
        self.assertIn("archive module expansion", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("funding load behavior", contract["excluded_surfaces"])
        self.assertIn("funding partition naming changes", contract["excluded_surfaces"])
        self.assertIn("UTC month boundary math", contract["excluded_surfaces"])
        self.assertIn("archive store layout changes", contract["excluded_surfaces"])
        self.assertIn("Binance upstream archive filename parsing", contract["excluded_surfaces"])
        self.assertIn("parquet or csv.gz reader behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_funding_facade_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_funding_facade_contract.json"
        )
        expected_facade_candidates = {
            "_funding_columns",
            "funding_symbol_root",
            "funding_partition_path",
            "funding_symbol_manifest_path",
            "funding_sync_summary_path",
            "_read_funding_partition",
            "_dedupe_funding_rows",
            "_http_get_json",
            "_resolve_funding_root",
            "_month_key_from_ms",
            "_month_start_ms",
            "_month_end_ms",
        }
        expected_entrypoints = {
            "sync_funding_cost_history",
            "fetch_funding_rate_rows",
            "write_funding_cost_rows",
            "load_funding_cost_daily",
            "attach_funding_cost_to_panel",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_funding_facade_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(set(contract["facade_candidate_targets"]), expected_facade_candidates)
        self.assertEqual(set(contract["protected_entrypoints"]), expected_entrypoints)
        self.assertEqual(
            contract["required_behavior_test"],
            "tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_funding_cost_sync_writes_daily_cost_only_rows_and_attaches_to_panel",
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for entrypoint in expected_entrypoints:
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, source_symbols)
                self.assertTrue(callable(getattr(module, entrypoint)))
        for helper_name, helper_contract in contract["facade_candidate_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract)

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("provider HTTP behavior", contract["excluded_surfaces"])
        self.assertIn("funding formula behavior", contract["excluded_surfaces"])
        self.assertIn("PIT eligibility behavior", contract["excluded_surfaces"])
        self.assertIn("_partition_month archive/funding boundary", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_funding_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_funding_module_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_funding_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_funding")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_funding.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_tiny_path_month_samples",
        )
        self.assertIn("_binance_canonical_funding.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        funding_facade_contract = _read_json(signature_source["path"])
        self.assertEqual(funding_facade_contract["contract_version"], signature_source["contract_version"])
        expected_targets = set(funding_facade_contract["facade_candidate_targets"])
        self.assertEqual(set(contract["funding_module_targets"]), expected_targets)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["funding_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(
                    _function_signature_contract(source_helper),
                    funding_facade_contract["facade_candidate_targets"][helper_name],
                )

        self.assertEqual(source_module._funding_columns(), contract["funding_columns_sample"])

        path_sample = contract["path_sample"]
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            funding_root = temp_path / path_sample["funding_root_child"]
            symbol = path_sample["symbol"]
            month = path_sample["month"]

            symbol_root = source_module.funding_symbol_root(funding_root, symbol=symbol)
            partition_path = source_module.funding_partition_path(funding_root, symbol=symbol, month=month)
            manifest_path = source_module.funding_symbol_manifest_path(funding_root, symbol=symbol)
            summary_path = source_module.funding_sync_summary_path(funding_root)
            self.assertEqual(symbol_root.relative_to(temp_path).as_posix(), path_sample["expected_symbol_root"])
            self.assertEqual(partition_path.relative_to(temp_path).as_posix(), path_sample["expected_partition_path"])
            self.assertEqual(manifest_path.relative_to(temp_path).as_posix(), path_sample["expected_manifest_path"])
            self.assertEqual(summary_path.relative_to(temp_path).as_posix(), path_sample["expected_summary_path"])

            resolve_sample = contract["resolve_root_sample"]
            explicit_root = temp_path / resolve_sample["explicit_root_child"]
            configured_root = temp_path / resolve_sample["configured_root_child"]
            self.assertEqual(
                source_module._resolve_funding_root(config={}, funding_root=explicit_root),
                explicit_root,
            )
            self.assertEqual(
                source_module._resolve_funding_root(
                    config={"funding_cost_root": str(configured_root)},
                    funding_root=None,
                ),
                configured_root,
            )

        month_samples = contract["month_samples"]
        self.assertEqual(
            source_module._month_key_from_ms(month_samples["timestamp_ms"]),
            month_samples["expected_month_key"],
        )
        self.assertEqual(
            source_module._month_start_ms(month_samples["month"]),
            month_samples["expected_start_ms"],
        )
        self.assertEqual(
            source_module._month_end_ms(month_samples["month"]),
            month_samples["expected_end_ms"],
        )

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("provider HTTP behavior", contract["excluded_surfaces"])
        self.assertIn("HTTP retry semantics", contract["excluded_surfaces"])
        self.assertIn("live Binance API behavior", contract["excluded_surfaces"])
        self.assertIn("full sync_funding_cost_history behavior", contract["excluded_surfaces"])
        self.assertIn("full load_funding_cost_daily behavior", contract["excluded_surfaces"])
        self.assertIn("_read_funding_partition IO snapshots", contract["excluded_surfaces"])
        self.assertIn("_dedupe_funding_rows row semantics", contract["excluded_surfaces"])
        self.assertIn("funding formula behavior", contract["excluded_surfaces"])
        self.assertIn("funding root relocation", contract["excluded_surfaces"])
        self.assertIn("funding partition naming changes beyond tiny sample", contract["excluded_surfaces"])
        self.assertIn("CSV compression changes", contract["excluded_surfaces"])
        self.assertIn("_partition_month archive/funding boundary", contract["excluded_surfaces"])
        self.assertIn("neutral partition helper implementation", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_hash_identity_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_hash_identity_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_hash_identity_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_identity_samples")

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        stable_hash = getattr(module, contract["stable_hash_target"]["helper_name"])
        stable_int = getattr(module, contract["stable_int_target"]["helper_name"])
        self.assertIn("_stable_hash", source_symbols)
        self.assertIn("_stable_int", source_symbols)
        self.assertEqual(
            _function_signature_contract(stable_hash),
            contract["stable_hash_target"]["signature"],
        )
        self.assertEqual(
            _function_signature_contract(stable_int),
            contract["stable_int_target"]["signature"],
        )

        for sample_name, sample in contract["stable_hash_target"]["sample_payloads"].items():
            with self.subTest(sample_name=sample_name):
                self.assertEqual(stable_hash(sample["payload"]), sample["expected_sha256"])

        for subject, expected in contract["stable_int_target"]["subject_buckets"].items():
            with self.subTest(subject=subject):
                actual_int = stable_int(subject)
                actual_mod = actual_int % 2
                actual_bucket = "holdout_a" if actual_mod == 0 else "holdout_b"
                self.assertEqual(actual_int, expected["expected_int"])
                self.assertEqual(actual_mod, expected["expected_mod_2"])
                self.assertEqual(actual_bucket, expected["expected_holdout_bucket"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("falsification metrics", contract["excluded_surfaces"])
        self.assertIn("backtest output", contract["excluded_surfaces"])
        self.assertIn("subject normalization", contract["excluded_surfaces"])
        self.assertIn("other module hash helpers", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_identity_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_identity_module_contract.json"
        )
        expected_helpers = {"_stable_hash", "_stable_int"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_identity_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_identity")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_identity.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_existing_contract_samples",
        )
        self.assertIn("_binance_canonical_identity.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        hash_contract = _read_json(signature_source["path"])
        self.assertEqual(hash_contract["contract_version"], signature_source["contract_version"])
        self.assertEqual(set(contract["identity_module_targets"]), expected_helpers)
        self.assertEqual(
            {
                hash_contract["stable_hash_target"]["helper_name"],
                hash_contract["stable_int_target"]["helper_name"],
            },
            expected_helpers,
        )

        expected_signatures = {
            hash_contract["stable_hash_target"]["helper_name"]: hash_contract["stable_hash_target"]["signature"],
            hash_contract["stable_int_target"]["helper_name"]: hash_contract["stable_int_target"]["signature"],
        }
        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["identity_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(source_helper.__module__, contract["source_module"])
                self.assertEqual(_function_signature_contract(source_helper), expected_signatures[helper_name])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full feature manifest content", contract["excluded_surfaces"])
        self.assertIn("falsification metrics", contract["excluded_surfaces"])
        self.assertIn("backtest output", contract["excluded_surfaces"])
        self.assertIn("pass/fail decisions", contract["excluded_surfaces"])
        self.assertIn("subject normalization", contract["excluded_surfaces"])
        self.assertIn("other module hash helpers", contract["excluded_surfaces"])
        self.assertIn("generic repo-wide hash utility migration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_datetime_boundary_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_datetime_boundary_contract.json"
        )
        expected_helpers = {"_parse_date", "_date_to_ms", "_ms_to_date", "_date_utc_series"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_datetime_boundary_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_utc_identity_samples")
        self.assertEqual(set(contract["datetime_boundary_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["datetime_boundary_targets"]
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        parse_date = getattr(module, "_parse_date")
        for sample_name, sample in targets["_parse_date"]["sample_cases"].items():
            with self.subTest(sample_name=sample_name):
                input_kind = sample["input_kind"]
                if input_kind == "iso_date_string":
                    value = sample["value"]
                elif input_kind == "date_object":
                    value = date.fromisoformat(sample["value"])
                elif input_kind == "aware_datetime_utc":
                    value = datetime.fromisoformat(sample["value"]).astimezone(UTC)
                else:
                    raise AssertionError(f"Unsupported _parse_date sample kind: {input_kind}")
                self.assertEqual(parse_date(value).isoformat(), sample["expected_iso_date"])

        date_to_ms = getattr(module, "_date_to_ms")
        for sample_name, sample in targets["_date_to_ms"]["sample_cases"].items():
            with self.subTest(sample_name=sample_name):
                self.assertEqual(date_to_ms(date.fromisoformat(sample["input_iso_date"])), sample["expected_ms"])

        ms_to_date = getattr(module, "_ms_to_date")
        for sample_name, sample in targets["_ms_to_date"]["sample_cases"].items():
            with self.subTest(sample_name=sample_name):
                self.assertEqual(ms_to_date(sample["input_ms"]).isoformat(), sample["expected_iso_date"])

        date_utc_series = getattr(module, "_date_utc_series")
        series_sample = targets["_date_utc_series"]["sample_case"]
        self.assertEqual(
            date_utc_series(pd.Series(series_sample["input_values"])).tolist(),
            series_sample["expected_values"],
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("naive datetime behavior changes", contract["excluded_surfaces"])
        self.assertIn("missing timestamp behavior changes", contract["excluded_surfaces"])
        self.assertIn("downstream validation metrics", contract["excluded_surfaces"])
        self.assertIn("funding behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_time_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_time_module_contract.json"
        )
        expected_helpers = {"_parse_date", "_date_to_ms", "_ms_to_date", "_date_utc_series"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_time_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_time")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_time.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_existing_contract_samples",
        )
        self.assertIn("_binance_canonical_time.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        datetime_contract = _read_json(signature_source["path"])
        self.assertEqual(datetime_contract["contract_version"], signature_source["contract_version"])
        self.assertEqual(set(contract["time_module_targets"]), expected_helpers)
        self.assertEqual(set(datetime_contract["datetime_boundary_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["time_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(source_helper.__module__, contract["source_module"])
                self.assertEqual(
                    _function_signature_contract(source_helper),
                    datetime_contract["datetime_boundary_targets"][helper_name]["signature"],
                )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("accepted _parse_date input type expansion", contract["excluded_surfaces"])
        self.assertIn("naive datetime behavior changes", contract["excluded_surfaces"])
        self.assertIn("missing timestamp behavior changes", contract["excluded_surfaces"])
        self.assertIn("downstream validation metrics", contract["excluded_surfaces"])
        self.assertIn("backtest output", contract["excluded_surfaces"])
        self.assertIn("funding behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("artifact schemas", contract["excluded_surfaces"])
        self.assertIn("generic repo-wide time utility migration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_artifact_writer_helpers_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.json"
        )
        expected_helpers = {"_write_json", "_frame_or_empty"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.v2",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_helper_behavior_samples")
        self.assertEqual(set(contract["artifact_writer_targets"]), expected_helpers)
        self.assertEqual(contract["governed_elsewhere_targets"], ["_write_universe_membership"])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["artifact_writer_targets"]
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        write_json = getattr(module, "_write_json")
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            for sample_name, sample in targets["_write_json"]["sample_payloads"].items():
                with self.subTest(sample_name=sample_name):
                    payload = sample["payload"]
                    if sample.get("payload_kind") == "date_default_str":
                        payload = {"as_of": date.fromisoformat(payload["as_of"])}
                    output_path = temp_path / sample_name / "payload.json"
                    write_json(output_path, payload)
                    self.assertEqual(output_path.read_text(encoding="utf-8"), sample["expected_text"])

        frame_or_empty = getattr(module, "_frame_or_empty")
        frame_sample = targets["_frame_or_empty"]["sample_frame"]
        frame = pd.DataFrame(frame_sample["records"], columns=frame_sample["columns"])
        copied = frame_or_empty(frame)
        self.assertIsNot(copied, frame)
        pd.testing.assert_frame_equal(copied, frame)
        self.assertTrue(frame_or_empty(None).empty)
        self.assertTrue(frame_or_empty({"not": "a frame"}).empty)

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full artifact schemas", contract["excluded_surfaces"])
        self.assertIn("output path selection", contract["excluded_surfaces"])
        self.assertIn("markdown report content", contract["excluded_surfaces"])
        self.assertIn("funding sync semantics", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("universe membership column schema", contract["excluded_surfaces"])
        self.assertIn("risk-brake column ownership", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_universe_membership_writer_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json"
        )
        expected_risk_columns = [
            "binance_short_squeeze_veto_multiplier",
            "binance_high_vol_rebound_short_multiplier",
            "binance_risk_brake_short_multiplier",
            "binance_short_squeeze_veto_flag",
            "binance_high_vol_rebound_flag",
            "binance_high_vol_rebound_severe_flag",
            "binance_market_realized_vol_5_median",
            "binance_market_realized_vol_5_threshold",
            "binance_market_momentum_20_median",
            "binance_market_positive_momentum_share_20",
            "binance_market_close_to_high_share_5",
        ]

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_column_registry_signature_projection_sample")
        self.assertEqual(contract["risk_brake_columns"], expected_risk_columns)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertIn("BINANCE_RISK_BRAKE_COLUMNS", source_symbols)
        self.assertEqual(list(getattr(module, "BINANCE_RISK_BRAKE_COLUMNS")), expected_risk_columns)

        target = contract["universe_membership_target"]
        helper_name = target["helper_name"]
        self.assertIn(helper_name, source_symbols)
        write_universe_membership = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(write_universe_membership), target["signature"])

        sample = target["projection_sort_sample"]
        with tempfile.TemporaryDirectory() as temp_root:
            output_path = Path(temp_root) / "universe_membership.csv"
            write_universe_membership(pd.DataFrame(sample["records"]), output_path)
            self.assertEqual(output_path.read_text(encoding="utf-8"), sample["expected_csv"])

        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("full universe membership schema", contract["excluded_surfaces"])
        self.assertIn("empty-frame full schema behavior", contract["excluded_surfaces"])
        self.assertIn("validation artifact path selection", contract["excluded_surfaces"])
        self.assertIn("strategy pass/fail metrics", contract["excluded_surfaces"])
        self.assertIn("feature subset behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_risk_columns_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_risk_columns_module_contract.json"
        )
        helper_name = "BINANCE_RISK_BRAKE_COLUMNS"

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_risk_columns_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_risk_columns")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_risk_columns.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_registry_identity_existing_contract_samples",
        )
        self.assertEqual(contract["risk_column_registry_target"], helper_name)
        self.assertIn("_binance_canonical_risk_columns.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        writer_contract = _read_json(signature_source["path"])
        self.assertEqual(writer_contract["contract_version"], signature_source["contract_version"])
        self.assertEqual(
            writer_contract["approved_registry_module_after_move"],
            signature_source["required_approved_registry_module_after_move"],
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        self.assertIn(helper_name, source_symbols)
        self.assertIn(helper_name, facade_symbols)
        source_columns = getattr(source_module, helper_name)
        facade_columns = getattr(facade_module, helper_name)
        self.assertIs(facade_columns, source_columns)
        self.assertEqual(list(source_columns), writer_contract["risk_brake_columns"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("full universe membership schema", contract["excluded_surfaces"])
        self.assertIn("empty-frame full schema behavior", contract["excluded_surfaces"])
        self.assertIn("validation artifact path selection", contract["excluded_surfaces"])
        self.assertIn("strategy pass/fail metrics", contract["excluded_surfaces"])
        self.assertIn("feature subset behavior", contract["excluded_surfaces"])
        self.assertIn("generic repo-wide risk column registry migration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_artifacts_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_artifacts_module_contract.json"
        )
        expected_targets = {"_write_json", "_frame_or_empty", "_write_universe_membership"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_artifacts_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_artifacts")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_artifacts.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_existing_contract_samples",
        )
        self.assertIn("_write_universe_membership", _read(contract["approved_by_review"]))
        self.assertEqual(set(contract["artifact_module_targets"]), expected_targets)

        expected_signatures: dict[str, dict[str, object]] = {}
        for spec in contract["signature_source_contracts"]:
            with self.subTest(signature_source_contract=spec["path"]):
                source_contract = _read_json(spec["path"])
                self.assertEqual(source_contract["contract_version"], spec["contract_version"])
                if "artifact_writer_targets" in source_contract:
                    for target in spec["targets"]:
                        expected_signatures[target] = source_contract["artifact_writer_targets"][target]["signature"]
                else:
                    writer_target = source_contract["universe_membership_target"]
                    self.assertEqual(spec["targets"], [writer_target["helper_name"]])
                    self.assertEqual(
                        source_contract["approved_writer_module_after_move"],
                        spec["required_writer_module"],
                    )
                    expected_signatures[writer_target["helper_name"]] = writer_target["signature"]
        self.assertEqual(set(expected_signatures), expected_targets)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["artifact_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(source_helper.__module__, contract["source_module"])
                self.assertEqual(_function_signature_contract(source_helper), expected_signatures[helper_name])

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        universe_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json"
        ]
        universe_contract = _read_json(universe_spec["path"])
        self.assertEqual(universe_contract["contract_version"], universe_spec["contract_version"])
        self.assertIn(universe_spec["must_exclude_surface"], universe_contract["excluded_surfaces"])

        artifact_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.json"
        ]
        artifact_contract = _read_json(artifact_spec["path"])
        self.assertEqual(artifact_contract["contract_version"], artifact_spec["contract_version"])
        self.assertIn(
            artifact_spec["must_govern_elsewhere_target"],
            artifact_contract["governed_elsewhere_targets"],
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("full artifact schemas", contract["excluded_surfaces"])
        self.assertIn("output path selection", contract["excluded_surfaces"])
        self.assertIn("report path ownership", contract["excluded_surfaces"])
        self.assertIn("markdown report content", contract["excluded_surfaces"])
        self.assertIn("funding sync semantics", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("risk-brake column ownership changes", contract["excluded_surfaces"])
        self.assertIn("CSV writer settings outside existing samples", contract["excluded_surfaces"])
        self.assertIn("universe membership full schema", contract["excluded_surfaces"])
        self.assertIn("write_validation_artifacts orchestration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_run_metadata_helpers_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract.json"
        )
        expected_helpers = {"utc_now", "_default_run_id", "_today_compact"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_format_samples")
        self.assertEqual(set(contract["run_metadata_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["run_metadata_targets"]
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        utc_now_value = getattr(module, "utc_now")()
        self.assertRegex(utc_now_value, targets["utc_now"]["output_regex"])

        default_run_id_contract = targets["_default_run_id"]
        run_id = getattr(module, "_default_run_id")(
            strategy_label=default_run_id_contract["sample_strategy_label"]
        )
        self.assertRegex(run_id, default_run_id_contract["output_regex"])
        self.assertTrue(run_id.endswith(f"-{default_run_id_contract['expected_label_suffix']}"))

        today_compact = getattr(module, "_today_compact")()
        self.assertRegex(today_compact, targets["_today_compact"]["output_regex"])

        self.assertIn("exact timestamp values", contract["excluded_surfaces"])
        self.assertIn("clock source replacement", contract["excluded_surfaces"])
        self.assertIn("output root selection", contract["excluded_surfaces"])
        self.assertIn("artifact path ownership", contract["excluded_surfaces"])
        self.assertIn("markdown report content", contract["excluded_surfaces"])
        self.assertIn("validation report payload structure", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("strategy pass/fail status", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("dataset or feature manifest schemas", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_run_metadata_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_run_metadata_module_contract.json"
        )
        expected_helpers = {"utc_now", "_default_run_id", "_today_compact"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_run_metadata_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_run_metadata")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_run_metadata.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_existing_contract_samples",
        )
        self.assertIn("_binance_canonical_run_metadata.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        run_metadata_contract = _read_json(signature_source["path"])
        self.assertEqual(run_metadata_contract["contract_version"], signature_source["contract_version"])
        self.assertEqual(
            run_metadata_contract["approved_module_after_move"],
            signature_source["required_approved_module_after_move"],
        )
        self.assertEqual(set(contract["run_metadata_module_targets"]), expected_helpers)
        self.assertEqual(set(run_metadata_contract["run_metadata_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["run_metadata_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(source_helper.__module__, contract["source_module"])
                self.assertEqual(
                    _function_signature_contract(source_helper),
                    run_metadata_contract["run_metadata_targets"][helper_name]["signature"],
                )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("exact timestamp values", contract["excluded_surfaces"])
        self.assertIn("clock source replacement", contract["excluded_surfaces"])
        self.assertIn("output root selection", contract["excluded_surfaces"])
        self.assertIn("artifact path ownership", contract["excluded_surfaces"])
        self.assertIn("markdown report content", contract["excluded_surfaces"])
        self.assertIn("validation report payload structure", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("strategy pass/fail status", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("dataset or feature manifest schemas", contract["excluded_surfaces"])
        self.assertIn("generic repo-wide time utility migration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_timestamp_normalization_helpers_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_timestamp_normalization_helpers_contract.json"
        )
        expected_helpers = {"_timestamp_zscore", "_timestamp_percentile_rank"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_timestamp_normalization_helpers_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_behavior_samples")
        self.assertEqual(set(contract["timestamp_normalization_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["timestamp_normalization_targets"]
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])
                sample = helper_contract["sample"]
                actual = helper(pd.Series(sample["values"]), pd.Series(sample["timestamps"]))
                expected = pd.Series(sample["expected_values"], dtype="float64")
                pd.testing.assert_series_equal(actual.reset_index(drop=True), expected, check_exact=False, atol=1e-12)

        self.assertIn("features.py helper behavior", contract["excluded_surfaces"])
        self.assertIn("full alpha formula behavior", contract["excluded_surfaces"])
        self.assertIn("score_binance_ohlcv_core_alpha output snapshots", contract["excluded_surfaces"])
        self.assertIn("feature weights", contract["excluded_surfaces"])
        self.assertIn("feature subset selection", contract["excluded_surfaces"])
        self.assertIn("backtest metrics", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("risk-brake behavior", contract["excluded_surfaces"])
        self.assertIn("partition or month-key helpers", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_normalization_module_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_normalization_module_contract.json"
        )
        expected_helpers = {"_timestamp_zscore", "_timestamp_percentile_rank"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_normalization_module_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_normalization")
        self.assertEqual(
            contract["source_path"],
            "src/enhengclaw/quant_research/_binance_canonical_normalization.py",
        )
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_identity_existing_contract_samples",
        )
        self.assertIn("_binance_canonical_normalization.py", _read(contract["approved_by_review"]))

        signature_source = contract["signature_source_contract"]
        normalization_contract = _read_json(signature_source["path"])
        self.assertEqual(normalization_contract["contract_version"], signature_source["contract_version"])
        self.assertEqual(
            normalization_contract["approved_module_after_move"],
            signature_source["required_approved_module_after_move"],
        )
        self.assertEqual(set(contract["normalization_module_targets"]), expected_helpers)
        self.assertEqual(set(normalization_contract["timestamp_normalization_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        for helper_name in contract["normalization_module_targets"]:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(source_helper.__module__, contract["source_module"])
                self.assertEqual(
                    _function_signature_contract(source_helper),
                    normalization_contract["timestamp_normalization_targets"][helper_name]["signature"],
                )

        self.assertIn("features.py helper behavior", contract["excluded_surfaces"])
        self.assertIn("full alpha formula behavior", contract["excluded_surfaces"])
        self.assertIn("score_binance_ohlcv_core_alpha output snapshots", contract["excluded_surfaces"])
        self.assertIn("feature weights", contract["excluded_surfaces"])
        self.assertIn("feature subset selection", contract["excluded_surfaces"])
        self.assertIn("backtest metrics", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("risk-brake behavior", contract["excluded_surfaces"])
        self.assertIn("partition or month-key helpers", contract["excluded_surfaces"])
        self.assertIn("generic repo-wide normalization utility migration", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_score_surface_behavior_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_score_surface_behavior_contract.json"
        )
        expected_functions = {
            "validate_alpha_feature_columns",
            "build_feature_manifest",
            "score_binance_ohlcv_core",
            "prepare_scored_backtest_frame",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_score_surface_behavior_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_allowlist_tiny_behavior_samples")
        self.assertEqual(set(contract["function_targets"]), expected_functions)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for function_name, function_contract in contract["function_targets"].items():
            with self.subTest(function_name=function_name):
                self.assertIn(function_name, source_symbols)
                function = getattr(module, function_name)
                self.assertEqual(_function_signature_contract(function), function_contract["signature"])

        constants = contract["constant_targets"]
        allowed_features = constants["ALLOWED_ALPHA_FEATURES"]
        feature_weights = constants["BINANCE_OHLCV_CORE_WEIGHTS"]
        self.assertIn("ALLOWED_ALPHA_FEATURES", source_symbols)
        self.assertIn("BINANCE_OHLCV_CORE_WEIGHTS", source_symbols)
        self.assertEqual(list(getattr(module, "ALLOWED_ALPHA_FEATURES")), allowed_features)
        self.assertEqual(dict(getattr(module, "BINANCE_OHLCV_CORE_WEIGHTS")), feature_weights)

        purity_samples = contract["purity_samples"]
        sidecar_column = purity_samples["forbidden_sidecar_column"]
        sidecar_purity = module.validate_alpha_feature_columns([*allowed_features, sidecar_column])
        self.assertFalse(sidecar_purity["passed"])
        self.assertEqual(sidecar_purity["forbidden_columns"], [sidecar_column])
        self.assertEqual(sidecar_purity["unexpected_columns"], [sidecar_column])

        subset_count = purity_samples["strict_subset_feature_count"]
        subset_features = allowed_features[:subset_count]
        expected_missing = purity_samples["expected_strict_subset_missing_columns"]
        strict_subset_purity = module.validate_alpha_feature_columns(subset_features)
        relaxed_subset_purity = module.validate_alpha_feature_columns(
            subset_features,
            require_all_allowed=False,
        )
        self.assertFalse(strict_subset_purity["passed"])
        self.assertEqual(strict_subset_purity["missing_columns"], expected_missing)
        self.assertTrue(relaxed_subset_purity["passed"])
        self.assertEqual(relaxed_subset_purity["missing_columns"], expected_missing)

        score_sample = contract["score_sample"]
        records = []
        for row_spec in score_sample["base_rows"]:
            row = {
                "subject": row_spec["subject"],
                "timestamp_ms": row_spec["timestamp_ms"],
            }
            for feature_name, offset in score_sample["feature_value_offsets"].items():
                row[feature_name] = float(row_spec["base"]) + float(offset)
            records.append(row)
        frame = pd.DataFrame(records)
        expected_score = pd.Series(score_sample["expected_scores"], index=frame.index, dtype="float64")
        actual_score = module.score_binance_ohlcv_core(frame)
        pd.testing.assert_series_equal(actual_score, expected_score, check_exact=False, atol=1e-12)

        sidecar_frame = frame.copy()
        sidecar_frame[score_sample["sidecar_column"]] = score_sample["sidecar_values"]
        sidecar_score = module.score_binance_ohlcv_core(sidecar_frame)
        pd.testing.assert_series_equal(sidecar_score, expected_score, check_exact=False, atol=1e-12)

        manifest_sample = contract["manifest_sample"]
        manifest = module.build_feature_manifest(config=manifest_sample["config"])
        self.assertEqual(manifest["strategy_label"], manifest_sample["config"]["strategy_label"])
        self.assertEqual(manifest["parent_label"], manifest_sample["config"]["parent_label"])
        self.assertEqual(manifest["feature_columns"], manifest_sample["config"]["feature_columns"])
        self.assertEqual(manifest["raw_parent_weight_subset"], manifest_sample["expected_raw_parent_weight_subset"])
        for feature_name, expected_weight in manifest_sample["expected_feature_weights"].items():
            self.assertAlmostEqual(manifest["feature_weights"][feature_name], expected_weight, places=15)
        self.assertEqual(manifest["purity_check"]["passed"], manifest_sample["expected_purity_passed"])
        self.assertIn("generated_at_utc", manifest)
        self.assertIn("feature_manifest_hash", manifest)
        self.assertFalse(manifest_sample["assert_feature_manifest_hash_identity"])
        self.assertFalse(manifest_sample["assert_generated_at_exact"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("full score formula behavior", contract["excluded_surfaces"])
        self.assertIn("feature_manifest_hash identity", contract["excluded_surfaces"])
        self.assertIn("exact generated_at_utc values", contract["excluded_surfaces"])
        self.assertIn("backtest metrics", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("features.py scorer formulas", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_reporting_metric_sanitation_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json"
        )
        expected_helpers = {
            "_rank_ic_summary",
            "_strip_periods",
            "_drop_periods_from_metrics",
            "_split_contract",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_reporting_sanitation_samples")
        self.assertEqual(set(contract["reporting_metric_sanitation_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        targets = contract["reporting_metric_sanitation_targets"]
        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        rank_ic_summary = getattr(module, "_rank_ic_summary")
        rank_sample = targets["_rank_ic_summary"]["sample"]
        rank_summary = rank_ic_summary(
            pd.DataFrame(rank_sample["records"]),
            score_column=rank_sample["score_column"],
            target_column=rank_sample["target_column"],
        )
        for key, expected_value in rank_sample["expected_summary"].items():
            self.assertAlmostEqual(rank_summary[key], expected_value, places=15)

        empty_rank_summary = rank_ic_summary(
            pd.DataFrame(),
            score_column=rank_sample["score_column"],
            target_column=rank_sample["target_column"],
        )
        self.assertEqual(empty_rank_summary, rank_sample["expected_empty_summary"])

        strip_periods = getattr(module, "_strip_periods")
        strip_sample = targets["_strip_periods"]["sample"]
        self.assertEqual(strip_periods(strip_sample["metrics"]), strip_sample["expected"])

        drop_periods_from_metrics = getattr(module, "_drop_periods_from_metrics")
        drop_sample = targets["_drop_periods_from_metrics"]["sample"]
        self.assertEqual(drop_periods_from_metrics(drop_sample["metrics"]), drop_sample["expected"])

        split_contract = getattr(module, "_split_contract")
        for sample_name, sample in targets["_split_contract"]["sample_cases"].items():
            with self.subTest(sample_name=sample_name):
                self.assertEqual(split_contract(sample["config"]), sample["expected"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("full validation report payloads", contract["excluded_surfaces"])
        self.assertIn("full falsification metrics", contract["excluded_surfaces"])
        self.assertIn("_run_backtest behavior", contract["excluded_surfaces"])
        self.assertIn("period-return construction", contract["excluded_surfaces"])
        self.assertIn("execution ledger behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("risk-brake behavior", contract["excluded_surfaces"])
        self.assertIn("funding behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_reporting_render_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_reporting_render_contract.json"
        )
        expected_helpers = {"_render_markdown_report", "_metric_row"}

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_reporting_render_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research._binance_canonical_reporting")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/_binance_canonical_reporting.py")
        self.assertEqual(contract["facade_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["facade_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "internal_module_facade_signature_tiny_render_samples",
        )
        self.assertIn("_render_markdown_report", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        facade_symbols = _read_module_level_symbols(str(contract["facade_path"]))
        source_module = importlib.import_module(contract["source_module"])
        facade_module = importlib.import_module(contract["facade_module"])
        targets = contract["reporting_render_targets"]
        self.assertEqual(set(targets), expected_helpers)

        for helper_name, helper_contract in targets.items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                self.assertIn(helper_name, facade_symbols)
                source_helper = getattr(source_module, helper_name)
                facade_helper = getattr(facade_module, helper_name)
                self.assertIs(facade_helper, source_helper)
                self.assertEqual(_function_signature_contract(source_helper), helper_contract["signature"])

        metric_row = getattr(source_module, "_metric_row")
        metric_sample = targets["_metric_row"]["format_sample"]
        self.assertEqual(
            metric_row(metric_sample["name"], metric_sample["metrics"]),
            metric_sample["expected_line"],
        )

        render_report = getattr(source_module, "_render_markdown_report")
        report_sample = targets["_render_markdown_report"]["minimal_report_sample"]
        report_text = render_report(
            report_sample["validation_report"],
            {key: PurePosixPath(value) for key, value in report_sample["paths"].items()},
        )
        self.assertTrue(report_text.endswith("\n"))
        for expected_text in report_sample["expected_contains"]:
            with self.subTest(expected_text=expected_text):
                self.assertIn(expected_text, report_text)
        for path_label in contract["required_path_labels"]:
            with self.subTest(path_label=path_label):
                self.assertIn(f"- {path_label}: `", report_text)

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        for spec in adjacent_contracts.values():
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("package layout expansion", contract["excluded_surfaces"])
        self.assertIn("full markdown report golden snapshots", contract["excluded_surfaces"])
        self.assertIn("exact artifact path roots", contract["excluded_surfaces"])
        self.assertIn("exact platform path separators", contract["excluded_surfaces"])
        self.assertIn("full validation report payload schemas", contract["excluded_surfaces"])
        self.assertIn("full blocker ordering", contract["excluded_surfaces"])
        self.assertIn("full falsification outputs", contract["excluded_surfaces"])
        self.assertIn("exact research metrics", contract["excluded_surfaces"])
        self.assertIn("exact attribution tables", contract["excluded_surfaces"])
        self.assertIn("artifact writer behavior", contract["excluded_surfaces"])
        self.assertIn("report path selection", contract["excluded_surfaces"])
        self.assertIn("run metadata behavior", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_pit_universe_eligibility_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_pit_universe_eligibility_contract.json"
        )
        expected_targets = {
            "freeze_binance_ohlcv_universe",
            "apply_point_in_time_rolling_universe",
            "add_pit_strategy_eligibility",
            "_pit_recent_data_eligible",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_pit_universe_eligibility_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_required_behavior_tests_only")
        self.assertEqual(set(contract["pit_universe_eligibility_targets"]), expected_targets)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for helper_name, helper_contract in contract["pit_universe_eligibility_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("full universe membership snapshots", contract["excluded_surfaces"])
        self.assertIn("exact prepared backtest-frame schemas", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("falsification outputs", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("risk-brake behavior", contract["excluded_surfaces"])
        self.assertIn("execution ledger behavior", contract["excluded_surfaces"])
        self.assertIn("_truthy_series as a generic utility", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_truthy_series_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_truthy_series_contract.json"
        )
        helper_name = "_truthy_series"

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_truthy_series_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_local_signature_tiny_truthy_mask_samples")
        self.assertIn("root-local behavior contract", _read(contract["approved_by_dry_run"]))

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        self.assertIn(helper_name, classification_contract["root_surface_groups"][classification_spec["required_group"]])

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["truthy_target"]
        self.assertEqual(target["helper_name"], helper_name)
        self.assertIn(helper_name, source_symbols)
        truthy_series = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(truthy_series), target["signature"])

        bool_sample = target["bool_sample"]
        bool_actual = truthy_series(pd.Series(bool_sample["values"], dtype=bool_sample["dtype"]))
        pd.testing.assert_series_equal(
            bool_actual.reset_index(drop=True),
            pd.Series(bool_sample["expected"], dtype="bool"),
        )

        text_sample = target["text_sample"]
        text_actual = truthy_series(pd.Series(text_sample["values"]))
        pd.testing.assert_series_equal(
            text_actual.reset_index(drop=True),
            pd.Series(text_sample["expected"], dtype="bool"),
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("generic utility extraction", contract["excluded_surfaces"])
        self.assertIn("caller behavior snapshots", contract["excluded_surfaces"])
        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("PIT membership snapshots", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("report payloads", contract["excluded_surfaces"])
        self.assertIn("funding status behavior", contract["excluded_surfaces"])
        self.assertIn("falsification behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_risk_brake_behavior_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_risk_brake_behavior_contract.json"
        )
        expected_targets = {
            "add_short_squeeze_veto_multiplier",
            "add_binance_risk_brake_columns",
            "_add_high_vol_rebound_short_brake",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_risk_brake_behavior_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_required_behavior_tests_only")
        self.assertEqual(set(contract["risk_brake_behavior_targets"]), expected_targets)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for helper_name, helper_contract in contract["risk_brake_behavior_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        registry_contract_spec = contract["required_column_registry_contract"]
        registry_contract = _read_json(registry_contract_spec["path"])
        self.assertEqual(registry_contract["contract_version"], registry_contract_spec["contract_version"])
        self.assertIn(registry_contract_spec["must_exclude_surface"], registry_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("exact risk-brake formula output snapshots", contract["excluded_surfaces"])
        self.assertIn("BINANCE_RISK_BRAKE_COLUMNS tuple ownership", contract["excluded_surfaces"])
        self.assertIn("full universe membership schema", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("ablation metric values", contract["excluded_surfaces"])
        self.assertIn("funding behavior", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("execution ledger behavior", contract["excluded_surfaces"])
        self.assertIn("_truthy_series as a generic utility", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_validation_status_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json"
        )
        expected_deferred = {
            "run_binance_canonical_validation",
            "write_validation_artifacts",
            "_run_falsification_suite",
            "_run_stratified_repeated_symbol_holdout",
            "_decision_time_liquidity_bucket_frame",
            "_funding_cost_status",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_validation_status_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_required_behavior_tests_only")
        self.assertEqual(set(contract["deferred_surfaces"]), expected_deferred)
        self.assertIn("_validation_status", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["validation_status_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "_validation_status")
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("falsification suite behavior", contract["excluded_surfaces"])
        self.assertIn("full validation runner behavior", contract["excluded_surfaces"])
        self.assertIn("artifact writer behavior", contract["excluded_surfaces"])
        self.assertIn("funding blocker behavior", contract["excluded_surfaces"])
        self.assertIn("full validation report payloads", contract["excluded_surfaces"])
        self.assertIn("full falsification outputs", contract["excluded_surfaces"])
        self.assertIn("backtest metric values", contract["excluded_surfaces"])
        self.assertIn("artifact path selection", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_decision_time_liquidity_bucket_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        self.assertIn("_decision_time_liquidity_bucket_frame", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["decision_time_liquidity_bucket_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "_decision_time_liquidity_bucket_frame")
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        validation_spec = contract["required_adjacent_contracts"][0]
        validation_contract = _read_json(validation_spec["path"])
        self.assertEqual(validation_contract["contract_version"], validation_spec["contract_version"])
        for surface in validation_spec["must_defer_surfaces"]:
            with self.subTest(deferred_surface=surface):
                self.assertIn(surface, validation_contract["deferred_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("broad falsification suite behavior", contract["excluded_surfaces"])
        self.assertIn("suite-level payload schemas", contract["excluded_surfaces"])
        self.assertIn("time-shuffle metric values", contract["excluded_surfaces"])
        self.assertIn("label-shuffle metric values", contract["excluded_surfaces"])
        self.assertIn("legacy symbol holdout split assignment beyond hash identity", contract["excluded_surfaces"])
        self.assertIn("stratified holdout formulas", contract["excluded_surfaces"])
        self.assertIn("stratified holdout thresholds", contract["excluded_surfaces"])
        self.assertIn("cost-stress backtest behavior", contract["excluded_surfaces"])
        self.assertIn("full validation runner behavior", contract["excluded_surfaces"])
        self.assertIn("full validation report payloads", contract["excluded_surfaces"])
        self.assertIn("full falsification outputs", contract["excluded_surfaces"])
        self.assertIn("backtest metric values", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_stratified_holdout_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_stratified_holdout_contract.json"
        )
        expected_targets = {
            "_run_stratified_repeated_symbol_holdout",
            "_stratified_holdout_policy",
        }
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_stratified_holdout_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        self.assertIn("_run_stratified_repeated_symbol_holdout", _read(contract["approved_by_dry_run"]))
        self.assertEqual(set(contract["stratified_holdout_targets"]), expected_targets)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for helper_name, helper_contract in contract["stratified_holdout_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        validation_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json"
        ]
        validation_contract = _read_json(validation_spec["path"])
        self.assertEqual(validation_contract["contract_version"], validation_spec["contract_version"])
        self.assertIn(validation_spec["must_defer_surface"], validation_contract["deferred_surfaces"])

        liquidity_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.json"
        ]
        liquidity_contract = _read_json(liquidity_spec["path"])
        self.assertEqual(liquidity_contract["contract_version"], liquidity_spec["contract_version"])
        for surface in liquidity_spec["must_exclude_surfaces"]:
            with self.subTest(excluded_surface=surface):
                self.assertIn(surface, liquidity_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("broad falsification suite behavior", contract["excluded_surfaces"])
        self.assertIn("suite-level payload schemas", contract["excluded_surfaces"])
        self.assertIn("exact fold subject membership", contract["excluded_surfaces"])
        self.assertIn("exact split assignment snapshots", contract["excluded_surfaces"])
        self.assertIn("exact backtest metric values", contract["excluded_surfaces"])
        self.assertIn("exact strata payload schemas", contract["excluded_surfaces"])
        self.assertIn("stratification formula snapshots", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("report text output", contract["excluded_surfaces"])
        self.assertIn("cost-stress backtest behavior", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_run_backtest_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_run_backtest_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_run_backtest_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        self.assertIn("_run_backtest", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["run_backtest_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "_run_backtest")
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        validation_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json"
        ]
        validation_contract = _read_json(validation_spec["path"])
        self.assertEqual(validation_contract["contract_version"], validation_spec["contract_version"])
        self.assertIn(validation_spec["must_exclude_surface"], validation_contract["excluded_surfaces"])

        reporting_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json"
        ]
        reporting_contract = _read_json(reporting_spec["path"])
        self.assertEqual(reporting_contract["contract_version"], reporting_spec["contract_version"])
        self.assertIn(reporting_spec["must_exclude_surface"], reporting_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("execution_backtest.backtest_cross_sectional behavior", contract["excluded_surfaces"])
        self.assertIn("exact portfolio return metrics", contract["excluded_surfaces"])
        self.assertIn("exact period-return payload values", contract["excluded_surfaces"])
        self.assertIn("exact trade cost values", contract["excluded_surfaces"])
        self.assertIn("exact capacity metric values", contract["excluded_surfaces"])
        self.assertIn("exact data-gap blocker strings", contract["excluded_surfaces"])
        self.assertIn("exact falsification metrics", contract["excluded_surfaces"])
        self.assertIn("exact ablation metrics", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_gap_policy_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_gap_policy_contract.json"
        )
        expected_targets = {
            "apply_selected_path_gap_symbol_exclusion",
            "_execution_data_gap_blockers_for_frame",
            "_subjects_from_data_gap_blockers",
        }
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_gap_policy_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_tests_only",
        )
        self.assertIn("selected-path gap policy", _read(contract["approved_by_dry_run"]))
        self.assertIn("Approve one minimal follow-up contract path", _read(contract["approved_by_owner_decision"]))

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        self.assertEqual(
            expected_targets,
            set(classification_contract["root_surface_groups"][classification_spec["required_group"]])
            - {"_run_backtest"},
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertEqual(set(contract["gap_policy_targets"]), expected_targets)
        for helper_name, helper_contract in contract["gap_policy_targets"].items():
            with self.subTest(helper=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("_run_backtest behavior", contract["excluded_surfaces"])
        self.assertIn("execution_backtest.backtest_cross_sectional behavior", contract["excluded_surfaces"])
        self.assertIn("exact blocker strings", contract["excluded_surfaces"])
        self.assertIn("real artifact excluded-subject snapshots", contract["excluded_surfaces"])
        self.assertIn("exact audit payload schemas", contract["excluded_surfaces"])
        self.assertIn("validation pass/fail status", contract["excluded_surfaces"])
        self.assertIn("report text output", contract["excluded_surfaces"])
        self.assertIn("execution metric values", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_paper_shadow_tiny_helpers_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_paper_shadow_tiny_helpers_contract.json"
        )
        expected_targets = {"_row_float", "_paper_shadow_action"}
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_paper_shadow_tiny_helpers_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(contract["validation_mode"], "root_facade_signature_tiny_synthetic_samples")
        dry_run = _read(contract["approved_by_dry_run"])
        self.assertIn("_row_float", dry_run)
        self.assertIn("_paper_shadow_action", dry_run)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        classified = set(classification_contract["root_surface_groups"][classification_spec["required_group"]])
        self.assertTrue(expected_targets.issubset(classified))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertEqual(set(contract["tiny_helper_targets"]), expected_targets)
        for helper_name, helper_contract in contract["tiny_helper_targets"].items():
            with self.subTest(helper=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        row_float = getattr(module, "_row_float")
        row_sample = contract["tiny_helper_targets"]["_row_float"]["sample_row"]
        row = pd.Series(row_sample["values"])
        self.assertEqual(row_float(row, "price"), row_sample["expected"]["price"])
        self.assertEqual(row_float(row, "bad"), row_sample["expected"]["bad"])
        self.assertEqual(row_float(row, "missing"), row_sample["expected"]["missing"])
        self.assertEqual(row_float(None, "price"), row_sample["expected"]["none_row"])

        paper_shadow_action = getattr(module, "_paper_shadow_action")
        for sample in contract["tiny_helper_targets"]["_paper_shadow_action"]["action_samples"]:
            with self.subTest(action_sample=sample["expected"]):
                self.assertEqual(
                    paper_shadow_action(
                        previous_weight=sample["previous_weight"],
                        target_weight=sample["target_weight"],
                    ),
                    sample["expected"],
                )

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("compute_position_attribution behavior", contract["excluded_surfaces"])
        self.assertIn("compute_factor_leave_one_out_attribution behavior", contract["excluded_surfaces"])
        self.assertIn("build_paper_shadow_execution_ledger behavior", contract["excluded_surfaces"])
        self.assertIn("empty payload helper schemas", contract["excluded_surfaces"])
        self.assertIn("paper-shadow ledger schemas", contract["excluded_surfaces"])
        self.assertIn("exact attribution metrics", contract["excluded_surfaces"])
        self.assertIn("exact factor leave-one-out deltas", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("_apply_short_position_multiplier behavior", contract["excluded_surfaces"])
        self.assertIn("_records JSON payload behavior", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_symbol_feature_builder_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_symbol_feature_builder_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_symbol_feature_builder_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        delegated_status = _read(contract["approved_by_owner_delegated_status"])
        self.assertIn("owner-delegated governance authorization", delegated_status)
        self.assertIn("build_symbol_feature_frame", delegated_status)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        target = contract["symbol_feature_builder_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "build_symbol_feature_frame")
        self.assertIn(helper_name, classification_contract["root_surface_groups"][classification_spec["required_group"]])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("_daily_bars_to_feature_panel", contract["deferred_surfaces"])
        self.assertIn("add_binance_ohlcv_core_features", contract["deferred_surfaces"])
        self.assertIn("build_binance_canonical_dataset", contract["deferred_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("real local archive path discovery", contract["excluded_surfaces"])
        self.assertIn("full daily feature-panel schema", contract["excluded_surfaces"])
        self.assertIn("daily feature formula snapshots", contract["excluded_surfaces"])
        self.assertIn("build_binance_canonical_dataset behavior", contract["excluded_surfaces"])
        self.assertIn("dataset manifest payloads", contract["excluded_surfaces"])
        self.assertIn("funding attachment", contract["excluded_surfaces"])
        self.assertIn("PIT universe behavior", contract["excluded_surfaces"])
        self.assertIn("validation metrics", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_ablation_rescore_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_ablation_rescore_contract.json"
        )
        expected_targets = {
            "run_binance_core_ablations",
            "add_core20_ablation_eligibility",
            "_reference_core20_subjects",
            "_rescore_for_feature_subset",
        }
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_ablation_rescore_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        delegated_status = _read(contract["approved_by_owner_delegated_status"])
        self.assertIn("owner-delegated governance authorization", delegated_status)
        self.assertIn("ablation/rescore bucket", delegated_status)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        self.assertEqual(
            set(classification_contract["root_surface_groups"][classification_spec["required_group"]]),
            expected_targets,
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertEqual(set(contract["ablation_rescore_targets"]), expected_targets)
        for helper_name, helper_contract in contract["ablation_rescore_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("exact ablation metric values", contract["excluded_surfaces"])
        self.assertIn("exact period-return payload values", contract["excluded_surfaces"])
        self.assertIn("exact core20 membership snapshots", contract["excluded_surfaces"])
        self.assertIn("score formula snapshots", contract["excluded_surfaces"])
        self.assertIn("risk-brake formula behavior", contract["excluded_surfaces"])
        self.assertIn("backtest metric values", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_attribution_runner_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_attribution_runner_contract.json"
        )
        expected_targets = {
            "compute_position_attribution",
            "compute_factor_leave_one_out_attribution",
            "build_paper_shadow_execution_ledger",
        }
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_attribution_runner_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        delegated_status = _read(contract["approved_by_owner_delegated_status"])
        self.assertIn("owner-delegated governance authorization", delegated_status)
        self.assertIn("attribution runners", delegated_status)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        classified = set(classification_contract["root_surface_groups"][classification_spec["required_group"]])
        self.assertTrue(expected_targets.issubset(classified))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertEqual(set(contract["attribution_runner_targets"]), expected_targets)
        for helper_name, helper_contract in contract["attribution_runner_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("_empty_position_attribution", contract["deferred_surfaces"])
        self.assertIn("_apply_short_position_multiplier", contract["deferred_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("exact attribution metrics", contract["excluded_surfaces"])
        self.assertIn("exact factor leave-one-out deltas", contract["excluded_surfaces"])
        self.assertIn("paper-shadow ledger schema snapshots", contract["excluded_surfaces"])
        self.assertIn("empty payload helper schemas", contract["excluded_surfaces"])
        self.assertIn("aggregation formula snapshots", contract["excluded_surfaces"])
        self.assertIn("_records JSON payload behavior", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_falsification_suite_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_falsification_suite_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_falsification_suite_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        delegated_status = _read(contract["approved_by_owner_delegated_status"])
        self.assertIn("owner-delegated governance authorization", delegated_status)
        self.assertIn("_run_falsification_suite", delegated_status)

        classification_spec = contract["required_classification_contract"]
        classification_contract = _read_json(classification_spec["path"])
        self.assertEqual(classification_contract["contract_version"], classification_spec["contract_version"])
        target = contract["falsification_suite_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "_run_falsification_suite")
        self.assertIn(helper_name, classification_contract["root_surface_groups"][classification_spec["required_group"]])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        for spec in contract["required_adjacent_contracts"]:
            with self.subTest(adjacent_contract=spec["path"]):
                adjacent_contract = _read_json(spec["path"])
                self.assertEqual(adjacent_contract["contract_version"], spec["contract_version"])
                self.assertIn(spec["must_exclude_surface"], adjacent_contract["excluded_surfaces"])

        self.assertIn("_symbol_stratification_frame", contract["deferred_surfaces"])
        self.assertIn("_stratified_two_way_subject_split", contract["deferred_surfaces"])
        self.assertIn("_stratum_counts", contract["deferred_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("suite-level payload schemas", contract["excluded_surfaces"])
        self.assertIn("time-shuffle metric values", contract["excluded_surfaces"])
        self.assertIn("label-shuffle metric values", contract["excluded_surfaces"])
        self.assertIn("cost-stress metric values", contract["excluded_surfaces"])
        self.assertIn("legacy symbol holdout split assignments", contract["excluded_surfaces"])
        self.assertIn("exact stratified fold subject membership", contract["excluded_surfaces"])
        self.assertIn("exact strata payload schemas", contract["excluded_surfaces"])
        self.assertIn("validation report payloads", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_binance_h10d_funding_cost_status_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_binance_canonical_h10d_funding_cost_status_contract.json"
        )
        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_binance_canonical_h10d_funding_cost_status_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.binance_canonical_h10d")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/binance_canonical_h10d.py")
        self.assertEqual(
            contract["validation_mode"],
            "root_facade_signature_required_behavior_test_presence_only",
        )
        self.assertIn("_funding_cost_status", _read(contract["approved_by_dry_run"]))

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        target = contract["funding_cost_status_target"]
        helper_name = target["helper_name"]
        self.assertEqual(helper_name, "_funding_cost_status")
        self.assertIn(helper_name, source_symbols)
        helper = getattr(module, helper_name)
        self.assertEqual(_function_signature_contract(helper), target["signature"])

        test_source = _read(contract["required_behavior_test_file"])
        for test_name in contract["required_behavior_tests"]:
            with self.subTest(required_behavior_test=test_name):
                self.assertRegex(test_source, rf"def {re.escape(test_name)}\(")

        adjacent_contracts = {
            spec["path"]: spec for spec in contract["required_adjacent_contracts"]
        }
        validation_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json"
        ]
        validation_contract = _read_json(validation_spec["path"])
        self.assertEqual(validation_contract["contract_version"], validation_spec["contract_version"])
        self.assertIn(validation_spec["must_defer_surface"], validation_contract["deferred_surfaces"])

        funding_facade_spec = adjacent_contracts[
            "config/quant_research/src_quant_research_binance_canonical_h10d_funding_facade_contract.json"
        ]
        funding_facade_contract = _read_json(funding_facade_spec["path"])
        self.assertEqual(funding_facade_contract["contract_version"], funding_facade_spec["contract_version"])
        self.assertNotIn(funding_facade_spec["must_not_protect_surface"], funding_facade_contract["protected_entrypoints"])
        self.assertNotIn(
            funding_facade_spec["must_not_protect_surface"],
            funding_facade_contract["facade_candidate_targets"],
        )

        self.assertIn("source migration", contract["excluded_surfaces"])
        self.assertIn("internal module layout", contract["excluded_surfaces"])
        self.assertIn("funding facade behavior", contract["excluded_surfaces"])
        self.assertIn("provider HTTP behavior", contract["excluded_surfaces"])
        self.assertIn("funding sync behavior", contract["excluded_surfaces"])
        self.assertIn("funding load behavior", contract["excluded_surfaces"])
        self.assertIn("funding attach behavior", contract["excluded_surfaces"])
        self.assertIn("PIT eligibility behavior", contract["excluded_surfaces"])
        self.assertIn("full validation runner behavior", contract["excluded_surfaces"])
        self.assertIn("full blocker list ordering", contract["excluded_surfaces"])
        self.assertIn("full validation report payloads", contract["excluded_surfaces"])
        self.assertIn("full falsification outputs", contract["excluded_surfaces"])
        self.assertIn("backtest metric values", contract["excluded_surfaces"])
        self.assertIn("funding root path policy", contract["excluded_surfaces"])
        self.assertIn("artifact path selection", contract["excluded_surfaces"])
        self.assertIn("strategy promotion status", contract["excluded_surfaces"])
        self.assertIn("live-readiness authorization", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])

    def test_quant_research_hypothesis_batch_external_compatibility_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_hypothesis_batch_compatibility_contract.json"
        )
        expected_keys = {
            "mutable_global_patch_targets",
            "global_read_targets",
            "private_helper_targets",
            "string_patch_targets",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_hypothesis_batch_compatibility_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.hypothesis_batch")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/hypothesis_batch.py")
        self.assertEqual(contract["scan_roots"], ["scripts", "tests"])
        self.assertEqual(
            _scan_hypothesis_batch_external_compatibility(list(contract["scan_roots"])),
            {key: contract[key] for key in expected_keys},
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        for key in expected_keys:
            for name in contract[key]:
                with self.subTest(contract_key=key, name=name):
                    self.assertIn(name, source_symbols)

    def test_quant_research_lab_external_compatibility_contract_stays_stable(self) -> None:
        contract = _read_json("config/quant_research/src_quant_research_lab_compatibility_contract.json")
        expected_keys = {
            "mutable_global_patch_targets",
            "public_facade_targets",
            "private_helper_targets",
            "string_patch_targets",
        }

        self.assertEqual(contract["contract_version"], "src_quant_research_lab_compatibility_contract.v1")
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.lab")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/lab.py")
        self.assertEqual(contract["scan_roots"], ["scripts", "tests"])
        self.assertEqual(
            _scan_lab_external_compatibility(list(contract["scan_roots"])),
            {key: contract[key] for key in expected_keys},
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        for key in expected_keys:
            for name in contract[key]:
                with self.subTest(contract_key=key, name=name):
                    self.assertIn(name, source_symbols)

    def test_quant_research_features_utility_compatibility_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_utility_compatibility_contract.json"
        )
        expected_helpers = {
            "_safe_rolling_skew",
            "_timestamp_percentile_rank",
            "_timestamp_zscore",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_utility_compatibility_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["scan_roots"], ["scripts", "tests"])
        self.assertEqual(set(contract["utility_helper_targets"]), expected_helpers)
        self.assertEqual(
            _scan_features_utility_external_compatibility(
                list(contract["scan_roots"]),
                set(contract["utility_helper_targets"]),
            ),
            contract["utility_helper_targets"],
        )

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        for helper_name in expected_helpers:
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
        self.assertIn("raw alpha ontology private scorers", contract["excluded_surfaces"])
        self.assertIn("feature builders", contract["excluded_surfaces"])
        self.assertIn("sidecar merge behavior", contract["excluded_surfaces"])

    def test_quant_research_features_f2_raw_scorer_shim_import_signature_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f2_raw_scorer_shim_compatibility_contract.json"
        )
        expected_helpers = {
            "_xs_alpha_ontology_v5_h10d_base_raw_score",
            "_xs_alpha_ontology_v6_h10d_base_raw_score",
            "_xs_alpha_ontology_v6_h10d_spk_short_replacement_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f2_raw_scorer_shim_compatibility_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(set(contract["raw_scorer_shim_targets"]), expected_helpers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for helper_name, helper_contract in contract["raw_scorer_shim_targets"].items():
            with self.subTest(helper_name=helper_name):
                self.assertIn(helper_name, source_symbols)
                helper = getattr(module, helper_name)
                self.assertEqual(_function_signature_contract(helper), helper_contract)

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("golden-output scorer snapshots", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_features_f3a_v11_stablecoin_flow_scorer_family_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f3a_v11_stablecoin_flow_scorer_family_contract.json"
        )
        expected_scorers = {
            "xs_alpha_ontology_v11_absorb_qshare_h10d_score",
            "xs_alpha_ontology_v11_drain_rs_h10d_score",
            "xs_alpha_ontology_v11_flow_blend_h10d_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f3a_v11_stablecoin_flow_scorer_family_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(contract["scorer_family"], "f3a_v11_stablecoin_flow")
        self.assertEqual(set(contract["scorer_targets"]), expected_scorers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for scorer_name, scorer_contract in contract["scorer_targets"].items():
            with self.subTest(scorer_name=scorer_name):
                self.assertIn(scorer_name, source_symbols)
                scorer = getattr(module, scorer_name)
                self.assertEqual(_function_signature_contract(scorer), scorer_contract)

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("stablecoin sidecar construction", contract["excluded_surfaces"])
        self.assertIn("feature-bundle sidecar merge behavior", contract["excluded_surfaces"])
        self.assertIn("v12 or v13 scorer families", contract["excluded_surfaces"])
        self.assertIn("SP-K or MF01 scorer families", contract["excluded_surfaces"])
        self.assertIn("pair or residualized scorer families", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_features_f3b1_relative_value_spread_scorer_family_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f3b1_relative_value_spread_scorer_family_contract.json"
        )
        expected_scorers = {
            "xs_relative_value_spread_v1_score",
            "xs_relative_value_spread_v2_score",
            "xs_relative_value_spread_v3_score",
            "xs_relative_value_spread_v4_score",
            "xs_relative_value_spread_v5_score",
            "xs_relative_value_spread_v6_score",
            "xs_relative_value_spread_v7_score",
            "xs_relative_value_spread_v8_score",
            "xs_relative_value_spread_v9_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f3b1_relative_value_spread_scorer_family_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(contract["scorer_family"], "f3b1_relative_value_spread")
        self.assertEqual(set(contract["scorer_targets"]), expected_scorers)
        self.assertEqual(set(contract["coverage_notes"]), expected_scorers)
        self.assertIn("no direct behavior coverage", contract["coverage_notes"]["xs_relative_value_spread_v9_score"])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for scorer_name, scorer_contract in contract["scorer_targets"].items():
            with self.subTest(scorer_name=scorer_name):
                self.assertIn(scorer_name, source_symbols)
                scorer = getattr(module, scorer_name)
                self.assertEqual(_function_signature_contract(scorer), scorer_contract)

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("score ordering", contract["excluded_surfaces"])
        self.assertIn("lab.py registry or dispatch semantics", contract["excluded_surfaces"])
        self.assertIn("archived manifest lifecycle semantics", contract["excluded_surfaces"])
        self.assertIn("v9 behavior coverage", contract["excluded_surfaces"])
        self.assertIn("pair book scorer family", contract["excluded_surfaces"])
        self.assertIn("residualized pair book scorer family", contract["excluded_surfaces"])
        self.assertIn("hypothesis_batch.py pair-construction normalization", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_features_f3b2_residualized_pair_book_scorer_family_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f3b2_residualized_pair_book_scorer_family_contract.json"
        )
        expected_scorers = {
            "xs_residualized_pair_book_v1_score",
            "xs_residualized_pair_book_v2_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f3b2_residualized_pair_book_scorer_family_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(contract["scorer_family"], "f3b2_residualized_pair_book")
        self.assertEqual(
            contract["required_behavior_smoke"],
            "tests/test_quant_hypothesis_batch.py::QuantHypothesisBatchTests::test_residualized_pair_book_scores_prefer_clean_cheap_over_broken_cheap",
        )
        self.assertEqual(set(contract["scorer_targets"]), expected_scorers)
        self.assertEqual(set(contract["coverage_notes"]), expected_scorers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for scorer_name, scorer_contract in contract["scorer_targets"].items():
            with self.subTest(scorer_name=scorer_name):
                self.assertIn(scorer_name, source_symbols)
                scorer = getattr(module, scorer_name)
                self.assertEqual(_function_signature_contract(scorer), scorer_contract)

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("exact score values", contract["excluded_surfaces"])
        self.assertIn("complete score ordering", contract["excluded_surfaces"])
        self.assertIn("lab.py registry or dispatch semantics", contract["excluded_surfaces"])
        self.assertIn("archived manifest lifecycle semantics", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])
        self.assertIn("pair book scorer family", contract["excluded_surfaces"])
        self.assertIn("relative value spread scorer family", contract["excluded_surfaces"])
        self.assertIn("hypothesis_batch.py pair-construction normalization", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_features_f3b3a_pair_book_v1_v12_scorer_family_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f3b3a_pair_book_v1_v12_scorer_family_contract.json"
        )
        expected_scorers = {
            "xs_pair_spread_book_v1_score",
            "xs_pair_spread_book_v2_score",
            "xs_pair_spread_book_v3_score",
            "xs_pair_spread_book_v4_score",
            "xs_pair_spread_book_v5_score",
            "xs_pair_spread_book_v6_score",
            "xs_pair_spread_book_v7_score",
            "xs_pair_spread_book_v8_score",
            "xs_pair_spread_book_v9_score",
            "xs_pair_spread_book_v10_score",
            "xs_pair_spread_book_v11_score",
            "xs_pair_spread_book_v12_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f3b3a_pair_book_v1_v12_scorer_family_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(contract["scorer_family"], "f3b3a_pair_book_v1_v12")
        self.assertEqual(
            contract["required_behavior_test"],
            "tests/test_quant_hypothesis_batch.py::QuantHypothesisBatchTests::test_pair_spread_book_v8_adds_tiny_near_high_tiebreaker",
        )
        self.assertEqual(set(contract["scorer_targets"]), expected_scorers)
        self.assertEqual(set(contract["coverage_notes"]), expected_scorers)
        self.assertIn("direct alias behavior coverage", contract["coverage_notes"]["xs_pair_spread_book_v10_score"])
        self.assertIn("direct alias behavior coverage", contract["coverage_notes"]["xs_pair_spread_book_v11_score"])
        self.assertIn("direct alias behavior coverage", contract["coverage_notes"]["xs_pair_spread_book_v12_score"])

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        for scorer_name, scorer_contract in contract["scorer_targets"].items():
            with self.subTest(scorer_name=scorer_name):
                self.assertIn(scorer_name, source_symbols)
                scorer = getattr(module, scorer_name)
                self.assertEqual(_function_signature_contract(scorer), scorer_contract)

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("exact score values", contract["excluded_surfaces"])
        self.assertIn("complete score ordering", contract["excluded_surfaces"])
        self.assertIn("frozen benchmark status", contract["excluded_surfaces"])
        self.assertIn("lab.py registry or dispatch semantics", contract["excluded_surfaces"])
        self.assertIn("hypothesis_batch.py pair-construction normalization", contract["excluded_surfaces"])
        self.assertIn("execution_backtest.py quality_bucket_pairs target-weight logic", contract["excluded_surfaces"])
        self.assertIn("archived manifest lifecycle semantics", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])
        self.assertIn("alias-only v16-v24 pair book scorers", contract["excluded_surfaces"])
        self.assertIn("archive-only v13-v15 pair book manifest references", contract["excluded_surfaces"])
        self.assertIn("residualized pair book scorer family", contract["excluded_surfaces"])
        self.assertIn("relative value spread scorer family", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_features_f3b3b_pair_book_v16_v24_alias_scorer_family_contract_stays_stable(
        self,
    ) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_features_f3b3b_pair_book_v16_v24_alias_scorer_family_contract.json"
        )
        expected_scorers = {
            "xs_pair_spread_book_v16_score",
            "xs_pair_spread_book_v17_score",
            "xs_pair_spread_book_v18_score",
            "xs_pair_spread_book_v19_score",
            "xs_pair_spread_book_v20_score",
            "xs_pair_spread_book_v21_score",
            "xs_pair_spread_book_v22_score",
            "xs_pair_spread_book_v23_score",
            "xs_pair_spread_book_v24_score",
        }

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_features_f3b3b_pair_book_v16_v24_alias_scorer_family_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.features")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/features.py")
        self.assertEqual(contract["validation_mode"], "importability_signature_only")
        self.assertEqual(contract["scorer_family"], "f3b3b_pair_book_v16_v24_alias_only")
        self.assertEqual(contract["alias_target"], "xs_pair_spread_book_v8_score")
        self.assertEqual(
            contract["required_behavior_smoke"],
            "tests/test_quant_hypothesis_batch.py::QuantHypothesisBatchTests::test_pair_spread_book_v16_v24_aliases_match_v8",
        )
        self.assertEqual(set(contract["scorer_targets"]), expected_scorers)
        self.assertEqual(set(contract["coverage_notes"]), expected_scorers)

        source_symbols = _read_module_level_symbols(str(contract["source_path"]))
        module = importlib.import_module(contract["source_module"])
        self.assertIn(contract["alias_target"], source_symbols)
        for scorer_name in contract["scorer_targets"]:
            with self.subTest(scorer_name=scorer_name):
                self.assertIn(scorer_name, source_symbols)
                scorer = getattr(module, scorer_name)
                self.assertEqual(_function_signature_contract(scorer), contract["expected_signature"])

        self.assertIn("scorer formula output", contract["excluded_surfaces"])
        self.assertIn("exact score values", contract["excluded_surfaces"])
        self.assertIn("complete score ordering", contract["excluded_surfaces"])
        self.assertIn("frozen benchmark status", contract["excluded_surfaces"])
        self.assertIn("lab.py registry or dispatch semantics", contract["excluded_surfaces"])
        self.assertIn("hypothesis_batch.py pair-construction normalization", contract["excluded_surfaces"])
        self.assertIn("execution_backtest.py quality_bucket_pairs target-weight logic", contract["excluded_surfaces"])
        self.assertIn("archived manifest lifecycle semantics", contract["excluded_surfaces"])
        self.assertIn("caller counts", contract["excluded_surfaces"])
        self.assertIn("pair book v1-v12 formula-family contract", contract["excluded_surfaces"])
        self.assertIn("archive-only v13-v15 pair book manifest references", contract["excluded_surfaces"])
        self.assertIn("residualized pair book scorer family", contract["excluded_surfaces"])
        self.assertIn("relative value spread scorer family", contract["excluded_surfaces"])
        self.assertIn("source migration", contract["excluded_surfaces"])

    def test_quant_research_frozen_benchmark_v35_identity_contract_stays_stable(self) -> None:
        contract = _read_json(
            "config/quant_research/src_quant_research_frozen_benchmark_v35_identity_contract.json"
        )

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_frozen_benchmark_v35_identity_contract.v1",
        )
        self.assertEqual(contract["source_module"], "enhengclaw.quant_research.hypothesis_batch")
        self.assertEqual(contract["source_path"], "src/enhengclaw/quant_research/hypothesis_batch.py")
        self.assertEqual(contract["validation_mode"], "identity_only_no_resolver")
        self.assertFalse(contract["assert_root_manifest_exists"])

        actual_manifest_filename = _read_with_name_assignment(
            contract["source_path"],
            "FROZEN_BENCHMARK_MANIFEST_PATH",
        )
        actual_source = _read_assignment_literal(
            contract["source_path"],
            "FROZEN_BENCHMARK_SOURCE",
        )
        actual_candidate_ids = _read_assignment_literal(
            contract["source_path"],
            "FROZEN_BENCHMARK_CANDIDATE_IDS",
        )

        self.assertEqual(actual_manifest_filename, contract["expected_manifest_filename"])
        self.assertEqual(actual_source, contract["expected_source"])
        self.assertEqual(tuple(actual_candidate_ids), tuple(contract["expected_candidate_ids"]))

        archive_manifest_path = ROOT / contract["archive_manifest_path"]
        self.assertTrue(archive_manifest_path.is_file())
        archive_manifest = _read_json(contract["archive_manifest_path"])
        self.assertEqual(
            archive_manifest["contract_version"],
            contract["expected_archive_contract_version"],
        )
        self.assertEqual(
            tuple(entry["candidate_id"] for entry in archive_manifest["entries"]),
            tuple(contract["expected_candidate_ids"]),
        )

        self.assertIn("root manifest path existence", contract["excluded_surfaces"])
        self.assertIn("archive-aware resolver bridge", contract["excluded_surfaces"])
        self.assertIn("active hypothesis-batch runtime loading", contract["excluded_surfaces"])
        self.assertIn("HYPOTHESIS_BATCH_MANIFEST_PATH", contract["excluded_surfaces"])
        self.assertIn("v35 reactivation", contract["excluded_surfaces"])

    def test_quant_research_terminal_governance_contract_stays_stable(self) -> None:
        contract = _read_json("config/quant_research/src_quant_research_terminal_governance_contract.json")

        self.assertEqual(
            contract["contract_version"],
            "src_quant_research_terminal_governance_contract.v1",
        )
        self.assertEqual(contract["validation_mode"], "composite_docs_config_static_test_only")

        terminal_rollup_doc = contract["terminal_rollup_doc"]
        governance_index_doc = contract["governance_index_doc"]
        terminal_rollup_text = _read(terminal_rollup_doc)
        governance_index_text = _read(governance_index_doc)
        static_test_source = _read("tests/test_static_contracts.py")

        self.assertIn(Path(terminal_rollup_doc).name, governance_index_text)
        for terminal_doc in contract["required_terminal_docs"]:
            with self.subTest(terminal_doc=terminal_doc):
                self.assertTrue((ROOT / terminal_doc).is_file(), terminal_doc)
                self.assertIn(terminal_doc, terminal_rollup_text)

        for marker in contract["terminal_markers"]:
            with self.subTest(terminal_marker=marker):
                self.assertIn(marker, terminal_rollup_text)

        for contract_group in ("required_h10d_terminal_contracts", "required_non_h10d_contracts"):
            for contract_spec in contract[contract_group]:
                with self.subTest(contract_group=contract_group, contract_path=contract_spec["path"]):
                    covered_contract = _read_json(contract_spec["path"])
                    self.assertEqual(covered_contract["contract_version"], contract_spec["contract_version"])

        for test_method in contract["required_static_test_methods"]:
            with self.subTest(required_static_test=test_method):
                self.assertRegex(static_test_source, rf"def {re.escape(test_method)}\(")

        excluded_surfaces = set(contract["excluded_surfaces"])
        for excluded_surface in (
            "source movement",
            "manifest movement",
            "runtime payload snapshots",
            "report payload snapshots",
            "local artifact snapshots",
            "build_binance_canonical_dataset behavior",
            "run_binance_canonical_validation behavior",
            "write_validation_artifacts behavior",
            "promotion status",
            "live-readiness authorization",
        ):
            with self.subTest(excluded_surface=excluded_surface):
                self.assertIn(excluded_surface, excluded_surfaces)

    def test_quant_code_does_not_read_legacy_status_aliases(self) -> None:
        forbidden_patterns = (
            'entry.get("status")',
            'experiment.get("status")',
            'alpha_card.get("status")',
            '.get("governance_status")',
        )
        offenders: list[tuple[str, int, str]] = []
        for path in (ROOT / "src" / "enhengclaw" / "quant_research").rglob("*.py"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if any(pattern in line for pattern in forbidden_patterns):
                    offenders.append((path.relative_to(ROOT).as_posix(), line_number, line.strip()))
        self.assertEqual(offenders, [])

    def test_checked_in_quant_artifacts_use_lifecycle_and_leakage_audit_contracts(self) -> None:
        if not (ROOT / "artifacts" / "quant_research").exists():
            self.skipTest("research artifacts excluded from public mirror")
        quant_root = ROOT / "artifacts" / "quant_research"
        experiments_root = quant_root / "experiments"
        manifests_root = quant_root / "governance" / "daily_alpha_manifests"
        strategy_library = _read_json("artifacts/quant_research/governance/strategy_library.json")
        for entry in strategy_library["entries"]:
            self.assertNotIn("status", entry)
            self.assertTrue(str(entry.get("lifecycle") or "").strip())

        manifest_ids: set[str] = set()
        manifest_experiment_dirs: set[str] = set()
        manifest_paths = sorted(manifests_root.glob("*.json"))
        self.assertTrue(manifest_paths)
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest.get("entries", []):
                experiment_id = str(entry["experiment_id"])
                manifest_ids.add(experiment_id)
                alpha_card_path = ROOT / str(entry["alpha_card_path"])
                manifest_experiment_dirs.add(alpha_card_path.parent.name)
                self.assertTrue(alpha_card_path.exists(), alpha_card_path)
                alpha_card = json.loads(alpha_card_path.read_text(encoding="utf-8"))
                self.assertNotIn("status", alpha_card)
                self.assertNotIn("governance_status", alpha_card)
                self.assertTrue(str(alpha_card.get("strategy_id") or "").strip())
                self.assertTrue(str(alpha_card.get("dataset_provenance") or "").strip())
                falsification_audit_path = str(alpha_card.get("falsification_audit_path") or "").strip()
                if falsification_audit_path:
                    self.assertTrue((ROOT / falsification_audit_path).exists(), falsification_audit_path)

        root_level_non_manifest_problems: list[str] = []
        for experiment_root in sorted(experiments_root.iterdir()):
            alpha_card_path = experiment_root / "alpha_card.json"
            if not experiment_root.is_dir() or experiment_root.name == "legacy" or not alpha_card_path.exists():
                continue
            if experiment_root.name in manifest_experiment_dirs:
                continue
            alpha_card = json.loads(alpha_card_path.read_text(encoding="utf-8"))
            problem_prefix = alpha_card_path.relative_to(ROOT).as_posix()
            if "status" in alpha_card:
                root_level_non_manifest_problems.append(f"{problem_prefix}: legacy status field")
            if "governance_status" in alpha_card:
                root_level_non_manifest_problems.append(f"{problem_prefix}: legacy governance_status field")
            if str(alpha_card.get("publication_status") or "").strip() != "archived_only":
                root_level_non_manifest_problems.append(f"{problem_prefix}: not archived_only")
            if not str(alpha_card.get("lifecycle") or "").strip():
                root_level_non_manifest_problems.append(f"{problem_prefix}: missing lifecycle")
            if not str(alpha_card.get("strategy_id") or "").strip():
                root_level_non_manifest_problems.append(f"{problem_prefix}: missing strategy_id")
            if not str(alpha_card.get("dataset_provenance") or "").strip():
                root_level_non_manifest_problems.append(f"{problem_prefix}: missing dataset_provenance")
            falsification_audit_path = str(alpha_card.get("falsification_audit_path") or "").strip()
            if falsification_audit_path:
                self.assertTrue((ROOT / falsification_audit_path).exists(), falsification_audit_path)
        self.assertEqual(root_level_non_manifest_problems, [])

        legacy_root = experiments_root / "legacy"
        self.assertTrue(legacy_root.exists())
        self.assertTrue(any((path / "alpha_card.json").exists() for path in legacy_root.iterdir() if path.is_dir()))

    def test_checked_in_positive_control_summaries_follow_contract_and_stay_outside_governance(self) -> None:
        if not (ROOT / "artifacts" / "quant_research").exists():
            self.skipTest("research artifacts excluded from public mirror")
        quant_root = ROOT / "artifacts" / "quant_research"
        manifest_ids: set[str] = set()
        for manifest_path in sorted((quant_root / "governance" / "daily_alpha_manifests").glob("*.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_ids.update(str(entry["experiment_id"]) for entry in manifest.get("entries", []))

        registry_text = _read("artifacts/quant_research/registry/alpha_registry.json")
        bridge_texts = [
            _read("artifacts/quant_research/bridge_exports/2026-04-20/bridge_summary.json"),
            _read("artifacts/quant_research/bridge_exports/2026-04-21/bridge_summary.json"),
        ]

        for as_of in ("2026-04-20", "2026-04-21"):
            summary_path = quant_root / "assessments" / "positive_controls" / as_of / "positive_control_summary.json"
            markdown_path = quant_root / "assessments" / "positive_controls" / as_of / "positive_control_summary.md"
            self.assertTrue(summary_path.exists(), summary_path)
            self.assertTrue(markdown_path.exists(), markdown_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["contract_version"], "quant_positive_control_summary.v1")
            self.assertEqual(summary["evidence_family"], "quant_positive_controls")
            self.assertEqual(summary["as_of"], as_of)
            self.assertIn(summary["pipeline_health"], {"broken", "marginal", "healthy"})
            self.assertIn("dataset_ids", summary)
            self.assertIn("control_cases", summary)
            self.assertIn("lane_interpretation", summary)
            self.assertIn("real_lane_reference", summary)
            self.assertGreaterEqual(len(summary["control_cases"]), 5)
            self.assertEqual(summary["real_lane_reference"]["global_canonical_experiment_count"], 88)
            markdown_text = markdown_path.read_text(encoding="utf-8")
            for section_name in (
                "## Controls",
                "## Results Matrix",
                "## Pipeline Health Verdict",
                "## What 0/88 Means Now",
                "## Implication For Track Choice",
            ):
                self.assertIn(section_name, markdown_text)
            for case in summary["control_cases"]:
                for key in (
                    "control_id",
                    "shape",
                    "control_kind",
                    "expected_future_dependency",
                    "raw_positive",
                    "production_admissibility",
                    "validation_metrics",
                    "test_metrics",
                    "walk_forward",
                    "score_sign_counts",
                    "position_sign_counts",
                    "nonzero_position_fraction",
                ):
                    self.assertIn(key, case)
                self.assertNotIn(case["control_id"], manifest_ids)
                self.assertNotIn(case["control_id"], registry_text)
                for bridge_text in bridge_texts:
                    self.assertNotIn(case["control_id"], bridge_text)

    def test_checked_in_repo_health_summary_exposes_positive_control_view(self) -> None:
        if not (ROOT / "artifacts" / "quant_research").exists():
            self.skipTest("research artifacts excluded from public mirror")
        summary_path = ROOT / "artifacts" / "quant_research" / "ops" / "repo_health" / "2026-04-21" / "repo_health_summary.json"
        self.assertTrue(summary_path.exists(), summary_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for key in (
            "positive_control_pipeline_health",
            "positive_control_rationale",
            "single_asset_strong_oracle_all_raw_positive",
            "cross_sectional_strong_oracle_all_raw_positive",
        ):
            self.assertIn(key, summary)
        self.assertIn(summary["positive_control_pipeline_health"], {"broken", "marginal", "healthy"})
        self.assertTrue(str(summary["positive_control_rationale"]).strip())
        self.assertIsInstance(summary["single_asset_strong_oracle_all_raw_positive"], bool)
        self.assertIsInstance(summary["cross_sectional_strong_oracle_all_raw_positive"], bool)

    def test_checked_in_single_asset_repair_assessments_exist_and_match_partition_contract(self) -> None:
        if not (ROOT / "artifacts" / "quant_research").exists():
            self.skipTest("research artifacts excluded from public mirror")
        quant_root = ROOT / "artifacts" / "quant_research"
        partition_path = quant_root / "assessments" / "single_asset_repairs" / "pre_fix_partition.json"
        validation_path = quant_root / "assessments" / "single_asset_repairs" / "repair_validation.json"
        self.assertTrue(partition_path.exists(), partition_path)
        self.assertTrue(validation_path.exists(), validation_path)
        partition = json.loads(partition_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        self.assertEqual(partition["contract_version"], "quant_single_asset_repair.v1")
        self.assertEqual(partition["evidence_family"], "quant_single_asset_repair")
        self.assertEqual(partition["cross_sectional_count"], 30)
        self.assertEqual(partition["single_asset_count"], 58)
        self.assertEqual(partition["total_canonical_count"], 88)
        self.assertEqual(partition["downgrade_status"], "pipeline_unreliable_pending_single_asset_fix")
        self.assertEqual(validation["contract_version"], "quant_single_asset_repair.v1")
        self.assertEqual(validation["evidence_family"], "quant_single_asset_repair")
        self.assertEqual(validation["post_fix_single_asset_total_status_counts"], {"fail": 54, "quarantined": 4})
        for as_of in ("2026-04-20", "2026-04-21"):
            self.assertIn(as_of, validation["before_pipeline_health"])
            self.assertIn(as_of, validation["after_pipeline_health"])
            self.assertEqual(validation["before_pipeline_health"][as_of], "broken")
            self.assertIn(validation["after_pipeline_health"][as_of], {"marginal", "healthy"})
            self.assertIn(validation["assessment_trust_by_as_of"][as_of], {"trusted", "trusted_with_weak_oracle_headroom_limit"})
            self.assertIn("single_asset_count", validation["post_fix_single_asset_status_counts"][as_of])
            self.assertIn("status_counts", validation["post_fix_single_asset_status_counts"][as_of])
            for record in validation["single_asset_strong_oracle"][as_of]:
                self.assertTrue(record["after_raw_positive"], record["control_id"])
        self.assertEqual(validation["assessment_trust_by_as_of"]["2026-04-20"], "trusted_with_weak_oracle_headroom_limit")
        self.assertEqual(validation["assessment_trust_by_as_of"]["2026-04-21"], "trusted")
        self.assertEqual(validation["post_fix_single_asset_status_counts"]["2026-04-20"]["status_counts"], {"fail": 54, "quarantined": 3})
        self.assertEqual(validation["post_fix_single_asset_status_counts"]["2026-04-21"]["status_counts"], {"quarantined": 1})

    def test_src_tree_compiles_cleanly(self) -> None:
        compiled = compileall.compile_dir(
            str(ROOT / "src"),
            quiet=1,
        )
        self.assertTrue(compiled)

    def test_checked_in_contract_and_quant_artifact_json_parses(self) -> None:
        json_paths: set[Path] = set((ROOT / "config").rglob("*.json"))
        quant_root = ROOT / "artifacts" / "quant_research"
        if quant_root.exists():
            json_paths.update(quant_root.rglob("*.json"))
        for path in sorted(json_paths):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                json.loads(path.read_text(encoding="utf-8-sig"))

    def test_non_real_margin_literal_is_scoped_to_the_named_constant(self) -> None:
        raw_occurrences: list[tuple[str, str]] = []
        for base in (ROOT / "src", ROOT / "scripts"):
            for path in base.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if "1800.0" not in line:
                        continue
                    raw_occurrences.append((path.relative_to(ROOT).as_posix(), line.strip()))

        self.assertEqual(
            raw_occurrences,
            [
                (
                    "src/enhengclaw/orchestration/shadow_acceptance.py",
                    "DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS = 1800.0",
                )
            ],
        )

    def test_real_24h_paths_do_not_reference_non_real_margin_constant(self) -> None:
        for relative_path in (
            "scripts/verify/run_real_24h_shadow_bundle.py",
            "scripts/verify/run_real_shadow_acceptance.py",
        ):
            text = _read(relative_path)
            self.assertNotIn("1800.0", text)
            self.assertNotIn("DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS", text)

    def test_large_python_files_over_threshold_are_explicitly_allowlisted(self) -> None:
        oversized: list[str] = []
        for path in (ROOT / "src").rglob("*.py"):
            with path.open(encoding="utf-8") as handle:
                line_count = sum(1 for _ in handle)
            if line_count > 1500:
                oversized.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(
            sorted(oversized),
            [
                "src/enhengclaw/live_trading/mainnet_core_loop_runner.py",
                "src/enhengclaw/live_trading/mainnet_delta_execution_runner.py",
                "src/enhengclaw/live_trading/mainnet_multiphase_target_shadow.py",
                "src/enhengclaw/live_trading/mainnet_rebalance_plan_runner.py",
                "src/enhengclaw/orchestration/runtime_runner.py",
                "src/enhengclaw/orchestration/shadow_acceptance.py",
                "src/enhengclaw/quant_research/binance_canonical_h10d.py",
                "src/enhengclaw/quant_research/discovery.py",
                "src/enhengclaw/quant_research/features.py",
                "src/enhengclaw/quant_research/governance.py",
                "src/enhengclaw/quant_research/hypothesis_batch.py",
                "src/enhengclaw/quant_research/lab.py",
                "src/enhengclaw/quant_research/repo_health.py",
            ],
        )

    def test_local_integrity_gate_scripts_exist(self) -> None:
        self.assertTrue((ROOT / "scripts" / "verify" / "run_disk_integrity.py").exists())
        self.assertTrue((ROOT / "scripts" / "verify" / "run_local_integrity_gates.py").exists())
        self.assertTrue((ROOT / "scripts" / "verify" / "run_quant_repo_health_guard.py").exists())
        self.assertTrue((ROOT / ".githooks" / "pre-commit").exists())
        self.assertTrue((ROOT / ".githooks" / "pre-push").exists())

    def test_scheduled_task_manifest_matches_registration_contract(self) -> None:
        manifest = json.loads((ROOT / "config" / "scheduled_tasks" / "manifest.json").read_text(encoding="utf-8"))
        tasks = manifest["tasks"]
        task_keys = {str(task["task_key"]) for task in tasks}
        self.assertEqual(manifest["contract_version"], "scheduled_tasks_manifest.v2")
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            registration_path = ROOT / str(task["registration_script"])
            runner_path = ROOT / str(task["runner_script"])
            self.assertTrue(registration_path.exists(), registration_path)
            self.assertTrue(runner_path.exists(), runner_path)
            registration_text = registration_path.read_text(encoding="utf-8")
            runner_text = runner_path.read_text(encoding="utf-8")
            self.assertIn("Get-OpenClawScheduledTaskEntry", registration_text)
            self.assertIn(str(task["task_key"]), registration_text)
            self.assertIn("Register-OpenClawScheduledTaskEntry", registration_text)
            self.assertIn("Get-OpenClawScheduledTaskEntry", runner_text)
            self.assertIn("Write-OpenClawScheduledTaskSummary", runner_text)
            registration = task["registration"]
            resilience = task["resilience"]
            self.assertIn("principal_mode", registration)
            self.assertIn("run_level", registration)
            self.assertIn("wake_to_run", resilience)
            self.assertIn("restart_count", resilience)
            self.assertIn("restart_interval_minutes", resilience)
            self.assertIn("startup_catchup_enabled", resilience)
            self.assertIn("startup_delay_minutes", resilience)
            for dependency_key in task.get("upstream_dependencies", []):
                self.assertIn(str(dependency_key), task_keys)

        batch_registration = ROOT / "scripts" / "common" / "register_openclaw_scheduled_tasks.ps1"
        power_script = ROOT / "scripts" / "common" / "configure_openclaw_power_resilience.ps1"
        smoke_script = ROOT / "scripts" / "common" / "test_openclaw_scheduler_resilience.ps1"
        startup_wrapper = ROOT / "scripts" / "common" / "run_openclaw_startup_catchup_wrapper.ps1"
        self.assertTrue(batch_registration.exists())
        self.assertTrue(power_script.exists())
        self.assertTrue(smoke_script.exists())
        self.assertTrue(startup_wrapper.exists())

    def test_key_runners_accept_catchup_switch(self) -> None:
        for relative_path in (
            "scripts/market_data/run_openclaw_binance_ohlcv_sync_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_derivatives_sync_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_universe_input_producer_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_universe_freeze_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_research_daily_cycle_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_repo_health_guard_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_strategy_proposal_cycle_runner.ps1",
        ):
            text = _read(relative_path)
            self.assertIn("[switch]$Catchup", text)

    def test_research_intake_runner_checks_upstream_freshness_before_consuming_queue(self) -> None:
        text = _read("scripts/openclaw/run_openclaw_research_intake_cycle_runner.ps1")
        self.assertIn("Test-OpenClawScheduledTaskUpstreamFreshness", text)
        self.assertIn("runner_status=RETRY_UPSTREAM_NOT_READY", text)


if __name__ == "__main__":
    unittest.main()
