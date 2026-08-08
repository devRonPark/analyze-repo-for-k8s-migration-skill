# Python MCP client templates

Set `ANALYSIS_PIPELINE_PYTHON` to the absolute Python 3.13 executable and
`ANALYSIS_PIPELINE_LAUNCHER` to the absolute installed path of
`runtime/python/launch_mcp.py`. Merge the appropriate JSON template into the
client's project configuration. The launcher intentionally does not use the
analysis target as its working directory.
