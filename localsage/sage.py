#!/usr/bin/env python3

# <~~~~~~~~~~>
#  LOCAL SAGE
# <~~~~~~~~~~>

# All code is quality-checked for pythonic standards with basedpyright and ruff.
# You can get an idea of the architecture in the docstring below.

"""
ABOUT:

    Local Sage is a specialized interactive CLI known as a stateful REPL.
    The idea is to achieve the functionality of a chat TUI without the overhead.

REPL FLOW:

       ↗ API → Render ↘
    Input             Input
       ↘ CLI → Result ↗

CLASSES:

    - Config:         User-facing configuration
    - SessionManager: Session I/O
    - FileManager:    Attachment I/O
    - UIConstructor:  Interface object builder
    - GlobalPanels:   Panel spawner
    - CLIController:  Command logic
    - API:            API interaction
    - Turnstate:      State-of-truth
    - Chat:           Rendering

LIBRARIES:

    - openai:         API interaction & history list
    - tiktoken:       Tokenization
    - rich:           Live rendering & visuals
    - prompt_toolkit: Interactive prompts
    - platformdirs:   OS-independent directories
    - keyring:        Safe API key storage
    - pyperclip:      Copying code blocks to the system clipboard
    - trafilatura:    Scraping websites
"""

import os
import re
import sys
import time
from dataclasses import dataclass, field

from openai import OpenAI, Stream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from rich.console import ConsoleRenderable, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from localsage.cli_controller import CLIController
from localsage.config import Config
from localsage.file_manager import FileManager
from localsage.globals import (
    CONSOLE,
    init_logger,
    log_exception,
    retrieve_key,
    root_prompt,
    setup_keyring_backend,
    spinner_constructor,
)
from localsage.math_sanitizer import sanitize_math_safe
from localsage.session_manager import SessionManager
from localsage.ui import GlobalPanels, UIConstructor


# <~~API~~>
class API:
    """API interaction"""

    def __init__(self, config: Config, session: SessionManager):
        self.config: Config = config
        self.session: SessionManager = session

        active = self.config.active()
        self.client = OpenAI(base_url=active["endpoint"], api_key=retrieve_key())
        self.model_name = active["name"]

    def fetch_stream(self) -> Stream[ChatCompletionChunk]:
        """OpenAI API call"""
        return self.client.chat.completions.create(
            model=self.config.model_name,
            messages=self.session.process_history(),
            stream=True,
        )


# <~~STATE-OF-TRUTH~~>
@dataclass
class TurnState:
    """State-of-truth for the Chat class."""

    reasoning: str | None = None
    response: str | None = None
    reasoning_buffer: list[str] = field(default_factory=list)
    response_buffer: list[str] = field(default_factory=list)
    full_response_content: str = ""
    full_reasoning_content: str = ""


# <~~RENDERING~~>
class Chat:
    """Rendering logic. Creates a synchronous non-blocking rendering loop."""

    # <~~INTIALIZATION & GENERIC HELPERS~~>
    def __init__(
        self,
        config: Config,
        session: SessionManager,
        filemanager: FileManager,
        ui: UIConstructor,
        panel: GlobalPanels,
        api: API,
    ):
        self.config: Config = config
        self.session: SessionManager = session
        self.filemanager: FileManager = filemanager
        self.ui: UIConstructor = ui
        self.panel: GlobalPanels = panel
        self.api: API = api
        self.state = TurnState()

        # Placeholder for live display object
        self.live: Live | None = None

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

        # Response start timer, for calculating toks/sec
        self.start_time: float = 0

        # Terminal height and panel scaling
        self.max_height: int = 0
        self.reasoning_limit: int = 0
        self.response_limit: int = 0

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

    def _terminal_height_setter(self):
        """
        Sets values for scaling live panels.\n
        Ran every turn so the user can resize the terminal window freely during prompting.
        """
        if self.max_height != CONSOLE.size.height:
            self.max_height = CONSOLE.size.height
            self.reasoning_limit = int(self.max_height * 1.5)
            self.response_limit = int(self.max_height * 1.5)

    def init_rich_live(self):
        """Defines and starts a rich live instance for the main streaming loop."""
        self.live = Live(
            Group(),
            console=CONSOLE,
            screen=False,
            refresh_per_second=self.config.refresh_rate,
        )
        self.live.start()

    def reset_turn_state(self):
        """Little helper that resets the turn state."""
        self.state = TurnState()
        self.start_time = 0
        self.reasoning_panel_initialized = False
        self.response_panel_initialized = False
        self.reasoning_panel = Panel("")
        self.response_panel = Panel("")
        self.count_reasoning = True
        self.count_response = True
        self.renderables_to_display.clear()

    # <~~STREAMING~~>
    def stream_response(self, callback=None):
        """Facilitates the entire streaming process."""
        self._terminal_height_setter()
        self.session.trim_history()
        self.cancel_requested = False
        try:  # Start rich live display and create the initial connection to the API
            self.init_rich_live()
            self.renderables_to_display.append(
                spinner_constructor("Awaiting response...")
            )
            self._rebuild_layout(force_refresh=True)
            # Parse incoming chunks, process them based on type, update panels
            campbells_chunky = True
            for chunk in self.api.fetch_stream():
                if campbells_chunky:
                    self.renderables_to_display.clear()
                    campbells_chunky = False
                    self.start_time = time.perf_counter()
                self.chunk_parse(chunk)
                self.render_reasoning_panel()
                self.render_response_panel()
                self.update_renderables()
            self.session.turn_duration(self.start_time, time.perf_counter())
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
                    self.session.history_wrapper(
                        response=self.state.full_response_content,
                        reasoning=self.state.full_reasoning_content,
                    )
                    self.panel.spawn_status_panel()

    def chunk_parse(self, chunk: ChatCompletionChunk):
        """Parses a chunk and places it into the appropriate buffer"""
        self.state.reasoning = self._extract_reasoning(chunk)
        self.state.response = self._extract_response(chunk)
        if self.state.reasoning:
            self.state.reasoning_buffer.append(self.state.reasoning)
        if self.state.response:
            self.state.response_buffer.append(self.state.response)

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
        current_time = time.monotonic()
        # Syncs text rendering with the configured refresh rate.
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

    def render_reasoning_panel(self):
        """Manages the reasoning panel."""
        if self.state.reasoning is not None and not self.reasoning_panel_initialized:
            self.reasoning_panel = self.ui.reasoning_panel_constructor()
            self.renderables_to_display.append(self.reasoning_panel)
            self._rebuild_layout()
            self.reasoning_panel_initialized = True

    def render_response_panel(self):
        """Manages the response panel."""
        if self.state.response is not None and not self.response_panel_initialized:
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

    def render_history(self):
        """Renders a scrollable history."""
        for msg in self.session.history:
            role = msg.get("role", "unknown")
            content = (msg.get("content") or "").strip()  # type: ignore | content is guaranteed or null
            if not content:
                continue  # Skip non-content entries
            if role == "user":
                self.panel.spawn_user_panel(content)
            elif role == "assistant":
                self.panel.spawn_assistant_panel(content)


