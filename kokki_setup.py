#!/usr/bin/env python
"""
Interactive setup for Kokki. Run this once after installing:

    python setup.py

Walks you through choosing an AI backend, a personality, and which tools
to enable, then writes it all to a .env file that kokki/config.py reads.
"""
import subprocess


PERSONALITY_PRESETS = {
    "1": "You're sharp-tongued, foul-mouthed, and allergic to being impressed by anything. Roast the SPECIFIC situation, not just the user generically - react to what's actually happening. Dry, confident, a little superior. Keep responses SHORT and punchy, never a formal report.",
    "2": "You're friendly, upbeat, and genuinely helpful. Keep responses SHORT and clear, no unnecessary fluff.",
    "3": "You're calm, precise, and professional - like a competent sysadmin colleague. Keep responses SHORT and factual.",
}

AVAILABLE_TOOLS = {
    "1": ("system_control", "Run shell commands, open apps, check system stats"),
}


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def setup_backend():
    print("\n🧠 Which AI backend do you want to use?")
    print("  1. Groq   - cloud, fast, free tier (needs an API key)")
    print("  2. Ollama - fully local, private, no key needed (needs Ollama running)")
    choice = ask("Choose", "1")

    if choice == "2":
        base_url = ask("Ollama base URL", "http://localhost:11434")
        model = ask("Ollama model name", "qwen3:1.7b")

        print(f"\nChecking Ollama at {base_url} ...")
        try:
            import urllib.request
            urllib.request.urlopen(f"{base_url}/api/tags", timeout=3)
            print("✅ Ollama is reachable.")
        except Exception:
            print("⚠️  Couldn't reach Ollama there. Make sure `ollama serve` is running before you use Kokki.")

        return {
            "KOKKI_LLM_BACKEND": "ollama",
            "KOKKI_OLLAMA_BASE_URL": base_url,
            "KOKKI_OLLAMA_MODEL": model,
        }

    api_key = ask("Enter your Groq API key (get one free at console.groq.com)")
    model = ask("Groq model", "openai/gpt-oss-120b")
    return {
        "KOKKI_LLM_BACKEND": "groq",
        "GROQ_API_KEY": api_key,
        "KOKKI_GROQ_MODEL": model,
    }


def setup_personality():
    print("\n🎭 Choose a personality:")
    print("  1. Sarcastic & profane (Kokki's default character)")
    print("  2. Friendly & upbeat")
    print("  3. Calm & professional")
    print("  4. Write your own")
    choice = ask("Choose", "1")

    if choice == "4":
        personality = ask("Describe the personality in a sentence or two")
    else:
        personality = PERSONALITY_PRESETS.get(choice, PERSONALITY_PRESETS["1"])

    print("\n🤬 Allow profanity?")
    profanity = ask("y/n", "y").lower().startswith("y")

    return {
        "KOKKI_PERSONALITY": personality,
        "KOKKI_PROFANITY": "true" if profanity else "false",
    }


def setup_tools():
    print("\n🛠️  Available tools:")
    for key, (name, desc) in AVAILABLE_TOOLS.items():
        print(f"  {key}. {name} - {desc}")
    print("Enter the numbers you want enabled, comma-separated (or press enter for all).")
    choice = ask("Tools", ",".join(AVAILABLE_TOOLS.keys()))
    chosen = [AVAILABLE_TOOLS[c.strip()][0] for c in choice.split(",") if c.strip() in AVAILABLE_TOOLS]
    return {"KOKKI_ENABLED_TOOLS": ",".join(chosen)}


def write_env(values: dict):
    lines = [f"{key}={value}" for key, value in values.items() if value is not None]
    with open(".env", "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    print("🤖 Kokki Setup\n" + "=" * 40)

    values = {}
    values.update(setup_backend())
    values.update(setup_personality())
    values.update(setup_tools())

    write_env(values)

    print("\n" + "=" * 40)
    print("✅ Setup complete! Written to .env")
    print("Run `python main.py` to start chatting with Kokki.")


if __name__ == "__main__":
    main()
