### 1.4.8

**Technical Improvements**
- Embedded links are no longer included when scraping a website, which greatly reduces context usage when scraping sources such as Wikipedia.
- Enviroment context now includes the current date.

---

### 1.4.7

**UX**: The CLI no longer clears the terminal when initialized, preserving previous terminal output.

---

### v1.4.6

More polish and technical improvements.

**Technical Improvements**
- Added manual HTML cleaning to the website scraping pipeline. Scraping a website now consumes far less context on average.
- Fixed a small bug with file attachment, which was causing the token cache to rebuild if a file failed to attach.

And quite a bit of code cleanup.

---

### v1.4.5

**Technical Improvements**
- Website attachment has been reinforced with a new robust ingestion pipeline. Github links are automatically converted to their raw equivalent for context injection when possible. Same with Pastebin links and GitLab links.
- Each release is now published to Docker Hub. The README has been updated with new instructions for running the CLI in Docker.
- Automated Environment Context should now be far more reliable when changing the working directory with `!cd`.

---

### v1.4.4 - Hotfix

Corrected a string accumulation bug that was affecting environment context.

---

### v1.4.3

This is mostly an optimization and refinement update, to shore up some feature quirks.

**Techinical Improvements**
- Copying code blocks is now far more robust. Model output quirks are now taken into consideration.
- File attachment has been optimized. A filter is now in place so that directories can be attached without the risk of attaching an unsupported file type.
- The CLI now exits with a descriptive message if piped content exceeds the configured context window.

---

### v1.4.2

**New:** Directory attachment, `!a` and `!attach` can now be used on directories. `!purge` can also be used to remove attached directories.

**Architecture:**
The entirety of `sage.py` has been broken up into modules, which consists of...
- cli_controller.py
- config.py
- file_manager.py
- globals.py
- math_sanitizer.py
- sage.py
- session_manager.py
- ui.py

Structurally and functionally, everything is the same. Certain classes are just isolated in standalone files now.

---

### v1.4.1

**New:**
- Web scraping! Websites can now be scraped and appended to history by using the `!web` command. `!purge` can also be used to remove attached website content.
- Sliding context window. Session history is now automatically truncated when exceeding 95% context consumption.

**UX**: Attachments are now removed by index, rather than by name. Index is now included when listing attachments.

---

### v1.4.0

Tons of new features for this release! This update is focused on turning Local Sage into a true shell-native tool!

**Automated Environment Awareness**: The CLI now provides your model with basic environment awareness. Here is what your model sees... 
```shell
[ENVIRONMENT CONTEXT]                        # Header
Current User: {USER_NAME}                    # Your username
Operating System: {system_info}              # Your operating system
Working Directory: {wd}                      # Current working directory, mutates when using !cd
Visible Files: {", ".join(files[:20])}       # Up to 20 visible file names, mutates when using !cd
Visible Directories: {", ".join(dirs[:20])}  # Up to 20 visible directory names, mutates when using !cd
```
**Input Piping**: You can now initiate the CLI by piping file content or command output via stdin. Here are some examples...
```shell
# Piping command output
ps aux | localsage "What process is eating up all of my RAM?"

# Piping file content
cat README.md | localsage "What dependencies are listed for this project?"
```

**New `!cd` command** to change the current working directory.

**New `!cp` command** to copy all code blocks from the previous assistant response to the system clipboard. Spawns a pretty Markdown preview panel as well!

And some code cleanup, as per usual.

---

### v1.3.3

**Technical Improvements:**
- Implemented reasoning retention for interleaved thinking. Reasoning output is now retained automatically when using a thinking model.
- Improved toks/sec throughput readout accuracy.

---

### v1.3.2

**Bug Fix**: Fixed an API error that could occur when sending a message after attaching a file. This was only affecting the new Devstral models as far as I know (due to a very strict chat template).

---

### v1.3.1

**UX:** Entering an incorrect command no longer triggers a model response.

**Technical Improvements:**
- **Architecture:**
  - Separated the API interaction in `sage.py` into its own class, rightfully named API.
  - Organized class structure in `sage.py` for maintainability.
- New docstring for `sage.py`, serving as a concise architectural overview.

---

### v1.3.0

**New:**
- Tokens-per-second throughput is now implemented in the status panel.
- New option for !purge, `!purge all`. Used to delete all file attachments from a session.
- Attaching a file now prints the file's size in raw tokens as well as percentage context consumption.

**Technical Improvements:**
- Token counting and caching has been optimized. Long sessions consume less memory.
- General code cleanup and de-duplication.

**UX:**
- Profile commands are argument-based now: `!profile add`, `!profile switch`, `!profile list`, and `!profile remove`.

---

### v1.2.2

**Dockerization!:** Local Sage can now be ran easily in Docker! Instructions are now posted at the front of the repo.

**Bug Fix:** Added logic to gracefully handle any lingering keyring errors.

---

### v1.2.1

**Architecture:** Decoupled chart spawning logic.

**UX:** Re-implemented the `!sessions` and `!attachments` commands.

---

### v1.2

**New:**
- Fancy time-to-first-token spinner.

**Technical Improvements:**
- **API Key:** The CLI now checks the **OPENAI_API_KEY** environment variable before relying on keyring.
- **Architecture:**
  - Separation of panel construction from Chat into it's own class called UIConstructor.
  - The API interaction now exists within it's own method.
- Thorough code clean up throughout the application.
  
**UX:** 
- Unified input handling and validation for all commands.

---

### v1.1.5
**Technical Improvements:**
- **Architecture:** Turn state has been decoupled and placed into it's own dataclass called TurnState. The rendering engine is now entirely state-based.
- Cleaned up the 1.1.4 hotfix to protect against future regression.
- General code clean-up throughout the Chat class.

---

### v1.1.4 - Hotfix
Fixed an issue with instruct models not triggering the Response panel after the 1.1.2 update.

---

### v1.1.3 - Hotfix
Fixed an API error that can occur when using the !switch command.

---

### v1.1.2
**Technical Improvements:**
- The Reasoning panel now activates correctly for a wider range of model providers, including DeepSeek and vLLM.
- Migrated to a different tokenizer for higher efficiency (o200k_base).

---

###  v1.1.1 - Hotfix
Fixed an API error that can occur if it receives a null value from keyring.

---

### v1.1.0

**Technical Improvements:**
- A **complete architectural refactor**, breaking Local Sage's monolithic architecture into several smaller, maintainable classes.
  - Chat (the old god class) now solely facilitates the synchronous rendering loop.
  - **New classes include:** FileManager, SessionManager, CLIController, and App (the new main controller).
  - This will be a continued effort, although I am very happy with the current state of the architecture.

**Minor Improvements:**
- Adjusted profile management command naming, all now start with 'profile'.
  - !addprofile -> !profileadd
  - !removeprofile -> !profileremove

**Bug fixes:**
- Fixed a critical crash on systems without a configured credential manager.
- Fixed a string formatting issue for a text object that printed when issuing !prompt.
