# Q1X review rollout policy

Enroll repositories that are Quoralinex-produced delivery, application, platform, control-plane, infrastructure, website or governance repositories.

Do not enroll passive upstream forks merely because they are present in the organization. Enroll a fork only where there is concrete evidence that it is an active dependency, implementation surface, controlled mirror or participant in a Quoralinex delivery workflow.

The rollout caller is `.github/workflows/q1x-goose-review.yml` and triggers for pull-request `opened`, `synchronize`, `reopened` and `ready_for_review` events. It passes the exact PR number and head SHA to the reusable workflow in `Quoralinex/goose`.
