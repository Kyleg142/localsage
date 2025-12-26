#!/usr/bin/env python3

# <~~~~~~~~~~>
#  LOCAL SAGE
# <~~~~~~~~~~>

import getpass
import json
import logging
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler

import keyring
import tiktoken
from keyring import get_password, set_password
from keyring.backends import null
from keyring.errors import KeyringError
from openai import OpenAI, Stream
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from platformdirs import user_data_dir
from prompt_toolkit import prompt
from prompt_toolkit.completion import (
    PathCompleter,
    WordCompleter,
)
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import Validator
from rich import box
from rich.console import Console, ConsoleRenderable, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from localsage import __version__
from localsage.sage_math_sanitizer import sanitize_math_safe

APP_DIR = user_data_dir("LocalSage")
CONFIG_DIR = os.path.join(APP_DIR, "config")
SESSIONS_DIR = os.path.join(APP_DIR, "sessions")
LOG_DIR = os.path.join(APP_DIR, "logs")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
USER_NAME = getpass.getuser()


# Logger setup
def init_logger():
    """Initializes the logging system."""
    date_str = datetime.now().strftime("%Y%m%d")
    # Output example: localsage_20251109.log
    log_path = os.path.join(LOG_DIR, f"localsage_{date_str}.log")
    # Max of 3 backups, max size of 1MB
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler],
    )


def log_exception(e: Exception, context: str = ""):
    """Creates a full, formatted traceback string and writes it to a log file"""
    import traceback

    # Format the traceback (exception class, exception instance, traceback object)
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    # Add optional context provided by error catchers ('except Exception as e:' blocks)
    msg = f"{context}\n{tb}" if context else tb
    logging.error(msg)


# Keyring safety net
def setup_keyring_backend():
    """Safely detects a keyring backend."""
    try:
        keyring.get_keyring()
    except Exception as e:
        keyring.set_keyring(null.Keyring())
        logging.error(
            f"Keyring backend failed. Falling back to NullBackend. Error: {e}"
        )


def retrieve_key() -> str:
    """
    Attempts to retrieve a stored API key

    Prio: OPENAI_API_KEY env variable -> OS keyring entry -> Dummy key
    """
    api_key = ""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
    except Exception:
        pass
    if not api_key:
        try:
            api_key = get_password("LocalSageAPI", USER_NAME)
        except Exception:
            pass
    if not api_key:
        api_key = "dummy-key"
    return api_key


# Spinner
def spinner_constructor(content: str) -> Spinner:
    # Needs to be a function, so it can be used in main() and Chat.stream_response
    return Spinner(
        "moon",
        text=f"[bold medium_orchid]{content}[/bold medium_orchid]",
    )


# <~~GLOBAL STYLING~~>
# Main prompt prefix
PROMPT_PREFIX = HTML("<seagreen>󰅂 </seagreen>")
# Dark style for all prompt_toolkit completers
COMPLETER_STYLER = Style.from_dict(
    {
        # Completions
        "completion-menu.completion": "bg:#202020 #ffffff",
        "completion-menu.completion.current": "bg:#024a1a #000000",  # 2E8B57
        # Tooltips
        "completion-menu.meta.completion": "bg:#202020 #aaaaaa",
        "completion-menu.meta.completion.current": "bg:#024a1a #000000",
    }
)
# Main prompt command completer
COMMAND_COMPLETER = WordCompleter(
    [
        "!a",
        "!attach",
        "!attachments",
        "!clear",
        "!config",
        "!consume",
        "!ctx",
        "!delete",
        "!h",
        "!help",
        "!key",
        "!l",
        "!load",
        "!profile add",
        "!profile list",
        "!profile remove",
        "!profile switch",
        "!prompt",
        "!purge",
        "!purge all",
        "!q",
        "!quit",
        "!rate",
        "!reset",
        "!s",
        "!save",
        "!sessions",
        "!sum",
        "!summary",
        "!theme",
    ],
    match_middle=True,
    WORD=True,
)

# <~~REGGIE~~>
# Compiled regex used in the file management system
# Alternative, allows whitespace: ^---\s*File:\s*(.+?)
FILE_PATTERN = re.compile(r"^---\nFile: `(.*?)`", re.MULTILINE)

# <~~INTEGRATION~~>
console = Console()


