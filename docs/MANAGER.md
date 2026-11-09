# Local document manager

Choose a project, add files, review uncertain information and ask a question. Each project has its own preserved originals and LadybugDB generations. The manager adds a browser workflow to the existing context service.

## Prepare once

Use Python 3.12 and an isolated environment. Install `requirements.txt`. Start LM Studio's local server and inspect its installed inventory. Keep the exact model IDs it returns. No launcher downloads or renames model weights.

Prepare the Ladybug **0.22.1** vector and FTS extension binaries for the execution platform. Native Windows needs Windows binaries; a Docker Linux container needs Linux binaries, even on a Windows host. Put the files in a private asset directory, either directly or under `vector/` and `fts/`. The application uses `LOAD`, not automatic `INSTALL`.

Prepare tiktoken's `cl100k_base` cache during online setup. Its expected cache file is `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` and its SHA-256 is `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`. The application checks the file before using it. If the cache is missing or different, it stops instead of downloading it.

The tested profile uses Nomic Embed Text v1.5 with 768 dimensions and query/document prefixes. This version is not an adapter for arbitrary embedding models. The answer model can use another installed canonical ID, but that model's tool/answer quality needs its own check. Scans use the configured GLM-OCR recipe. If its model is unavailable, the original is retained and processing needs attention.

## Native startup

First run, replacing every placeholder with your local values:

```text
python manager.py --home /PRIVATE/MANAGER --extensions /LOCAL/NATIVE/EXTENSIONS --token-cache /LOCAL/TOKEN/CACHE --chat-model CANONICAL_CHAT_ID --embedding-model CANONICAL_NOMIC_ID --ocr-model CANONICAL_GLM_OCR_ID --model-origin http://127.0.0.1:1235
```

On Windows, use quoted absolute Windows paths. Keep `--home` outside this checkout. It contains private documents, credentials and logs; never commit it.

Open `http://127.0.0.1:8791`. Read the access code from `PRIVATE_MANAGER/control/owner-code.txt`. The token is not printed. Ctrl+C stops the three owned processes and preserves state. Ports 8791 and 8792 must be free; the launcher never stops another service to claim them.

Later runs reuse the profile:

```text
python manager.py --home /PRIVATE/MANAGER --extensions /LOCAL/NATIVE/EXTENSIONS --token-cache /LOCAL/TOKEN/CACHE
```

Add `--check` to verify the local prerequisites and saved profile without starting servers. A conflicting model ID or endpoint is rejected. To change the profile, make a deliberate private configuration change and rebuild embeddings when required; do not create aliases to label experiments.

## Docker startup

Docker Desktop must already be running. The host still uses Python for the restricted inference bridge. Docker workers cannot call the host's loopback directly, so they exchange bounded inference requests through a private file queue. The host bridge accepts only the configured local model endpoint and routes.

Pull the proxy image during online preparation:

```text
docker pull nginxinc/nginx-unprivileged:stable-alpine
```

Then start the full stack. Use **Linux** extension assets here:

```text
python manager.py --deployment docker --build --home /PRIVATE/DOCKER-MANAGER --extensions /LOCAL/LINUX/EXTENSIONS --token-cache /LOCAL/TOKEN/CACHE --chat-model CANONICAL_CHAT_ID --embedding-model CANONICAL_NOMIC_ID --ocr-model CANONICAL_GLM_OCR_ID --model-origin http://127.0.0.1:1235
```

`--build` creates the image from the repository's source allowlist and pinned public dependencies. This preparation step needs Internet access. The Docker build context excludes runtime state and documents. On later starts, omit `--build` and the saved model arguments. The same image serves API, worker and reader roles. No private prepared image is required.

The launcher creates a named data volume derived from the private home path. It prints that volume's name, not its contents. The volume survives shutdown and container recreation. The host home holds the profile, inference bridge, access-code copy and private startup logs. The Docker volume holds the actual project catalog and documents. Do not alternate native and Docker deployments using one home path; use separate private homes.

