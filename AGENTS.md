# Sunday Blue development rules

This is an independent Windows desktop app. All source, runtime assets, configuration,
conversation data, memory, and build outputs belong to this directory. Do not introduce
runtime dependencies on Great_blue, RedOS, Sunday, Claude Desktop, cc-switch, or global
Claude settings. Do not read or migrate other projects without a specific request.

Preserve the seven imported personalities. Runtime host rules live in agent.py; the
legacy rules.md/responsibilities.md files are archival references, not executable host
instructions. TickTick and Mubu are professional tool assistants, not persona clones.

Secrets: use Windows DPAPI for the primary API key. Never log keys or full request
headers. Default external file access is empty. Permission checks belong in files.py,
not solely in model prompts. Writes must be backed up and revalidated. User-selected
trusted writable workspaces auto-approve file operations; other writes require review.
Trust is per-role/per-directory, never an implicit bypass for memory updates or MCP.
MCP subprocesses are not sandboxed; never claim that role directory rules constrain them.

Do not destroy user conversations or overwrite configured API credentials during tests.
Use isolated temporary fixtures under tests. Test API behavior with local HTTP fixtures.
Run `python -m unittest discover -s tests -v` after changes to permissions, persistence,
wire protocols, tool execution, or session lifecycle. For UI verification use the native
Windows Qt platform: offscreen mode may show missing glyphs on Windows. Do not assume
that mock tests establish compatibility with a real paid account or relay service.

Keep README and docs/ARCHITECTURE.md current. Build changes with build.ps1 when delivering
a new executable. assets/personas/extensions/data remain external to the bundle so the
user can edit them without recompiling. No embedded arbitrary shell tool.

Packaging cadence: the user decides when to rebuild. Ordinary development changes only
source; do not run a build after every task. Keep Build Sunday Blue.bat as the stable
manual entry point; adjust build.ps1/Spec only when dependencies or packaging need it.
