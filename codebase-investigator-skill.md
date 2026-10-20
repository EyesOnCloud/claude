---
name: codebase-investigator
description: Investigate repository architecture, dependencies, defects, and improvement opportunities without modifying files.
context: fork
allowed-tools:
  - Read
  - Glob
  - Grep
argument-hint: [module-or-question]
---


Investigate the Taskflow codebase, focusing on: $ARGUMENTS


If no specific module or question is provided, investigate the overall
repository architecture.


Tasks:
1. Identify relevant files and modules.
2. Trace important dependencies and interactions.
3. Inspect related tests and documentation.
4. Identify potential defects, risks, and improvement opportunities.
5. Support each finding with file paths and available evidence.


Return a structured report containing:
Summary
Findings
Supporting evidence
Potential impact
Recommended next steps
Do not modify files. Base conclusions on repository evidence.
