"""Limo CLI: Diagnostic and verification tool for developers and AI coding agents (Rule 12)."""

import argparse
import sys
from typing import NoReturn

from .config import settings
from .db.connection import get_connection
from .storage.service import storage_service


def check_health() -> bool:
    """Diagnose backend SQLite and sandboxed storage health."""
    print(f"=== Limo Backend Health Diagnostic (env: {settings.environment}) ===")
    all_ok = True

    # 1. Database Check
    try:
        with get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"[OK] SQLite DB Connection: {settings.db_path} ({len(tables)} tables found)")
            expected_tables = {
                "projects", "sources", "chats", "messages", "jobs",
                "canonical_contents", "artifacts", "artifact_versions",
                "validation_results", "provenance"
            }
            missing = expected_tables - set(tables)
            if missing:
                print(f"[WARN] Missing expected tables: {missing}")
                all_ok = False
            else:
                print("[OK] Schema Integrity: All 10 expected core tables present")
    except Exception as e:
        print(f"[FAIL] Database check error: {e}")
        all_ok = False

    # 2. Storage Sandbox Check
    try:
        storage_service.ensure_directories()
        base_dir = storage_service.base_dir
        if base_dir.exists() and base_dir.is_dir():
            print(f"[OK] Sandboxed Storage Base: {base_dir}")
        else:
            print(f"[FAIL] Storage directory missing: {base_dir}")
            all_ok = False

        for sub in ("sources", "artifacts", "temp"):
            sub_path = base_dir / sub
            if sub_path.exists():
                print(f"[OK] Storage Subdirectory: {sub}/")
            else:
                print(f"[FAIL] Missing subdirectory: {sub}/")
                all_ok = False
    except Exception as e:
        print(f"[FAIL] Storage check error: {e}")
        all_ok = False

    if all_ok:
        print("\nAll diagnostic health checks PASSED.")
    else:
        print("\nOne or more diagnostic checks FAILED.")
    return all_ok


def run_verify() -> bool:
    """Execute end-to-end baseline contract self-test probe."""
    print("=== Limo Master Backend Contract Verification ===")
    from .db import init_db
    from .services.project_service import project_service
    from .services.source_service import source_service
    from .services.chat_service import chat_service
    from .services.transform_service import transform_service
    from .models.enums import OutputFormat

    try:
        init_db()
        # 1. Project
        proj = project_service.create_project(name="CLI Probe Project")
        print(f"[OK] Service Layer: Created Project {proj.id}")

        # 2. Source
        src = source_service.register_text_source(
            name="CLI Test Document",
            text_content="Q3 corporate revenue and operational findings.",
            project_id=proj.id,
        )
        print(f"[OK] Storage + Service: Registered Source {src.id} ({src.size_bytes} bytes)")

        # 3. Chat
        chat = chat_service.create_session(title="CLI Probe Chat", project_id=proj.id)
        print(f"[OK] Chat Service: Created Chat Session {chat.id}")

        # 4. Transform Contract
        job = transform_service.create_transform_contract(
            requested_formats=[OutputFormat.SUMMARY],
            source_ids=[src.id],
            prompt="Generate an executive summary",
            project_id=proj.id,
            session_id=chat.id,
        )
        print(f"[OK] Transform Contract: Queued Job {job.id} (prompt: '{job.prompt}')")

        # Clean up
        project_service.delete_project(proj.id)
        print(f"[OK] Cleanup: Deleted test project {proj.id}")
        print("\nVerification probe PASSED with 100% success.")
        return True
    except Exception as e:
        print(f"\n[FAIL] Verification probe error: {e}")
        return False


