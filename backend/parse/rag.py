"""
RAG (Retrieval-Augmented Generation) module for Q&A over CVs.

Retrieves top candidate matches and generates LLM answers with citations.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from llama_index.llms.ollama import Ollama

from backend.parse.retrieval import search_resumes, ResumeRanking

logger = logging.getLogger(__name__)


class LLMTimeout(Exception):
    """Raised when the underlying LLM request times out after retries."""
    pass


@dataclass
class RAGAnswer:
    """A generated RAG answer with sources."""
    question: str
    answer: str
    sources: List[Dict[str, Any]]  # List of {resume_id, candidate_name, chunk_text}
    num_resumes_retrieved: int
    model: str = "phi4-mini:latest"
    
    def to_dict(self) -> dict:
        return {
            'question': self.question,
            'answer': self.answer,
            'sources': self.sources,
            'num_resumes_retrieved': self.num_resumes_retrieved,
            'model': self.model,
        }


def format_context_for_rag(rankings: List[ResumeRanking], max_chunks: int = 10) -> str:
    """
    Format retrieved resume rankings into context for LLM.
    
    Args:
        rankings: List of ranked resumes from retrieval
        max_chunks: Max total chunks to include
    
    Returns:
        Formatted context string
    """
    context_parts = []
    chunk_count = 0
    
    for resume in rankings[:3]:  # Limit to top 3 resumes for efficiency
        if chunk_count >= max_chunks:
            break
        
        context_parts.append(f"\n--- {resume.candidate_name or 'Unknown'} (Score: {resume.aggregate_score:.0%}) ---")
        
        for chunk in resume.top_chunks[:2]:  # Limit to 2 chunks per resume
            if chunk_count >= max_chunks:
                break
            # Truncate chunk to 300 chars for efficiency
            chunk_preview = chunk.chunk_text[:300] + ("..." if len(chunk.chunk_text) > 300 else "")
            context_parts.append(f"\n{chunk_preview}")
            chunk_count += 1
    
    return "".join(context_parts)


def extract_sources(rankings: List[ResumeRanking], max_chunks: int = 5) -> List[Dict[str, Any]]:
    """Extract top chunks as citation sources."""
    sources = []
    chunk_count = 0
    
    for resume in rankings:
        if chunk_count >= max_chunks:
            break
        for chunk in resume.top_chunks:
            if chunk_count >= max_chunks:
                break
            sources.append({
                'resume_id': chunk.resume_id,
                'candidate_name': resume.candidate_name,
                'chunk_text': chunk.chunk_text[:300] + ("..." if len(chunk.chunk_text) > 300 else ""),
                'similarity_score': chunk.similarity_score,
            })
            chunk_count += 1
    
    return sources


def generate_rag_answer(
    question: str,
    top_k: int = 10,
    llm_model: str = "phi4-mini:latest",
    llm_timeout: float = 120.0,
) -> RAGAnswer:
    """
    Generate an answer to a question using RAG.
    
    Pipeline:
    1. Retrieve top-k resumes/chunks for the question
    2. Format retrieved context
    3. Call LLM with context + question
    4. Extract answer with citations
    
    Args:
        question: The question to answer (requirement, skill, or JD snippet)
        top_k: Number of chunks to retrieve
        llm_model: Ollama model to use
        llm_timeout: Timeout for LLM calls (seconds)
    
    Returns:
        RAGAnswer with generated response and sources
    """
    try:
        # 1. Retrieve relevant resumes
        logger.info(f"Retrieving candidates for: {question}")
        rankings = search_resumes(question, top_k=top_k)
        
        if not rankings:
            return RAGAnswer(
                question=question,
                answer="No matching candidates found in the database.",
                sources=[],
                num_resumes_retrieved=0,
                model=llm_model,
            )
        
        # 2. Format context (compact)
        context = format_context_for_rag(rankings, max_chunks=6)
        
        # 3. Call LLM with shorter prompt
        llm = Ollama(
            model=llm_model,
            request_timeout=llm_timeout,
            temperature=0.2,  # Very low temp for consistency
        )
        
        rag_prompt = f"""Answer based on the candidates below. Be brief.

CANDIDATES:
{context}

QUESTION: {question}

ANSWER:"""
        
        logger.info("Calling LLM to generate answer...")
        # Acquire GPU lock before invoking LLM so embeddings and LLM don't run concurrently
        from backend.gpu_lock import acquire_gpu, release_gpu
        # Use the LLM timeout as a sensible GPU lock timeout so we don't
        # wait indefinitely for the lock while the LLM call is expected
        # to run for up to `llm_timeout` seconds.
        got_gpu = acquire_gpu(blocking=True, timeout=llm_timeout)

        # Retry loop for transient timeouts/connection issues
        import time
        try:
            import httpx
            import httpcore
        except Exception:
            httpx = None
            httpcore = None

        try:
            max_retries = 2
            backoff = 2.0
            last_exc = None
            answer_text = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = llm.complete(rag_prompt)
                    answer_text = response.message.content if hasattr(response, 'message') else str(response)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    should_retry = False
                    if httpx and httpcore:
                        if isinstance(e, (httpx.ReadTimeout, httpcore.ReadTimeout)):
                            should_retry = True
                    else:
                        # If exception types are unavailable, allow a single retry
                        should_retry = attempt < max_retries

                    logger.warning(f"LLM call attempt {attempt} failed: {e}. retry={should_retry}")
                    if not should_retry or attempt == max_retries:
                        # Raise a clearer timeout exception for the API to map to 504
                        raise LLMTimeout(f"LLM call timed out after {llm_timeout}s (attempt {attempt}). Last error: {e}")
                    time.sleep(backoff * attempt)
        finally:
            if got_gpu:
                release_gpu()
                logger.info("Released GPU lock after LLM call")
        
        # 4. Extract sources
        sources = extract_sources(rankings, max_chunks=5)
        
        logger.info(f"Generated answer based on {len(rankings)} candidates")
        
        return RAGAnswer(
            question=question,
            answer=answer_text,
            sources=sources,
            num_resumes_retrieved=len(rankings),
            model=llm_model,
        )
    
    except Exception as e:
        logger.error(f"RAG generation failed: {e}", exc_info=True)
        raise
