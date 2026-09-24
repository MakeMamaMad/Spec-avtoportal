# Telegram Ads always-on strategy

Goal: buy relevant Telegram reach, acquire subscribers to @specavtoportal, and let the existing automated channel publishing convert that audience into site visits.

## Funnel

Telegram Ads -> @specavtoportal landing post -> regular channel content -> spec-avtoportal.ru

The landing post contains a Yandex Metrika tagged site link using:
- utm_source=telegram_ads
- utm_medium=paid_social
- utm_campaign=telegram_ads_always_on

## Why one ad per target channel

Telegram Ads reports views and channel joins for each ad. Keeping one target channel per ad gives channel-level performance without needing to guess which placement worked.

## Targeting

Only verified public channels with 1000+ subscribers are included in the first wave:
- @truckers_club
- @Cargonomica
- @truksandall
- @reiszr
- @tehnika_info
- @LogisticAggregator

Groups/chats are excluded from the Telegram Ads package even if they are useful for direct placements.

## Budget model

The package starts at the official minimum CPM of 0.1 TON. The per-ad Maximum Budget and CPM ceiling are intentionally left unset until the owner chooses a spend cap.

For the requested "only replenish balance" operating mode:
1. Create the six ads once.
2. Set a sufficiently high Maximum Budget for each ad, but only after choosing an acceptable spend ceiling.
3. Keep actual cash control at the account balance level.
4. Replenish the Telegram Ads balance when desired.

Telegram serves an ad only while both the account balance and the ad's Maximum Budget allow it.

## Automation boundary

Telegram's public documentation exposes the Ad Platform web interface but no documented advertiser API for creating/managing campaigns. We do not scrape authenticated Telegram Ads sessions or store login cookies in GitHub.

The repository automatically maintains the destination landing post, validated ad texts, target list, UTM attribution and setup package. Initial ad creation and funding remain in Telegram Ads.
