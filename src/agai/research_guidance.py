from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from .hypothesis import HypothesisExplorer
from .types import ExperimentPlan, HypothesisProgram


class ResearchGuidanceEngine:
    def __init__(self, explorer: Optional[HypothesisExplorer] = None) -> None:
        self.explorer = explorer or HypothesisExplorer()
        self._last_sandbox_report: dict[str, Any] = {}
        self._last_execution_dag: dict[str, Any] = {}
        self._last_execution_validation: dict[str, Any] = {}

    def build_experiment_plan(
        self,
        question: str,
        domain: str,
        constraints: list[str],
        budget: Optional[dict[str, float]] = None,
    ) -> tuple[ExperimentPlan, list[dict[str, Any]]]:
        seed = HypothesisProgram(
            rules=[
                f"Primary objective for {domain}: {question}",
                "Minimize logical error rate while preserving practical runtime.",
            ],
            priors={"known-physics-consistency": 0.8, "novelty-drive": 0.6},
            provenance=[f"generated:{datetime.utcnow().isoformat()}"],
        )
        sandbox = self.explorer.sandbox(seed_program=seed, limit=10, top_k=4)
        self._last_sandbox_report = sandbox
        ranked = sandbox.get("ranked_candidates", [])
        accepted_count = int(sandbox.get("accepted_count", 0))
        rejected_count = int(sandbox.get("rejected_count", 0))
        total_budget = budget or {
            "max_tokens": 3600.0,
            "max_latency_ms": 80_000.0,
            "max_energy_joules": 240.0,
            "max_usd": 0.12,
        }
        execution_dag = self._build_execution_dag(
            question=question,
            constraints=constraints,
            sandbox=sandbox,
            total_budget=total_budget,
        )
        validation = self._validate_execution_dag(execution_dag)
        self._last_execution_dag = execution_dag
        self._last_execution_validation = validation
        experiment = ExperimentPlan(
            simulator="qec-sim-lite",
            tool_chain=["literature-retrieval", "symbolic-checker", "qec-simulator", "statistical-validator"],
            parameters={
                "question": question,
                "domain": domain,
                "constraints": constraints,
                "num_hypotheses": len(ranked),
                "top_k": 4,
                "accepted_hypotheses": accepted_count,
                "rejected_hypotheses": rejected_count,
                "family_coverage": sandbox.get("family_coverage", {}),
                "execution_dag_nodes": len(execution_dag.get("nodes", [])),
                "parallel_simulation_branches": execution_dag.get("parallel_branch_count", 0),
                "execution_validation_ok": bool(validation.get("ok", False)),
            },
            stop_criteria={
                "max_runs": 60,
                "stability_delta": 0.03,
                "budget_guard": "strict",
                "min_acceptance_rate": 0.35,
                "min_budget_remaining_usd": 0.01,
                "rollback_on_failed_invariant": True,
            },
            steps=[
                "Formalize assumptions and target metric.",
                "Generate counterfactual hypotheses with control parameters.",
                "Run strict falsification gate and reject hard-invariant violations before simulation.",
                "Execute simulation and compare against baseline.",
                "Report confidence intervals, contradictions, and rejected-rule diagnostics.",
            ],
        )
        return experiment, [dict(item) for item in ranked]

    def latest_sandbox_report(self) -> dict[str, Any]:
        return deepcopy(self._last_sandbox_report)

    def latest_execution_dag(self) -> dict[str, Any]:
        return deepcopy(self._last_execution_dag)

    def latest_execution_validation(self) -> dict[str, Any]:
        return deepcopy(self._last_execution_validation)

    def _build_execution_dag(
        self,
        question: str,
        constraints: list[str],
        sandbox: dict[str, Any],
        total_budget: dict[str, float],
    ) -> dict[str, Any]:
        top_candidates = [item for item in sandbox.get("top_candidates", []) if isinstance(item, dict)]
        if not top_candidates:
            top_candidates = [
                {
                    "rule": "Fallback hypothesis: compare baseline and constrained variant with falsification checks.",
                    "score": 0.5,
                    "passed": False,
                }
            ]

        base_nodes = [
            {
                "id": "N0_FORMALIZE",
                "title": "Formalize objective and invariants",
                "kind": "analysis",
                "depends_on": [],
                "success_criteria": [
                    "Target metric and baseline defined.",
                    "Hard invariants declared before any simulation.",
                ],
                "failure_policy": {"on_fail": "abort", "rollback_to": None, "retry_limit": 0},
            },
            {
                "id": "N1_GENERATE",
                "title": "Generate and rank counterfactual hypotheses",
                "kind": "generation",
                "depends_on": ["N0_FORMALIZE"],
                "success_criteria": [
                    "Counterfactual families generated.",
                    "Top hypotheses ranked by falsification score.",
                ],
                "failure_policy": {"on_fail": "rollback", "rollback_to": "N0_FORMALIZE", "retry_limit": 1},
            },
            {
                "id": "N2_GATE",
                "title": "Run strict falsification and consistency gate",
                "kind": "validation",
                "depends_on": ["N1_GENERATE"],
                "success_criteria": [
                    "Hard-failing hypotheses are rejected.",
                    "Acceptance rate remains above minimum threshold.",
                ],
                "failure_policy": {"on_fail": "rollback", "rollback_to": "N1_GENERATE", "retry_limit": 2},
            },
        ]

        simulation_nodes: list[dict[str, Any]] = []
        for idx, candidate in enumerate(top_candidates, start=1):
            label = candidate.get("rule", "candidate")
            simulation_nodes.append(
                {
                    "id": f"N3_SIM_{idx}",
                    "title": f"Simulate hypothesis branch {idx}",
                    "kind": "simulation",
                    "depends_on": ["N2_GATE"],
                    "hypothesis_ref": f"H{idx}",
                    "hypothesis_summary": str(label)[:220],
                    "success_criteria": [
                        "QEC simulation executes with consistency status accepted or accepted-with-warnings.",
                        "Baseline delta and uncertainty metrics captured.",
                    ],
                    "failure_policy": {"on_fail": "rollback", "rollback_to": "N2_GATE", "retry_limit": 1},
                }
            )

        merge_node = {
            "id": "N4_ABLATE",
            "title": "Cross-branch ablation and robustness check",
            "kind": "analysis",
            "depends_on": [node["id"] for node in simulation_nodes],
            "success_criteria": [
                "Cross-branch tradeoff matrix produced.",
                "At least one hypothesis survives ablation.",
            ],
            "failure_policy": {"on_fail": "rollback", "rollback_to": "N3_SIM_1", "retry_limit": 1},
        }
        report_node = {
            "id": "N5_REPORT",
            "title": "Produce executable recommendation and next experiments",
            "kind": "reporting",
            "depends_on": ["N4_ABLATE"],
            "success_criteria": [
                "Recommendation includes uncertainty and contradictions.",
                "Next-step experiment DAG exported for researcher execution.",
            ],
            "failure_policy": {"on_fail": "rollback", "rollback_to": "N4_ABLATE", "retry_limit": 1},
        }

        nodes = base_nodes + simulation_nodes + [merge_node, report_node]
        budgets = self._allocate_node_budgets(total_budget=total_budget, node_count=len(nodes))
        for node, node_budget in zip(nodes, budgets):
            node["budget"] = node_budget
            node["entry_checks"] = [
                "Dependency nodes completed.",
                "Budget remains above node minimum threshold.",
            ]

        edges: list[dict[str, str]] = []
        for node in nodes:
            for dependency in node.get("depends_on", []):
                edges.append({"from": dependency, "to": node["id"], "condition": "on_success"})

        return {
            "version": "1.0",
            "question": question,
            "constraints": constraints,
            "entry_node": "N0_FORMALIZE",
            "terminal_node": "N5_REPORT",
            "nodes": nodes,
            "edges": edges,
            "parallel_branch_count": len(simulation_nodes),
            "stop_conditions": {
                "max_failed_nodes": 2,
                "min_budget_remaining_usd": 0.01,
                "abort_on_hard_invariant_failure": True,
            },
        }

    def _allocate_node_budgets(self, total_budget: dict[str, float], node_count: int) -> list[dict[str, float]]:
        if node_count <= 0:
            return []
        weights = [0.12, 0.16, 0.20]
        sim_weight_total = 0.34
        remaining_weight = 0.18
        sim_nodes = max(1, node_count - 5)
        sim_weight_each = sim_weight_total / sim_nodes
        dynamic_weights = weights + [sim_weight_each] * sim_nodes + [0.10, remaining_weight - 0.10]
        if len(dynamic_weights) < node_count:
            dynamic_weights.extend([sim_weight_each] * (node_count - len(dynamic_weights)))
        if len(dynamic_weights) > node_count:
            dynamic_weights = dynamic_weights[:node_count]
        total_weight = sum(dynamic_weights) or 1.0
        normalized = [weight / total_weight for weight in dynamic_weights]

        max_tokens = float(total_budget.get("max_tokens", 3600.0))
        max_latency_ms = float(total_budget.get("max_latency_ms", 80_000.0))
        max_energy_joules = float(total_budget.get("max_energy_joules", 240.0))
        max_usd = float(total_budget.get("max_usd", 0.12))
        allocations: list[dict[str, float]] = []
        for weight in normalized:
            allocations.append(
                {
                    "max_tokens": max(50.0, round(max_tokens * weight, 2)),
                    "max_latency_ms": max(1_000.0, round(max_latency_ms * weight, 2)),
                    "max_energy_joules": max(5.0, round(max_energy_joules * weight, 3)),
                    "max_usd": max(0.001, round(max_usd * weight, 4)),
                }
            )
        return allocations

    def _validate_execution_dag(self, dag: dict[str, Any]) -> dict[str, Any]:
        nodes = dag.get("nodes", [])
        errors: list[str] = []
        if not isinstance(nodes, list) or not nodes:
            return {"ok": False, "errors": ["Execution DAG has no nodes."], "topological_order": []}

        ids = [str(node.get("id", "")) for node in nodes]
        if len(set(ids)) != len(ids):
            errors.append("Execution DAG contains duplicate node IDs.")
        id_set = set(ids)

        for node in nodes:
            node_id = str(node.get("id", ""))
            dependencies = node.get("depends_on", [])
            if not isinstance(dependencies, list):
                errors.append(f"{node_id}: depends_on must be a list.")
                continue
            for dependency in dependencies:
                if dependency not in id_set:
                    errors.append(f"{node_id}: missing dependency '{dependency}'.")

            budget = node.get("budget", {})
            if not isinstance(budget, dict):
                errors.append(f"{node_id}: budget is missing or invalid.")
                continue
            for field in ("max_tokens", "max_latency_ms", "max_energy_joules", "max_usd"):
                try:
                    value = float(budget.get(field, 0.0))
                except (TypeError, ValueError):
                    errors.append(f"{node_id}: budget field '{field}' must be numeric.")
                    continue
                if value <= 0.0:
                    errors.append(f"{node_id}: budget field '{field}' must be > 0.")

        order, cycle_error = self._topological_order(nodes)
        if cycle_error:
            errors.append(cycle_error)
        entry = str(dag.get("entry_node", ""))
        if entry and entry not in id_set:
            errors.append(f"entry_node '{entry}' not found in DAG.")

        return {
            "ok": not errors,
            "errors": errors,
            "topological_order": order,
            "node_count": len(nodes),
        }

    def _topological_order(self, nodes: list[dict[str, Any]]) -> tuple[list[str], str]:
        ids = [str(node.get("id", "")) for node in nodes]
        indegree = {node_id: 0 for node_id in ids}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in ids}
        for node in nodes:
            node_id = str(node.get("id", ""))
            for dependency in node.get("depends_on", []):
                if dependency not in outgoing:
                    continue
                outgoing[dependency].append(node_id)
                indegree[node_id] += 1

        queue = [node_id for node_id, degree in indegree.items() if degree == 0]
        order: list[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for child in outgoing.get(current, []):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(nodes):
            return order, "Execution DAG contains a cycle."
        return order, ""
