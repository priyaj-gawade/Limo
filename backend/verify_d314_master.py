"""Limo Phase D3.14 — Master Backend Live Verification Script.

Executes the complete 16-step live verification flow over HTTP against
the running FastAPI server and validates real SQLite persistence and disk files.
"""

import hashlib
import sys
import time
from pathlib import Path
import httpx

from app.config import settings
from app.core.ids import generate_artifact_id
from app.db.connection import get_connection
from app.models.enums import JobState
from app.services.job_service import job_service
from app.storage.service import storage_service

BASE_URL = f"http://127.0.0.1:{settings.port}"


def run_master_verification() -> bool:
    print("=" * 70)
    print(" LIMO PHASE D3.14 — FINAL MASTER BACKEND VERIFICATION FLOW")
    print(f" Target Server: {BASE_URL}")
    print(f" Database: {settings.db_path}")
    print(f" Storage Sandbox: {storage_service.base_dir}")
    print("=" * 70)

    steps = {}
    client = httpx.Client(base_url=BASE_URL, timeout=10.0)

    try:
        # Step 1: Start FastAPI backend (already running & accepting connections)
        print("\n[Step 1/16] Checking FastAPI server connectivity...")
        try:
            res = client.get("/api/v1/health")
            if res.status_code == 200:
                print("  [PASS] FastAPI server is live and responsive.")
                steps["Step 1: Server Startup"] = "PASS"
            else:
                print(f"  [FAIL] Server returned unexpected status: {res.status_code}")
                steps["Step 1: Server Startup"] = "FAIL"
                return False
        except Exception as e:
            print(f"  [FAIL] Cannot connect to server at {BASE_URL}: {e}")
            steps["Step 1: Server Startup"] = "FAIL"
            return False

        # Step 2: Verify GET /api/v1/health
        print("\n[Step 2/16] Verifying GET /api/v1/health contract...")
        health_data = res.json()
        req_id = res.headers.get("X-Request-ID")
        assert health_data["status"] == "healthy", "status != healthy"
        assert health_data["app"] == "Limo Backend Engine", "app name mismatch"
        assert health_data["version"] == "0.1.0", "version mismatch"
        assert req_id is not None and req_id.startswith("req_"), f"Invalid X-Request-ID: {req_id}"
        print(f"  [PASS] Health check OK. (app: '{health_data['app']}', X-Request-ID: '{req_id}')")
        steps["Step 2: Health Contract"] = "PASS"

        # Step 3: Create a real Project
        print("\n[Step 3/16] Creating real Project via POST /api/v1/projects...")
        proj_res = client.post("/api/v1/projects", json={
            "name": "D3.14 Master Verification Workspace",
            "description": "Validation environment for full Phase D3 verification flow.",
            "metadata": {"test_run": "D3.14"}
        })
        assert proj_res.status_code == 201, f"Expected 201, got {proj_res.status_code}: {proj_res.text}"
        proj_data = proj_res.json()
        proj_id = proj_data["id"]
        assert proj_id.startswith("proj_"), f"Invalid project ID: {proj_id}"
        print(f"  [PASS] Project created successfully. (id: {proj_id}, name: '{proj_data['name']}')")
        steps["Step 3: Create Project"] = "PASS"

        # Step 4: Upload/register a real Source
        print("\n[Step 4/16] Registering real Source via POST /api/v1/sources/text...")
        sample_text = "Q3 National Infrastructure Telemetry Audit. Zero security anomalies detected across regional feeders."
        sample_hash = hashlib.sha256(sample_text.encode("utf-8")).hexdigest().lower()
        src_res = client.post("/api/v1/sources/text", json={
            "name": "telemetry_audit.txt",
            "text": sample_text,
            "project_id": proj_id,
            "metadata": {"origin": "d314_probe"}
        })
        assert src_res.status_code == 201, f"Expected 201, got {src_res.status_code}: {src_res.text}"
        src_data = src_res.json()
        src_id = src_data["id"]
        assert src_id.startswith("src_"), f"Invalid source ID: {src_id}"
        print(f"  [PASS] Source registered. (id: {src_id}, size: {src_data['size_bytes']} bytes)")
        steps["Step 4: Register Source"] = "PASS"

        # Step 5: Verify the stored source and SHA-256
        print("\n[Step 5/16] Verifying Source retrieval and physical SHA-256 digest...")
        get_src_res = client.get(f"/api/v1/sources/{src_id}")
        assert get_src_res.status_code == 200, f"Expected 200, got {get_src_res.status_code}"
        retrieved_src = get_src_res.json()
        assert retrieved_src["content_hash"] == sample_hash, f"Hash mismatch: {retrieved_src['content_hash']} vs {sample_hash}"

        # Download content and verify binary bytes
        dl_res = client.get(f"/api/v1/sources/{src_id}/download")
        assert dl_res.status_code == 200, f"Expected 200, got {dl_res.status_code}"
        assert dl_res.text == sample_text, "Downloaded text does not match ingested text"
        print(f"  [PASS] Source content and SHA-256 verified. (hash: {sample_hash[:16]}...)")
        steps["Step 5: Verify Source & Hash"] = "PASS"

        # Step 6: Create a real Chat session
        print("\n[Step 6/16] Creating real Chat session via POST /api/v1/chats...")
        chat_res = client.post("/api/v1/chats", json={
            "title": "D3.14 Synthesis Thread",
            "project_id": proj_id,
            "mode": "docs"
        })
        assert chat_res.status_code == 201, f"Expected 201, got {chat_res.status_code}: {chat_res.text}"
        chat_data = chat_res.json()
        chat_id = chat_data["id"]
        assert chat_id.startswith("chat_"), f"Invalid chat ID: {chat_id}"
        print(f"  [PASS] Chat session created. (id: {chat_id}, mode: '{chat_data['mode']}')")
        steps["Step 6: Create Chat Session"] = "PASS"

        # Step 7: Add a user message and assistant message
        print("\n[Step 7/16] Appending user message and assistant response...")
        msg1_res = client.post(f"/api/v1/chats/{chat_id}/messages", json={
            "role": "user",
            "content": "Synthesize the quarterly telemetry findings into an executive report.",
            "mode": "docs"
        })
        assert msg1_res.status_code == 201, f"Expected 201, got {msg1_res.status_code}"
        msg1_id = msg1_res.json()["id"]

        time.sleep(0.01)  # Ensure distinct timestamp for ordering

        msg2_res = client.post(f"/api/v1/chats/{chat_id}/messages", json={
            "role": "assistant",
            "content": "I have reviewed all telemetry feeds. Zero critical vulnerabilities were detected.",
            "mode": "docs"
        })
        assert msg2_res.status_code == 201, f"Expected 201, got {msg2_res.status_code}"
        msg2_id = msg2_res.json()["id"]
        print(f"  [PASS] User message ({msg1_id}) and assistant message ({msg2_id}) appended.")
        steps["Step 7: Add Messages"] = "PASS"

        # Step 8: Retrieve the chat history and verify ordering
        print("\n[Step 8/16] Retrieving chat history and verifying chronological ordering...")
        hist_res = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert hist_res.status_code == 200, f"Expected 200, got {hist_res.status_code}"
        messages = hist_res.json()
        assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"
        assert messages[0]["id"] == msg1_id and messages[0]["role"] == "user"
        assert messages[1]["id"] == msg2_id and messages[1]["role"] == "assistant"
        assert messages[0]["created_at"] <= messages[1]["created_at"], "Message order violated"
        print("  [PASS] Chat history ordering verified (user -> assistant).")
        steps["Step 8: Verify Message Ordering"] = "PASS"

        # Step 9: Create a real TransformationJob contract
        print("\n[Step 9/16] Enqueuing TransformationJob contract via POST /api/v1/transform...")
        job_res = client.post("/api/v1/transform", json={
            "requested_formats": ["presentation", "summary"],
            "source_ids": [src_id],
            "prompt": "Synthesize a 10-slide executive presentation and concise summary",
            "project_id": proj_id,
            "session_id": chat_id,
            "configuration": {
                "audience": "Board of Directors",
                "tone": "Executive",
                "presentation": {
                    "slide_count": 10,
                    "theme": "corporate_dark"
                }
            }
        })
        assert job_res.status_code == 201, f"Expected 201, got {job_res.status_code}: {job_res.text}"
        job_data = job_res.json()
        job_id = job_data["id"]
        assert job_id.startswith("job_"), f"Invalid job ID: {job_id}"
        assert job_data["state"] == "queued"
        assert job_data["progress"] == 0.0
        assert job_data["source_ids"] == [src_id]
        assert job_data["prompt"] == "Synthesize a 10-slide executive presentation and concise summary"
        assert job_data["artifact_ids"] == [], "Non-empty artifact_ids (zero fake deliverables rule violated)"
        print(f"  [PASS] Transformation contract queued. (id: {job_id}, state: '{job_data['state']}')")
        steps["Step 9: Create Transformation Contract"] = "PASS"

        # Step 10: Update/read its stored state
        print("\n[Step 10/16] Updating job execution state to 'processing' and reading back...")
        updated_job = job_service.update_progress(
            job_id=job_id,
            state=JobState.PROCESSING,
            progress=0.45,
            current_stage="Canonical Synthesis Ingestion",
        )
        assert updated_job.state.value == "processing"
        assert updated_job.progress == 0.45

        get_job_res = client.get(f"/api/v1/transform/{job_id}")
        assert get_job_res.status_code == 200, f"Expected 200, got {get_job_res.status_code}"
        live_job = get_job_res.json()
        assert live_job["state"] == "processing"
        assert live_job["progress"] == 0.45
        assert live_job["current_stage"] == "Canonical Synthesis Ingestion"
        print(f"  [PASS] Job state updated and verified via REST contract. (progress: {live_job['progress']})")
        steps["Step 10: Update & Read Job State"] = "PASS"

        # Step 11: Create a real test artifact file inside the approved storage boundary
        print("\n[Step 11/16] Creating real test deliverable file in sandboxed storage...")
        real_artifact_bytes = b"PK\x03\x04Real PowerPoint Presentation Binary Stream Deliverable for Limo D3.14"
        expected_art_hash = hashlib.sha256(real_artifact_bytes).hexdigest().lower()
        temp_art_id = generate_artifact_id()
        storage_ref, size_bytes, computed_hash = storage_service.save_artifact_file(
            artifact_id=temp_art_id,
            filename="board_presentation.pptx",
            content=real_artifact_bytes,
        )
        assert storage_service.file_exists(storage_ref), f"Physical file missing at {storage_ref}"
        assert computed_hash == expected_art_hash, "Storage hash mismatch"
        print(f"  [PASS] Deliverable file saved to disk. (ref: '{storage_ref}', size: {size_bytes} bytes)")
        steps["Step 11: Create Storage Artifact"] = "PASS"

        # Step 12: Register the artifact
        print("\n[Step 12/16] Registering Deliverable Artifact via POST /api/v1/artifacts...")
        art_res = client.post("/api/v1/artifacts", json={
            "job_id": job_id,
            "project_id": proj_id,
            "title": "Board Executive Presentation",
            "artifact_type": "slide",
            "file_format": ".pptx",
            "storage_ref": storage_ref,
        })
        assert art_res.status_code == 201, f"Expected 201, got {art_res.status_code}: {art_res.text}"
        art_data = art_res.json()
        art_id = art_data["id"]
        assert art_id.startswith("art_"), f"Invalid artifact ID: {art_id}"
        assert art_data["content_hash"] == expected_art_hash
        assert art_data["version"] == 1
        assert art_data["size_bytes"] == len(real_artifact_bytes)
        print(f"  [PASS] Artifact registered with disk validation. (id: {art_id}, hash: {expected_art_hash[:16]}...)")
        steps["Step 12: Register Artifact"] = "PASS"

        # Step 13: Retrieve the artifact metadata
        print("\n[Step 13/16] Fetching artifact metadata via GET /api/v1/artifacts/{id}...")
        get_art_res = client.get(f"/api/v1/artifacts/{art_id}")
        assert get_art_res.status_code == 200, f"Expected 200, got {get_art_res.status_code}"
        meta = get_art_res.json()
        assert meta["id"] == art_id
        assert meta["title"] == "Board Executive Presentation"
        assert meta["project_id"] == proj_id
        assert meta["job_id"] == job_id
        print(f"  [PASS] Artifact metadata verified. (title: '{meta['title']}', type: '{meta['artifact_type']}')")
        steps["Step 13: Retrieve Artifact Metadata"] = "PASS"

        # Step 14: Download/read the artifact and verify its bytes/hash
        print("\n[Step 14/16] Downloading artifact payload via GET /api/v1/artifacts/{id}/download...")
        dl_art_res = client.get(f"/api/v1/artifacts/{art_id}/download")
        assert dl_art_res.status_code == 200, f"Expected 200, got {dl_art_res.status_code}"
        downloaded_bytes = dl_art_res.content
        assert downloaded_bytes == real_artifact_bytes, "Downloaded artifact bytes mismatch disk content"
        downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest().lower()
        assert downloaded_hash == expected_art_hash, "Downloaded SHA-256 mismatch"
        print(f"  [PASS] Artifact payload verified byte-for-byte. ({len(downloaded_bytes)} bytes, SHA-256 match)")
        steps["Step 14: Download & Verify Bytes"] = "PASS"

        # Step 15: Verify all records persist correctly in SQLite
        print("\n[Step 15/16] Directly querying SQLite database tables for persistence integrity...")
        with get_connection() as conn:
            proj_count = conn.execute("SELECT COUNT(*) FROM projects WHERE id = ?", (proj_id,)).fetchone()[0]
            src_count = conn.execute("SELECT COUNT(*) FROM sources WHERE id = ?", (src_id,)).fetchone()[0]
            chat_count = conn.execute("SELECT COUNT(*) FROM chats WHERE id = ?", (chat_id,)).fetchone()[0]
            msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (chat_id,)).fetchone()[0]
            job_count = conn.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
            art_count = conn.execute("SELECT COUNT(*) FROM artifacts WHERE id = ?", (art_id,)).fetchone()[0]

            assert proj_count == 1, f"Project not found in SQLite (count: {proj_count})"
            assert src_count == 1, f"Source not found in SQLite (count: {src_count})"
            assert chat_count == 1, f"Chat not found in SQLite (count: {chat_count})"
            assert msg_count == 2, f"Messages not found in SQLite (count: {msg_count})"
            assert job_count == 1, f"Job not found in SQLite (count: {job_count})"
            assert art_count == 1, f"Artifact not found in SQLite (count: {art_count})"

        print(f"  [PASS] SQLite persistence verified across all 6 entity tables.")
        print(f"         projects=1, sources=1, chats=1, messages=2, jobs=1, artifacts=1")
        steps["Step 15: SQLite Persistence Integrity"] = "PASS"

        # Step 16: Clean up only the temporary verification data
        print("\n[Step 16/16] Cleaning up temporary verification data...")
        # 1. Delete physical deliverable file and artifact row
        storage_service.delete_file(storage_ref)
        assert not storage_service.file_exists(storage_ref), "Physical artifact file not cleaned up"
        with get_connection() as conn:
            conn.execute("DELETE FROM artifacts WHERE id = ?", (art_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

        # 2. Delete source & physical source file via REST API
        del_src_res = client.delete(f"/api/v1/sources/{src_id}")
        assert del_src_res.status_code == 204, f"Failed deleting source: {del_src_res.status_code}"

        # 3. Delete chat session (cascades to messages) via REST API
        del_chat_res = client.delete(f"/api/v1/chats/{chat_id}")
        assert del_chat_res.status_code == 204, f"Failed deleting chat: {del_chat_res.status_code}"

        # 4. Delete project via REST API
        del_proj_res = client.delete(f"/api/v1/projects/{proj_id}")
        assert del_proj_res.status_code == 204, f"Failed deleting project: {del_proj_res.status_code}"

        # 5. Confirm 404 on deleted project
        confirm_404 = client.get(f"/api/v1/projects/{proj_id}")
        assert confirm_404.status_code == 404, "Project still accessible after deletion"
        assert confirm_404.json()["error"]["code"] == "ENTITY_NOT_FOUND"

        print("  [PASS] Temporary verification project, source, chat, job, and artifact cleaned up.")
        steps["Step 16: Clean Up Verification Data"] = "PASS"

        # Summary
        print("\n" + "=" * 70)
        print(" MASTER BACKEND VERIFICATION REPORT")
        print("=" * 70)
        for step_name, status in steps.items():
            print(f"  {step_name:<45} [{status}]")
        print("=" * 70)
        print(" ALL 16 REAL BACKEND VERIFICATION STEPS PASSED WITH 100% SUCCESS.")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n[FAIL] Verification error encountered: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()


if __name__ == "__main__":
    success = run_master_verification()
    sys.exit(0 if success else 1)
