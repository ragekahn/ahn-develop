"""Quick demo / entry point for the LLM app.

Usage:
    python main.py                  # uses your .env settings
    python main.py "your question"  # ask a custom question
"""
import sys

from llm_app import LLMClient


def main() -> None:
    client = LLMClient()
    print(f"Provider: {client.config.provider} | Model: {client.config.model}\n")

    question = sys.argv[1] if len(sys.argv) > 1 else "In one sentence, introduce yourself."
    answer = client.chat(
        messages=[{"role": "user", "content": question}],
        system="You are a helpful, concise assistant.",
    )
    print("Q:", question)
    print("A:", answer)


if __name__ == "__main__":
    main()
