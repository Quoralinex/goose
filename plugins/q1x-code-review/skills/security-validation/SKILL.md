---
name: security-validation
description: Validate repository changes against security controls, secrets hygiene and automated security checks.
---

# Security Validation

For repository changes:

1. inspect permission, authentication, network and secret-handling changes;
2. ensure credentials are never committed to manifests, registries, generated bundles or logs;
3. preserve required CodeQL, CircleCI or repository-specific security checks;
4. fail closed when production credentials or required authorization are incomplete;
5. avoid exposing local-only MCP or control services to public networks;
6. verify generated configuration cannot grant permissions or authorization by itself.

Security findings must identify the changed path and concrete risk. Infrastructure failures should be distinguished from security defects in the change.
