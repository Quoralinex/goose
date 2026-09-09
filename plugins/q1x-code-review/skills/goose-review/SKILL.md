---
name: goose-review
description: Apply the Q1X Goose code-review role as an independent repository review gate.
---

# Goose Review

Use Goose as an independent code-review/security signal for repositories enrolled with the `code-reviewer` profile or where repository policy requires it.

- review the exact PR head;
- keep reviewer effort at the configured repository level;
- report concrete findings separately from workflow/infrastructure failures;
- do not treat a failed reviewer transport or API invocation as a code defect;
- rerun a transient reviewer job when repository policy permits;
- preserve independence between implementation and review.

Goose review does not supersede mandatory CI/CodeQL/security gates or the target repository's own merge/release policy. It has no Q1X Control Plane dependency.
