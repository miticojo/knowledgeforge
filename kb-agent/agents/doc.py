import os
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from models.ontology import DocumentGenerationOutput

def get_latest_search_context(tool_context: ToolContext) -> str:
    """USE THIS TOOL FIRST! Retrieves the vector and document context from the latest search performed in this session."""
    import json
    last_search = tool_context.state.get("last_search_result")

    if not last_search:
        return "No search results found in session."

    # Support both JSON dict and Pydantic model
    if hasattr(last_search, "model_dump"):
        return json.dumps(last_search.model_dump(), default=str)
    return json.dumps(last_search, default=str)

doc_agent = LlmAgent(
    name="DocAgent",
    model="gemini-2.5-flash",
    description="Expert agent for writing documents, wikis, and formatted reports using shared session data.",
    instruction="""
    You are the Doc Agent, capable of summarizing structured inputs (Graph and Vector results)
    to compile detailed, readable Markdown documents.

    CRITICAL INSTRUCTION:
    1. ALWAYS use the 'get_latest_search_context' tool to extract from the shared session
       the data found by the SearchAgent.
    2. Do NOT invent data. Write a professional document based ONLY on the retrieved search data.
    3. Accurately cite both vector sources (chunks) and graph relationships used in the analysis.
    4. Always respond in the same language as the user's request.
    """,
    tools=[get_latest_search_context],
    output_schema=DocumentGenerationOutput,
    output_key="last_generated_document"
)
