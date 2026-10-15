@echo off
rem myOS hardened Claude shim for Graphify semantic extraction.
rem Graphify pipes note text to `claude -p`. This shim removes every tool, MCP
rem server and skill so text inside a note cannot make the model act on the
rem machine, and forces the default (manual) permission mode.
"%USERPROFILE%\.local\bin\claude.exe" --tools "" --strict-mcp-config --disable-slash-commands --permission-mode default %*
