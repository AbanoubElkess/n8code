from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReflectionOutcome:
    revised_answer: str
    critiques: list[str]
    falsification_checks: list[str]


class ReflectionDebateLoop:
    """
    Small-model compatible reflection loop.
    Forces a falsification-first pass before accepting an answer.
    """

    def run(self, draft_answer: str) -> ReflectionOutcome:
        critiques = self._collect_critiques(draft_answer)
        checks = self._falsification_checks(draft_answer)
        revised = draft_answer
        if critiques:
            revised += "\n\nRevision Notes:\n" + "\n".join(f"- {c}" for c in critiques)
        if checks:
            revised += "\n\nFalsification Checklist:\n" + "\n".join(f"- {c}" for c in checks)
        return ReflectionOutcome(revised_answer=revised, critiques=critiques, falsification_checks=checks)

    def _collect_critiques(self, text: str) -> list[str]:
        critiques: list[str] = []
        lower = text.lower()
        if "assume" not in lower:
            critiques.append("No explicit assumptions listed.")
        if "risk" not in lower:
            critiques.append("Risk section missing.")
        if "experiment" not in lower and "test" not in lower:
            critiques.append("No concrete experiment/test step provided.")
        return critiques

    def _falsification_checks(self, text: str) -> list[str]:
        checks: list[str] = []
        if any(token in text.lower() for token in ("always", "never", "guarantee")):
            checks.append("Absolute claims detected; require counter-example search.")
        if len(text.split()) < 70:
            checks.append("Answer may be under-specified for scientific reproducibility.")
        checks.append("Validate against held-out benchmark tasks before acceptance.")
        return checks

