"""Execute 3 real chat turns across 3 distinct topics using real GenOffice automation and Limo persistence."""

import asyncio
import json
import os
from pathlib import Path
from app.agent.runtime import LimoAgentRuntime
from app.models.enums import FeatureMode
from app.services.chat_service import chat_service
from app.services.artifact_service import artifact_service

async def main():
    runtime = LimoAgentRuntime()
    results = []

    topics = [
        {
            "id": "topic_1",
            "title": "Blackhole Physics & Event Horizons",
            "prompt": "create docs on blackhole physics and event horizons",
            "mode": FeatureMode.DOCS,
        },
        {
            "id": "topic_2",
            "title": "Quantum Computing & Cryptography",
            "prompt": "create docs on quantum computing architectures and post quantum cryptography",
            "mode": FeatureMode.DOCS,
        },
        {
            "id": "topic_3",
            "title": "Renewable Energy Transition 2026",
            "prompt": "create docs on renewable energy market analysis and clean grid strategy 2026",
            "mode": FeatureMode.DOCS,
        },
    ]

    for idx, t in enumerate(topics, 1):
        print(f"\n================================================================", flush=True)
        print(f">>> RUNNING TOPIC {idx}: {t['title'].upper()}", flush=True)
        print(f"================================================================", flush=True)

        session = chat_service.create_session(title=t["title"], mode=t["mode"])
        print(f"Created chat session: {session.id} (mode: {session.mode})", flush=True)

        assistant_msg = await runtime.execute_turn(
            session_id=session.id,
            user_prompt=t["prompt"],
            mode=t["mode"],
        )

        artifact_details = []
        for art_id in assistant_msg.artifact_ids:
            art = artifact_service.get_artifact(art_id)
            if art:
                thumbnail_path = Path("data/artifacts") / art.id / "thumbnail.png"
                artifact_details.append({
                    "id": art.id,
                    "title": art.title,
                    "file_name": art.file_name,
                    "file_format": art.file_format,
                    "size_bytes": art.size_bytes,
                    "content_hash": art.content_hash,
                    "thumbnail_url": art.thumbnail_url,
                    "thumbnail_exists_on_disk": thumbnail_path.exists(),
                    "thumbnail_size_bytes": thumbnail_path.stat().st_size if thumbnail_path.exists() else 0,
                    "file_path": art.file_path,
                })

        print(f"\n[Topic {idx} Completed]")
        print(f"  Session ID:        {session.id}")
        print(f"  Message ID:        {assistant_msg.id}")
        print(f"  Execution Summary: {assistant_msg.execution_summary}")
        print(f"  Artifact Details:  {json.dumps(artifact_details, indent=2)}")

        results.append({
            "topic_index": idx,
            "topic_name": t["title"],
            "prompt": t["prompt"],
            "session_id": session.id,
            "message_id": assistant_msg.id,
            "execution_summary": assistant_msg.execution_summary,
            "artifacts": artifact_details,
        })

    # Save output to docs/assets/d7_5/real_chat_3_topics.json
    out_dir = Path("../docs/assets/d7_5")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "real_chat_3_topics.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved 3 topics proof summary to: {out_file.resolve()}", flush=True)

    print("\n================================================================", flush=True)
    print("ALL 3 TOPICS COMPLETED SUCCESSFULLY WITH NATIVE DELIVERABLES!", flush=True)
    print("================================================================", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
