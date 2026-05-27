from __future__ import annotations
from typing import TYPE_CHECKING

from franki.skills import get_system_prompt

if TYPE_CHECKING:
    from franki.routing import RoutingTracker
    from franki.cost_tracker import CostTracker
    from franki.change_tracker import ChangeTracker


class Session:
    def __init__(
        self,
        skill: str = "coding",
        memory_context: str = "",
        project_context: str | None = None,
    ) -> None:
        self.skill = skill
        self.scope: str | None = None
        self._memory_context = memory_context
        self._project_context = project_context or ""
        self._env_context = ""
        self._pinned: list[str] = []
        self._messages: list[dict] = []
        self.sandbox: bool = False
        self._branches: dict[str, list[dict]] = {}
        # Attached by the REPL
        self.routing_tracker: "RoutingTracker | None" = None
        self.cost_tracker: "CostTracker | None" = None
        self.change_tracker: "ChangeTracker | None" = None
        self._rebuild_system()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_system(self) -> None:
        prompt = get_system_prompt(self.skill)
        if self.scope and self.skill == "pentest":
            prompt += (
                f"\n\nActive pentest scope: {self.scope}"
                " — only target systems within this scope."
            )
        if self._pinned:
            prompt += "\n\n[Pinned reminders]\n" + "\n".join(f"- {p}" for p in self._pinned)
        if self._project_context:
            prompt += f"\n\n[Project context from .franki.md]\n{self._project_context}"
        if self._memory_context:
            prompt += f"\n\n{self._memory_context}"
        if self._env_context:
            prompt += f"\n\n{self._env_context}"
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

    def set_env_context(self, env_context: str) -> None:
        self._env_context = env_context
        self._rebuild_system()

    # ── Pinned reminders ──────────────────────────────────────────────────────

    def add_pin(self, text: str) -> int:
        """Add a pinned reminder. Returns its 1-based index."""
        self._pinned.append(text)
        self._rebuild_system()
        return len(self._pinned)

    def remove_pin(self, idx: int) -> bool:
        """Remove pin by 1-based index. Returns True if removed."""
        if 1 <= idx <= len(self._pinned):
            self._pinned.pop(idx - 1)
            self._rebuild_system()
            return True
        return False

    def list_pins(self) -> list[str]:
        return list(self._pinned)

    def clear_pins(self) -> None:
        self._pinned = []
        self._rebuild_system()

    # ── Session branching ─────────────────────────────────────────────────────

    def create_branch(self, name: str) -> None:
        """Save a named snapshot of the current message state."""
        import copy
        self._branches[name] = copy.deepcopy(self._messages)

    def restore_branch(self, name: str) -> bool:
        """Restore messages from a named snapshot. Returns False if not found."""
        import copy
        if name not in self._branches:
            return False
        self._messages = copy.deepcopy(self._branches[name])
        return True

    def list_branches(self) -> list[str]:
        return list(self._branches.keys())

    def set_memory_context(self, memory_context: str) -> None:
        self._memory_context = memory_context
        self._rebuild_system()

    def set_project_context(self, project_context: str | None) -> None:
        self._project_context = project_context or ""
        self._rebuild_system()

    # ── Message management ────────────────────────────────────────────────────

    def add_user(self, content) -> None:
        """Add a user message. content may be a str or a list (multimodal)."""
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})

    def add_tool_call_message(self, msg: dict) -> None:
        """Add an assistant message that contains tool_calls (from chat_with_tools)."""
        self._messages.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool result message (response to a specific tool call)."""
        self._messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def get_messages_for_api(
        self,
        tool_result_max_chars: int = 2000,
        max_history_turns: int = 0,
    ) -> list[dict]:
        """Return messages optimised for API calls.

        Trims large tool results to *tool_result_max_chars* chars so that
        file reads and command outputs don't accumulate and re-consume tokens
        on every subsequent request.  The full content is preserved in
        self._messages for /history and /diff display.

        If *max_history_turns* > 0, only the most recent N user turns (and
        everything after them) are included, keeping the system message.
        """
        msgs: list[dict] = list(self._messages)

        # ── Trim large tool results ───────────────────────────────────────────
        trimmed: list[dict] = []
        for msg in msgs:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > tool_result_max_chars:
                    msg = dict(msg)
                    excess = len(content) - tool_result_max_chars
                    msg["content"] = (
                        content[:tool_result_max_chars]
                        + f"\n… [{excess} chars not re-sent to save tokens]"
                    )
            trimmed.append(msg)

        # ── Sliding window: keep last N user turns ────────────────────────────
        if max_history_turns > 0:
            user_idxs = [i for i, m in enumerate(trimmed) if m["role"] == "user"]
            if len(user_idxs) > max_history_turns:
                cutoff = user_idxs[-max_history_turns]
                system_msgs = [m for m in trimmed if m["role"] == "system"]
                trimmed = system_msgs + trimmed[cutoff:]

        return trimmed

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

    def rewind_full(self) -> tuple[int, "str | list | None"]:
        """
        Remove everything from (and including) the last user message.
        Handles agent turns with interleaved tool/assistant messages.
        Returns (count_removed, last_user_content).
        """
        last_user_idx = None
        for i, m in enumerate(self._messages):
            if m["role"] == "user":
                last_user_idx = i
        if last_user_idx is None:
            return 0, None
        content = self._messages[last_user_idx]["content"]
        removed = len(self._messages) - last_user_idx
        self._messages = self._messages[:last_user_idx]
        return removed, content

    @property
    def last_user_message(self) -> "str | list | None":
        for m in reversed(self._messages):
            if m["role"] == "user":
                return m["content"]
        return None

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
        tokens = sum(len(m["content"]) // 4 for m in self._messages
                     if isinstance(m.get("content"), str))
        return {"user": user, "assistant": asst, "total": user + asst, "approx_tokens": tokens}

    # ── Session restore ───────────────────────────────────────────────────────

    @classmethod
    def from_dict(
        cls,
        data: dict,
        memory_context: str = "",
        project_context: str | None = None,
    ) -> "Session":
        """Restore a session from a dict produced by session_store.save_session."""
        s = cls.__new__(cls)
        s.skill            = data.get("skill", "coding")
        s.scope            = data.get("scope")
        s._memory_context  = memory_context
        s._project_context = project_context or ""
        s._env_context     = ""
        s._pinned          = data.get("pinned", [])
        s._messages        = []
        s.sandbox          = False
        s._branches        = {}
        s.routing_tracker  = None
        s.cost_tracker     = None
        s.change_tracker   = None
        # Rebuild fresh system message with current memory/project context
        s._rebuild_system()
        # Restore saved conversation (skip the saved system message)
        for m in data.get("messages", []):
            if m.get("role") != "system":
                s._messages.append(m)
        return s
