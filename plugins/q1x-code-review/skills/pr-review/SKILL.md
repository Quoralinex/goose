---
name: pr-review
description: Review pull-request changes for correctness, scope, regressions, repository policy and merge readiness.
---

# Pull Request Review

Review the exact head commit and changed files.

Prioritise:

- correctness and regression risk;
- unintended scope changes;
- missing tests or validation;
- security and permission changes;
- CI, CodeQL and required reviewer status;
- compatibility with repository-specific merge and release rules.

Separate introduced failures from known pre-existing failures. Do not approve or merge merely because checks are noisy; establish whether each required gate is satisfied or legitimately non-blocking under repository policy.
