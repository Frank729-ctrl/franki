from franki.skills import get_system_prompt


class Session:
    def __init__(self, skill: str = "coding", memory_context: str = "") -> None:
        self.skill = skill
        self.scope: str | None = None
        self._memory_context = memory_context
        self._messages: list[dict] = []
        self._rebuild_system()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_system(self) -> None:
        prompt = get_system_prompt(self.skill)
        if self.scope and self.skill == "pentest":
            prompt += (
                f"\n\nActive pentest scope: {self.scope}"
                " — only target systems within this scope."
            )
        if self._memory_context:
            prompt += f"\n\n{self._memory_context}"
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = prompt
        else:
            self._messages.insert(0, {"role": "system", "content": prompt})

    # ── Skill / scope ─────────────────────────────────────────────────────────

    def set_skill(self, skill: str) -> None:
        self.skill = skill
        self._rebuild_system()

    def set_scope(self, scope: str | None) -> None:
        self.scope = scope
        self._rebuild_system()

    def set_memory_context(self, memory_context: str) -> None:
        self._memory_context = memory_context
        self._rebuild_system()

    # ── Message management ────────────────────────────────────────────────────

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages = []
        self._rebuild_system()

    def rewind(self) -> int:
        """
        Remove the last user+assistant pair.
        Returns the number of messages removed (0, 1, or 2).
        """
        removed = 0
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
            removed += 1
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
            removed += 1
        return removed

    def compact(self, summary: str) -> None:
        """Replace history with a single compact summary, keeping system prompt."""
        self._messages = []
        self._rebuild_system()
        self._messages.append({
            "role": "assistant",
            "content": f"[Previous conversation summary]\n{summary}",
        })

    # ── Read-only views ───────────────────────────────────────────────────────

    def history_display(self) -> list[dict]:
        return [m for m in self._messages if m["role"] != "system"]

    @property
    def last_response(self) -> str | None:
        for m in reversed(self._messages):
            if m["role"] == "assistant":
                return m["content"]
        return None

    def message_stats(self) -> dict:
        user  = sum(1 for m in self._messages if m["role"] == "user")
        asst  = sum(1 for m in self._messages if m["role"] == "assistant")
        tokens = sum(len(m["content"]) // 4 for m in self._messages)
        return {"user": user, "assistant": asst, "total": user + asst, "approx_tokens": tokens}
