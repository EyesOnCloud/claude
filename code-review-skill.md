---
name: personal-code-review
description: Perform a structured personal code review without modifying files.
context: fork
allowed-tools:
  - Read
  - Glob
  - Grep
argument-hint: [file-or-directory]
---


Review the following code: $ARGUMENTS


Evaluate:
1. Correctness and edge cases.
2. Error handling.
3. Security risks.
4. Maintainability and readability.
5. Test coverage.


For each finding, provide:
Severity
File path and supporting evidence
Explanation of the risk
Recommended remediation
Prioritize actionable findings.
Do not modify files.
