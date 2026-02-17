from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


class TraceDistiller:
    """
    Compress trace artifacts into compact behavioral policies.
    """

    def distill(self, trace_path: str, output_path: str, max_rules: int = 12) -> dict[str, Any]:
        trace_file = Path(trace_path)
        if not trace_file.exists():
            raise FileNotFoundError(trace_path)

        word_counter: Counter[str] = Counter()
        events = 0
        with trace_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                events += 1
                event = json.loads(line)
                payload = json.dumps(event.get("payload", {}), sort_keys=True)
                words = [w.lower() for w in payload.split() if len(w) > 4]
                word_counter.update(words)

        frequent = [token for token, _count in word_counter.most_common(max_rules)]
        policies = [f"Prefer reasoning patterns emphasizing '{token}'." for token in frequent]
        distilled = {
            "events_processed": events,
            "policies": policies,
            "token_basis": frequent,
        }
        Path(output_path).write_text(json.dumps(distilled, indent=2, ensure_ascii=True), encoding="utf-8")
        return distilled

