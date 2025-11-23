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
from datetime import datetime
from logging.handlers import RotatingFileHandler

import tiktoken
from keyring import get_password, set_password
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

# Sets and creates directories for the config file, session management, and logging
APP_DIR = user_data_dir("LocalSage")
CONFIG_DIR = os.path.join(APP_DIR, "config")
SESSIONS_DIR = os.path.join(APP_DIR, "sessions")
LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


# Logger setup
def init_logger():
    """Initializes the logging system."""
    date_str = datetime.now().strftime("%Y%m%d")
    # Output example: localsage_20251109.log
    log_path = os.path.join(LOG_DIR, f"localsage_{date_str}.log")
    # Set up the file handler, max of 3 backups, max size of 1MB
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    # Define the log file format
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
    # Log the message in the current active log file
    logging.error(msg)


# Config file location setter
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Current user name
USER_NAME = getpass.getuser()

# Reasoning panel configuration
REASONING_PANEL_TITLE = Text("🧠 Reasoning", style="bold yellow")
REASONING_TITLE_ALIGN = "left"
REASONING_BORDER_STYLE = "yellow"
REASONING_TEXT_STYLE = "#b0b0b0 italic"  # grey66 looks great but is opinionated
REASONING_PANEL_WIDTH = None

# Response panel configuration
RESPONSE_PANEL_TITLE = Text("💬 Response", style="bold green")
RESPONSE_TITLE_ALIGN = "left"
RESPONSE_BORDER_STYLE = "green"
RESPONSE_TEXT_STYLE = "default"
RESPONSE_PANEL_WIDTH = None

# Prompt configuration
PROMPT_PREFIX = HTML("<seagreen>󰅂 </seagreen>")
SESSION_PROMPT = HTML("Enter a session name<seagreen>:</seagreen> ")

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

# Compiled regex used in the file management system
# Alternative, allows whitespace: ^---\s*File:\s*(.+?)
FILE_PATTERN = re.compile(r"^---\nFile: `(.*?)`", re.MULTILINE)

# Terminal intergration
console = Console()


def spawn_error_panel(error: str, exception: str):
    """Error panel template for Local Sage, used in Chat() and main()"""
    error_panel = Panel(
        exception,
        title=Text(f"❌ {error}", style="bold red"),
        title_align="left",
        border_style="red",
        expand=False,
    )
    console.print(error_panel)
    console.print()


class Config:
    """
    User-facing configuration variables.
    """

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


class SessionManager:
    """
    Handles session management
    - Session-related I/O
    - Session history management
    - Token caching
    """

    def __init__(self, config: Config):
        self.config: Config = config
        self.history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.config.system_prompt}
        ]
        self.active_session: str = ""
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.token_cache: list[tuple[str, int] | None] = []

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
        if self.history and self.history[-1]["role"] == "user":
            _ = self.history.pop()

    def reset_session(self):
        """Reset the current session state"""
        self.history = [{"role": "system", "content": self.config.system_prompt}]
        self.active_session = ""
        self.token_cache = []

    def reset_with_summary(self, summary_text: str):
        """Wipes the session and starts fresh with a summary."""
        self.active_filename = ""
        self.token_cache = []
        self.history = [
            {"role": "system", "content": self.config.system_prompt},
            {
                "role": "system",
                "content": "This summary represents the previous session.",
            },
            {"role": "assistant", "content": summary_text},
        ]

    def list_sessions(self):
        """Lists all sessions that exist within SESSIONS_DIR"""
        sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        if not sessions:
            console.print("[dim]No saved sessions found.[/dim]\n")
            return False
        console.print("[cyan]Available sessions:[/cyan]")
        for s in sorted(sessions):
            console.print(f"• {s}", highlight=False)
        console.print()
        return True

    def count_tokens(self) -> int:
        """Counts and caches tokens."""
        # Ensure cache aligns with current conversation history length
        if len(self.token_cache) > len(self.history):
            self.token_cache = self.token_cache[: len(self.history)]
        while len(self.token_cache) < len(self.history):
            self.token_cache.append(None)
        total = 0

        # Start counting tokens
        for i, msg in enumerate(self.history):
            raw_content = msg.get("content")
            text: str
            # Process raw_content depending on it's type
            if raw_content is None:
                text = ""
            elif isinstance(raw_content, str):
                text = raw_content
            elif isinstance(raw_content, list):
                parts = [p.get("text", "") for p in raw_content if isinstance(p, dict)]
                text = " ".join(parts) if parts else ""
            else:
                text = str(raw_content)
            cached = self.token_cache[i]
            if cached is None or cached[0] != text:
                try:
                    token_count = len(self.encoder.encode(text))
                # Cache protection, to deter critical exceptions
                except Exception:
                    token_count = 0
                self.token_cache[i] = (text, token_count)  # Expand the cache
                total += token_count
            else:
                total += cached[1]
        return total

    def _json_helper(self, file_name: str) -> str:
        """
        JSON extension helper.

        Used throughout most session management methods.
        """
        if not file_name.endswith(".json"):
            file_name += ".json"
        file_path = os.path.join(SESSIONS_DIR, file_name)
        return file_path


class ProfileManager:
    """Handles model profile management"""


