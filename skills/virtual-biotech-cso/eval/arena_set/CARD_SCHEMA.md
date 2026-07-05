# Arena hypothesis card — schema

One card per target. The arena's axis-judges read the `per_axis` block: for a pair
(A, B), the judge for each 5R axis compares A's `finding` vs B's `finding` and returns
better/worse/tied/incomparable/insufficient_evidence. `grade` is a coarse hint, the
qualitative `finding` is what the judge weighs.

```json
{
  "target": "BRAF",
  "disease": "melanoma",
  "per_axis": {
    "right_target":    {"finding": "1-2 sentences of qualitative evidence", "grade": "strong|supporting|weak|absent", "provenance": "tool + key numbers"},
    "right_tissue":    {"finding": "...", "grade": "...", "provenance": "..."},
    "right_safety":    {"finding": "...", "grade": "...", "provenance": "..."},
    "right_patient":   {"finding": "...", "grade": "...", "provenance": "..."},
    "right_commercial":{"finding": "...", "grade": "...", "provenance": "..."},
    "tractability":    {"finding": "...", "grade": "...", "provenance": "..."}
  }
}
```

Grades: `strong` = direct, high-confidence evidence; `supporting` = indirect/partial;
`weak` = present but thin; `absent` = no evidence found (honest, not fabricated).
