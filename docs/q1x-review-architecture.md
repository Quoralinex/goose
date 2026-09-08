# Q1X review architecture

The active Q1X code-review architecture is deliberately provider-neutral.

1. Pull requests in active Quoralinex delivery repositories trigger a lightweight caller workflow.
2. The caller binds the review request to the exact pull-request head SHA and invokes the reusable workflow in `Quoralinex/goose`.
3. Ordinary ChatGPT chat using GPT-5.6 at High effort is the primary/supervising semantic review surface.
4. Repository-native deterministic and independent assurance remains authoritative where configured, including CircleCI, CodeQL, Semgrep Community Edition, Trivy, Gitleaks, SonarQube Cloud Free, Snyk Free and Codecov Developer.
5. Goose collects and binds the exact-head evidence. It does not select Anthropic, Codex Cloud or any other hosted semantic reviewer implicitly.
6. Any independent semantic model is enabled only through an explicitly approved Q1X reviewer bridge.
7. Passive upstream forks are not enrolled merely because they exist in the Quoralinex organization. A fork is enrolled only when it is an active dependency or delivery surface in a Quoralinex workflow.

## Safety rules

- No Work Chat dependency.
- No Codex Cloud automatic reviewer dependency.
- No Anthropic/Claude dependency.
- No silent fallback model/provider.
- Exact-head binding is mandatory.
- Reviewer/assurance failure must never be represented as approval.
- Repository-specific CI/security controls remain complementary and are not replaced by Goose.
