"""
Entry-point — Reply Mirror 2026 Fraud Detection System.

Sistema multi-agente basato su LangGraph + ReAct per rilevare frodi finanziarie.
Usa OpenRouter come provider LLM e Langfuse (SDK v3) per il tracking.

Uso:
    python main.py [--data-dir PATH] [--output PATH]

Esempi:
    python main.py
    python main.py --data-dir "../The Truman Show - train" --output output/result.txt
    python main.py --data-dir "../The Truman Show - eval" --output output/submission.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Carica .env dalla directory del progetto
load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

from agents.llm_factory import flush_langfuse
from agents.orchestrator import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reply Mirror 2026 — Fraud Detection System"
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "The Truman Show - train"),
        help="Cartella con il dataset (default: ../The Truman Show - train)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "output" / "result.txt"),
        help="File di output con gli ID delle transazioni fraudolente",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 65)
    print("  Reply Mirror 2026 — Fraud Detection System")
    print("  The Eye Initiative — MirrorPay Fraud Intelligence")
    print("  Architecture: Multi-Agent ReAct + LangGraph")
    print("=" * 65)
    print(f"  Data dir : {args.data_dir}")
    print(f"  Output   : {args.output}")
    print("=" * 65)

    fraud_txs: list[str] = []
    try:
        fraud_txs = run_pipeline(
            data_dir=args.data_dir,
            output_path=args.output,
        )
        print(f"\nDone. {len(fraud_txs)} transazione/i fraudolente/i rilevate.")
        print(f"Output salvato in: {args.output}")
    finally:
        # Flush Langfuse anche in caso di interrupt/errori.
        try:
            flush_langfuse()
            print("Langfuse traces flushed.")
        except Exception as e:
            print(f"Langfuse flush skipped: {e}")


if __name__ == "__main__":
    main()
