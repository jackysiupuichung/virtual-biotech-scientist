# data/ — local test fixtures only

**Data access is ToolUniverse's job, not ours.** In the workflow, every dataset is pulled live
through ToolUniverse's MCP tools (Open Targets, CELLxGENE Census, TCGA/GDC, openFDA,
ClinicalTrials.gov), which the scientist divisions call to populate evidence per axis
(see [../docs/DESIGN.md](../docs/DESIGN.md)). We do **not** ship cached or fabricated results.

This directory holds only **small, real test fixtures** used to validate our analytic skills
(e.g. single-cell specificity) offline — for example a real public single-cell slice or scanpy's
built-in `pbmc3k` dataset, standing in for the expression matrix an upstream ToolUniverse tool
hands over in production. These are real data, never synthetic, and are not required at runtime.
