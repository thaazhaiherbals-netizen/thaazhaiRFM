# Orders and customer support usability

- Orders accept inclusive from/to dates alongside search. Sorting and pagination retain the range; invalid ranges show an error and empty results have guidance.
- Support figures appear on the executive dashboard and customer screen. They cover all customers and team members, independent of list filters, using Asia/Kolkata calendar days.
- People contacted counts distinct customers with a result other than no answer today. Positive/negative counts are conversation records with that sentiment today. Scheduled counts customers whose latest record schedules a follow-up today, excluding do-not-contact customers and superseded schedules.
- The green Customer follow-up button opens a native modal dialog with customer context and a flat purchase list alongside the form. Selecting an order displays its products, quantities, unit prices, line totals, payment and location inside the same dialog. Loading failures offer a retry, and switching orders cancels stale requests without resetting feedback entries. Small screens put the form first. Escape/Close checks for unsaved edits; focus is contained by the native dialog. Saving refreshes the support figures.
- Customer overview, Log a follow-up and Follow-up history are separate blue, green and purple cards. Purchase history has its own teal card. The entry form has three numbered, colored fieldsets: Contact details, Customer feedback and Next action. Labels and headings distinguish the sections without relying on color alone.
- Shared small text is raised to 14px, key controls and table text to 16px, with larger control targets and visible keyboard focus.

Validation: production Next.js build, TypeScript, 11 authorization tests, production HTTP smoke for admin/viewer/support, and 8 PostgreSQL operations tests. Regression coverage includes inclusive dates, search/pagination, invalid dates, distinct contacts, sentiment totals, India midnight, and replaced schedules.

Limitations: browser visual inspection was blocked because the desktop browser automation sandbox failed to start. Review desktop/mobile layout and modal keyboard interaction before release. Backend and web changes must be released together; no schema migration is needed. Delivery remains feature PR to develop, followed by develop to main for production.
