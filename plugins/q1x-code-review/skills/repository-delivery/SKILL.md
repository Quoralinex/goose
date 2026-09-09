---
name: repository-delivery
description: Deliver repository changes through a branch, validation, pull request and repository-policy merge sequence.
---

# Repository Delivery

Use a branch-based delivery flow unless the target repository explicitly defines another approved workflow.

## Sequence

1. confirm the target repository and baseline commit;
2. create or reuse the approved delivery branch;
3. implement only the required scope;
4. run repository-native validation and tests;
5. preserve CI, CodeQL, security and reviewer checks;
6. open or update the rollout pull request with an exact scope summary;
7. inspect failures and distinguish introduced regressions from pre-existing blockers;
8. merge only when required checks and the repository's own policy permit it;
9. verify the merged default branch and post-merge checks.

Do not silently bypass failing gates, rewrite unrelated code, or stop solely because no user action is required.
