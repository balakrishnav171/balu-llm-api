#!/usr/bin/env python3
"""
Balu LLM API - Interactive Client
Talk to your local API from the terminal
"""
import requests
import json

API_URL = "http://localhost:8000"
API_KEY = "Uq93NGGuc12rJtzzJOYvu7fRcQkwE5qRfKyALAmJ6dFwRUyDmJ"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}


def check_health():
    """Check if the API is running"""
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        data = r.json()
        print(f"\n  API Status : {data['status'].upper()}")
        print(f"  Model      : {data['model']}")
        print(f"  Backend    : {data['backend']}")
        print(f"  LLM Ready  : {data['llm_reachable']}")
    except Exception:
        print("\n  API is not running. Start it with:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        exit(1)


def chat(messages):
    """Send messages to the API and get a response"""
    try:
        r = requests.post(
            f"{API_URL}/v1/chat",
            headers=HEADERS,
            json={"messages": messages},
            timeout=60
        )
        if r.status_code == 200:
            return r.json()["message"]["content"]
        else:
            return f"Error {r.status_code}: {r.json().get('detail', 'Unknown error')}"
    except requests.exceptions.Timeout:
        return "Request timed out. The model may be slow."
    except Exception as e:
        return f"Error: {e}"


def main():
    print("\n" + "="*50)
    print("   Balu LLM API - Interactive Client")
    print("="*50)

    check_health()

    print("\n  Commands: 'quit' to exit | 'clear' to reset chat")
    print("="*50 + "\n")

    chat_history = []

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit"]:
                print("\nGoodbye!\n")
                break

            if user_input.lower() == "clear":
                chat_history = []
                print("\nChat history cleared.\n")
                continue

            # Add user message to history
            chat_history.append({"role": "user", "content": user_input})

            # Get response
            print("Bot: ", end="", flush=True)
            response = chat(chat_history)
            print(response)
            print()

            # Add bot response to history
            chat_history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print("\n\nGoodbye!\n")
            break


if __name__ == "__main__":
    main()
