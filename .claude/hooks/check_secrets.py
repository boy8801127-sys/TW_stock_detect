import sys
import json
import re
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

SENSITIVE_PATTERN = re.compile(
    r"(^|/)(\.env(\..*)?|tw-stock-job\.yaml|.*\.pem|.*\.key|id_rsa.*|.*credential.*|.*secret.*|.*apikey.*)$",
    re.IGNORECASE,
)


def main():
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    if not re.search(r"\bgit\s+(add|commit)\b", cmd):
        return

    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return

    files = [line[3:].strip() for line in out.splitlines() if line.strip()]
    hits = [f for f in files if SENSITIVE_PATTERN.search(f)]
    if hits:
        reason = (
            "偵測到即將被 git add/commit 的變更中包含疑似機密檔案："
            + ", ".join(hits)
            + "。請確認這不是密鑰／憑證／環境變數檔後才繼續。"
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
