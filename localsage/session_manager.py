"""Session I/O and history management."""

import json
import os
import platform
import textwrap

import tiktoken
from openai.types.chat import ChatCompletionMessageParam

from localsage.globals import SESSIONS_DIR, USER_NAME


class SessionManager:
    """Handles session-related I/O"""

    def __init__(self, config):
        self.config = config
        self.history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.config.system_prompt}
        ]
        self.active_session: str = ""
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.token_cache: list[tuple[int, int] | None] = []
        self.gen_time: float = 0

    def _json_helper(self, file_name: str) -> str:
        """JSON extension helper"""
        if not file_name.endswith(".json"):
            file_name += ".json"
        file_path = os.path.join(SESSIONS_DIR, file_name)
        return file_path

    def save_to_disk(self, filepath: str):
        """Save the current session to disk"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)
        self.active_session = filepath

    def load_from_disk(self, filepath: str):
        """Load session file from disk"""
        with open(filepath, "r", encoding="utf-8") as f:
            self.history = json.load(f)
        self.active_session = filepath

    def delete_file(self, filepath: str):
        """Used to remove a session file"""
        os.remove(filepath)

    def append_message(self, role: str, content: str):
        """Append content to the conversation history"""
        self.history.append({"role": role, "content": content})  # pyright: ignore

    def correct_history(self):
        """Corrects history if the API conncetion was interrupted"""
        if self.history and self.history[-1]["role"] == "user":
            _ = self.history.pop()

    def remove_history(self, index: int):
        """Removes a history entry via index"""
        # No longer assumes that index is valid
        try:
            self.history.pop(index)
        except IndexError:
            pass

    def reset(self):
        """Reset the current session state"""
        self.history = [{"role": "system", "content": self.config.system_prompt}]
        self.active_session = ""
        self.token_cache = []

    def reset_with_summary(self, summary_text: str):
        """Wipes the session and starts fresh with a summary."""
        self.active_session = ""
        self.token_cache = []
        self.history = [
            {"role": "system", "content": self.config.system_prompt},
            {
                "role": "system",
                "content": "This summary represents the previous session.",
            },
            {"role": "assistant", "content": summary_text},
        ]

    def find_sessions(self) -> list[str]:
        """Lists all sessions that exist within SESSIONS_DIR"""
        sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        return sorted(sessions)

    def count_tokens(self) -> int | tuple[int, float]:
        """Counts and caches tokens."""
        # Ensure cache length matches history
        cache: list[tuple[int, int] | None] = self.token_cache
        diff = len(self.history) - len(cache)
        if diff > 0:
            cache.extend([None] * diff)
        elif diff < 0:
            del cache[len(self.history) :]

        # Count tokens, then cache and return the total token count
        total = 0
        throughput = 0
        for i, msg in enumerate(self.history):
            raw_content = msg.get("content") or ""
            if isinstance(raw_content, list):
                text = "".join(
                    p.get("text", "") for p in raw_content if isinstance(p, dict)
                )
            else:
                text = str(raw_content)
            text_hash = hash(text)
            cached = cache[i]
            if cached is None or cached[0] != text_hash:
                count = self.encode(text)
                if self.gen_time:
                    throughput = count / self.gen_time
                cache[i] = (text_hash, count)
                total += count
            else:
                total += cached[1]
        if throughput:
            return total, throughput
        return total

    def count_turns(self) -> int:
        """Calculates and returns the turn number"""
        return sum(1 for m in self.history if m["role"] == "user")

    def turn_duration(self, start: float, end: float):
        """Sets gen_time by subtraction of two timers."""
        self.gen_time = end - start

    def encode(self, text: str) -> int:
        """Converts a string to tokens"""
        try:
            count = len(self.encoder.encode(text))
        except Exception:
            count = 0
        return count

    def history_wrapper(self, response: str, reasoning: str = ""):
        """Detects and wraps reasoning/CoT output for inclusion in assistant entries"""
        history_entry = ""
        if reasoning:
            history_entry += f"<think>\n{reasoning.strip()}\n</think>\n\n"
        history_entry += response.strip()
        self.append_message("assistant", history_entry)

    def get_environment(self) -> str:
        """Gathers details about the current environment."""
        system_info = platform.platform()
        wd = os.getcwd()

        try:
            items = os.listdir(wd)
            files = [f for f in items if os.path.isfile(os.path.join(wd, f))]
            dirs = [d for d in items if os.path.isdir(os.path.join(wd, d))]
        except OSError:
            files, dirs = [], []

        return textwrap.dedent(f"""
        [ENVIRONMENT CONTEXT]
        RULE: ONLY REFERENCE ENVIRONMENT CONTEXT IF IT IS RELEVANT TO THE CONVERSATION
        Current User: {USER_NAME}
        Operating System: {system_info}
        Working Directory: {wd}
        Visible Files: {", ".join(files[:20])}
        Visible Directories: {", ".join(dirs[:20])}
        """).strip()

    def process_history(self) -> list:
        """Condenses duplicate user entries within session history"""
        processed_history = []
        for msg in self.history:
            if (
                processed_history
                and processed_history[-1]["role"] == "user"
                and msg["role"] == "user"
            ):
                processed_history[-1]["content"] += f"\n\n{msg['content']}"
            else:
                processed_history.append(msg.copy())

        if processed_history and processed_history[0]["role"] == "system":
            processed_history[0]["content"] = (
                f"{processed_history[0]['content']}\n\n{self.get_environment()}"
            )

        return processed_history

    def trim_history(self):
        """Prunes oldest messages when the context window is full"""
        limit = int(self.config.context_length * 0.95)
        tokens = self.count_tokens()
        if isinstance(tokens, tuple):
            tokens = tokens[0]

        while tokens > limit and len(self.history) > 1:
            if len(self.token_cache) > 1:
                removed_item = self.token_cache.pop(1)
                if removed_item is not None:
                    tokens -= removed_item[1]
            self.history.pop(1)

    def return_assistant_msg(self) -> str | None:
        """Returns the last assistant message detected in history"""
        for msg in reversed(self.history):
            if msg["role"] == "assistant":
                assistant_msg = msg.get("content", "")
                if isinstance(assistant_msg, str or None):
                    return assistant_msg
