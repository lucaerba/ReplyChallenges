"""
Entry-point — MirrorLife Agentic Prevention System.

A differenza di solution/, questo sistema è fully agentic:
- Nessun parametro --strategy (è sempre LLM-driven)
- Gli agenti decidono autonomamente quali dati analizzare
- Il flusso del grafo stesso è determinato dalle decisioni LLM (conditional edges)
- Richiede OPENROUTER_API_KEY e LANGFUSE_* nel file .env

Uso:
    python main.py [--data-dir PATH] [--output PATH]

Esempi:
    python main.py
    python main.py --data-dir ../public_lev_1_eval --output output/result_agentic.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MirrorLife Agentic Prevention System — Reply Challenge 2026"
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "public_lev_3"),
        help="Cartella con i dati del livello (default: ../public_lev_3)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "output" / "result_agentic.txt"),
        help="File di output (default: output/result_agentic.txt)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("  MirrorLife Agentic Prevention System")
    print("  Reply Challenges 2026 — The Eye Initiative")
    print("  Mode: Fully Agentic (ReAct + LangGraph)")
    print("=" * 60)
    print(f"  Data dir : {args.data_dir}")
    print(f"  Output   : {args.output}")
    print("=" * 60)

    citizens_at_risk = run_pipeline(
        data_dir=args.data_dir,
        output_path=args.output,
    )

    print(f"\nDone. {len(citizens_at_risk)} citizen(s) flagged for preventive support.")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
