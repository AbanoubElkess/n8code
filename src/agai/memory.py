from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .types import EvidenceRecord, MessageEnvelope, ResultBundle


class ProvenanceMemory:
    def __init__(self, db_path: str = "artifacts/agai.sqlite", trace_path: str = "artifacts/trace.jsonl") -> None:
        self.db_path = Path(db_path)
        self.trace_path = Path(trace_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    cost_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    retrieval_time TEXT NOT NULL,
                    verifiability TEXT NOT NULL,
                    license TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    notes TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outcomes_json TEXT NOT NULL,
                    confidence_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    contradictions_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL
                )
                """
            )

    def record_message(self, message: MessageEnvelope) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (
                    sender, receiver, intent, content, evidence_refs, confidence, cost_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.sender,
                    message.receiver,
                    message.intent.value,
                    message.content,
                    json.dumps(message.evidence_refs),
                    message.confidence,
                    json.dumps(message.cost_spent.__dict__),
                    message.timestamp,
                ),
            )
            message_id = int(cur.lastrowid)
        self._append_trace({"type": "message", "id": message_id, "payload": message.__dict__})
        return message_id

    def record_evidence(self, evidence: EvidenceRecord) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO evidence (
                    source, retrieval_time, verifiability, license, hash, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.source,
                    evidence.retrieval_time,
                    evidence.verifiability,
                    evidence.license,
                    evidence.hash,
                    evidence.notes,
                ),
            )
            evidence_id = int(cur.lastrowid)
        self._append_trace({"type": "evidence", "id": evidence_id, "payload": evidence.__dict__})
        return evidence_id

    def record_result(self, result: ResultBundle) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO results (
                    outcomes_json, confidence_json, artifacts_json, contradictions_json, trace_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    json.dumps(result.outcomes),
                    json.dumps(result.confidence_intervals),
                    json.dumps(result.reproducibility_artifact_ids),
                    json.dumps(result.contradictions),
                    json.dumps(result.trace_ids),
                ),
            )
            result_id = int(cur.lastrowid)
        self._append_trace({"type": "result", "id": result_id, "payload": result.__dict__})
        return result_id

    def list_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sender, receiver, intent, content, evidence_refs, confidence, cost_json, timestamp
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            output.append(
                {
                    "sender": row[0],
                    "receiver": row[1],
                    "intent": row[2],
                    "content": row[3],
                    "evidence_refs": json.loads(row[4]),
                    "confidence": row[5],
                    "cost": json.loads(row[6]),
                    "timestamp": row[7],
                }
            )
        return output

    def _append_trace(self, event: dict[str, Any]) -> None:
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._to_jsonable(event), ensure_ascii=True) + "\n")

    def _to_jsonable(self, obj: Any) -> Any:
        if is_dataclass(obj):
            return self._to_jsonable(asdict(obj))
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, dict):
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._to_jsonable(v) for v in obj]
        return obj
