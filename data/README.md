# data/ — local test fixtures only

**Data access is ClawBio's job, not ours.** In the workflow, every dataset is pulled live by an
existing ClawBio skill (`gwas-lookup`, `scrna-embedding`, `clinical-trial-finder`, …), which wrap
the real sources (GWAS Catalog, CELLxGENE Census, ClinicalTrials.gov) and are chained by
`bio-orchestrator`. We do **not** ship cached or fabricated results.

This directory holds only **small, real test fixtures** used to validate our one analytic skill
(`celltype-specificity-profiler`) offline — e.g. a real public single-cell slice or scanpy's
built-in `pbmc3k` dataset, standing in for the expression matrix an upstream ClawBio skill hands
over in production. These are real data, never synthetic, and are not required at runtime.
