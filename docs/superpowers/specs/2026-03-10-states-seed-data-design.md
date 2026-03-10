# States Seed Data Design

**Issue:** #4 — [M1] Seed data: states.json (all 50 states)
**Date:** 2026-03-10

## Scope

Populate `src/tdc_auction_calendar/db/seed/states.json` with statutory auction metadata for US states that have tax lien, deed, or hybrid sales. States without tax sale processes are omitted entirely.

## Decisions

- **`typical_months` as `list[int]`** — integers (1-12) not month name strings. Avoids locale/typo issues, sortable, human-readable formatting done downstream.
- **Omit non-auction states** — states without tax lien/deed/hybrid auctions are excluded. If a state changes its laws, we add it later.
- **No model changes** — existing `StateRules` Pydantic model and `StateRulesRow` ORM model already match the required schema.

## JSON Entry Structure

```json
{
  "state": "FL",
  "sale_type": "lien",
  "statutory_timing_description": "Counties hold annual tax certificate sales starting June 1",
  "typical_months": [6],
  "notice_requirement_weeks": 4,
  "redemption_period_months": 24,
  "public_notice_url": null,
  "state_agency_url": null,
  "governing_statute": "Fla. Stat. § 197"
}
```

### Field Notes

- `sale_type`: one of `lien`, `deed`, `hybrid` (existing `SaleType` enum)
- `typical_months`: integer months when auctions typically occur
- `redemption_period_months`: null for deed states (no redemption period)
- `public_notice_url` / `state_agency_url`: populated where known, null otherwise
- `governing_statute`: reference to relevant state statute chapter/title

## Validation

Test that loads `states.json` and asserts:
- Each entry passes `StateRules` Pydantic validation
- Required fields non-null: `state`, `sale_type`, `governing_statute`, `typical_months`, `notice_requirement_weeks`, `statutory_timing_description`
- No duplicate state codes
- All `sale_type` values are valid enum members

## Spot-Check

Web search verification for FL, TX, CA, CO, IL, NJ against primary sources — checking `sale_type`, `redemption_period_months`, and `governing_statute`.

## Approach

1. Compile data from training knowledge for all applicable states
2. Web-search spot-check the 6 required states
3. Write validation test
4. Create `states.json`
5. Run validation, fix any issues
