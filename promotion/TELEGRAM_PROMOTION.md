# External Telegram promotion

This module promotes SpecAvtoPortal in third-party Telegram channels and groups.

## Safety / permission model

- Discovery, scoring, UTM generation and ad-copy preparation are automatic.
- The bot never posts to a third-party channel unless the target is marked `approved` **and** an `approval_record` is stored.
- A third-party channel must also grant the existing SpecAvtoPortal Telegram bot permission to post there.
- Channels that prohibit advertising are marked `blocked`.
- CAPTCHA, spam bypassing, unsolicited user-account mass messaging and impersonation are not used.

## Approval format

When a channel administrator agrees to let the bot post, update its target entry:

```json
{
  "status": "approved",
  "approval_record": "Admin @name approved one site-promo post on 2026-09-24",
  "chat_id": "@channelhandle"
}
```

The scheduled workflow will then publish the prepared tracked ad once and record the Telegram message id.
