"""Document chunking and multimodal embedding for RAG.

Splits documents into semantic chunks (text + images) and computes embeddings
using gemini-embedding-2-preview (multimodal: text, images, video, audio, PDF).

Chunk strategy:
- Text: semantic split by paragraphs/sections, ~2000 tokens with 200 token overlap
- Images: each extracted image becomes a separate chunk with multimodal embedding
- Tables: detected table blocks become separate chunks

Embedding model: gemini-embedding-2-preview
- Input: up to 8192 tokens (text) or multimodal content
- Output: configurable 128-3072 dimensions (we use 768 for schema compatibility)
"""
import uuid
import json
import logging
from dataclasses import dataclass, field
from google import genai

from services.cost_tracker import get_tracker

logger = logging.getLogger(__name__)

# gemini-embedding-2-preview è multimodale ma disponibile solo in us-central1.
# Su Vertex AI in europe-west1 usiamo text-embedding-005 come fallback.
# La selezione è automatica in base all'ambiente.
import os
_USE_VERTEXAI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip() == "1"
# Always use gemini-embedding-2-preview (preview, Gemini API key only — not on Vertex AI yet)
EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIMENSIONS = 768

def _get_embedding_client():
    """Return a genai.Client that targets the Gemini API (not Vertex AI).

    gemini-embedding-2-preview is only available via Gemini API key,
    not Vertex AI. On Cloud Run where GOOGLE_GENAI_USE_VERTEXAI=1,
    genai.Client(api_key=...) still routes to Vertex AI, so we must
    explicitly set vertexai=False to force the Gemini API endpoint.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key, vertexai=False)
    return genai.Client()  # Fallback: local dev without explicit key
CHUNK_SIZE_CHARS = 1500       # ~500 tokens ≈ 1500 chars (smaller = more precise retrieval)
CHUNK_OVERLAP_CHARS = 200     # ~65 tokens overlap


@dataclass
class Chunk:
    chunk_id: str
    chunk_index: int
    chunk_text: str
    chunk_type: str           # "text", "image", "table"
    page_number: int | None = None
    image_uri: str | None = None
    context_prefix: str = ""  # Contextual Retrieval: prepended before embedding
    embedding: list[float] = field(default_factory=list)


def chunk_document(
    text: str,
    images: list[dict] | None = None,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    """Split document text and images into chunks.

    Args:
        text: Full document text
        images: List of extracted images, each with keys: pageNum, dataUri
        chunk_size: Target chunk size in characters
        overlap: Overlap between consecutive text chunks in characters

    Returns:
        List of Chunk objects (without embeddings — call compute_chunk_embeddings next)
    """
    chunks: list[Chunk] = []
    idx = 0

    # 1. Semantic text chunking
    text_chunks = _split_text_semantically(text, chunk_size, overlap)
    for chunk_text in text_chunks:
        chunks.append(Chunk(
            chunk_id=str(uuid.uuid4()),
            chunk_index=idx,
            chunk_text=chunk_text,
            chunk_type="text",
            page_number=_estimate_page(chunk_text, text),
        ))
        idx += 1

    # 2. Image chunks (one per extracted image, with Gemini Vision captions)
    if images:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        client = genai.Client()

        def _caption_and_build(img):
            page_num = img.get("pageNum") or img.get("page_number")
            data_uri = img.get("dataUri") or img.get("data_uri", "")
            caption = _caption_image(client, data_uri) if data_uri else ""
            return page_num, data_uri, caption

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_caption_and_build, img): img for img in images}
            for future in as_completed(futures):
                page_num, data_uri, caption = future.result()
                chunk_text = f"[Image from page {page_num}] {caption}" if caption else f"[Image from page {page_num}]"
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    chunk_index=idx,
                    chunk_text=chunk_text,
                    chunk_type="image",
                    page_number=page_num,
                    image_uri=data_uri,
                ))
                idx += 1
        logger.info(f"Captioned {len(images)} images via Gemini Vision")

    logger.info(f"Document chunked into {len(chunks)} chunks "
                f"({sum(1 for c in chunks if c.chunk_type == 'text')} text, "
                f"{sum(1 for c in chunks if c.chunk_type == 'image')} image)")
    return chunks


def _contextualize_batch(
    batch: list[Chunk],
    batch_idx: int,
    doc_title: str,
    doc_summary: str,
    client,
) -> int:
    """Contextualize a single batch of chunks. Returns number of chunks contextualized."""
    chunks_text = ""
    for j, c in enumerate(batch):
        chunks_text += f"[CHUNK_{j}]\n{c.chunk_text[:800]}\n\n"

    prompt = f"""You are contextualizing document chunks for a retrieval system.
For each chunk below, write a SHORT context prefix (2-3 sentences max) that explains:
1. What document and section this chunk is from
2. What specific topic this chunk discusses

Document title: {doc_title}
Document summary: {doc_summary[:500]}

{chunks_text}

