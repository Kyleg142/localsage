### v1.1.3 - Hotfix
Fixed an API error that can occur when using the !switch command.

---

### v1.1.2
**Improvements:**
- The reasoning panel now activates correctly for a wider range of model providers, including DeepSeek and vLLM.
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
