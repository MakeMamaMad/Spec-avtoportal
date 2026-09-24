# Promotion Core

PR #81 introduces an additive planning layer for future promotion unification.

## Scope

- shared campaign registry;
- common promotion action/event models;
- deterministic UTM builder;
- channel-agnostic planner;
- planning-only job that can build frontend/data/promotion/action_queue.json.

## Compatibility

This PR intentionally does not replace or modify the existing catalog,
Telegram outreach, Telegram Ads, VK, or other publishing workflows.

promotion/jobs/plan.py is planning-only. Later PRs can migrate existing
executors to consume this queue after their behaviour is covered by tests.
