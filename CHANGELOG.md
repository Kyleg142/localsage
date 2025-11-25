**The road to 1.1.0**

Bug fixes:
- Fixed a critical exception, keyring was refusing to allow the CLI to run if it did not find a supported OS keychain.
- Small text fomatting fix in stream summarization

Technical Improvements
- A **complete refactor** of the Chat class into several distinct classes, decoupling most features.
  - Chat now solely facilitates the synchronous rendering loop.
  - New classes include: FileManager, SessionManager, CLIController, and App (the new main controller).
  - I wanted most of Local Sage to be contained in one file, and that logic carried over into how I built the architecture. Now, it should be FAR easier to maintain.