def inspect_tools() -> bool:
    """Inspect and list all registered agent tools, schemas, and permissions."""
    from .agent.tools import create_default_tool_registry

    registry = create_default_tool_registry()
    tools = registry.list_tools()
    print(f"=== Limo Agent Tool Registry ({len(tools)} tools registered) ===")
    for tool in tools:
        print(f"\nTool: {tool.name}")
        print(f"  Permission:  {tool.permission_type.value}")
        print(f"  Description: {tool.description}")
        schema = tool.parameters_schema
        props = schema.get("properties", {})
        required = schema.get("required", [])
        print(f"  Arguments ({len(props)}):")
        for prop, details in props.items():
            req_mark = "*" if prop in required else ""
            desc = details.get("description", "")
            print(f"    - {prop}{req_mark} ({details.get('type', 'any')}): {desc}")
    print("\n[OK] Tool inspection complete.")
    return True


def inspect_skills() -> bool:
    """Inspect and list all discovered agent skills, triggers, and deliverables."""
    from .agent.skills import SkillRegistry

    registry = SkillRegistry()
    skills = registry.list_skills()
    print(f"=== Limo Agent Skill Registry ({len(skills)} skills discovered) ===")
    for skill in skills:
        print(f"\nSkill: {skill.name}")
        print(f"  Category:     {skill.category}")
        print(f"  Description:  {skill.description}")
        print(f"  Modes:        {', '.join(skill.modes) or 'all'}")
        print(f"  Deliverables: {', '.join(skill.deliverables)}")
        print(f"  Triggers:     {', '.join(skill.triggers)}")
        print(f"  Path:         {skill.path}")
    print("\n[OK] Skill inspection complete.")
    return True


def inspect_providers() -> bool:
    """Inspect configured LLM providers, credentials, quotas, and active cooldowns."""
    from .agent.llm.manager import llm_provider_manager

    diag = llm_provider_manager.get_diagnostics()
    print(f"=== Limo LLM Provider Diagnostics (Provider: {diag['provider']}) ===")
    print(f"Primary Model:   {diag['primary_model']}")
    print(f"Fallback Chain:  {', '.join(diag['fallback_models'])}")
    print(f"Configured Keys: {diag['credentials_count']}")
    for c in diag["credentials"]:
        status = "ACTIVE" if c["active"] else "INACTIVE"
        print(f"  - [{c['project']}] {c['id']}: {c['masked_key']} ({status})")
    print(f"\nRequests: {diag['total_requests']}, Retries: {diag['total_retries']}, Failovers: {diag['total_failovers']}")
    print("\nRoutes & Quota Status:")
    for r in diag["routes"]:
        cooldown_str = f"COOLDOWN ({r['cooldown_remaining_sec']}s left)" if r["in_cooldown"] else "AVAILABLE"
        print(f"  Route: {r['route']}")
        print(f"    Status:   {cooldown_str}")
        print(f"    RPM (1m): {r['rpm_1m']} / {r['rpm_limit']}")
        print(f"    TPM (1m): {r['total_tpm_1m']} / {r['tpm_limit']} (in: {r['input_tpm_1m']}, out: {r['output_tpm_1m']})")
        print(f"    RPD (24h): {r['rpd_24h']} / {r['rpd_limit']}")
    print("\n[OK] Provider inspection complete.")
    return True


def test_llm() -> bool:
    """Perform real minimal model request and report provider, project, model, latency, success/failure."""
    import asyncio
    from .agent.llm.manager import llm_provider_manager

    print("=== Limo LLM Minimal Connectivity Probe ===")

    async def _run() -> bool:
        try:
            res = await llm_provider_manager.generate(
                prompt="Reply strictly with the word: READY",
                temperature=0.1,
            )
            parts = res.route_key.split(":")
            proj = parts[0] if len(parts) > 0 else "unknown"
            model = parts[2] if len(parts) > 2 else "unknown"
            print(f"[OK] Provider:        {llm_provider_manager.adapter.provider_name}")
            print(f"[OK] Project:         {proj}")
            print(f"[OK] Model:           {model}")
            print(f"[OK] Latency:         {res.latency_sec:.2f}s")
            print(f"[OK] Retries:         {res.retries_used}")
            print(f"[OK] Tokens:          {res.total_tokens} (in: {res.input_tokens}, out: {res.output_tokens})")
            print(f"[OK] Response Text:   '{res.text.strip() if res.text else ''}'")
            print("\nLLM connectivity probe PASSED.")
            return True
        except Exception as e:
            print(f"\n[FAIL] LLM probe error: {e}")
            return False

    return asyncio.run(_run())