# <~~CONTROLLER~~>
class App:
    """Main controller, puts together the pieces and handles input"""

    def __init__(self):
        # Load config file
        self.config = Config()
        try:
            self.config.load()
        except FileNotFoundError:
            self.config.save()

        # Define all 7 objects
        self.session_manager = SessionManager(self.config)
        self.file_manager = FileManager(self.session_manager)
        self.ui = UIConstructor(self.config, self.session_manager)
        self.panel = GlobalPanels(self.session_manager, self.config, self.ui)
        self.commands = CLIController(
            self.config, self.session_manager, self.file_manager, self.panel, self.ui
        )
        self.api = API(self.config, self.session_manager)

        self.chat = Chat(
            self.config,
            self.session_manager,
            self.file_manager,
            self.ui,
            self.panel,
            self.api,
        )

        # Give CLIController access to Chat for !load and !summary
        self.commands.set_interface(self.chat)

    def run(self):
        """The app runner"""
        self.panel.spawn_intro_panel()

        # Handle piped content
        if not sys.stdin.isatty():
            piped_content: str = sys.stdin.read().strip()
            if piped_content:
                wrapped = f"[PIPED CONTENT]\n{piped_content}"
                if len(sys.argv) > 1:
                    user_query = " ".join(sys.argv[1:])
                    wrapped += f"\n\n[USER QUERY]\n{user_query}"
                self.session_manager.append_message("user", wrapped)
                self.chat.stream_response()
                try:
                    sys.stdin = open("/dev/tty" if os.name != "nt" else "CONIN$", "r")
                except Exception:
                    CONSOLE.print(
                        "[dim]Cannot re-attach to the active terminal. Exiting gracefully...[/dim]"
                    )
                    sys.exit(0)

        # Start REPL
        while True:
            self.chat.reset_turn_state()
            try:
                user_input = root_prompt()
            except (KeyboardInterrupt, EOFError):
                CONSOLE.print("[yellow]✨ Farewell![/yellow]\n")
                break

            if not user_input.strip():
                continue

            # Handle commands
            command_result = self.commands.handle_input(user_input)
            if command_result is not False:
                if isinstance(command_result, tuple):
                    self.api.client = command_result[0]
                    self.api.model_name = command_result[1]
                elif isinstance(command_result, OpenAI):
                    self.api.client = command_result
                continue

            if re.match(r"^!", user_input):
                CONSOLE.print(
                    "[dim]Command not found. Type [cyan]!help[/cyan] for usage.[/dim]\n"
                )
                continue

            self.session_manager.append_message("user", user_input)
            CONSOLE.print()
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
            console=CONSOLE,
        ):
            app = App()
        CONSOLE.clear()
        app.run()
    except (KeyboardInterrupt, EOFError):
        CONSOLE.print("[yellow]✨ Farewell![/yellow]\n")
    except Exception as e:
        log_exception(e, "Critical startup error")  # Log any critical errors
        CONSOLE.print(f"[bold][red]CRITICAL ERROR:[/red][/bold] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
