# 🔮 Local Sage
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20Windows-red)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**A modern LLM chat interface that embraces the command line.**

![Demo gif placeholder](path/to/demo.gif)
*Asking GPT-OSS 20B for a rundown on `getopts`, saving, exiting, and reloading the session.*

Local Sage is designed to hook into any **OpenAI API endpoint**, and is tested extensively with local models hosted through **llama.cpp**.

## About 🔎
Local Sage is an open-source CLI for chatting with LLMs. Not automation, not agents, just pure dialogue. 
Perhaps the *only* terminal interface that renders **live Markdown with readable in-line math**.

### What makes **Local Sage** shine? ✨
- Sessions that exist right in your terminal viewport via **gorgeous live Rich panels**.
- Fancy prompts with **command completion** and **in-memory history**.
- **Context-aware file management**. Files are replaced on re-attachment and can be selectively purged.
- Lightweight, below 2000 lines of **Python** 🐍.

### Plus everything you'd expect from a solid chat frontend.
- **Session management**: load, save, delete, reset, and summarize sessions.
- **Profile management**: save, delete, and switch between models and endpoints.
- Reasoning/Chain-of-thought support with a dedicated Reasoning panel.
- Context length monitoring via **tiktoken**, shown through a subtle status panel.

There is even a collection of [built-in Markdown themes](https://pygments.org/styles/) to choose from, courtesy of **Rich**.

## Demo & Screenshots 🗺
![Screenshot1](path/to/screenshot.png)
*Local Sage running in Zellij alongside Yazi, Btop, and Helix.*

![Screenshot2](path/to/screenshot.png)
*Output for attaching a file and purging it.*

## Under the Hood 🛠️
At its core, Local Sage uses the **Rich** library combined with a custom math sanitizer to render live Markdown and readable in-line math. Chunk processing is frame-synchronized to the refresh rate of a rich.live display, meaning that the entire rendering process occurs on a customizable interval. Effectively a hand-rolled, lightweight, synchronized rendering engine running right in your terminal.

No flickering, no race conditions, and no coroutine overhead. Just a smooth flow of rendered output.

You can adjust the refresh rate using the `!rate` command (30 FPS by default).

### Design Philosophy
Local Sage abides by a **CLI-first** design philosophy. Configuration, interaction, and workflow are all bound to the command line. No GUI mimicry and no hidden layers.

## Compatibility 🔩
**Python 3.9** or later required.

The big three (**Linux, macOS,** and **Windows**) are all supported, ensure your terminal emulator has relatively modern features. Alacritty works well. So does kitty and ghostty.

Local Sage is designed to work with any backend that features an OpenAI API endpoint. I personally use **llama.cpp** and can thus guarantee compatibility for it.

You can use non-local models with Local Sage if desired. If you set an API key, the CLI will store it in your OS's built-in credential manager via **keyring**.

Local Sage is tested with four small and diverse models hosted via llama.cpp on my humble 7900xt.
- GPT-OSS 20B
- LFM2 8B A1B
- Nemotron Nano 12B v2
- Qwen3 30B A3B Instruct 2507

## Installation 💽
Install **pip** for your OS, the Python package manager.

Open up your terminal and type:

```bash
pip install localsage
```

Type `localsage` into your terminal to launch the CLI. Type `!h` to view usage.

**Read through the usage tables carefully!** Proper command usage is key to getting full use out of Local Sage. It is a CLI frontend, after all.

### Dependencies 🧰
- [Rich](https://github.com/Textualize/rich) - Used extensively throughout. Panels, live rendering, etc.
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Prompts and completers, also used extensively.
- [OpenAI](https://github.com/openai/openai-python) - Provides all API interaction as well as the conversation history list.
- [keyring](https://github.com/jaraco/keyring) - Safely handles API keys on all platforms.
- [tiktoken](https://github.com/openai/tiktoken) - Provides tokenization and enables context length calculation.
- [platformdirs](https://github.com/platformdirs/platformdirs) - Detects default directories across operating systems.
- [pylatexenc](https://github.com/phfaist/pylatexenc) - Absolutely vital for live math sanitization.

Local Sage was designed with minimal dependencies, so the download is very light.

### File Locations 📁
Your config file, session files, and error logs are stored in your user's data directory.

| **OS** | **Directory** |
| --- | --- |
| Linux: | ~/.local/share/LocalSage |
| macOS: | ~/Library/Application Support/LocalSage |
| Windows: | %localappdata%/LocalSage |

## Display Notes 🖥️
Typing into the terminal while streaming is occurring will cause visual artifacting, since output is rendered directly into the main viewport rather than an alternate buffer. Avoid typing into the terminal window until streaming completes.

A monospaced Nerd font is **HIGHLY** recommended as well for a seamless experience. It ensures that Markdown, math, and icons all align well on-screen. The main prompt uses a cool Nerd font chevron. If you want it to display correctly, **use a Nerd font**.

## Limitations 🛑
Once the live panel group fills the terminal viewport, real-time rendering cannot continue due to terminal constraints. Rich.live displays an ellipsis at the bottom of the viewport to indicate that streaming continues. By default, the Response panel consumes the Reasoning panel to conserve space (toggleable with the `!consume` command).

**This should only be an issue on large responses that consume over an entire viewport's worth of vertical space.**

**Local Sage is text-only.** This limitation keeps Local Sage portable, lightweight, and backend-agnostic. Unlike text generation and file handling, methods for image generation and attachment vary between backends.

**NOTE:** Local Sage will only ever store one API key in your keychain. If you switch providers often, you will have swap your API key with `!key`.

## Notes & Acknowledgements 🫵
Local Sage’s math sanitizer doesn’t attempt to fix broken LaTeX, and Rich’s Markdown parser can’t repair malformed Markdown. Please report rendering issues only if you’ve confirmed they originate from Local Sage’s math sanitizer.

Local Sage is an **open-source, single-dev project** built purely for the love of the game. Please be kind!

## Versioning 🔧
Version **1.0.0** is the fully 'finished' release, containing full CLI functionality.
- **1.0.x** - Minor patches consisting of bug fixes and aesthetic tweaks.
- **1.x.0** - Major patches consisting of feature expansions or necessary refactors.

## License ⚖️
Local Sage is released under the **MIT License**.

You are free to use, modify, and distribute this software, provided that attribution is maintained and the license notice is included in derivative works.

## And most of all!
I wanted to say thank you to the OSS community! ❤️
Without all of your wonderful creations, I never would have had the inspiration to create something myself.

Contributions are always welcome! Please open an issue for discussion!

---

💼 I am currently seeking opportunities! If Local Sage impressed you or you think my skill set would fit your team, feel free to reach out.
