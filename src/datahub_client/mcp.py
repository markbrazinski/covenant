from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .core import gms_url


def _normalise(result: Any) -> Any:
    if getattr(result, "structuredContent", None) is not None:
        return result.structuredContent
    blocks = getattr(result, "content", [])
    texts = [getattr(block, "text", "") for block in blocks if getattr(block, "text", None)]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {"text": joined}


async def call_tools(calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    env = os.environ.copy()
    env.update(
        DATAHUB_GMS_URL=gms_url(),
        DATAHUB_GMS_TOKEN=os.getenv("DATAHUB_TOKEN", ""),
    )
    venv_dir = os.getenv("COVENANT_VENV", ".venv")
    params = StdioServerParameters(
        command=str(os.path.join(os.getcwd(), venv_dir, "bin", "mcp-server-datahub")),
        args=[],
        env=env,
        cwd=os.getcwd(),
    )
    results: list[Any] = []
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                for name, arguments in calls:
                    result = await session.call_tool(name, arguments)
                    if result.isError:
                        raise RuntimeError(f"MCP tool {name} failed: {_normalise(result)}")
                    results.append(_normalise(result))
    return results


def call_mcp(calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    return asyncio.run(call_tools(calls))