def test_loop() -> bool:
    """Perform an end-to-end real agent conversational turn and verify persistence."""
    import asyncio
    from .agent.runtime import LimoAgentRuntime
    from .services.chat_service import chat_service

    print("=== Limo Agent Full Loop Turn Diagnostic ===")

    async def _run() -> bool:
        try:
            session = chat_service.create_session(title="CLI Test Loop Session")
            runtime = LimoAgentRuntime()
            msg = await runtime.execute_turn(
                session_id=session.id,
                user_prompt="Provide a brief one-sentence greeting.",
            )
            print(f"[OK] Session ID:       {session.id}")
            print(f"[OK] Assistant Msg:    {msg.id}")
            print(f"[OK] Execution Summary:{msg.execution_summary}")
            print(f"[OK] Response Content: '{msg.content.strip()}'")
            # Cleanup test session
            chat_service.delete_session(session.id)
            print("\nAgent full loop probe PASSED.")
            return True
        except Exception as e:
            print(f"\n[FAIL] Agent loop probe error: {e}")
            return False

    return asyncio.run(_run())


def main() -> None:
    parser = argparse.ArgumentParser(description="Limo Backend Diagnostic CLI (Rule 12)")
    subparsers = parser.add_subparsers(dest="command", help="Available diagnostic commands")

    subparsers.add_parser("health", help="Diagnose database and filesystem storage sandbox")
    subparsers.add_parser("verify", help="Run live end-to-end self-test probe")
    subparsers.add_parser("inspect-tools", help="Inspect all registered agent tools and schemas")
    subparsers.add_parser("inspect-skills", help="Inspect all discovered skills and triggers")
    subparsers.add_parser("inspect-providers", help="Inspect LLM providers, credentials, and quotas")
    subparsers.add_parser("test-llm", help="Test live minimal LLM model connectivity")
    subparsers.add_parser("test-loop", help="Test live agent execution loop")

    # 'agent' nested subcommand group
    agent_parser = subparsers.add_parser("agent", help="Agent diagnostic subcommands")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", help="Agent commands")
    agent_subparsers.add_parser("inspect-tools", help="Inspect registered tools")
    agent_subparsers.add_parser("inspect-skills", help="Inspect discovered skills")
    agent_subparsers.add_parser("inspect-providers", help="Inspect LLM providers and quotas")
    agent_subparsers.add_parser("test-llm", help="Test live LLM connectivity")
    agent_subparsers.add_parser("test-loop", help="Test live agent execution loop")

    args = parser.parse_args()
    cmd = args.command
    agent_cmd = getattr(args, "agent_command", None)

    if cmd == "health":
        success = check_health()
        sys.exit(0 if success else 1)
    elif cmd == "verify":
        success = run_verify()
        sys.exit(0 if success else 1)
    elif cmd == "inspect-tools" or (cmd == "agent" and agent_cmd == "inspect-tools"):
        success = inspect_tools()
        sys.exit(0 if success else 1)
    elif cmd == "inspect-skills" or (cmd == "agent" and agent_cmd == "inspect-skills"):
        success = inspect_skills()
        sys.exit(0 if success else 1)
    elif cmd == "inspect-providers" or (cmd == "agent" and agent_cmd == "inspect-providers"):
        success = inspect_providers()
        sys.exit(0 if success else 1)
    elif cmd == "test-llm" or (cmd == "agent" and agent_cmd == "test-llm"):
        success = test_llm()
        sys.exit(0 if success else 1)
    elif cmd == "test-loop" or (cmd == "agent" and agent_cmd == "test-loop"):
        success = test_loop()
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
