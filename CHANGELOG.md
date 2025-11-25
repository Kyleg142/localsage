##v1.1.0

Minor Improvements:
- Adjusted profile management command naming, all now start with 'profile'.
  - !addprofile -> !profileadd
  - !removeprofile -> !profileremove

Bug fixes:
- Fixed a critical crash on systems without a configured credential manager.
- Fixed a string formatting issue for a text object that printed when issuing !prompt.

Technical Improvements
- A **complete architectural refactor**, breaking Local Sage's monolithic god class into several smaller, maintainable classes.
  - Chat (the old god class) now solely facilitates the synchronous rendering loop.
  - **New classes include:** FileManager, SessionManager, CLIController, and App (the new main controller).
