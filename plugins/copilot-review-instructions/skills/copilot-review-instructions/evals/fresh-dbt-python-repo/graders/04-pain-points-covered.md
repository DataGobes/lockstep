---
type: llm
focus: trace
weight: 1
---

The rules include: source() only in staging models, HTTP only via ingest.client.ApiClient, configuration only via get_settings() (no os.environ), and primary-key unique/not_null tests for new models.
