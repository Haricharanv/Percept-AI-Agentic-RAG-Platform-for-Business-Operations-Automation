# Meeting Action Items — Demo Inputs

These are NOT seed data — they are never automatically ingested into
the KB. They exist purely for manually testing/demoing the Submit
page (vertical = "meeting_action_items"). Each is genuinely new
content, not a copy of anything in `seed_data/`, so retrieval against
it actually proves something.

## demo_1_likely_recurring_match.txt

Describes Alex hitting the deployment pipeline connection timeout
issue again — the same recurring pattern already seeded three times
in `seed_data/meeting_action_items/transcripts/` (transcripts 1, 2,
and 6). Expect:

- Trigger 1: the extracted item should show `is_recurring: true`,
  matched against one of the earlier deploy-pipeline items.
- Priya's item here has no matching action described (just a status
  confirmation), so expect it to correctly extract ZERO items from
  that paragraph — a good check that the extraction prompt doesn't
  invent an action item where none was assigned.

## demo_2_unrelated_new_topic.txt

Two new items (Jamie: conference booth logistics; Morgan: vendor
contract audit) with no relation to anything already seeded. Expect:

- Both items extract cleanly with `is_recurring: false`.
- No existing `owner_activity` will match either — once their
  deadlines pass, Trigger 2 should show `verdict: no_evidence` and
  fire `send_nudge` on first check.
