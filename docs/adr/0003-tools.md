# ADR 3 — Tools

Calendar, email, and the CV store are draft or read tools in `tools/`. `email.draft` and `calendar.propose` set `sent` and `created` to false. `email.send` and `calendar.create` are execute names, not agent tools. Award rates and role templates are in-process lookups that return `source`, `version`, and `summary`.
