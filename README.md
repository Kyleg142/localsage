# 🔮 Local Sage
<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue">
  <img src="https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20Windows-red">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg">
</p>

<p align="center"><b>A lightweight LLM chat interface that embraces the command line.</b></p>

<p align="center"><img width="1200" alt="Local Sage Demo" src="https://raw.githubusercontent.com/Kyleg142/localsage/main/assets/localsagedemo.gif"></p>

<p align="center"><img src="https://raw.githubusercontent.com/Kyleg142/localsage/main/assets/localsage%2Bzellij.png" width="1200"><br><i>Local Sage running in Zellij, alongside Helix and Yazi.</i></p>

## About 🔎
Local Sage is an open-source CLI for chatting with LLMs. Not automation, not agents, just pure dialogue. 

Featuring **live Markdown rendering with inline math conversion** for a *silky smooth* chatting experience. Designed to hook into any **OpenAI API endpoint**, and tested with local LLMs hosted via **llama.cpp**.

#### What else makes **Local Sage** shine? ✨
- **Conversations live in your shell**, rendering directly to standard output for persistent history.
- Fancy prompts with **command completion** and **in-memory history**.
- **Context-aware file management.** See the [Under the Hood](#under-the-hood-%EF%B8%8F) section for more info!
- Small but mighty, below 2000 lines of **Python** 🐍.

#### Plus everything you'd expect from a solid chat frontend.
- **Session management**: load, save, delete, reset, and summarize sessions.
- **Profile management**: save, delete, and switch model profiles.
- Reasoning/Chain-of-thought support with a dedicated Reasoning panel.
- Context length monitoring, shown through a subtle status panel.

There is also a collection of [built-in Markdown themes](https://pygments.org/styles/) to choose from to customize your sessions!

## Compatibility 🔩
**Python 3.10** or later required.

The big three (**Linux, macOS,** and **Windows**) are all supported. Ensure your terminal emulator has relatively modern features. Alacritty works well. So does kitty and Ghostty.

You can use non-local models with Local Sage if desired. If you set an API key, the CLI will store it safely in your OS's built-in credential manager via **keyring**.

## Installation 💽
Install a Python package manager for your OS. Both [**uv**](https://github.com/astral-sh/uv) and [**pipx**](https://github.com/pypa/pipx) are highly recommended.\

###### For `uv`, open your terminal and type:
```bash
uv tool install localsage
```
###### Or, for `pipx`, type:
```bash
pipx install localsage
```
Type **`localsage`** into your terminal to launch the CLI. Type **`!h`** to view command usage.

### Getting Started ✔️
Configuration is done entirely through interactive commands. You never have to touch a config file.
1. Configure a profile with `!profile add`.
2. Type `!profile switch` to switch to your new profile.
3. Use `!ctx` to set your context length.
4. (Optional) Set your own system prompt with `!prompt` or an API key with `!key`.

**Typical API endpoint format:** `http://ipaddress:port/v1`

**Tip:** If you press `tab` while at the main prompt, you can access a command completer for easy command use.

### Dependencies 🧰
Local Sage is designed with minimal dependencies, keeping the download light and minimizing library bloat.
- [Rich](https://github.com/Textualize/rich) - Used extensively throughout. Panels, live rendering, etc.
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Prompts and completers, also used extensively.
- [OpenAI](https://github.com/openai/openai-python) - Provides all API interaction as well as the conversation history list.
- [keyring](https://github.com/jaraco/keyring) - Safely handles API keys on all platforms.
- [tiktoken](https://github.com/openai/tiktoken) - Provides tokenization and enables context length calculation.
- [platformdirs](https://github.com/platformdirs/platformdirs) - Detects default directories across operating systems.
- [pylatexenc](https://github.com/phfaist/pylatexenc) - Absolutely vital for live math sanitization.

### File Locations 📁
Your config file, session files, and error logs are stored in your user's data directory.

| **OS** | **Directory** |
| --- | --- |
| Linux: | ~/.local/share/LocalSage |
| macOS: | ~/Library/Application Support/LocalSage |
| Windows: | %localappdata%/LocalSage |

## Docker 🐋
This is a general guide for running Local Sage in a Docker container. The `docker` commands below are suggested templates, feel free to edit them as necessary.

A bash script, `containerize.sh`, is available to Linux & macOS users for convenient dockerization. You may have to run it with elevated permissions.

Start by creating and setting a working directory.

**If you'd like to use the script, perform the following:**
```bash
# 1) Clone the repo:
git clone https://github.com/Kyleg142/localsage

# 2) Build the image:
chmod u+x containerize.sh
./containerize.sh build

# 3) Run the container with sane defaults:
./containerize.sh run
```
###### Or, if you run a non-containerized backend/API on the same machine:
```bash
./containerize.sh run local
```
The script stores persistent files in `/var/lib/LocalSage`.

**Dockerizing Local Sage manually:**
```bash
# 1) Clone the repo:
git clone https://github.com/Kyleg142/localsage

# 2) Build the image
docker image build -t python-localsage .

# 3) Run the container
docker run -it --rm \     
  --name localsage \ 
  -e OPENAI_API_KEY \
  -v /home/<YourUsername>/.local/share/LocalSage:/root/.local/share/LocalSage \
  python-localsage
```
###### For Windows users, here is the equivalent `docker run` command in PowerShell:
```powershell
docker run -it --rm `
  --name localsage `
  -e OPENAI_API_KEY `
  -v "${env:LOCALAPPDATA}/LocalSage:/root/.local/share/LocalSage" `
  python-localsage
```
### Notes on Networking
You may have to add specific options to your `docker run` command if you are running a non-containerized backend/API on the same machine. `./containerize.sh run local` applies these options automatically. 

**Local Linux**
1) Add `--network host` to your `docker run` options to allow the container to reach services on localhost.
2) Follow the [**Getting Started**](#getting-started-%EF%B8%8F) section above.

**Local Windows/Mac**
1) Add `--add-host=host.docker.internal:host-gateway` to your `docker run` options.
2) Run the container, type `!profile add` to create a new profile. Set the API endpoint to `http://host.docker.internal:8080/v1` when prompted.
3) Ensure your API endpoint (llama.cpp, vllm, etc.) is listening on `0.0.0.0:8080`.

## Display Notes 🖥️
Typing into the terminal while streaming is active may cause visual artifacting. Avoid typing into the terminal until the current generation finishes.

A monospaced Nerd font is **HIGHLY** recommended. It ensures that Markdown, math, and icons all align well on-screen. The main prompt uses a Nerd font chevron.

## Under the Hood 🛠️

#### Context-Aware File Management
If you re-attach a file, context consumption is **massively reduced** by removing the original file from the conversation history and then appending the new copy. Removing an attachment (via the `!purge` command) will **fully refund** its context consumption.

#### Rendering & Streaming (For Technical Users)
At its core, Local Sage uses the **Rich** library combined with a custom math sanitizer to render live Markdown and readable inline math. Chunk processing is frame-synchronized to the refresh rate of a rich.live display, meaning that the entire rendering process occurs at a customizable interval. Effectively a hand-rolled, lightweight, synchronized rendering engine running right in your terminal.

You can adjust the refresh rate using the `!rate` command (30 FPS by default).

## Limitations 🛑
Once the live panel group fills the terminal viewport, real-time rendering cannot continue due to terminal constraints. By default, the Response panel consumes the Reasoning panel to conserve space (toggleable with the `!consume` command).

**This should only be noticeable on large responses that consume over an entire viewport's worth of vertical space.**

**Local Sage is text-only.** This limitation keeps Local Sage portable, lightweight, and backend-agnostic.

Local Sage will only ever store one API key in your keychain. If you switch providers often, you will have to swap your API key with `!key`.

## What's Next?
Upcoming features, in order:
- System prompt list feature, for storing and swapping system prompts.

## Versioning 🔧
The project follows basic versioning:
- **1.0.x** - Minor patches consisting of bug fixes and aesthetic tweaks.
- **1.x.0** - Major patches consisting of feature expansions or necessary refactors.

## License ⚖️
Local Sage is released under the [**MIT License**](https://opensource.org/license/mit).

## Closing Notes 🫵
Local Sage is an **open-source, single-dev project** built purely for the love of the game. Please be kind!

Contributions are always welcome! See [**Contributing**](https://github.com/Kyleg142/localsage/blob/main/.github/CONTRIBUTING.md).