The worker has `network_mode: none`. API and reader use an internal network. Only the proxy publishes ports, on `127.0.0.1`. The reader mounts project state read-only. Roles run without root, with dropped capabilities and a read-only root filesystem. The one-time root initialization changes ownership only on the new dedicated volume root. It does not traverse host directories.

Ctrl+C stops this stack and its host broker. A failed startup also attempts to stop only its own stack. Volumes and originals are retained. No volume-deletion command is part of normal shutdown. Keep LM Studio running while the manager processes files or answers questions.

## Use the fictional check

1. Create a project called House Orchid.
2. Upload `examples/orchid-statement.txt` and `examples/orchid-receipt.txt`.
3. Open Needs attention. Inspect and approve the suggested statement-to-receipt relationship.
4. Ask: **What is the balance, as of what date, and was payment received or overdue? Is a bank account number provided?**
5. Expect **127 dollars as of 6 November 2026; payment received on 5 November, not overdue; no bank account number provided**. Check the actual returned chunk IDs.

Scans and uncertain classifications wait for review before indexing. The library view can change folders, inspect originals and links, update a document or withdraw it from active retrieval. Withdrawal preserves its original and history. Organized-folder export creates readable copies with a checksum manifest.

## MCP and chat clients

Connect chat copies the project's Streamable HTTP endpoint and Bearer token. The endpoint is `http://127.0.0.1:8792/projects/PROJECT_ID/mcp`. The token authorizes that project only. It is not the owner's browser access code. Never publish either credential.

The five read-only tools are `search_context`, `related_documents`, `get_evidence`, `related_topics` and `library_status`. Search returns a generation ID. Pass it to subsequent relationship and evidence calls to keep the conversation on the same document versions. An omitted generation uses the current active one.

Bionic or LM Studio Chat must execute MCP calls, with the answer model configured separately. This endpoint uses HTTP, not a stdio subprocess. Configure a compatible client's URL and `Authorization: Bearer PROJECT_TOKEN` header; the surrounding client-settings format may differ.

A containerized OpenWebUI cannot reach this endpoint through its own `127.0.0.1`. It needs an intentionally configured route, matching Host/Origin policy and project token. Existing client installations are not silently rebound by the launcher. Family user accounts and LAN sharing are outside this owner-only release. A cloud-model client can transmit retrieved evidence elsewhere: keep private questions on local models and disable unrelated cloud/web tools.

## Travel and backups

Export a project snapshot, then restore it into an empty project using the same embedding profile. It includes originals, prepared text, vectors, links and manifests. Model weights and credentials are excluded. Restore checks hashes and rebuilds a native generation; it does not open an untrusted database binary from the ZIP.

Snapshots and folder exports contain the document contents. They are not encrypted by this application. Protect the account, disk and backup media. A snapshot on the same disk is not an independent backup. Test the restored project with the network disconnected before relying on it during travel.

The manager retains uploaded staging files, derivatives, failed attempts and old generations. Vault objects deduplicate identical input bytes within a project; history and exports still consume space. Automatic retention cleanup is not included.

## Verification and limits

See [VALIDATION.md](../VALIDATION.md) for the distinction between earlier desktop/Mac client checks, this manager's tests and the public launcher checks. The new manager's macOS deployment has not been verified. The earlier Mac offline result does not establish that this new package is tested there.

Search uses exact vector similarity, literal term scoring and approved links. It is not an ANN performance benchmark, full ontology or a replacement for checking an answer. Most requests select up to 2,000 approximate evidence tokens and eight chunks; those estimates use a different tokenizer from Gemma.

Jobs support retry, cancellation and lease recovery. Cancellation is checked between stages, so an in-flight model request may finish first. Failed builds leave the active generation intact. Long-term retention, multi-user permissions, folder watching, automatic cross-project moves and general entity extraction remain future work.
