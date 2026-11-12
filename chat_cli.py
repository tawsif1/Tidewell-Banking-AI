"""Send one message to the running Tidewell API and print the result as JSON.

Usage, from the project folder with the server running:
    .venv/Scripts/python.exe chat_cli.py new "What are my balances?"
    .venv/Scripts/python.exe chat_cli.py <session_id> "Maria Chen, 1988-04-12, card 4821"

"new" starts a conversation; pass the printed session_id to continue it.
"""

import json
import sys
import urllib.error
import urllib.request

API_URL = "http://127.0.0.1:8000/chat"


def send(session_id: str | None, message: str) -> dict:
    """POST one message to /chat and return the response, or the error, as a dict."""
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return {"status": response.status, **json.loads(response.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode("utf-8", errors="replace")}
    except urllib.error.URLError as e:
        return {"status": 0, "error": f"Can't reach {API_URL}: {e.reason}. Is the server running?"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")  # replies can contain characters the Windows console code page lacks
    session_arg, text = sys.argv[1], sys.argv[2]
    result = send(None if session_arg == "new" else session_arg, text)
    print(json.dumps(result, indent=2, ensure_ascii=False))
