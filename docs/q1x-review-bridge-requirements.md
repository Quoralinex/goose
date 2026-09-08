# Q1X reviewer bridge requirements

The automatic GitHub caller and Goose reusable workflow may collect exact-head repository evidence automatically. Ordinary Chat is not represented as completed unless a real Ordinary-Chat reviewer invocation has occurred.

A compliant Q1X reviewer bridge must:

- accept repository, PR number and exact head SHA;
- route to Ordinary Chat GPT-5.6 High without consuming Work/Codex review allowance;
- return a structured primary review bound to the exact head;
- expose reviewer identity/surface and evidence digest;
- fail closed on transport/model/provider ambiguity;
- permit CircleCI and the approved free assurance stack to remain independently observable;
- never substitute Codex Cloud, Work Chat or Anthropic/Claude implicitly.
