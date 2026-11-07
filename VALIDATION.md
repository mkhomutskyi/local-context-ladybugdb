# Validation boundaries

The implementation's private deployment tests and this public package's checks are separate.

The original Windows service passed 12 synthetic lifecycle tests after the broker-readiness fix. The restored native Mac implementation recorded 11 lifecycle passes. Actual Windows Bionic, LM Studio Chat and OpenWebUI conversations executed tools and answered the fictional question. Windows LM Studio and both Mac clients passed owner-performed offline checks. Bionic on the Mac also operated on battery without Wi-Fi, as confirmed by the owner.

No latency ranking, battery-endurance result or general semantic-accuracy score is inferred from these checks. The raw private deployment reports and document library are not published here.

This release preserves the core retrieval and ingestion implementation, adds a native runtime with an explicit extension directory, and adds `run.py` for initialization and repeatable startup. Its checks are added below before the initial public commit. Fresh-machine installation and the public wrapper on the Mac remain separate from the earlier application acceptance tests.

On 7 November 2026, all **18 synthetic release tests passed** in 3.732 seconds on Windows, using the already installed dependencies and native assets. The 12 core tests cover generation integrity, scope/budget limits, evidence, extraction, selective OCR, authenticated HTTP and inference restrictions. Six startup tests cover source/state separation, unavailable models, preserved canonical IDs, rejection of a remote model origin before a request, refusal to replace existing records with a demo, and successful first-run demo initialization followed by a second run that preserves settings and the active generation. Model inference was mocked in these tests.

Starlette emitted a deprecation warning for its HTTPX-backed test client. It did not fail the tests. Clean dependency installation, a fresh-machine run and this release wrapper on macOS have not been claimed as tested.

The code-only repository was rebuilt from a fresh allowlisted staging directory on 7 November 2026 after editorial review. Its 18 tests passed again in 3.835 seconds using existing Windows dependencies and assets. The revised README separates demo and real-library directories, explains that `--check` exits, gives the management asset settings, and distinguishes the native service from the author's Windows Docker deployment. No additional model, platform or battery-performance claim follows from this rebuild.
