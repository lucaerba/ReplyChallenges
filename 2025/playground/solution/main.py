"""
Entry-point principale — MirrorLife Preventive Intelligence System.

Uso:
    python main.py [--data-dir PATH] [--output PATH] [--strategy STRATEGY]

Strategie:
    heuristic  Classificazione puramente rule-based, nessuna API (default)
    hybrid     Rule-based + LLM per i casi borderline (richiede OPENROUTER_API_KEY o ANTHROPIC_API_KEY)
    llm        Solo LLM per tutti i casi (richiede OPENROUTER_API_KEY o ANTHROPIC_API_KEY)

Esempi:
    python main.py
    python main.py --strategy llm --output output/result_lev1.txt
    python main.py --data-dir ../public_lev_2 --output output/result_lev2.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Carica .env se presente
load_dotenv(Path(__file__).parent / ".env")

# Aggiungi la cartella solution al path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MirrorLife Preventive Intelligence — Reply Challenge 2026"
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "public_lev_1_eval"),
        help="Cartella con i dati del livello (default: ../public_lev_1_eval)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "output" / "result.txt"),
        help="File di output con i Citizen ID a rischio (default: output/result.txt)",
    )
    parser.add_argument(
        "--strategy",
        choices=["llm", "heuristic", "hybrid"],
        default="hybrid",
        help="Strategia di classificazione (default: hybrid)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("  MirrorLife Preventive Intelligence System")
    print("  Reply Challenges 2026 — The Eye Initiative")
    print("=" * 60)
    print(f"  Data dir : {args.data_dir}")
    print(f"  Output   : {args.output}")
    print(f"  Strategy : {args.strategy}")
    print("=" * 60)

    citizens_at_risk = run_pipeline(
        data_dir=args.data_dir,
        output_path=args.output,
        strategy=args.strategy,
    )

    print(f"\nDone. {len(citizens_at_risk)} citizen(s) flagged for preventive support.")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