class Chat:
    """Houses the main application logic for Local Sage"""

    # <~~INTIALIZATION & GENERIC HELPERS~~>
    def __init__(self, config: Config, session: SessionManager):
        """Initializes all variables for Chat"""

        # Imports configuration variables from the Config class
        self.config: Config = config

        self.session: SessionManager = session

        # Placeholder for live display object
        self.live: Live | None = None

        # API object
        self.completion: Stream[ChatCompletionChunk]

        # API endpoint - Pulls the endpoint from config.json and the api key from keyring
        active = self.config.active()
        self.client = OpenAI(
            base_url=active["endpoint"], api_key=get_password("LocalSageAPI", USER_NAME)
        )
        self.model_name = active["name"]

        # Initialization for boolean flags
        self.reasoning_panel_initialized: bool = False
        self.response_panel_initialized: bool = False
        self.count_reasoning: bool = True
        self.count_response: bool = True
        self.cancel_requested: bool = False
        self.context_flag: bool = True

        # Rich panels
        self.reasoning_panel: Panel = Panel("")
        self.response_panel: Panel = Panel("")
        self.intro_panel: Panel = Panel("")
        self.status_panel: Panel = Panel("")

        # Rich renderables (the rendered panel group)
        self.renderables_to_display: list[ConsoleRenderable] = []

        # Strings extracted from a streamed chunk, fed to buffers
        self.reasoning: str | None = None
        self.response: str | None = None

        # String buffers
        self.reasoning_buffer: list[str] = []
        self.response_buffer: list[str] = []

        # Collectors for output content, appended by the buffers
        self.full_response_content: str = ""
        self.full_reasoning_content: str = ""

        # Baseline timer for the rendering loop
        self.last_update_time: float = time.monotonic()

        # Holds the total token amount for display
        self.total_tokens: int = 0

        # Terminal height and panel scaling
        self.max_height: int = 0
        self.reasoning_limit: int = 0
        self.response_limit: int = 0

        # Prompt input history
        self.main_history = InMemoryHistory()
        self.filepath_history = InMemoryHistory()

    def slate_cleaner(self):
        """
        Sets baseline values for each turn with it's sibling, _mini_slate_cleaner().

        Houses the command structure and the main prompt.
        """
        # Variables are set to their baseline for the API call
        self._mini_slate_cleaner()

        while True:
            # User is prompted for input
            try:
                user_message = prompt(
                    PROMPT_PREFIX,
                    completer=self._command_completer(),
                    style=COMPLETER_STYLER,
                    complete_while_typing=False,
                    history=self.main_history,
                )  # Prompts the user for input
            except (KeyboardInterrupt, EOFError):  # Ctrl + c implementation for exiting
                return False
            # Command detection
            if user_message.lower() in ["!q", "!quit"]:  # Quit
                if len(self.session.history) > 1:
                    choice = (
                        prompt(
                            HTML(
                                "Save before quiting? (<seagreen>y</seagreen>/<ansired>N</ansired>): "
                            )
                        )
                        .lower()
                        .strip()
                    )
                    if choice in ("y", "yes"):
                        try:
                            self.save_session()
                        except Exception:
                            continue
                return False
            if user_message.lower() in ["!l", "!load"]:  # Load
                if len(self.session.history) > 1:
                    choice = (
                        prompt(
                            HTML(
                                "Loading a session will overwrite your active session.\nContinue? (<seagreen>y</seagreen>/<ansired>N</ansired>): "
                            )
                        )
                        .lower()
                        .strip()
                    )
                    if choice not in ("y", "yes"):
                        console.print("[dim]Load canceled by user.[/dim]\n")
                        continue
                self.load_session()
                continue
            if user_message.lower() in ["!s", "!save"]:  # Save
                self.save_session()
                console.print()
                continue
            if user_message.lower() in ["!sessions"]:  # List sessions
                self.session.list_sessions()
                continue
            if user_message.lower() in ["!delete"]:  # Delete a session
                self.delete_session()
                continue
            if user_message.lower() in ["!h", "!help"]:  # Command guide
                self.spawn_help_panel()
                continue
            if user_message.lower() in ["!reset"]:  # Reset session
                self.reset_session()
                continue
            if user_message.lower() in ["!key"]:  # API key
                self.set_api_key()
                continue
            if user_message.lower() in ["!ctx"]:  # Context length
                self.set_context_length()
                continue
            if user_message.lower() in ["!rate"]:  # Refresh rate
                self.set_refresh_rate()
                continue
            if user_message.lower() in ["!prompt"]:  # System prompt
                self.set_system_prompt()
                continue
            if user_message.lower() in ["!theme"]:  # Markdown theme
                self.set_code_theme()
                continue
            if user_message.lower() in ["!a", "!attach"]:  # Attach a file
                self.attach_file()
                continue
            if user_message.lower() in ["!attachments"]:  # List attachments
                self.list_attachments()
                continue
            if user_message.lower() in ["!purge"]:  # Purge an attachment
                self.purge_attachment()
                continue
            if user_message.lower() in ["!consume"]:  # Toggle panel consumption
                self.config.reasoning_panel_consume = (
                    not self.config.reasoning_panel_consume
                )
                self.config.save()
                if self.config.reasoning_panel_consume:
                    console.print(
                        "Reasoning panel consumption toggled [green]on[/green].\n"
                    )
                else:
                    console.print(
                        "Reasoning panel consumption toggled [red]off[/red].\n"
                    )
                continue
            if user_message.lower() in ["!sum", "!summary"]:  # Prompt for a summary
                if len(self.session.history) > 1:
                    try:
                        choice = (
                            prompt(
                                HTML(
                                    "Save the active session before summarization? (<seagreen>y</seagreen>/<ansired>N</ansired>): "
                                )
                            )
                            .lower()
                            .strip()
                        )
                        if choice in ("y", "yes"):
                            try:
                                self.save_session()
                            except Exception:
                                continue
                    except KeyboardInterrupt or EOFError:
                        console.print("[dim]Summarization canceled.[/dim]\n")
                        continue
                    self.summarize_session()
                    continue
                else:
                    console.print(
                        "[yellow]The conversation history is empty. There is nothing to summarize.[/yellow]\n"
                    )
                    continue
            if user_message.lower() in ["!config"]:  # Config table
                self.spawn_settings_panel()
                continue
            if user_message.lower() in ["!clear"]:  # Clear the viewport
                console.clear()
                continue
            if user_message.lower() in ["!profiles"]:  # List models
                self.list_models()
                continue
            if user_message.lower() in ["!addprofile"]:  # Add a new model
                self.add_model()
                continue
            if user_message.lower() in ["!removeprofile"]:  # Remove a model
                self.remove_model()
                continue
            if user_message.lower() in ["!switch"]:  # Switch models
                self.switch_model()
                continue
            if not user_message.strip():  # Loop back if the user inputs nothing
                continue

            # User input is appended to the conversation history list if a command was not used
            self.session.append_message("user", user_message)
            # New height is set, in case the user resized their terminal window during the prompt
            self._terminal_height_setter()
            console.print()
            # Return true and break if no command was used, stream/rendering then starts
            return True

    def init_rich_live(self):
        """Defines and starts a rich live instance for the main streaming loop."""
        self.live = Live(
            Group(),
            console=console,
            screen=False,
            refresh_per_second=self.config.refresh_rate,
        )
        self.live.start()

    def _mini_slate_cleaner(self):
        """Little helper that resets the turn state."""
        self.full_response_content = ""
        self.full_reasoning_content = ""
        self.full_sanitized_response = ""
        self.reasoning_panel_initialized = False
        self.response_panel_initialized = False
        self.reasoning_panel = Panel("")
        self.response_panel = Panel("")
        self.count_reasoning = True
        self.count_response = True
        self.renderables_to_display.clear()
        self.reasoning_buffer.clear()
        self.response_buffer.clear()
        self.reasoning = None
        self.response = None

    def _terminal_height_setter(self):
        """
        Helper that provides values for scaling live panels.

        Ran every turn so the user can resize the terminal window freely during prompting.
        """
        if self.max_height != console.size.height:
            self.max_height = console.size.height
            self.reasoning_limit = int(self.max_height * 1.5)
            self.response_limit = int(self.max_height * 1.5)

    def _command_completer(self):
        """Custom word completer containing all main commands."""
        return WordCompleter(
            [
                "!a",
                "!addprofile",
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
                "!profiles",
                "!prompt",
                "!purge",
                "!q",
                "!quit",
                "!rate",
                "!removeprofile",
                "!reset",
                "!s",
                "!save",
                "!sessions",
                "!sum",
                "!summary",
                "!switch",
                "!theme",
            ],
            match_middle=True,
            WORD=True,
        )

    # <~~STREAMING~~>
    def stream_response(self):
        """
        Facilitates the entire streaming process, including:
        - The API interaction
        - The streaming loop ('for chunk in self.completion')
        - Appending the final response to history
        """
        self.cancel_requested = False

        try:  # Start rich live display and create the initial connection to the API
            self.init_rich_live()
            self.completion = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=self.session.history,
                stream=True,
            )
            # Parse incoming chunks, process them based on type, update panels
            for chunk in self.completion:
                self.chunk_parse(chunk)
                self.spawn_reasoning_panel()
                self.spawn_response_panel()
                self.update_renderables()
            time.sleep(0.02)  # Small timeout before buffers are flushed
            self.buffer_flusher()
        # Allows the user to safely use Ctrl+C to end streaming abruptly
        except KeyboardInterrupt:
            self._mini_slate_cleaner()  # _mini_slate_cleaner keeps the session clean
            if self.live:
                self.live.update(Group(*self.renderables_to_display))
                self.live.stop()
            self.cancel_requested = True
        # Non-quit exception catcher for errors that occur during the API call
        except Exception as e:
            log_exception(e, "Error in stream_response()")
            self._mini_slate_cleaner()
            if self.live:
                self.live.stop()
            spawn_error_panel("API ERROR", f"{e}")
            self.cancel_requested = True
        finally:
            if self.live:
                # Stop the live display since streaming has ended
                self.live.stop()
            if self.cancel_requested:
                # If the user canceled the stream, remove their input.
                self.session.correct_history()
            if not self.cancel_requested:  # Normal completion
                # Append the final response to history
                self.append_history()
                # Spawn the status panel
                self.spawn_status_panel()

    def chunk_parse(self, chunk: ChatCompletionChunk):
        """Parses an incoming chunk into a reasoning string or a response string"""
        # Extracts reasoning content from a streamed chat completion chunk
        self.reasoning = getattr(chunk.choices[0].delta, "reasoning_content", "")
        # Extracts response content from a streamed chat completion chunk
        self.response = getattr(chunk.choices[0].delta, "content", "")
        # Feeds reasoning and response into their respective buffers
        if self.reasoning:
            self.reasoning_buffer.append(self.reasoning)
        if self.response:
            self.response_buffer.append(self.response)

    def buffer_flusher(self):
        """Stops residual buffer content from 'leaking' into the next turn."""
        if self.reasoning_buffer:
            if self.reasoning_panel in self.renderables_to_display:
                self.full_reasoning_content += "".join(self.reasoning_buffer)
            self.reasoning_buffer.clear()

        if self.response_buffer:
            self.full_response_content += "".join(self.response_buffer)
            self.response_buffer.clear()

        # Fully update the live display after the buffers were flushed.
        if self.live:
            final_text = sanitize_math_safe(self.full_response_content)
            self.response_panel.renderable = Markdown(
                final_text,
                code_theme=self.config.rich_code_theme,
                style=RESPONSE_TEXT_STYLE,
            )
            if self.reasoning_panel in self.renderables_to_display:
                self.reasoning_panel.renderable = Text(
                    self.full_reasoning_content, style=REASONING_TEXT_STYLE
                )
            self.live.refresh()

    def update_renderables(self):
        """
        Updates rendered panel(s). Where the heavy lifting happens.
        - Renders at a hard-coded refresh rate that is in sync with the rich.live instance.
        - 'Two-cylinder engine', concatenates content from two separate buffers.
        - Performs math sanitization, markdown rendering, and stylized text rendering.
        """
        # Sets up the internal timer for frame-limiting
        current_time = time.monotonic()
        # Syncs text rendering with the live display's refresh rate.
        if (
            self.live
            and current_time - self.last_update_time >= 1 / self.config.refresh_rate
        ):
            if self.reasoning_buffer:
                # Reasoning buffer is appended and then cleared
                self.full_reasoning_content += "".join(self.reasoning_buffer)
                self.reasoning_buffer.clear()
                if self.count_reasoning:  # Simple flag, for disabling text processing
                    reasoning_lines = self.full_reasoning_content.splitlines()
                    # Stylizes reasoning_text and outputs it to the reasoning panel.
                    if len(reasoning_lines) < self.reasoning_limit:
                        self.reasoning_panel.renderable = Text(
                            self.full_reasoning_content, style=REASONING_TEXT_STYLE
                        )
                        # Refreshes the live display
                        self.live.refresh()
                    # Once the panel grows to the panel limit, disable live text processing
                    else:
                        self.count_reasoning = False
            if self.response_buffer:
                # Response buffer is appended and then cleared
                self.full_response_content += "".join(self.response_buffer)
                self.response_buffer.clear()
                if self.count_response:  # Simple flag, for disabling text processing
                    response_lines = self.full_response_content.splitlines()
                    if len(response_lines) < self.response_limit:
                        # Math sanitization is performed
                        sanitized = sanitize_math_safe(self.full_response_content)
                        self.response_panel.renderable = Markdown(
                            sanitized,
                            code_theme=self.config.rich_code_theme,
                            style=RESPONSE_TEXT_STYLE,
                        )
                        self.live.refresh()
                    else:
                        self.count_response = False
            # Sets last_update_time for frame-synchronization
            self.last_update_time = current_time

    def append_history(self):
        """Appends full response content to the conversation history"""
        if self.full_response_content:
            self.session.append_message("assistant", self.full_response_content)

    # <~~PANELS & CHARTS~~>
    def spawn_intro_panel(self):
        """Simple welcome panel, prints on application launch."""
        # Intro panel content
        intro_text = Text.assemble(
            ("Model: ", "bold sandy_brown"),
            (f"{self.config.model_name}"),
            ("\nProfile: ", "bold sandy_brown"),
            (f"{self.config.alias_name}"),
            ("\nSystem Prompt: ", "bold sandy_brown"),
            (f"{self.config.system_prompt}", "italic"),
        )

        # Intro panel constructor
        intro_panel = Panel(
            intro_text,
            title=Text(f"🔮 Local Sage {__version__}", "bold medium_orchid"),
            title_align="left",
            border_style="medium_orchid",
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

        console.print(intro_panel)
        console.print(Markdown("Type `!h` for a list of commands."))
        console.print()

    def spawn_reasoning_panel(self):
        """Manages the reasoning panel."""
        if (
            self.reasoning is not None
            and not self.reasoning_panel_initialized
            and self.live
        ):
            # Reasoning panel constructor
            self.reasoning_panel = Panel(
                "",
                title=REASONING_PANEL_TITLE,
                title_align=REASONING_TITLE_ALIGN,
                border_style=REASONING_BORDER_STYLE,
                width=REASONING_PANEL_WIDTH,
                box=box.HORIZONTALS,
                padding=(0, 0),
            )
            # Adds the reasoning panel to the live display
            self.renderables_to_display.insert(0, self.reasoning_panel)
            self.live.update(Group(*self.renderables_to_display))
            self.reasoning_panel_initialized = True

    def spawn_response_panel(self):
        """Manages the response panel."""
        if (
            self.response is not None
            and not self.response_panel_initialized
            and self.live
        ):
            # Response panel constructor
            self.response_panel = Panel(
                "",
                title=RESPONSE_PANEL_TITLE,
                title_align=RESPONSE_TITLE_ALIGN,
                border_style=RESPONSE_BORDER_STYLE,
                width=RESPONSE_PANEL_WIDTH,
                box=box.HORIZONTALS,
                padding=(0, 0),
            )
            # Adds the response panel to the live display, optionally consume the reasoning panel
            if self.reasoning_panel in self.renderables_to_display:
                if self.config.reasoning_panel_consume:
                    self.renderables_to_display.clear()
                    self.renderables_to_display.insert(0, self.response_panel)
                    self.live.update(Group(*self.renderables_to_display))
                else:
                    self.renderables_to_display.append(self.response_panel)
                    self.live.update(Group(*self.renderables_to_display))
            self.response_panel_initialized = True

    def spawn_status_panel(self):
        """
        Defines and prints the status panel.

        Also calculates total_tokens at the end of every context-consuming interaction.
        """
        self.total_tokens = self.session.count_tokens()
        context_percentage = round(
            (self.total_tokens / self.config.context_length) * 100, 1
        )

        # Colorize context percentage based on context consumption
        context_color: str = "dim"
        if context_percentage >= 50 and context_percentage < 80:
            context_color = "yellow"
        elif context_percentage >= 80:
            context_color = "red"
            if self.context_flag:
                console.print(
                    "[red]WARNING:[/red] Context use has surpassed [red]80%[/red]! You can use [yellow]!sum[/yellow] to generate a summary and start a fresh session.",
                    "You may want to use [yellow]!save[/yellow] first, if desired.",
                )
                self.context_flag = False

        # Turn counter
        turns = sum(1 for m in self.session.history if m["role"] == "user")

        # Status panel content
        status_text = Text.assemble(
            (" ", "cyan"),
            ("Context: "),
            (f"{context_percentage}%", f"{context_color}"),
            (" | "),
            (f"Turn: {turns}"),
        )

        # Status panel constructor
        self.status_panel = Panel(
            status_text,
            border_style="dim",
            style="dim",
            expand=False,
        )
        # Print the panel, no need to render it live
        console.print(self.status_panel)
        console.print()

    def spawn_help_panel(self):
        """Markdown usage chart."""
        help_markdown = Markdown(
            textwrap.dedent("""
            | **Profile Management** | *Manage multiple models & API endpoints* |
            | --- | ----------- |
            | `!addprofile` | Add a new model profile. Prompts for alias, model name, and **API endpoint**. |
            | `!removeprofile` | Remove an existing profile. |
            | `!profiles` | List configured profiles. |
            | `!switch` | Switch between profiles. |

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
            | `!reset` | Reset for a fresh session. |
            | `!delete` | Delete a saved session. |
            | `!sessions` | List all saved sessions. |
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
            | | |
            | **FILE TYPES:** | All text-based file types are acceptable. |
            | **NOTE:** | If you ever attach a problematic file, `!purge` can be used to rescue the session. |
            """)
        )
        console.print(help_markdown)
        console.print()

    def spawn_settings_panel(self):
        """Markdown settings chart."""
        settings_markdown = Markdown(
            textwrap.dedent(f"""
            | **Current Settings** | *Your current persistent settings* |
            | --- | ----------- |
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
        console.print(settings_markdown)
        console.print()

    def spawn_user_panel(self, content: str):
        """Places user input into a readable panel. Used for scrollable history in _resurrect_session()."""
        user_panel = Panel(
            content,
            box=box.HORIZONTALS,
            padding=(0, 0),
            title=Text("🌐 You", style="bold blue"),
            title_align="left",
            border_style="blue",
        )
        console.print()
        console.print(user_panel)
        console.print()

    def spawn_assistant_panel(self, content: str):
        """Response panel, but for loaded model reponses. Used for scrollable history in _resurrect_session()."""
        assistant_panel = Panel(
            Markdown(
                sanitize_math_safe(content), code_theme=self.config.rich_code_theme
            ),
            box=box.HORIZONTALS,
            padding=(0, 0),
            title=Text("💬 Response", style="bold green"),
            title_align=RESPONSE_TITLE_ALIGN,
            border_style=RESPONSE_BORDER_STYLE,
        )
        console.print(assistant_panel)

    # <~~MAIN CONFIG~~>
    def set_system_prompt(self):
        """Sets a new persistent system prompt within the config file."""
        try:
            sysprompt = prompt(HTML("Enter a system prompt<seagreen>:</seagreen> "))
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Edit canceled.[/dim]\n")
            return

        self.config.system_prompt = sysprompt
        self.config.save()
        console.print(f"[green]System prompt updated to:[/green] {sysprompt}")
        console.print(
            Text(
                "[dim]Use [cyan]!reset[/cyan] to start a session with the new prompt. Be sure to [cyan]!save[/cyan] first, if desired.[/dim]"
            )
        )
        console.print()

    def set_context_length(self):
        """Sets a new persistent context length"""
        try:
            ctx = prompt(HTML("Enter a max context length<seagreen>:</seagreen> "))
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Edit canceled.[/dim]\n")
            return

        if not ctx.strip():
            console.print("[dim]Edit canceled. No input provided.[/dim]\n")
            return

        try:
            value = int(ctx)
            if value <= 0:
                raise ValueError
        except ValueError:
            spawn_error_panel("VALUE ERROR", "Please enter a positive number.")
            return

        self.config.context_length = value
        self.config.save()
        console.print(f"[green]Context length set to:[/green] {value}\n")

    def set_api_key(self):
        """
        Allows the user to set an API key.

        SAFELY stores the user's API key with keyring
        """
        # API key is referenced in memory during runtime. Never stored in text or code.
        # See how it is initialized in config.__init__ for further reference
        try:
            new_key = prompt(HTML("Enter an API key<seagreen>:</seagreen> ")).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Edit canceled.[/dim]\n")
            return

        if not new_key:
            console.print("[dim]Edit canceled. No input provided.[/dim]\n")
            return

        try:
            set_password(
                "LocalSageAPI", USER_NAME, new_key
            )  # Store securely w/ keyring
        except (KeyringError, ValueError, RuntimeError, OSError) as e:
            spawn_error_panel("KEYRING ERROR", f"{e}")
            return

        self.client = OpenAI(base_url=self.config.endpoint, api_key=new_key)
        # Reinitialize self.client with the new key
        console.print("[green]API key updated.[/green]\n")

    def set_refresh_rate(self):
        """Set a new custom refresh rate"""
        try:
            rate = prompt(HTML("Enter a refresh rate<seagreen>:</seagreen> "))
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Edit canceled.[/dim]\n")
            return

        if not rate.strip():
            console.print("[dim]Edit canceled. No input provided.[/dim]\n")
            return

        try:
            value = int(rate)
            if value <= 3:
                raise ValueError
        except ValueError:
            spawn_error_panel("VALUE ERROR", "Please enter a positive number ≥ 4.")
            return

        self.config.refresh_rate = value
        self.config.save()
        console.print(f"[green]Refresh rate set to:[/green] {value}\n")

    def set_code_theme(self):
        """Allows the user to change out the rich markdown theme"""
        try:
            theme = prompt(HTML("Enter a valid theme name<seagreen>:</seagreen> "))
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Edit canceled.[/dim]")
            return

        theme = theme.lower()  # All theme names are lowercase
        if not theme.strip():
            console.print("[dim]Edit canceled. No input provided.[/dim]\n")
            return

        self.config.rich_code_theme = theme
        self.config.save()
        console.print(f"[green]Your theme has been set to: [/green]{theme}\n")

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
        try:
            alias = prompt(HTML("Profile name<seagreen>:</seagreen> ")).strip()
            name = prompt(HTML("Model name<seagreen>:</seagreen> ")).strip()
            endpoint = prompt(HTML("API endpoint<seagreen>:</seagreen> ")).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Profile addition canceled.[/dim]\n")
            return

        if not alias or not endpoint:
            console.print(
                "[red]Profile name and API endpoint are required fields.[/red]\n"
            )
            return

        if any(m["alias"] == alias for m in self.config.models):
            console.print(f"[red]Profile[/red] '{alias}' [red]already exists.[/red]\n")
            return

        self.config.models.append(
            {
                "alias": alias,
                "name": name or "Unnamed",
                "endpoint": endpoint,
                "api_key": "stored",
            }
        )
        self.config.save()
        console.print(f"[green]Profile[/green] '{alias}' [green]added.[/green]\n")

    def remove_model(self):
        """Remove a model profile by alias."""
        self.list_models()
        try:
            alias = prompt(HTML("Profile to remove<seagreen>:</seagreen> ")).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Canceled.[/dim]\n")
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

    def switch_model(self, alias=None):
        """Switch active model profile by alias."""
        if not alias:
            self.list_models()
            alias = prompt(HTML("Enter a profile name<seagreen>:</seagreen> ")).strip()

        match = next((m for m in self.config.models if m["alias"] == alias), None)
        if not match:
            console.print(f"[red]No profile found under alias[/red] '{alias}'.\n")
            return

        self.config.active_model = alias
        self.config.save()
        self.client = OpenAI(
            base_url=match["endpoint"], api_key=get_password("LocalSageAPI", USER_NAME)
        )
        console.print(
            f"[green]Switched to:[/green] {match['name']} "
            f"[dim]{match['endpoint']}[/dim]\n"
        )

    # <~~SESSION MANAGEMENT~~>
    def save_session(self):
        """Saves a session to a .json file"""
        if self.session.active_session:
            file_name = self.session.active_session
        else:
            try:
                file_name = prompt(SESSION_PROMPT)
            except (KeyboardInterrupt, EOFError):
                console.print("[dim]Saving canceled[/dim]")
                return

        if not file_name.strip():
            console.print("[dim]Saving canceled. No name entered.[/dim]")
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.save_to_disk(file_path)
            console.print(f"[green]Session saved in:[/green] {file_path}")
        except Exception as e:
            log_exception(
                e, f"Error in save_session() - file: {os.path.basename(file_path)}"
            )
            spawn_error_panel("ERROR SAVING", f"{e}")
            return

    def load_session(self):
        """Loads a session from a .json file"""
        try:
            if not self.session.list_sessions():
                return
            file_name = prompt(
                SESSION_PROMPT,
                completer=self._session_completer(),
                style=COMPLETER_STYLER,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Loading canceled.[/dim]\n")
            return

        if not file_name.strip():
            console.print("[dim]Saving canceled. No name entered.[/dim]\n")
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.load_from_disk(file_path)
            self.context_flag = True
            self._resurrect_session()
            console.print(f"[green]Session loaded from:[/green] {file_path}")
            self.spawn_status_panel()
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
            spawn_error_panel("ERROR LOADING", f"{e}")

    def delete_session(self):
        """Session deleter. Also lists files for user friendliness."""
        try:
            if not self.session.list_sessions():
                return
            file_name = prompt(
                SESSION_PROMPT,
                completer=self._session_completer(),
                style=COMPLETER_STYLER,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]Deletion canceled.[/dim]\n")
            return

        if not file_name.strip():
            console.print("[dim]Deletion canceled. No name entered.[/dim]\n")
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
            spawn_error_panel("DELETION ERROR", f"{e}")

    def reset_session(self):
        """Simple session resetter."""
        # Start a new conversation history list with the system prompt
        self.session.reset_session()
        self.context_flag = True
        console.print("[green]The current session has been reset successfully.[/green]")
        self.spawn_status_panel()

    def summarize_session(self):
        """Prompts the model for a summary, resets the session state, and injects the summary."""
        console.print(
            "[yellow]Beginning summarization. You can cancel summarization at any time with[/yellow] [cyan]Ctrl + C[/cyan].\n"
        )
        # summary_prompt - Used to ask the model for a summary in a digestible way
        summary_prompt = (
            "Summarize the full conversation for use in a new session."
            "Include the main goals, steps taken, and results achieved."
        )
        self.session.append_message("user", summary_prompt)
        self.cancel_requested = False
        try:
            # Just the regular streaming loop, patched in for the summarization process. See stream_response()
            self.init_rich_live()
            self.completion = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=self.session.history,
                stream=True,
            )
            for chunk in self.completion:
                self.chunk_parse(chunk)
                self.spawn_reasoning_panel()
                self.spawn_response_panel()
                self.update_renderables()
            time.sleep(0.02)  # Small timeout before buffers are flushed
            self.buffer_flusher()
            if self.live:
                self.live.stop()
            # Grab the summary from conversation history
            summary_text = self.full_response_content
            # Reset the session state entirely, scorched-earth
            self._mini_slate_cleaner()
            self.loaded_session_name = ""
            self.context_flag = True
            # Start a new session and deliver the summary, starting with the system prompt
            self.session.reset_with_summary(summary_text)
            console.print(
                "[green]Summarization complete! Your new session is primed and ready.[/green]"
            )
            # Spawn the status panel, showing proof that the user is now in a new session
            self.spawn_status_panel()
        except KeyboardInterrupt:
            self._mini_slate_cleaner()
            if self.live:
                self.live.update(Group(*self.renderables_to_display))
                self.live.stop()
            self.cancel_requested = True
            return
        # Error catcher
        except Exception as e:
            log_exception(e, "Error in summarize_session()")
            if self.live:
                self.live.stop()
            spawn_error_panel("SUMMARIZATION ERROR", f"{e}")
            self.cancel_requested = True
            return
        finally:
            if self.live:
                self.live.stop()
            if self.cancel_requested:
                self.session.correct_history()

    def _resurrect_session(self):
        """
        Utilized by load_session() to print a scrollable history.
        """
        for msg in self.session.history:
            role = msg.get("role", "unknown")
            content = (msg.get("content") or "").strip()  # type: ignore
            if not content:
                continue  # Skip non-content entries
            if role == "user":
                # Print a user panel for user messages
                self.spawn_user_panel(content)
            elif role == "assistant":
                # Print an assistant panel for assistant messages
                self.spawn_assistant_panel(content)

    def _session_completer(self):
        """Session completion helper for prompt_toolkit"""
        return WordCompleter(
            [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
            ignore_case=True,
            sentence=True,
        )

    # <~~FILE MANAGEMENT~~>
    def attach_file(self):
        """Reads a file from disk and inserts its contents into the current session."""
        # Setup for prompt_toolkit's validator and path completer features
        file_completer = PathCompleter(expanduser=True)
        validator = Validator.from_callable(
            self._file_validator,
            error_message="File does not exist.",
            move_cursor_to_end=True,
        )

        try:
            # Prompt the user for a filepath
            path = prompt(
                HTML("Enter file path<seagreen>:</seagreen> "),
                completer=file_completer,
                validator=validator,
                validate_while_typing=False,
                style=COMPLETER_STYLER,
                history=self.filepath_history,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]File read canceled.[/dim]\n")
            return

        # Normalize path input and check file size
        path = os.path.abspath(os.path.expanduser(path))
        max_size = 1_000_000  # 1 MB
        file_size = os.path.getsize(path)
        if file_size > max_size:
            console.print(
                f"[yellow]Warning:[/yellow] File is {file_size / 1_000_000:.2f} MB and may consume a large amount of context."
            )
            choice = (
                prompt(
                    HTML(
                        "Attach anyway? (<seagreen>y</seagreen>/<ansired>N</ansired>): "
                    )
                )
                .lower()
                .strip()
            )
            if choice not in ("y", "yes"):
                console.print("[dim]Attachment canceled by user.[/dim]\n")
                return

        # File attachment process begins
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(path, "r", encoding="latin-1") as f:
                    content = f.read()
        except Exception as e:  # If the file can't be read, log it bail out.
            log_exception(e, "Error in attach_file()")
            spawn_error_panel("ERROR READING FILE", f"{e}")
            return

        content = content.replace("```", "ʼʼʼ")
        filename = os.path.basename(path)
        wrapped = f"---\nFile: `{os.path.basename(path)}`\n```\n{content}\n```\n---"
        existing = [(i, t, n) for i, t, n in self._get_attachments() if n == filename]

        # If the file exists already in context, delete it.
        if existing:
            index = existing[-1][0]
            self.session.history.pop(index)
            console.print(f"{filename} [yellow]is being updated in context...[/yellow]")
        # Add the file's content to context, wrapped in Markdown for retrieval
        self.session.history.append({"role": "user", "content": wrapped})
        console.print(f"{filename} [green]read and added to context.[/green]")
        # Print out the status panel, show updated context consumption
        self.spawn_status_panel()

    def list_attachments(self):
        """Return [(index, type, name)] list for files."""
        attachments = self._get_attachments()
        if not attachments:
            console.print("[dim]No attachments found.[/dim]\n")
            return

        console.print("[cyan]Attachments in context:[/cyan]")
        for _, kind, name in attachments:
            console.print(f"• [{kind}] {name}")
        console.print()

    def purge_attachment(self):
        """
        Purges files/images from context and recovers context length.
        """
        # Generate the attachment list using _get_attachments()
        attachments = self._get_attachments()
        if not attachments:
            console.print("[dim]No attachments found.[/dim]\n")
            return

        console.print("[cyan]Attachments in context:[/cyan]")
        for _, kind, name in attachments:
            console.print(f"• [{kind}] {name}")
        console.print()
        # Prompt for a file to purge
        try:
            choice = prompt(
                HTML("Enter file/image name to remove<seagreen>:</seagreen> ")
            )
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]File purge canceled.[/dim]\n")
            return

        # Search the attachment list for the designated file by name
        for idx, kind, name in reversed(attachments):
            if choice.lower().strip() == name.lower():
                # Remove the attachment by index from the conversation history list
                _ = self.session.history.pop(idx)
                console.print(
                    f"[green]{kind.capitalize()}[/green] '{name}' [green]removed.[/green]"
                )
                # Print the status panel, to show the user their updated context consumption
                self.spawn_status_panel()
                return
        console.print(f"[red]No match found for:[/red] '{choice}'\n")

    def _get_attachments(self) -> list[tuple[int, str, str]]:
        """Retrieves a list of all attachments by utilizing compiled regex."""
        attachments: list[tuple[int, str, str]] = []
        # Iterate through all messages in the conversation history
        for i, msg in enumerate(self.session.history):
            content = msg.get("content")
            # Only process messages where "content" is a string.
            if isinstance(content, str):
                # Look for a file attachment pattern using compiled regex.
                match = FILE_PATTERN.match(content)
                if match:
                    # Append each attachment to a new structured list
                    attachments.append((i, "file", match.group(1)))
        # Return the complete list of detected attachments.
        return attachments

    def _file_validator(self, text: str):
        """File validation helper for prompt_toolkit"""
        # Boiled down to two lines, simply validates that a file exists
        text = os.path.abspath(os.path.expanduser(text))
        return os.path.isfile(text)

    # <~~RUN~~>
    def run(self):
        """Helper function for running the application"""
        self.spawn_intro_panel()  # Prints out the intro panel
        while True:
            # Prompts for input, resets temp variables to baseline
            # Returns False and breaks if the user issues an exit command
            if not self.slate_cleaner():
                console.print("[yellow]✨ Farewell![/yellow]\n")
                break
            self.stream_response()  # Streaming process begins, panels are populated


# <~~MAIN FLOW~~>
def main():
    try:
        # Start a spinner, mostly for cold starts
        spinner = Spinner(
            "moon",
            text="[bold medium_orchid]Launching Local Sage...[/bold medium_orchid]",
        )
        with Live(spinner, refresh_per_second=8, console=console):
            init_logger()  # Initialize the log file
            config = Config()
            session_manager = SessionManager(config)
            try:
                config.load()  # Loads config variables from file
            except FileNotFoundError:
                config.save()  # Generates a config file if one does not exist
            session = Chat(config, session_manager)
        console.clear()  # Clears the viewport
        session.run()  # Runs the application
        config.save()  # Saves config on exit
    except (KeyboardInterrupt, EOFError):
        console.print("[yellow]✨ Farewell![/yellow]\n")
    except Exception as e:
        log_exception(e, "Critical startup error")  # Log any critical errors
        spawn_error_panel("CRITICAL ERROR", f"{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
