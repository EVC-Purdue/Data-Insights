# Report evidence validation

All evidence tokens (ev- followed by letters, digits, underscores or hyphens) in report strings are checked against the analysis evidence registry and, in production, the delivered evidence set. Narrative-only citations are included in the returned evidence array. Unknown or undelivered citations reject the report. Existing structured citation, simulator classification, empty-window and aligned-window checks still apply. The response schema and six-attempt budget are unchanged.

Guidance asks for separate same-window observations, not simultaneity without paired timestamp evidence; use "the window contains...". Coverage claims must stay within delivered signal and interval evidence, explicitly retaining leading command unavailability and its coverage citation. Requested speed remains distinct from applied control. No interpolation or tracking calculations are added.

Offline tests deterministically check citation rejection, evidence inclusion, structured citations and preservation of the [0,30] leading command gap. Prompt guidance does not guarantee semantic correctness or that a model will cite every relevant limitation; those behaviors still require report review. No live model requests are needed for these tests.
