import subprocess
import sys
from datetime import datetime
from engine import SlothEngine

SYSTEM_PROMPT = """
You are an expert developer assistant. Read the provided git diff and return ONLY a JSON object with these exact keys:
- "commit_message": A clean Conventional Commit message (e.g., "feat(parser): add PDF text extraction fallback").
- "changelog_bullets": A list of 1 to 3 concise markdown bullet strings explaining what changed for CHANGELOG.md.
- "lazy_score": A fun short comment on how much typing you just saved the developer.
"""

class GitSloth:
    def __init__(self, model: str = "qwen2.5-coder:3b"):
        self.engine = SlothEngine(model=model)

    def get_staged_diff(self) -> str:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, encoding="utf-8"
        )
        return result.stdout.strip()

    def update_changelog(self, bullets: list):
        date_str = datetime.now().strftime("%Y-%m-%d")
        header = f"\n## [{date_str}]\n"
        body = "\n".join(f"- {b}" for b in bullets) + "\n"
        
        with open("CHANGELOG.md", "a", encoding="utf-8") as f:
            f.write(header + body)

    def run(self):
        diff = self.get_staged_diff()
        if not diff:
            print("🦥 Nothing staged! Run `git add .` first so I can do your work.")
            sys.exit(0)

        print("🦥 Reading your git diff locally (0 bytes sent to the cloud)...")
        data = self.engine.ask_json(SYSTEM_PROMPT, diff[:6000])

        commit_msg = data.get("commit_message", "chore: update code")
        bullets = data.get("changelog_bullets", ["Updated project files."])
        lazy_score = data.get("lazy_score", "Saved 2 minutes of thinking.")

        print(f"\n✨ Proposed Commit: \033[92m{commit_msg}\033[0m")
        print("📝 Changelog Entry:")
        for b in bullets:
            print(f"   • {b}")
        print(f"💤 {lazy_score}\n")

        choice = input("Commit and update CHANGELOG.md? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            self.update_changelog(bullets)
            subprocess.run(["git", "add", "CHANGELOG.md"])
            subprocess.run(["git", "commit", "-m", commit_msg])
            print("🦥 Done! Go take a break.")
        else:
            print("🦥 Aborted. No files changed.")

if __name__ == "__main__":
    GitSloth(model="qwen2.5-coder:3b").run()