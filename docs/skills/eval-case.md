# eval-case

**What it does.** Helps write golden eval cases for a spec's criteria and checks each dataset file: unique ids, an `ac`
reference that exists in the specs, non-empty inputs and expectations, and no email addresses, phone numbers or IBANs.

**When to reach for it.** When an AI-track criterion is tested with evals, in the tests-first step.

**Common questions.**
- *It flags an email in my case.* Use an invented domain such as `example.com` or `.invalid`.
- *JSONL or CSV?* Either; one case per line or row.

**It's working if** every eval regression points at a criterion, and the dataset never needs scrubbing.
