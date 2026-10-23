"""Human-readable, offline review of existing DBOSS Smart Cache Advisor output.

No PostgreSQL connection, subprocess, service, or tuning operation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

MAX_REPORT_BYTES = 64 * 1024 * 1024
ALLOWED = {"investigate", "non_scan_activity", "observe", "cache_effective_in_sample"}


def read_advice(path: str | Path) -> dict:
    source = Path(path)
    if source.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("advice file exceeds 64 MiB")
    with source.open(encoding="utf-8") as stream:
        doc = json.load(stream)
    if not isinstance(doc, dict) or doc.get("mode") != "smart-cache-advisor":
        raise ValueError("not a DBOSS advice report")
    if doc.get("read_only") is not True or doc.get("actions_taken") != []:
        raise ValueError("report does not attest observation-only operation")
    if not isinstance(doc.get("database"), str) or not doc["database"]:
        raise ValueError("database name missing")
    count = doc.get("intervals_analyzed")
    if type(count) is not int or count < 1:
        raise ValueError("invalid interval count")
    candidates = doc.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("missing candidate list")
    for item in candidates:
        if not isinstance(item, dict) or item.get("kind") not in {"index", "relation"}:
            raise ValueError("invalid candidate kind")
        if item.get("classification") not in ALLOWED:
            raise ValueError("invalid candidate classification")
        if not isinstance(item.get("relname"), str) or not isinstance(item.get("schemaname"), str):
            raise ValueError("missing object name")
        if item["kind"] == "index" and not isinstance(item.get("indexrelname"), str):
            raise ValueError("missing index name")
        missed = item.get("missed_blocks")
        if type(missed) is not int or missed < 0:
            raise ValueError("invalid missed_blocks")
        ratio = item.get("postgres_buffer_hit_ratio")
        if ratio is not None and (type(ratio) not in (int, float) or not 0 <= ratio <= 1):
            raise ValueError("invalid hit ratio")
    return doc


def _safe(value: object, max_width: int = 70) -> str:
    """Keep control characters out of terminal output from untrusted JSON."""
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "?", str(value))
    return cleaned[:max_width]


def render_advice(doc: dict, *, limit: int = 10) -> str:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    items = doc["candidates"]
    counts = Counter(item["classification"] for item in items)
    verified = "sim" if doc.get("source_identity_verified") is True else "nao"
    lines = [
        "DBOSS - Resumo do Smart Cache Advisor (somente leitura)",
        f"Banco: {_safe(doc['database'])} | Intervalos: {doc['intervals_analyzed']}",
        f"Confianca: {_safe(doc.get('confidence', 'nao informada'))} | Identidade da origem verificada: {verified}",
        f"Candidatos neste arquivo: {len(items)} (lista ja limitada pelo Advisor)",
        ("Classificacoes: investigacao=" + str(counts["investigate"]) +
         ", atividade_sem_scan=" + str(counts["non_scan_activity"]) +
         ", observar=" + str(counts["observe"]) +
         ", cache_eficiente=" + str(counts["cache_effective_in_sample"])),
        "",
        "Tipo    Objeto                                                  Faltas  Hit PG  Situacao",
    ]
    for item in items[:limit]:
        name = f"{item['schemaname']}.{item['relname']}"
        if item["kind"] == "index":
            name += f" / {item['indexrelname']}"
        ratio = item["postgres_buffer_hit_ratio"]
        pct = f"{100*ratio:5.1f}%" if ratio is not None else "  n/d "
        lines.append(f"{_safe(item['kind'],7):7} {_safe(name,54):54} "
                     f"{item['missed_blocks']:>8}  {pct:>6}  {_safe(item['classification'],26)}")
    lines.extend([
        "",
        "Interpretacao: faltas em shared_buffers NAO provam leitura fisica em disco.",
        "A classificacao 'investigate' NAO autoriza pg_prewarm, DROP INDEX ou tuning.",
        "Uma janela isolada e a identidade nao verificada limitam as conclusoes.",
        "Nenhuma acao foi executada no banco, no ZFS ou no kernel.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dboss review",
                                     description="Readable review of an existing DBOSS advice JSON")
    parser.add_argument("--advice", required=True, help="Existing advice.json file")
    parser.add_argument("--limit", type=int, default=10, help="Rows to show (1..100)")
    args = parser.parse_args(argv)
    try:
        print(render_advice(read_advice(args.advice), limit=args.limit), end="")
        return 0
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # Do not dump untrusted report contents or paths containing private names.
        print(f"dboss review: invalid advice input ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
