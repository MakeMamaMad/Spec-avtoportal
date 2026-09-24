# External promotion automation

This module is intentionally separate from the existing owned Telegram/VK publishers.

## What it automates

- reads the latest materials from `frontend/data/news.json`;
- selects a relevant article for each external community;
- creates a target-specific UTM link;
- creates a short post draft;
- creates an admin outreach message;
- writes the ready-to-review queue to `frontend/data/promotion_queue.json`;
- excludes targets whose rules prohibit advertising.

## Safety / anti-spam rule

No third-party community is auto-posted to unless its configuration is explicitly changed to an approved integration. Candidate groups that require admin approval stay in `ready_for_review`.

Do not add user-account automation that bypasses group rules or platform restrictions.

## Target statuses

- `candidate` + `approval_required`: contact admin first;
- `candidate` + `manual_review`: verify rules before posting;
- `do_not_post`: never generate a placement;
- future `approved`: may be connected to an official API/webhook if the community grants permission.


## Industry editorial placement

The active editorial-placement workflow uses original SpecAvtoPortal knowledge-base
articles rather than republishing scraped third-party news.

Default mode is hands-off automation:
- only targets with a proven automatic adapter are selected;
- MEXZONA is currently the enabled automatic publisher;
- one target is not used more often than once every 7 days;
- existing legacy MEXZONA history is counted toward that cooldown;
- CAPTCHA, login failure, or a broken external form becomes a manual fallback
  instead of repeated automatic retries;
- manual-only publisher preparation can be enabled explicitly with
  `EDITORIAL_PREPARE_MANUAL=1`.

The daily manual-outreach digest remains the fallback path for actions that
cannot be completed safely by automation.