Return a JSON array with {len(batch)} objects, each with "id" (integer 0 to {len(batch)-1}) and "context" (string, 2-3 sentences).
JSON array:"""

    try:
        _ctx_config = genai.types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            service_tier="flex",  # 50% cost reduction
        )
        # Flex tier requires the global Vertex AI endpoint, not regional
        flex_client = genai.Client(vertexai=True, location="global")
        response = flex_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=_ctx_config,
        )
        tracker = get_tracker()
        if tracker:
            tracker.track_generate(response, model="gemini-2.5-flash", tier="flex")
        result_text = response.text or "[]"
        contexts = json.loads(result_text)
        count = 0
        if isinstance(contexts, list):
            for ctx in contexts:
                idx = ctx.get("id")
                context = ctx.get("context", "")
                if isinstance(idx, int) and 0 <= idx < len(batch) and context:
                    batch[idx].context_prefix = context.strip()
                    count += 1
        return count
    except Exception as e:
        logger.warning(f"Contextualization batch {batch_idx} failed: {e}")
        return 0


def contextualize_chunks(
    chunks: list[Chunk],
    doc_title: str = "",
    doc_summary: str = "",
    batch_size: int = 10,
    max_workers: int = 3,
) -> list[Chunk]:
    """Contextual Retrieval: enrich each chunk with document-level context.

    Based on vendor's Contextual Retrieval (2024): prepends a short context
    to each chunk before embedding, reducing retrieval failure rate by 35-67%.

    Uses parallel processing (max_workers threads) to speed up LLM calls
    while staying within API rate limits.

    Args:
        chunks: List of Chunk objects
        doc_title: Title of the source document
        doc_summary: Brief summary of the document (first ~2000 chars)
        batch_size: Number of chunks to contextualize per LLM call
        max_workers: Number of parallel LLM calls (keep low for rate limits)

    Returns:
        Same list with context_prefix populated on text chunks
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    text_chunks = [c for c in chunks if c.chunk_type == "text" and c.chunk_text.strip()]
    if not text_chunks:
        return chunks

    client = genai.Client()
    total = len(text_chunks)

    # Split into batches
    batches = []
    for i in range(0, total, batch_size):
        batches.append(text_chunks[i:i + batch_size])

    # Process batches in parallel (controlled concurrency)
    contextualized = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _contextualize_batch, batch, idx, doc_title, doc_summary, client
            ): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            contextualized += future.result()

    logger.info(f"Contextualized {contextualized}/{total} chunks for '{doc_title}' ({max_workers} workers)")
    return chunks


def compute_chunk_embeddings(chunks: list[Chunk], metadata_prefix: str = "") -> list[Chunk]:
    """Compute embeddings for all chunks using gemini-embedding-2-preview.

    Text chunks: embedded as text (optionally with metadata prefix for better retrieval)
    Image chunks: embedded as multimodal content (image)

    The metadata_prefix is prepended ONLY for embedding computation, NOT stored.
    Based on "Utilizing Metadata for Better RAG" (ECIR 2026): metadata prefix
    nearly triples the margin between relevant/irrelevant chunks (AUC 0.625→0.940).

    Args:
        chunks: List of Chunk objects (embeddings will be populated in-place)
        metadata_prefix: Optional document metadata to prepend for embedding only
            (e.g. "[doc:Architecture Overview; type:Technical Document]")

    Returns:
        Same list with embeddings populated
    """
    if not chunks:
        return chunks

    client = _get_embedding_client()

    # Separate text and image chunks for different embedding strategies
    text_chunks = [c for c in chunks if c.chunk_type in ("text", "table")]
    image_chunks = [c for c in chunks if c.chunk_type == "image"]

    # Batch embed text chunks
    # - Contextual Retrieval: prepend context_prefix to chunk text
    # - Metadata prefix: prepend doc metadata for better embedding space separation
    #   (based on ECIR 2026 "Utilizing Metadata for Better RAG")
    # Note: task instruction prefix ("search_document:") was tested but REMOVED —
    # it improved vector-only recall (+14%) but hurt pipeline correctness (-8%)
    # because overly precise vector search left less room for graph-expanded chunks.
    # See evaluation/results/OPTIMIZATION_LOG.md for benchmark details.
    if text_chunks:
        texts = []
        for c in text_chunks:
            parts = []
            if metadata_prefix:
                parts.append(metadata_prefix)
            if c.context_prefix:
                parts.append(c.context_prefix)
            parts.append(c.chunk_text)
            texts.append("\n---\n".join(parts))
        # Batch in groups of 100 (Gemini API limit)
        _EMBED_BATCH_SIZE = 100
        for batch_start in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch_texts = texts[batch_start:batch_start + _EMBED_BATCH_SIZE]
            batch_chunks = text_chunks[batch_start:batch_start + _EMBED_BATCH_SIZE]
            try:
                response = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch_texts,
                    config=genai.types.EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIMENSIONS,
                    ),
                )
                tracker = get_tracker()
                if tracker:
                    tracker.track_embed(texts=batch_texts, model=EMBEDDING_MODEL)
                for chunk, emb in zip(batch_chunks, response.embeddings):
                    chunk.embedding = list(emb.values)
            except Exception as e:
                logger.error(f"Text batch embedding failed (batch {batch_start}): {e}")
                for chunk, text in zip(batch_chunks, batch_texts):
                    chunk.embedding = _embed_single_text(client, text)
        logger.info(f"Embedded {len(text_chunks)} text chunks ({EMBEDDING_DIMENSIONS} dim)")

    # Embed image chunks individually (multimodal)
    for chunk in image_chunks:
        if chunk.image_uri and chunk.image_uri.startswith("data:image"):
            try:
                chunk.embedding = _embed_image(client, chunk.image_uri)
                tracker = get_tracker()
                if tracker:
                    tracker.track_embed(texts=chunk.chunk_text, model=EMBEDDING_MODEL, is_image=True)
            except Exception as e:
                logger.warning(f"Image embedding failed for chunk {chunk.chunk_id}: {e}")
                # Fallback: embed the text description
                chunk.embedding = _embed_single_text(client, chunk.chunk_text)
        else:
            chunk.embedding = _embed_single_text(client, chunk.chunk_text)

    return chunks


