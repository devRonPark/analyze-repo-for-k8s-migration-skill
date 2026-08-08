# Python MCP client templates

Set `ANALYSIS_PIPELINE_PYTHON` to the absolute Python 3.13 executable and
`ANALYSIS_PIPELINE_LAUNCHER` to the absolute installed path of
`runtime/python/launch_mcp.py`. Merge the appropriate JSON template into the
client's project configuration. The launcher intentionally does not use the
analysis target as its working directory.

For OpenCode 1.x, place the local server directly at `mcp.analysis` and set
`enabled` to `true`, as in `opencode-mcp.json`. Do not nest it under
`mcp.servers`; that is a later OpenCode configuration format.

On Windows, pass both environment values with forward slashes (for example,
`C:/Python313/python.exe`). OpenCode expands `{env:...}` before parsing the
JSON template; unescaped Windows backslashes would otherwise make the expanded
configuration invalid. Python accepts these absolute paths unchanged.
