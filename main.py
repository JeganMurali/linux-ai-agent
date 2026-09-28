#!/usr/bin/env python

from kokki.agent import KokkiAgent

def main():
    kokki = KokkiAgent()
    print("🤖 Kokki Kumar is ready!")
    print("Type 'exit' to quit\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Kokki: Catch you later! 👋")
            break

        response = kokki.chat(user_input)
        print(f"Kokki: {response}\n")


if __name__ == "__main__":
    main()
