---
name: documentation-drafter
description: Draft documentation based on the Taskflow repository structure and implementation.
context: fork
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
argument-hint: [feature-or-file]
---


Draft documentation for the following feature or file: $ARGUMENTS


Instructions:
1. Read the relevant implementation and existing documentation.
2. Use repository evidence to describe the feature accurately.
3. Follow the terminology and style of existing documentation.
4. Save new draft documentation under docs/drafts/.
5. Do not modify application source code.
6. Do not overwrite existing files.
7. If the required information is missing, identify the gap instead
   of inventing implementation details.


Return a summary of the draft and its location.
