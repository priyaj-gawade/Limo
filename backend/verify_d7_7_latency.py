"""Empirical Latency and Token Profiling for Phase D7.7 (Fast Chat & Dynamic Routing).

Measures:
1. Fast Intent Gate latency distribution (< 1 ms per query across 10,000 iterations).
2. Live end-to-end Gemini API latency comparing:
   - Tool-schema injected turn (~2,200 input tokens)
   - Zero-tool Fast Chat turn (~25 input tokens)
3. Computes p50, p95, token reduction %, and throughput improvements.
"""

import asyncio
import statistics
import time
from typing import List

from app.agent.intent import intent_resolver
from app.agent.tools import create_default_tool_registry
from app.agent.llm.manager import llm_provider_manager


def benchmark_intent_gate():
    """Benchmark deterministic intent gate sub-millisecond execution."""
    test_prompts = [
        "hey",
        "thanks for the help",
        "What is Markdown?",
        "what is an API?",
        "I mentioned Markdown in my report.",
        "Create a Markdown document about renewable energy with a 5-row table",
        "Create a table in Markdown",
        "Create a table in a document",
        "Create a spreadsheet table of sales",
        "Create a table",
        "Make something for my project",
        "Create a document or slides",
        "Convert my notes into a presentation",
    ]

    # Warmup
    for p in test_prompts:
        intent_resolver.resolve(p)

    iterations = 5000
    latencies = []
    t0 = time.perf_counter()
    for _ in range(iterations):
        for p in test_prompts:
            start = time.perf_counter()
            intent_resolver.resolve(p)
            latencies.append((time.perf_counter() - start) * 1000.0)  # ms
    total_time = time.perf_counter() - t0

    total_queries = iterations * len(test_prompts)
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    mean_lat = statistics.mean(latencies)
    qps = total_queries / total_time

    print("=" * 60)
    print("1. DETERMINISTIC INTENT GATE BENCHMARK")
    print("=" * 60)
    print(f"Total resolutions: {total_queries:,}")
    print(f"Total wall time:   {total_time:.3f} s")
    print(f"Throughput:        {qps:,.0f} resolutions/sec")
    print(f"Mean latency:      {mean_lat:.4f} ms")
    print(f"p50 latency:       {p50:.4f} ms")
    print(f"p95 latency:       {p95:.4f} ms")
    print(f"Gate overhead:     <{mean_lat * 1000:.1f} microseconds per prompt")
    assert p95 < 1.0, f"p95 latency {p95}ms exceeds 1.0ms SLA!"
    print("STATUS: PASSED (Zero remote latency, <1ms deterministic gate)")
    print()


async def benchmark_gemini_fast_chat_vs_tools():
    """Benchmark live Gemini API latency with and without tool schema injection."""
    tool_registry = create_default_tool_registry()
    tools = tool_registry.list_tools()
    tool_declarations = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters_schema,
        }
        for t in tools
    ]

    test_prompt = "What is an API?"
    system_instruction = "You are Limo, an intelligent AI workspace agent. Respond helpfully and concisely."

    print("=" * 60)
    print("2. GEMINI API FAST CHAT VS FULL TOOLS BENCHMARK")
    print("=" * 60)

    # 1. Measure Fast Chat (Zero tools)
    print("Benchmarking Fast Chat path (tools_declarations=None)...")
    fast_latencies = []
    fast_tokens_in = []
    fast_tokens_out = []
    
    # Warmup
    await llm_provider_manager.generate(
        prompt=test_prompt,
        system_instruction=system_instruction,
        tools_declarations=None,
    )

    for i in range(3):
        res = await llm_provider_manager.generate(
            prompt=test_prompt,
            system_instruction=system_instruction,
            tools_declarations=None,
        )
        fast_latencies.append(res.latency_sec)
        fast_tokens_in.append(res.input_tokens)
        fast_tokens_out.append(res.output_tokens)
        print(f"  Run {i+1}: latency={res.latency_sec:.2f}s, tokens_in={res.input_tokens}, tokens_out={res.output_tokens}")
        await asyncio.sleep(0.5)

    # 2. Measure Legacy / Tool-injected Path
    print("\nBenchmarking Legacy Tool-injected path (8 tool schemas)...")
    tool_latencies = []
    tool_tokens_in = []
    tool_tokens_out = []

    # Warmup
    await llm_provider_manager.generate(
        prompt=test_prompt,
        system_instruction=system_instruction,
        tools_declarations=tool_declarations,
    )

    for i in range(3):
        res = await llm_provider_manager.generate(
            prompt=test_prompt,
            system_instruction=system_instruction,
            tools_declarations=tool_declarations,
        )
        tool_latencies.append(res.latency_sec)
        tool_tokens_in.append(res.input_tokens)
        tool_tokens_out.append(res.output_tokens)
        print(f"  Run {i+1}: latency={res.latency_sec:.2f}s, tokens_in={res.input_tokens}, tokens_out={res.output_tokens}")
        await asyncio.sleep(0.5)

    fast_p50 = statistics.median(fast_latencies)
    tool_p50 = statistics.median(tool_latencies)
    avg_fast_in = statistics.mean(fast_tokens_in)
    avg_tool_in = statistics.mean(tool_tokens_in)
    token_savings = ((avg_tool_in - avg_fast_in) / avg_tool_in) * 100.0

    print()
    print("-" * 60)
    print("COMPARATIVE RESULTS SUMMARY:")
    print("-" * 60)
    print(f"Input tokens (Legacy with tools):  {avg_tool_in:.0f} tokens")
    print(f"Input tokens (D7.7 Fast Chat):      {avg_fast_in:.0f} tokens")
    print(f"Token reduction:                   {token_savings:.1f}% ({avg_tool_in - avg_fast_in:.0f} tokens saved per turn)")
    print(f"Median latency (Legacy with tools): {tool_p50:.2f}s")
    print(f"Median latency (D7.7 Fast Chat):    {fast_p50:.2f}s")
    speedup = ((tool_p50 - fast_p50) / tool_p50) * 100.0 if tool_p50 > fast_p50 else 0.0
    print(f"Latency delta:                     {fast_p50 - tool_p50:+.2f}s ({speedup:.1f}% faster)")
    print("=" * 60)


async def main():
    benchmark_intent_gate()
    await benchmark_gemini_fast_chat_vs_tools()


if __name__ == "__main__":
    asyncio.run(main())
