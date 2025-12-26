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
