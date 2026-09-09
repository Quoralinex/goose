---
name: repository-context
description: Resolve repository context and only the capabilities justified by the current task for Quoralinex/goose.
---

# Quoralinex/goose Repository Context

Profile: code-reviewer
Plugin: q1x-code-review
Default branch: main
Enabled canonical skills: repository-delivery, pr-review, security-validation, goose-review
Required capabilities: github, goose-review
Optional capabilities: remote-machine, systematic-debugging

Use normal ChatGPT as the inference and reasoning runtime. Installed capabilities are not automatic dependencies. Select and activate a capability only when the repository and current task require it. Preserve repository-native CI, security, review, merge and deployment policy. Do not connect this repository directly to Q1X Control Plane.
