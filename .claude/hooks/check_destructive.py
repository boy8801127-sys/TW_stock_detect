import sys
import json
import re

sys.stdout.reconfigure(encoding="utf-8")

DANGEROUS_PATTERNS = [
    r"\brm\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\b",
    r"\bgit\s+clean\b[^\n]*-[a-zA-Z]*f",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+push\b[^\n]*(--force|-f)\b",
    r"\bgit\s+branch\s+-D\b",
    r"\bgit\s+checkout\s+\.(\s|$)",
    r"\bgit\s+restore\s+\.(\s|$)",
]


def main():
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            reason = (
                "偵測到危險的破壞性指令，可能永久刪除檔案或覆寫歷史／工作區："
                + cmd
                + "。請再次確認後才執行。"
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }, ensure_ascii=False))
            return


if __name__ == "__main__":
    main()
