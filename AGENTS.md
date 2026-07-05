# Project Collaboration Instructions

The user is developing this project both to build the software and to learn the
relevant engineering knowledge.

For every implementation step:

- Explain what is being changed and why it is needed.
- Explain the relevant technical concepts in accessible language.
- Point out meaningful alternatives and trade-offs when they affect the design.
- Mention common mistakes or risks that are useful for learning.
- Work in small steps and obtain the user's opinion before moving to the next
  implementation step.
- After verification succeeds on an isolated feature branch, treat committing
  and pushing that branch as one step. Request separate confirmation for work
  that affects `main`, merges branches, deletes branches, or performs another
  high-impact repository operation.

## High-token capabilities

- Do not use potentially high-token capabilities without the user's explicit
  permission for that specific use.
- This includes OCR or image-text recognition, visual webpage analysis,
  browser-driven frontend inspection or interaction, repeated real-LLM calls,
  and similar token-intensive tools.
- Prefer local automated tests, builds, structured API responses, and direct
  text/code inspection when they can verify the same behavior.
- Before requesting permission, explain why the high-token capability is
  necessary and give a lower-cost alternative when one exists.