# <~~CONFIG STATE~~>
class Config:
    """User-facing configuration variables"""

    def __init__(self):
        """Initialization for configurable variables."""
        self.models: list[dict] = [
            {
                "alias": "default",
                "name": "Sage",
                "endpoint": "http://localhost:8080/v1",
                "api_key": "stored",
            }
        ]
        self.active_model: str = "default"
        self.context_length: int = 131072
        self.refresh_rate: int = 30
        self.rich_code_theme: str = "monokai"
        self.reasoning_panel_consume: bool = True
        self.system_prompt: str = "You are Sage, an AI learning assistant."

    def active(self) -> dict:
        """Return the currently active model profile."""
        for m in self.models:
            if m["alias"] == self.active_model:
                return m
        return self.models[0]

    def save(self):
        """Saves any config changes to the config file."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2)

    def load(self):
        """Loads the config file."""
        if not os.path.exists(CONFIG_FILE):
            self.save()
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            setattr(self, key, val)

    @property
    def endpoint(self) -> str:
        """Returns the API endpoint for use in Chat"""
        return self.active()["endpoint"]

    @property
    def model_name(self) -> str:
        """Returns the model name for use in Chat"""
        return self.active()["name"]

    @property
    def alias_name(self) -> str:
        """Returns the profile name for use in Chat"""
        return self.active()["alias"]


# <~~SESSION STATE~~>
class SessionManager:
    """
    Handles session management
    - Session-related I/O
    - Session history
    - Session tokenization
    """

    def __init__(self, config: Config):
        self.config: Config = config
        self.history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.config.system_prompt}
        ]
        self.active_session: str = ""
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.token_cache: list[tuple[int, int] | None] = []
        self.gen_time: float = 0

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
        try:
            count = len(self.encoder.encode(text))
        except Exception:
            count = 0
        return count

    def _json_helper(self, file_name: str) -> str:
        """
        JSON extension helper.\n
        Used throughout most session management methods.
        """
        if not file_name.endswith(".json"):
            file_name += ".json"
        file_path = os.path.join(SESSIONS_DIR, file_name)
        return file_path

    def _session_completer(self) -> WordCompleter:
        """Session completion helper for the session manager"""
        return WordCompleter(
            [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
            ignore_case=True,
            sentence=True,
        )


class FileManager:
    """Handles file management (I/O)"""

    def __init__(self, session: SessionManager):
        self.session: SessionManager = session

    def process_file(self, path: str) -> tuple[bool, int]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()

        consumption = self.session.encode(content)
        content = content.replace("```", "ʼʼʼ")
        filename = os.path.basename(path)
        wrapped = f"---\nFile: `{filename}`\n```\n{content}\n```\n---"
        existing = [(i, t, n) for i, t, n in self.get_attachments() if n == filename]
        is_update = False

        # If the file exists already in context, delete it.
        if existing:
            index = existing[-1][0]
            self.session.remove_history(index)
            is_update = True
        # Add the file's content to context, wrapped in Markdown for retrieval
        self.session.append_message("user", wrapped)
        return is_update, consumption

    def remove_attachment(self, target_name: str) -> str | None:
        """Removes an attachment by name."""
        attachments = self.get_attachments()
        target = target_name.lower().strip()
        for index, kind, name in reversed(attachments):
            if target == "[all]":
                self.session.remove_history(index)
                continue
            if target == name.lower():
                self.session.remove_history(index)
                return kind  # For the UI to catch
        return None

    def get_attachments(self) -> list[tuple[int, str, str]]:
        """Retrieves a list of all attachments by utilizing regex."""
        attachments: list[tuple[int, str, str]] = []
        # Iterate through all messages in the conversation history
        for i, msg in enumerate(self.session.history):
            content = msg.get("content")
            if isinstance(content, str):
                match = FILE_PATTERN.match(content)
                if match:
                    # Append each attachment to a new structured list
                    attachments.append((i, "file", match.group(1)))
        return attachments

    def file_validator(self) -> Validator:
        return Validator.from_callable(
            self._file_validator,
            error_message="File does not exist.",
            move_cursor_to_end=True,
        )

    def _file_validator(self, text: str) -> bool:
        """File validation helper for prompt_toolkit"""
        # Boiled down to two lines, simply validates that a file exists
        text = os.path.abspath(os.path.expanduser(text))
        return os.path.isfile(text)


# <~~USER INTERFACE~~~>
class UIConstructor:
    """Constructs and returns various UI objects"""

    def __init__(self, config: Config, session: SessionManager):
        self.config = config
        self.session = session

    def reasoning_panel_constructor(self) -> Panel:
        return Panel(
            "",
            title=Text("🧠 Reasoning", style="bold yellow"),
            title_align="left",
            border_style="yellow",
            style="#b0b0b0 italic",
            width=None,
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def response_panel_constructor(self) -> Panel:
        return Panel(
            "",
            title=Text("💬 Response", style="bold green"),
            title_align="left",
            border_style="green",
            style="default",
            width=None,
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def user_panel_constructor(self, content: str) -> Panel:
        return Panel(
            content,
            box=box.HORIZONTALS,
            padding=(0, 0),
            title=Text("🌐 You", style="bold blue"),
            title_align="left",
            border_style="blue",
            style="default",
        )

    def status_panel_constructor(self, toks=True) -> Panel:
        turns = self.session.count_turns()
        tokens = self.session.count_tokens()
        throughput = 0
        if isinstance(tokens, tuple):
            context = tokens[0]
            throughput = tokens[1]
        else:
            context = tokens
        context_percentage = round((context / self.config.context_length) * 100, 1)

        # Colorize context percentage based on context consumption
        context_color: str = "dim"
        if context_percentage >= 50 and context_percentage < 80:
            context_color = "yellow"
        elif context_percentage >= 80:
            context_color = "red"

        # Status panel content
        status_text = Text.assemble(
            (" ", "cyan"),
            ("Context: "),
            (f"{context_percentage}%", f"{context_color}"),
            (" | "),
            (f"Turn: {turns}"),
        )
        if throughput and toks:
            status_text.append(f" | Tk/s: {throughput:.1f}")
        return Panel(
            status_text,
            border_style="dim",
            style="dim",
            expand=False,
        )

    def intro_panel_constructor(self) -> Panel:
        intro_text = Text.assemble(
            ("Model: ", "bold sandy_brown"),
            (f"{self.config.model_name}"),
            ("\nProfile: ", "bold sandy_brown"),
            (f"{self.config.alias_name}"),
            ("\nSystem Prompt: ", "bold sandy_brown"),
            (f"{self.config.system_prompt}", "italic"),
        )
        return Panel(
            intro_text,
            title=Text(f"🔮 Local Sage {__version__}", "bold medium_orchid"),
            title_align="left",
            border_style="medium_orchid",
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def error_panel_constructor(self, error: str, exception: str) -> Panel:
        return Panel(
            exception,
            title=Text(f"❌ {error}", style="bold red"),
            title_align="left",
            border_style="red",
            expand=False,
        )

    def help_chart_constructor(self) -> Markdown:
        return Markdown(
            textwrap.dedent("""
            | **Profile Management** | *Manage multiple models & API endpoints* |
            | --- | ----------- |
            | `!profile add` | Add a new model profile. Prompts for alias, model name, and **API endpoint**. |
            | `!profile remove` | Remove an existing profile. |
            | `!profile list` | List configured profiles. |
            | `!profile switch` | Switch between profiles. |

            | **Configuration** | *Main configuration commands* |
            | --- | ----------- |
            | `!config` | Display your current configuration settings and default directories. |
            | `!consume` | Toggle Reasoning panel consumption.  |
            | `!ctx` | Set maximum context length (for CLI functionality). |
            | `!key` | Set an API key, if needed. Your API key is stored in your OS keychain. |
            | `!prompt` | Set a new system prompt. Takes effect on your next session. |
            | `!rate` | Set the current refresh rate (default is 30). Higher refresh rate = higher CPU usage. |
            | `!theme` | Change your Markdown theme. Built-in themes can be found at https://pygments.org/styles/ |

            | **Session Management** | *Session management commands* |
            | --- | ----------- |
            | `!s` or `!save` | Save the current session. |
            | `!l` or `!load` | Load a saved session, including a scrollable conversation history. |
            | `!sum` or `!summary` | Prompt your model for summarization and start a fresh session with the summary. |
            | `!sessions` | List all saved sessions. |
            | `!reset` | Reset for a fresh session. |
            | `!delete` | Delete a saved session. |
            | `!clear` | Clear the terminal window. |
            | `!q` or `!quit` | Exit Local Sage. |
            | | |
            | `Ctrl + C` | Abort mid-stream, reset the turn, and return to the main prompt. Also acts as an immediate exit. |
            | **WARNING:** | Using `Ctrl + C` as an immediate exit does not trigger an autosave! |

            | **File Management** | *Commands for attaching and managing files* |
            | --- | ----------- |
            | `!a` or `!attach` | Attaches a file to the current session. |
            | `!attachments` | List all current attachments. |
            | `!purge` | Choose a specific attachment and purge it from the session. Recovers context length. |
            | `!purge all` | Purges all attachments from the current session. |
            | | |
            | **FILE TYPES:** | All text-based file types are acceptable. |
            | **NOTE:** | If you ever attach a problematic file, `!purge` can be used to rescue the session. |
            """)
        )

    def settings_chart_constructor(self) -> Markdown:
        return Markdown(
            textwrap.dedent(f"""
            | **Current Settings** | *Your current persistent settings* |
            | --- | ----------- |
            | **Profile**: | *{self.config.alias_name}* |
            | | |
            | **Model Name**: | *{self.config.model_name}* |
            | | |
            | **System Prompt**: | *{self.config.system_prompt}* |
            | | |
            | **Context Length**: | *{self.config.context_length}* |
            | | |
            | **Refresh Rate**: | *{self.config.refresh_rate}* |
            | | |
            | **Markdown Theme**: | *{self.config.rich_code_theme}* |
            - Your configuration file is located at: `{CONFIG_FILE}`
            - Your session files are located at:     `{SESSIONS_DIR}`
            - Your error logs are located at:        `{LOG_DIR}`
            """)
        )


class GlobalPanels:
    """Global panel spawner"""

    def __init__(self, session: SessionManager, config: Config, ui: UIConstructor):
        self.session: SessionManager = session
        self.config: Config = config
        self.ui: UIConstructor = ui

    def spawn_intro_panel(self):
        """Simple welcome panel, prints on application launch."""
        console.print(self.ui.intro_panel_constructor())
        console.print(Markdown("Type `!h` for a list of commands."))
        console.print()

    def spawn_status_panel(self, toks=True):
        """Prints a status panel."""
        # Status panel constructor
        console.print(self.ui.status_panel_constructor(toks))
        console.print()

    def spawn_error_panel(self, error: str, exception: str):
        """Error panel template for Local Sage, used in Chat() and main()"""
        console.print(self.ui.error_panel_constructor(error, exception))
        console.print()


# <~~COMMANDS~~>
class CLIController:
    """Handles and supports all command input"""

    def __init__(
        self,
        config: Config,
        session: SessionManager,
        filemanager: FileManager,
        panel: GlobalPanels,
        ui: UIConstructor,
    ):
        self.config: Config = config
        self.ui: UIConstructor = ui
        self.session: SessionManager = session
        self.filemanager: FileManager = filemanager
        self.panel: GlobalPanels = panel
        self.filepath_history = InMemoryHistory()
        self.interface = None

        # Command dict
        self.commands = {
            "!h": self.spawn_help_chart,
            "!help": self.spawn_help_chart,
            "!s": self.save_session,
            "!save": self.save_session,
            "!l": self.load_session,
            "!load": self.load_session,
            "!a": self.attach_file,
            "!attach": self.attach_file,
            "!attachments": self.list_attachments,
            "!purge": self.purge_attachment,
            "!purge all": self.purge_all_attachments,
            "!consume": self.toggle_consume,
            "!sessions": self.list_sessions,
            "!delete": self.delete_session,
            "!reset": self.reset_session,
            "!sum": self.summarize_session,
            "!summary": self.summarize_session,
            "!config": self.spawn_settings_chart,
            "!clear": console.clear,
            "!profile list": self.list_models,
            "!profile add": self.add_model,
            "!profile remove": self.remove_model,
            "!profile switch": self.switch_model,
            "!q": sys.exit,
            "!quit": sys.exit,
            "!ctx": self.set_context_length,
            "!rate": self.set_refresh_rate,
            "!theme": self.set_code_theme,
            "!key": self.set_api_key,
            "!prompt": self.set_system_prompt,
        }

        self.session_prompt = HTML("Enter a session name<seagreen>:</seagreen> ")

    def handle_input(self, user_input: str) -> bool | None | OpenAI:
        """Parse user input for a command & handle it"""
        cmd = user_input.lower()
        if cmd in self.commands:
            if (
                cmd in ("!q", "!quit", "!sum", "!summarize", "!l", "!load")
                and len(self.session.history) > 1
            ):
                choice = self._prompt_wrapper(
                    HTML("Save first? (<seagreen>y</seagreen>/<ansired>N</ansired>): "),
                    allow_empty=True,
                )
                if choice and choice.lower() in ("y", "yes"):
                    self.save_session()
                elif choice is None:
                    return True
            if cmd in ("!q", "!quit"):
                console.print("[yellow]✨ Farewell![/yellow]\n")
            return self.commands[cmd]()
        return False  # No command detected

    def set_interface(self, chat_interface):
        """Setter to inject the Chat/Renderer instance."""
        self.interface = chat_interface

    # <~~CHARTS~~>
    def spawn_help_chart(self):
        """Markdown usage chart."""
        console.print(self.ui.help_chart_constructor())
        console.print()

    def spawn_settings_chart(self):
        """Markdown settings chart."""
        console.print(self.ui.settings_chart_constructor())
        console.print()

    # <~~MAIN CONFIG~~>
    def set_system_prompt(self):
        """Sets a new persistent system prompt within the config file."""
        sysprompt = (
            self._prompt_wrapper(
                HTML("Enter a system prompt<seagreen>:</seagreen> "),
                allow_empty=True,
            )
            or ""
        )
        self.config.system_prompt = sysprompt
        self.config.save()
        console.print(f"[green]System prompt updated to:[/green] {sysprompt}")
        console.print(
            "[dim]Use [cyan]!reset[/cyan] to start a session with the new prompt. Be sure to [cyan]!save[/cyan] first, if desired.[/dim]"
        )
        console.print()

    def set_context_length(self):
        """Sets a new persistent context length"""
        ctx = self._prompt_wrapper(
            HTML("Enter a max context length<seagreen>:</seagreen> ")
        )
        if not ctx:
            return
        try:
            value = int(ctx)
            if value <= 0:
                raise ValueError
        except ValueError:
            self.panel.spawn_error_panel(
                "VALUE ERROR", "Please enter a positive number."
            )
            return

        self.config.context_length = value
        self.config.save()
        console.print(f"[green]Context length set to:[/green] {value}\n")

    def set_api_key(self) -> OpenAI | None:
        """Allows the user to set an API key. SAFELY stores the user's API key with keyring"""
        new_key = self._prompt_wrapper(HTML("Enter an API key<seagreen>:</seagreen> "))
        if not new_key:
            return
        try:
            # Try to store securely w/ keyring
            set_password("LocalSageAPI", USER_NAME, new_key)
            console.print("[green]API key updated.[/green]\n")
        except (KeyringError, ValueError, RuntimeError, OSError) as e:
            self.panel.spawn_error_panel(
                "KEYRING ERROR",
                f"Could not save to your OS keychain: {e}\nUsing key for this session only.",
            )
        return OpenAI(base_url=self.config.endpoint, api_key=new_key)

    def set_refresh_rate(self):
        """Set a new custom refresh rate"""
        rate = self._prompt_wrapper(HTML("Enter a refresh rate<seagreen>:</seagreen> "))
        if not rate:
            return
        try:
            value = int(rate)
            if value <= 3:
                raise ValueError
        except ValueError:
            self.panel.spawn_error_panel(
                "VALUE ERROR", "Please enter a positive number ≥ 4."
            )
            return

        self.config.refresh_rate = value
        self.config.save()
        console.print(f"[green]Refresh rate set to:[/green] {value}\n")

    def set_code_theme(self):
        """Allows the user to change out the rich markdown theme"""
        theme = self._prompt_wrapper(
            HTML("Enter a valid theme name<seagreen>:</seagreen> ")
        )
        if not theme:
            return

        self.config.rich_code_theme = theme.lower()
        self.config.save()
        console.print(f"[green]Your theme has been set to: [/green]{theme}\n")

    def toggle_consume(self):
        "Toggles reasoning panel consumption on or off"
        self.config.reasoning_panel_consume = not self.config.reasoning_panel_consume
        self.config.save()
        state = "on" if self.config.reasoning_panel_consume else "off"
        color = "green" if self.config.reasoning_panel_consume else "red"
        console.print(
            f"Reasoning panel consumption toggled [{color}]{state}[/{color}].\n"
        )

    # <~~MODEL MANAGEMENT~~>
    def list_models(self):
        """List all configured models."""
        console.print("[cyan]Configured profiles:[/cyan]")
        for m in self.config.models:
            tag = "(active)" if m["alias"] == self.config.active_model else ""
            console.print(f"• {m['alias']} → {m['name']} [{m['endpoint']}] {tag}")
        console.print()

    def add_model(self):
        """Interactively add a model profile."""
        alias = self._prompt_wrapper(HTML("Profile name<seagreen>:</seagreen> "))
        if not alias:
            return
        name = self._prompt_wrapper(HTML("Model name<seagreen>:</seagreen> "))
        if not name:
            return
        console.print("[yellow]Format:[/yellow] https://ipaddress:port/v1")
        endpoint = self._prompt_wrapper(HTML("API endpoint<seagreen>:</seagreen> "))
        if not endpoint:
            return

        if any(m["alias"] == alias for m in self.config.models):
            console.print(f"[red]Profile[/red] '{alias}' [red]already exists.[/red]\n")
            return

        self.config.models.append(
            {
                "alias": alias,
                "name": name,
                "endpoint": endpoint,
                "api_key": "stored",
            }
        )
        self.config.save()
        console.print(f"[green]Profile[/green] '{alias}' [green]added.[/green]\n")

    def remove_model(self):
        """Remove a model profile by alias."""
        self.list_models()
        alias = self._prompt_wrapper(
            HTML("Enter a profile name<seagreen>:</seagreen> ")
        )
        if not alias:
            return

        if alias == self.config.active_model:
            console.print("[red]The active profile cannot be removed.[/red]\n")
            return

        before = len(self.config.models)
        self.config.models = [m for m in self.config.models if m["alias"] != alias]
        if len(self.config.models) < before:
            self.config.save()
            console.print(f"[green]Profile[/green] '{alias}' [green]removed.[/green]\n")
        else:
            console.print(f"[red]No profile found under alias[/red] '{alias}'.\n")

    def switch_model(self) -> tuple[OpenAI, str] | None:
        """Switch active model profile by alias."""
        self.list_models()
        alias = self._prompt_wrapper(
            HTML("Enter a profile name<seagreen>:</seagreen> ")
        )
        if not alias:
            return

        match = next((m for m in self.config.models if m["alias"] == alias), None)
        if not match:
            console.print(f"[red]No profile found under alias[/red] '{alias}'.\n")
            return

        self.config.active_model = alias
        self.config.save()
        console.print(
            f"[green]Switched to:[/green] {match['name']} "
            f"[dim]{match['endpoint']}[/dim]\n"
        )
        return (
            OpenAI(base_url=match["endpoint"], api_key=retrieve_key()),
            match["name"],
        )

    # <~~SESSION MANAGEMENT~~>
    def save_session(self):
        """Saves a session to a .json file"""
        if self.session.active_session:
            file_name = self.session.active_session
        else:
            file_name = self._prompt_wrapper(self.session_prompt)
            if not file_name:
                return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.save_to_disk(file_path)
            console.print(f"[green]Session saved in:[/green] {file_path}\n")
        except Exception as e:
            log_exception(
                e, f"Error in save_session() - file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("ERROR SAVING", f"{e}")
            return

    def load_session(self):
        """Loads a session from a .json file"""
        if not self.list_sessions():
            return
        file_name = self._prompt_wrapper(
            self.session_prompt,
            completer=self.session._session_completer(),
            style=COMPLETER_STYLER,
        )
        if not file_name:
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.load_from_disk(file_path)
            # Create scrollable history
            if self.interface:
                self.interface.reset_turn_state()
                self.interface.render_history()
            console.print(f"[green]Session loaded from:[/green] {file_path}")
            self.panel.spawn_status_panel(toks=False)
        except FileNotFoundError:
            console.print(f"[red]No session file found:[/red] {file_path}\n")
            return
        except json.JSONDecodeError:
            console.print(f"[red]Corrupted session file:[/red] {file_path}\n")
            return
        except Exception as e:
            log_exception(
                e, f"Error in load_session() — file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("ERROR LOADING", f"{e}")

    def delete_session(self):
        """Session deleter. Also lists files for user friendliness."""
        if not self.list_sessions():
            return
        file_name = self._prompt_wrapper(
            self.session_prompt,
            completer=self.session._session_completer(),
            style=COMPLETER_STYLER,
        )
        if not file_name:
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.delete_file(file_path)  # Remove the session file
            if self.session.active_session == file_name:
                self.session.active_session = ""
            console.print(f"[green]Session deleted:[/green] {file_path}\n")
        except FileNotFoundError:
            console.print(f"[red]No session file found:[/red] {file_path}\n")
            return
        except Exception as e:
            log_exception(
                e, f"Error in delete_session() — file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("DELETION ERROR", f"{e}")

    def reset_session(self):
        """Simple session resetter."""
        # Start a new conversation history list with the system prompt
        self.session.reset()
        console.print("[green]The current session has been reset successfully.[/green]")
        self.panel.spawn_status_panel(toks=False)

    def summarize_session(self):
        """Sets up and triggers summarization"""
        if not self.interface:
            return

        console.print("[yellow]Beginning summarization...[/yellow]\n")

        summary_prompt = (
            "Summarize the full conversation for use in a new session."
            "Include the main goals, steps taken, and results achieved."
        )

        # Append the prompt temporarily
        self.session.append_message("user", summary_prompt)
        # Passes a callback to Chat.stream_response
        self.interface.stream_response(callback=self._handle_summary_completion)

    def _handle_summary_completion(self, summary_text: str):
        """Callback executed by Chat after streaming finishes successfully."""
        # Reset session, apply summary
        self.session.reset_with_summary(summary_text)

        # Clean up the turn state in Chat
        if self.interface:
            self.interface.reset_turn_state()
            self.session.active_session = ""

        console.print("[green]Summarization complete! New session primed.[/green]")
        self.panel.spawn_status_panel()

    def list_sessions(self):
        """Fetches the session list and displays it."""
        sessions = self.session.find_sessions()

        if not sessions:
            console.print("[dim]No saved sessions found.[/dim]\n")
            return

        console.print("[cyan]Available sessions:[/cyan]")
        for s in sessions:
            console.print(f"• {s}", highlight=False)
        console.print()
        return 1

    # <~~FILE MANAGEMENT~~>
    def attach_file(self):
        """Command structure for reading a file from disk"""
        path = self._prompt_wrapper(
            HTML("Enter file path<seagreen>:</seagreen> "),
            completer=PathCompleter(expanduser=True),
            validator=self.filemanager.file_validator(),
            validate_while_typing=False,
            style=COMPLETER_STYLER,
            history=self.filepath_history,
        )
        if not path:
            return

        # Normalize path input and check file size
        path = os.path.abspath(os.path.expanduser(path))
        max_size = 1_000_000  # 1 MB
        file_size = os.path.getsize(path)
        if file_size > max_size:
            console.print(
                f"[yellow]Warning:[/yellow] File is {file_size / 1_000_000:.2f} MB and may consume a large amount of context."
            )
            choice = self._prompt_wrapper(
                HTML("Attach anyway? (<seagreen>y</seagreen>/<ansired>N</ansired>): "),
                allow_empty=True,
            )
            if not choice:
                return
            if choice.lower() not in ("y", "yes"):
                console.print("[dim]Attachment canceled.[/dim]\n")
                return

        try:
            file = self.filemanager.process_file(path)
            is_update = file[0]
            filename = os.path.basename(path)
            consumption = (file[1] / self.config.context_length) * 100
            if is_update:
                console.print(
                    f"{filename} [green]updated successfully.[/green]\n[yellow]Context size:[/yellow] {file[1]}, {consumption:.1f}%"
                )
            else:
                console.print(
                    f"{filename} [green]attached successfully.[/green]\n[yellow]Context size:[/yellow] {file[1]}, {consumption:.1f}%"
                )
            self.panel.spawn_status_panel(toks=False)
        except Exception as e:
            log_exception(e, "Error in process_file()")
            self.panel.spawn_error_panel("ERROR READING FILE", f"{e}")
            return

    def list_attachments(self):
        """List attachments"""
        attachments = self.filemanager.get_attachments()
        if not attachments:
            console.print("[dim]No attachments found.[/dim]\n")
            return
        console.print("[cyan]Attachments in context:[/cyan]")
        for _, kind, name in attachments:
            console.print(f"• [{kind}] {name}")
        console.print()

    def purge_attachment(self):
        """Purges files/images from context and recovers context length"""
        attachments = self.filemanager.get_attachments()
        if not attachments:
            console.print("[dim]No attachments found.[/dim]\n")
            return
        console.print("[cyan]Attachments in context:[/cyan]")
        for _, kind, name in attachments:
            console.print(f"• [{kind}] {name}")
        console.print()

        # Prompt for a file to purge
        choice = self._prompt_wrapper(
            HTML("Enter file name to remove<seagreen>:</seagreen> ")
        )
        if not choice:
            return

        # And purge the file from the session
        removed_file = self.filemanager.remove_attachment(choice)
        if removed_file:
            console.print(
                f"[green]{removed_file.capitalize()}[/green] '{choice}' [green]removed.[/green]"
            )
            self.panel.spawn_status_panel(toks=False)
        else:
            console.print(f"[red]No match found for:[/red] '{choice}'\n")

    def purge_all_attachments(self):
        self.filemanager.remove_attachment("[all]")
        console.print("[cyan]All attachments removed.")
        self.panel.spawn_status_panel(toks=False)

    # <~~PROMPT WRAPPER~~>
    def _prompt_wrapper(
        self, prefix, cancel_msg="Canceled.", allow_empty=False, **kwargs
    ) -> str | None:
        """Prompt_toolkit wrapper for validating input."""
        try:
            # **kwargs passes completers, styles, history, etc automatically
            user_input = prompt(prefix, **kwargs)
            stripped = user_input.strip()
            if not stripped and not allow_empty:
                console.print("[dim]No input detected.[/dim]\n")
                return None
            return stripped
        except (KeyboardInterrupt, EOFError):
            console.print(f"[dim]{cancel_msg}[/dim]\n")
            return None


@dataclass
class TurnState:
    reasoning: str | None = None
    response: str | None = None
    reasoning_buffer: list[str] = field(default_factory=list)
    response_buffer: list[str] = field(default_factory=list)
    full_response_content: str = ""
    full_reasoning_content: str = ""


# <~~RENDERING~~>
class Chat:
    """Handles synchronized rendering. Couples API interaction with Rich renderables."""

    # <~~INTIALIZATION & GENERIC HELPERS~~>
    def __init__(
        self,
        config: Config,
        session: SessionManager,
        filemanager: FileManager,
        ui: UIConstructor,
        panel: GlobalPanels,
    ):
        """Initializes all variables for Chat"""

        self.config: Config = config
        self.session: SessionManager = session
        self.filemanager: FileManager = filemanager
        self.panel: GlobalPanels = panel
        self.ui: UIConstructor = ui
        self.state = TurnState()

        # Placeholder for live display object
        self.live: Live | None = None

        # API object
        self.completion: Stream[ChatCompletionChunk]

        # API endpoint - Pulls the endpoint from config.json and the api key from keyring
        active = self.config.active()
        self.client = OpenAI(base_url=active["endpoint"], api_key=retrieve_key())
        self.model_name = active["name"]

        # Initialization for boolean flags
        self.reasoning_panel_initialized: bool = False
        self.response_panel_initialized: bool = False
        self.count_reasoning: bool = True
        self.count_response: bool = True
        self.cancel_requested: bool = False

        # Rich panels
        self.reasoning_panel: Panel = Panel("")
        self.response_panel: Panel = Panel("")

        # Rich renderables (the rendered panel group)
        self.renderables_to_display: list[ConsoleRenderable] = []

        # Baseline timer for the rendering loop
        self.last_update_time: float = time.monotonic()

        # Response start time, for calculating toks/sec in SessionManager
        self.start_time: float = 0

        # Terminal height and panel scaling
        self.max_height: int = 0
        self.reasoning_limit: int = 0
        self.response_limit: int = 0

    def init_rich_live(self):
        """Defines and starts a rich live instance for the main streaming loop."""
        self.live = Live(
            Group(),
            console=console,
            screen=False,
            refresh_per_second=self.config.refresh_rate,
        )
        self.live.start()

    def reset_turn_state(self):
        """Little helper that resets the turn state."""
        self.state = TurnState()
        self.reasoning_panel_initialized = False
        self.response_panel_initialized = False
        self.reasoning_panel = Panel("")
        self.response_panel = Panel("")
        self.count_reasoning = True
        self.count_response = True
        self.renderables_to_display.clear()

    def _terminal_height_setter(self):
        """
        Helper that provides values for scaling live panels.

        Ran every turn so the user can resize the terminal window freely during prompting.
        """
        if self.max_height != console.size.height:
            self.max_height = console.size.height
            self.reasoning_limit = int(self.max_height * 1.5)
            self.response_limit = int(self.max_height * 1.5)

    # <~~STREAMING~~>
    def stream_response(self, callback=None):
        """Facilitates the entire streaming process."""
        self._terminal_height_setter()
        self.cancel_requested = False
        try:  # Start rich live display and create the initial connection to the API
            self.init_rich_live()
            self.renderables_to_display.append(
                spinner_constructor("Awaiting response...")
            )
            self._rebuild_layout(force_refresh=True)
            self.completion = self._fetch_stream()
            # Parse incoming chunks, process them based on type, update panels
            campbells_chunky = True
            for chunk in self.completion:
                if campbells_chunky:
                    self.renderables_to_display.clear()
                    campbells_chunky = False
                self.chunk_parse(chunk)
                self.spawn_reasoning_panel()
                self.spawn_response_panel()
                self.update_renderables()
            end_time = time.perf_counter()
            self.session.turn_duration(self.start_time, end_time)
            time.sleep(0.02)  # Small timeout before buffers are flushed
            self.buffer_flusher()
        # Ctrl + C interrupt support
        except KeyboardInterrupt:
            self.reset_turn_state()
            self._rebuild_layout()
            self.cancel_requested = True
        # Non-quit exception catcher
        except Exception as e:
            log_exception(e, "Error in stream_response()")
            self.reset_turn_state()
            if self.live:
                self.live.stop()
            self.panel.spawn_error_panel("API ERROR", f"{e}")
            self.cancel_requested = True
        finally:
            if self.live:
                self.live.stop()
            if self.cancel_requested:
                self.session.correct_history()
            elif not self.cancel_requested:
                if callback:  # Callback for summarization
                    callback(self.state.full_response_content)
                else:  # Normal completion
                    self.session.append_message(
                        "assistant", self.state.full_response_content
                    )
                    self.panel.spawn_status_panel()

    def _fetch_stream(self) -> Stream[ChatCompletionChunk]:
        """Isolated API call."""
        return self.client.chat.completions.create(
            model=self.config.model_name,
            messages=self.session.history,
            stream=True,
        )

    def chunk_parse(self, chunk: ChatCompletionChunk):
        """Parses a chunk and places it into the appropriate buffer"""
        self.state.reasoning = self._extract_reasoning(chunk)
        self.state.response = self._extract_response(chunk)
        if self.state.reasoning:
            self.state.reasoning_buffer.append(self.state.reasoning)
        if self.state.response:
            self.state.response_buffer.append(self.state.response)

    def _extract_reasoning(self, chunk: ChatCompletionChunk) -> str | None:
        """Extracts reasoning content from a chunk"""
        delta = chunk.choices[0].delta
        reasoning = (
            getattr(delta, "reasoning_content", None)
            or getattr(delta, "reasoning", None)
            or getattr(delta, "thinking", None)
        )
        return reasoning

    def _extract_response(self, chunk: ChatCompletionChunk) -> str | None:
        """Extracts response content from a chunk"""
        delta = chunk.choices[0].delta
        response = getattr(delta, "content", None) or getattr(delta, "refusal", None)
        return response

    def buffer_flusher(self):
        """Stops residual buffer content from 'leaking' into the next turn."""
        if self.state.reasoning_buffer:
            if self.reasoning_panel in self.renderables_to_display:
                self.state.full_reasoning_content += "".join(
                    self.state.reasoning_buffer
                )
            self.state.reasoning_buffer.clear()

        if self.state.response_buffer:
            self.state.full_response_content += "".join(self.state.response_buffer)
            self.state.response_buffer.clear()

        # Update the live display
        if self.reasoning_panel in self.renderables_to_display:
            self._update_reasoning(self.state.full_reasoning_content)
        self._update_response(self.state.full_response_content)

    def update_renderables(self):
        """Updates rendered panels at a synchronized rate."""
        # Sets up the internal timer for frame-limiting
        current_time = time.monotonic()
        # Syncs text rendering with the live display's refresh rate.
        if current_time - self.last_update_time >= 1 / self.config.refresh_rate:
            if self.state.reasoning_buffer:
                self.state.full_reasoning_content += "".join(
                    self.state.reasoning_buffer
                )
                self.state.reasoning_buffer.clear()
                if self.count_reasoning:  # Simple flag, for disabling text processing
                    reasoning_lines = self.state.full_reasoning_content.splitlines()
                    if len(reasoning_lines) < self.reasoning_limit:
                        self._update_reasoning(self.state.full_reasoning_content)
                    else:
                        self.count_reasoning = False
            if self.state.response_buffer:
                self.state.full_response_content += "".join(self.state.response_buffer)
                self.state.response_buffer.clear()
                if self.count_response:
                    response_lines = self.state.full_response_content.splitlines()
                    if len(response_lines) < self.response_limit:
                        self._update_response(self.state.full_response_content)
                    else:
                        self.count_response = False
            self.last_update_time = current_time

    def render_history(self):
        """Renders a scrollable history."""
        for msg in self.session.history:
            role = msg.get("role", "unknown")
            content = (msg.get("content") or "").strip()  # type: ignore , content is guaranteed or null
            if not content:
                continue  # Skip non-content entries
            if role == "user":
                self.spawn_user_panel(content)
            elif role == "assistant":
                self.spawn_assistant_panel(content)

    def _update_reasoning(self, content: str):
        """Updates reasoning panel content"""
        self.reasoning_panel.renderable = content
        if self.live:
            self.live.refresh()

    def _update_response(self, content: str):
        """Updates response panel content"""
        sanitized = sanitize_math_safe(content)
        self.response_panel.renderable = Markdown(
            sanitized,
            code_theme=self.config.rich_code_theme,
        )
        if self.live:
            self.live.refresh()

    def _rebuild_layout(self, force_refresh: bool = False):
        """Rebuilds the display layout"""
        # force_refresh: forces an immediate repaint to the terminal
        if self.live:
            self.live.update(Group(*self.renderables_to_display), refresh=force_refresh)

    # <~~PANEL SPAWNERS~~>
    def spawn_reasoning_panel(self):
        """Manages the reasoning panel."""
        if self.state.reasoning is not None and not self.reasoning_panel_initialized:
            self.reasoning_panel = self.ui.reasoning_panel_constructor()
            self.renderables_to_display.append(self.reasoning_panel)
            self._rebuild_layout()
            self.reasoning_panel_initialized = True

    def spawn_response_panel(self):
        """Manages the response panel."""
        if self.state.response is not None and not self.response_panel_initialized:
            self.start_time = time.perf_counter()
            self.response_panel = self.ui.response_panel_constructor()
            # Adds the response panel to the live display, optionally consume the reasoning panel
            if (
                self.reasoning_panel in self.renderables_to_display
                and self.config.reasoning_panel_consume
            ):
                self.renderables_to_display.clear()
            self.renderables_to_display.append(self.response_panel)
            self._rebuild_layout()
            self.response_panel_initialized = True

    def spawn_user_panel(self, content: str):
        """Spawns the user panel."""
        console.print()
        console.print(self.ui.user_panel_constructor(content))
        console.print()

    def spawn_assistant_panel(self, content: str):
        """Spawns the Response panel - for a scrollable history."""
        self.response_panel = self.ui.response_panel_constructor()
        self._update_response(content)
        console.print(self.response_panel)


# <~~CONTROLLER~~>
class App:
    """Main controller, handles input"""

    def __init__(self):
        # Load config file
        self.config = Config()
        try:
            self.config.load()
        except FileNotFoundError:
            self.config.save()

        # Set up all 6 objects
        self.session_manager = SessionManager(self.config)
        self.file_manager = FileManager(self.session_manager)
        self.ui = UIConstructor(self.config, self.session_manager)
        self.panel = GlobalPanels(self.session_manager, self.config, self.ui)
        self.commands = CLIController(
            self.config, self.session_manager, self.file_manager, self.panel, self.ui
        )
        self.chat = Chat(
            self.config, self.session_manager, self.file_manager, self.ui, self.panel
        )

        # Give CLIController access to Chat for !load and !summary
        self.commands.set_interface(self.chat)
        # Prompt history
        self.main_history = InMemoryHistory()

    def run(self):
        """The app runner"""
        self.panel.spawn_intro_panel()

        while True:
            self.chat.reset_turn_state()
            try:
                user_input = prompt(
                    PROMPT_PREFIX,
                    completer=COMMAND_COMPLETER,
                    style=COMPLETER_STYLER,
                    complete_while_typing=False,
                    history=self.main_history,
                )
            except (KeyboardInterrupt, EOFError):
                console.print("[yellow]✨ Farewell![/yellow]\n")
                break

            if not user_input.strip():
                continue

            # Handle commands
            command_result = self.commands.handle_input(user_input)
            if command_result is not False:
                if isinstance(command_result, tuple):
                    self.chat.client = command_result[0]
                    self.chat.model_name = command_result[1]
                elif isinstance(command_result, OpenAI):
                    self.chat.client = command_result
                continue

            # Hand user input over to the session manager
            self.session_manager.append_message("user", user_input)
            console.print()
            # Tell Chat that it is go time
            self.chat.stream_response()

        # Save on exit
        self.config.save()


# <~~MAIN FLOW~~>
def main():
    try:
        init_logger()
        setup_keyring_backend()
        # Start a spinner, mostly for cold starts
        with Live(
            spinner_constructor("Launching Local Sage..."),
            refresh_per_second=8,
            console=console,
        ):
            app = App()
        console.clear()
        app.run()
    except (KeyboardInterrupt, EOFError):
        console.print("[yellow]✨ Farewell![/yellow]\n")
    except Exception as e:
        log_exception(e, "Critical startup error")  # Log any critical errors
        console.print(f"[bold][red]CRITICAL ERROR:[/red][/bold] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