def compute_entity_embeddings(entities: list[dict]) -> list[list[float]]:
    """Compute embeddings for a list of entities.

    Args:
        entities: List of dicts with 'name' and optional 'description' keys

    Returns:
        List of embedding vectors (768 dim each)
    """
    if not entities:
        return []

    client = _get_embedding_client()
    texts = [e["name"] for e in entities]

    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
        tracker = get_tracker()
        if tracker:
            tracker.track_embed(texts=texts, model=EMBEDDING_MODEL)
        return [list(emb.values) for emb in response.embeddings]
    except Exception as e:
        logger.error(f"Entity batch embedding failed: {e}")
        # Fallback: embed individually
        return [_embed_single_text(client, t) for t in texts]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _caption_image(client, data_uri: str) -> str:
    """Describe an image using Gemini Vision for searchable chunk text."""
    import base64
    try:
        header, b64_data = data_uri.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        image_bytes = base64.b64decode(b64_data)
        image_part = genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "Describe this image in detail for a document retrieval system. "
                "Include all visible text, numbers, labels, diagram elements, and "
                "technical details. Be factual and complete. "
                "Write in the same language as the visible text.",
                image_part,
            ],
            config=genai.types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=500,
            ),
        )
        tracker = get_tracker()
        if tracker:
            tracker.track_generate(response, model="gemini-2.5-flash")
        caption = (response.text or "").strip()
        logger.debug(f"Image caption: {caption[:80]}...")
        return caption
    except Exception as e:
        logger.warning(f"Image captioning failed: {e}")
        return ""


def _split_text_semantically(
    text: str, chunk_size: int, overlap: int
) -> list[str]:
    """Split text into chunks by paragraph boundaries with overlap."""
    if not text or not text.strip():
        return []

    # Split hierarchically: try \n\n first, then \n, then sentences
    paragraphs = []
    for block in text.split("\n\n"):
        stripped = block.strip()
        if stripped:
            # If block is still too large, split by single newlines
            if len(stripped) > chunk_size:
                for line in stripped.split("\n"):
                    line = line.strip()
                    if line:
                        paragraphs.append(line)
            else:
                paragraphs.append(stripped)

    if not paragraphs:
        # Single block — split by sentences
        paragraphs = [s.strip() for s in text.split(". ") if s.strip()]

    # Merge paragraphs into chunks of ~chunk_size chars
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # Start new chunk with overlap from end of previous
            if overlap > 0 and current:
                overlap_text = current[-overlap:]
                current = f"{overlap_text}\n\n{para}"
            else:
                current = para

    if current:
        chunks.append(current)

    # If document is very short, ensure at least one chunk
    if not chunks and text.strip():
        chunks.append(text.strip())

    return chunks


def _estimate_page(chunk_text: str, full_text: str) -> int | None:
    """Estimate which page a chunk belongs to based on position in full text."""
    # Look for page markers like "--- Slide N ---" or "Page N"
    import re
    page_match = re.search(r"(?:Slide|Page|Pagina)\s+(\d+)", chunk_text)
    if page_match:
        return int(page_match.group(1))

    # Rough estimate: position in document / average page size
    pos = full_text.find(chunk_text[:100])
    if pos >= 0:
        # Assume ~3000 chars per page
        return (pos // 3000) + 1
    return None


def _embed_single_text(client, text: str) -> list[float]:
    """Embed a single text string."""
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text[:8000],
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
        return list(response.embeddings[0].values)
    except Exception as e:
        logger.error(f"Single text embedding failed: {e}")
        return [0.0] * EMBEDDING_DIMENSIONS


def _embed_image(client, data_uri: str) -> list[float]:
    """Embed an image using gemini-embedding-2-preview multimodal capability."""
    import base64

    # Parse data URI: "data:image/png;base64,..."
    header, b64_data = data_uri.split(",", 1)
    mime_type = header.split(":")[1].split(";")[0]
    image_bytes = base64.b64decode(b64_data)

    # Create multimodal content with image
    image_part = genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=image_part,
        config=genai.types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return list(response.embeddings[0].values)
