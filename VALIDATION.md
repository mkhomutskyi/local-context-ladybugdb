# Validation boundaries

The implementation's private deployment tests and this public package's checks are separate.

The original Windows service passed 12 synthetic lifecycle tests after the broker-readiness fix. The restored native Mac implementation recorded 11 lifecycle passes. Actual Windows Bionic, LM Studio Chat and OpenWebUI conversations executed tools and answered the fictional question. Windows LM Studio and both Mac clients passed owner-performed offline checks. Bionic on the Mac also operated on battery without Wi-Fi, as confirmed by the owner.

No latency ranking, battery-endurance result or general semantic-accuracy score is inferred from these checks. The raw private deployment reports and document library are not published here.

This release preserves the core retrieval and ingestion implementation, adds a native runtime with an explicit extension directory, and adds `run.py` for initialization and repeatable startup. Its checks are added below before the initial public commit. Fresh-machine installation and the public wrapper on the Mac remain separate from the earlier application acceptance tests.

On 7 November 2026, all **18 synthetic release tests passed** in 3.732 seconds on Windows, using the already installed dependencies and native assets. The 12 core tests cover generation integrity, scope/budget limits, evidence, extraction, selective OCR, authenticated HTTP and inference restrictions. Six startup tests cover source/state separation, unavailable models, preserved canonical IDs, rejection of a remote model origin before a request, refusal to replace existing records with a demo, and successful first-run demo initialization followed by a second run that preserves settings and the active generation. Model inference was mocked in these tests.

Starlette emitted a deprecation warning for its HTTPX-backed test client. It did not fail the tests. Clean dependency installation, a fresh-machine run and this release wrapper on macOS have not been claimed as tested.

The code-only repository was rebuilt from a fresh allowlisted staging directory on 7 November 2026 after editorial review. Its 18 tests passed again in 3.835 seconds using existing Windows dependencies and assets. The revised README separates demo and real-library directories, explains that `--check` exits, gives the management asset settings, and distinguishes the native service from the author's Windows Docker deployment. No additional model, platform or battery-performance claim follows from this rebuild.


## Document manager 0.2.0

On 9 November 2026, the public-source suite passed **40 synthetic tests** on Windows with the installed native assets. These comprise 18 existing library/startup tests, 16 manager lifecycle/access tests and six manager-launcher tests. Model inference is mocked in the automated suite. The local test runner's HTTPX deprecation warning remains non-fatal.

Live desktop manager checks used actual local Gemma, Nomic and GLM-OCR inference with fictional inputs. TXT, native PDF, DOCX and CSV ingestion passed. A scanned PNG waited for OCR review, then became searchable after approval. A source-backed link was accepted. The answer contained the expected dated balance, payment status, missing account number and actual returned source IDs. Authenticated HTTP MCP search, related-document traversal and evidence reads passed. Unauthorized access and a cross-project generation request were denied. Project snapshot, organized-folder export and restore into a new project passed.

The clean public Docker image was built from `python:3.12-slim` and the pinned requirements. This build installed public dependencies during preparation. No private prepared image, model weights or personal build context was used. Runtime tests reused the already prepared native extensions and tokenizer cache.

The public native launcher was then started and stopped on Windows. The public Docker launcher was started, stopped and started again using the same volume. Each run indexed or retained two fictional documents, produced an answer with expected facts and citations, and completed an actual HTTP MCP tool call. The Docker restart retained the documents and profile. These are prepared-host Windows checks, not fresh-machine or macOS acceptance tests. No new owner-performed physical-offline test is attributed to this manager.

The earlier Mac offline observations above remain evidence for the earlier restored service. The new browser manager's deployment on macOS and family access through OpenWebUI have not been verified. Source code, setup instructions and synthetic test fixtures are public; raw private reports and personal documents are not.
