![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)
![Release](https://img.shields.io/github/v/release/steveswain14/mcp-json-suppressor)

# JSON Suppressor (MCP)



A standalone MCP server that validates and cleans structured data returned by AI agents. It removes invented fields, coerces incorrect types, and ensures the output matches the expected schema before it enters your pipeline.



This repository contains the full implementation and runs independently. It does not depend on the full suite.



## Usage



Add this server to your MCP client configuration (Claude Desktop, Cursor, Windsurf, or any MCP‑compatible environment):



{

&nbsp; "mcpServers": {

&nbsp;   "json\_suppressor": {

&nbsp;     "command": "python3",

&nbsp;     "args": \["/path/to/mcp-json-suppressor/server.py"]

&nbsp;   }

&nbsp; }

}



## What it does



\- Validates JSON against a schema  

\- Removes hallucinated or extra fields  

\- Coerces simple type errors where possible  

\- Returns cleaned JSON plus a list of violations  



## Relationship to the full suite

This suppressor is also included in the consolidated mcp-hallucination-suite, which bundles all four suppressors and provides a meta-orchestrator:
https://github.com/steveswain14/mcp-hallucination-suite


## Related repositories
- mcp-prompt-suppressor
- mcp-tool-response-suppressor
- mcp-grounding-enforcer



