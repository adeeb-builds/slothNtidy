import subprocess
import sys
from datetime import datetime
from engine import SlothEngine

SYSTEM_PROMPT = """
You are an expert developer assistant. Read the provided git diff and return ONLY a JSON object with these exact keys:
- "commit_message": A clean Conventional Commit message (e.g., "feat(tidy): add batch duplicate detection and SlothVault").
- "changelog_bullets": A list of 1 to 3 concise markdown bullet strings explaining what changed for CHANGELOG.md.
- "lazy_score": A fun short comment on how much typing you just saved the developer.
"""

class GitSloth:
    def __init__(self, model: str = "qwen2.5:7b"):
        self.engine = SlothEngine(model=model)

    def get_staged_status_and_diff(self) -> str:
        # Gets both deleted/renamed file names (--stat) and the code changes
        stat = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout.strip()

        diff = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout.strip()

        if not stat and not diff:
            return ""
        return f"CHANGED FILES SUMMARY:\n{stat}\n\nCODE DIFF:\n{diff[:3500]}"

    def update_changelog(self, bullets: list):
        date_str = datetime.now().strftime("%Y-%m-%d")
        header = f"\n## [{date_str}]\n"
        body = "\n".join(f"- {b}" for b in bullets) + "\n"
        
        with open("CHANGELOG.md", "a", encoding="utf-8") as f:
            f.write(header + body)

    def run(self):
        diff_payload = self.get_staged_status_and_diff()
        if not diff_payload:
            print("🦥 Nothing staged! Run `git add -A` first so I can see your changes.")
            sys.exit(0)

        print("🦥 Reading your staged changes locally with qwen2.5:7b (0 bytes sent to cloud)...")
        data = self.engine.ask_json(SYSTEM_PROMPT, diff_payload)

        commit_msg = data.get("commit_message", "feat: update Sloth deduplication and vault")
        bullets = data.get("changelog_bullets", ["Updated project files and removed old inbox folder."])
        lazy_score = data.get("lazy_score", "Saved 2 minutes of typing.")

        print(f"\n✨ Proposed Commit: \033[92m{commit_msg}\033[0m")
        print("📝 Changelog Entry:")
        for b in bullets:
            print(f"   • {b}")
        print(f"💤 {lazy_score}\n")

        choice = input("👉 Commit and push these changes to GitHub? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            self.update_changelog(bullets)
            subprocess.run(["git", "add", "CHANGELOG.md"])
            subprocess.run(["git", "commit", "-m", commit_msg])
            print("🚀 Pushing to GitHub...")
            subprocess.run(["git", "push"])
            print("🦥 Done! Refresh your GitHub repo page to see the update.")
        else:
            print("🦥 Aborted. Nothing was committed or pushed.")

if __name__ == "__main__":
    GitSloth(model="qwen2.5:7b").run()