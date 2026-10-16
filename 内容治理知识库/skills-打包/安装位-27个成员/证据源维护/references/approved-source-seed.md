# Approved source seed list

These are starting references for the US-market v0 rule library. They are source candidates, not automatic legal decisions. A designated owner must approve scope, effective date, and the exact rule derived from each source.

## Federal and product context

- `SRC-FTC-ADVERTISING`: [FTC Advertising and Marketing](https://www.ftc.gov/business-guidance/advertising-marketing) — truthfulness, deception, endorsements, health claims.
- `SRC-FTC-HEALTH`: [FTC Health Products Compliance Guidance](https://www.ftc.gov/business-guidance/resources/health-products-compliance-guidance) — health and safety claim substantiation.
- `SRC-FTC-ENDORSEMENT`: [FTC Endorsement Guides](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking) — endorsements, testimonials, material connections, influencer disclosures.
- `SRC-FDA-BREAST-PUMP`: [FDA Breast Pumps](https://www.fda.gov/medical-devices/consumer-products/breast-pumps) — product context; breast pumps are FDA-regulated medical devices.
- `SRC-FDA-CLASSIFICATION`: [FDA Product Classification](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm) — verify device classification and product-code scope.

## Platform policies

- `SRC-AMAZON-IMAGE`: [Amazon product image requirements](https://sellercentral.amazon.com/help/hub/reference/external/G1881?locale=en_us) — image accuracy, text, claims, badges, and product representation.
- `SRC-GOOGLE-MISREPRESENTATION`: [Google Ads misrepresentation](https://support.google.com/adspolicy/answer/6020955?hl=en) — misleading representation, unreliable claims, unavailable offers, and manipulated media.
- `SRC-TIKTOK-ADS`: [TikTok Advertising Policies](https://ads.tiktok.com/help/article/tiktok-advertising-policies-ad-creatives-landing-page?redirected=1) — ad creative, misleading content, dangerous activities, healthcare, IP, and market-specific policy links.

## Required source record fields

For each derived rule, record `source_id`, canonical URL, locator, publisher, jurisdiction, channel, product scope, effective date, review date, snapshot hash, owner, approval status, and the exact internal rule text. Do not cite a search-result page or a model-generated URL.

## Update policy

Recheck platform sources before each release and at least monthly during the pilot. Recheck federal and product sources on a defined legal-owner cadence. Mark superseded sources instead of deleting them so old review records remain reproducible.
