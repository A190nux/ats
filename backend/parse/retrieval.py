"""
Retrieval module for semantic search and RAG over CV vectors in Chroma.

Provides:
- Query embedding and chunk retrieval
- Resume ranking and grouping
- Citation-ready snippet extraction
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

try:
    import chromadb
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
except ImportError as e:
    raise ImportError(f"Required packages not installed for retrieval: {e}")

logger = logging.getLogger(__name__)


@dataclass
class ChunkMatch:
    """A single chunk retrieved from vector DB."""
    chunk_id: str
    resume_id: str
    candidate_name: Optional[str]
    chunk_text: str
    similarity_score: Optional[float] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'resume_id': self.resume_id,
            'candidate_name': self.candidate_name,
            'chunk_text': self.chunk_text,
            'similarity_score': self.similarity_score,
            'start_char': self.start_char,
            'end_char': self.end_char,
        }


@dataclass
class ResumeRanking:
    """A ranked resume with associated chunk matches."""
    resume_id: str
    candidate_name: Optional[str]
    top_chunks: List[ChunkMatch]
    aggregate_score: float  # Average or max similarity of top chunks
    
    def to_dict(self) -> dict:
        return {
            'resume_id': self.resume_id,
            'candidate_name': self.candidate_name,
            'top_chunks': [c.to_dict() for c in self.top_chunks],
            'aggregate_score': self.aggregate_score,
        }


class ChromaRetriever:
    """Semantic retrieval from Chroma vector store."""
    
    def __init__(
        self,
        chroma_db_path: str = "./chroma_db",
        collection_name: str = "cv_collection",
        embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    ):
        """Initialize retriever."""
        self.chroma_db_path = chroma_db_path
        self.collection_name = collection_name
        
        # Connect to Chroma
        try:
            self.db = chromadb.PersistentClient(path=chroma_db_path)
            self.collection = self.db.get_or_create_collection(collection_name)
            # Separate collection for resume-level embeddings
            self.resume_collection = self.db.get_or_create_collection(f"{collection_name}_resumes")
            logger.info(f"Connected to Chroma at {chroma_db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to Chroma: {e}")
            raise
        
        # Initialize embedding model
        try:
            self.embed_model = HuggingFaceEmbedding(model_name=embedding_model)
            logger.info(f"Loaded embedding model: {embedding_model}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

        # Optional reranker model (can be None to skip reranking)
        self.rerank_model_name: Optional[str] = None
        self.rerank_embedder = None
    
    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[ChunkMatch]:
        """
        Retrieve top-k matching chunks for a query.
        
        Args:
            query: Search query (CV requirement or JD snippet)
            top_k: Number of top chunks to retrieve
        
        Returns:
            List of ChunkMatch objects ranked by similarity
        """
        try:
            # Embed the query
            query_embedding = self.embed_model.get_text_embedding(query)
            
            # Query Chroma
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=['metadatas', 'documents', 'distances']
            )
            
            matches = []
            if results and results['ids'] and len(results['ids']) > 0:
                chunk_ids = results['ids'][0]
                metadatas = results['metadatas'][0]
                documents = results['documents'][0]
                distances = results.get('distances', [[]])[0]
                
                for i, chunk_id in enumerate(chunk_ids):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    doc_text = documents[i] if i < len(documents) else ""
                    distance = distances[i] if i < len(distances) else None
                    
                    # Convert distance to similarity (1 / (1 + distance) for cosine)
                    similarity = 1.0 / (1.0 + (distance or 0)) if distance is not None else None
                    
                    match = ChunkMatch(
                        chunk_id=chunk_id,
                        resume_id=meta.get('resume_id', 'unknown'),
                        candidate_name=meta.get('candidate_name'),
                        chunk_text=meta.get('chunk_text', doc_text),
                        similarity_score=similarity,
                        start_char=meta.get('start_char'),
                        end_char=meta.get('end_char'),
                    )
                    matches.append(match)
            
            logger.info(f"Retrieved {len(matches)} chunks for query")
            return matches
        
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def search_by_resume(self, query: str, top_n_resumes: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve top resumes using resume-level embeddings.
        Returns list of dicts: {resume_id, candidate_name, similarity_score}
        """
        try:
            q_emb = self.embed_model.get_text_embedding(query)
            results = self.resume_collection.query(
                query_embeddings=[q_emb],
                n_results=top_n_resumes,
                include=['metadatas', 'documents', 'distances']
            )

            out = []
            if results and results['ids'] and len(results['ids']) > 0:
                ids = results['ids'][0]
                metadatas = results['metadatas'][0]
                distances = results.get('distances', [[]])[0]

                for i, rid in enumerate(ids):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    dist = distances[i] if i < len(distances) else None
                    sim = 1.0 / (1.0 + (dist or 0)) if dist is not None else None
                    out.append({
                        'resume_id': rid,
                        'candidate_name': meta.get('candidate_name'),
                        'similarity': sim,
                        'metadata': meta,
                    })

            return out
        except Exception as e:
            logger.error(f"Resume-level search failed: {e}")
            raise

    def search_resumes_v2(self, query: str, top_n_resumes: int = 10, chunks_per_resume: int = 3, rerank_model: Optional[str] = None) -> List[ResumeRanking]:
        """
        New resume-first retrieval pipeline:
        1. Find top N resumes by resume-level embedding
        2. For each resume, fetch top M chunks from chunk collection (filtered by resume_id)
        3. Optionally rerank candidate chunks/resumes using a reranker embedding model
        """
        try:
            # 1. get top resumes
            top_resumes = self.search_by_resume(query, top_n_resumes)

            # Prepare reranker if requested
            if rerank_model and rerank_model != self.rerank_model_name:
                try:
                    self.rerank_embedder = HuggingFaceEmbedding(model_name=rerank_model)
                    self.rerank_model_name = rerank_model
                    logger.info(f"Loaded reranker model: {rerank_model}")
                except Exception as e:
                    logger.warning(f"Failed to load reranker model {rerank_model}: {e}")
                    self.rerank_embedder = None

            rankings: List[ResumeRanking] = []

            # 2. for each resume, fetch top chunks
            for r in top_resumes:
                resume_id = r.get('resume_id')
                candidate_name = r.get('candidate_name')
                resume_sim = r.get('similarity') or 0.0

                # query chunk collection filtered by resume_id
                try:
                    q_emb = self.embed_model.get_text_embedding(query)
                    res = self.collection.query(
                        query_embeddings=[q_emb],
                        n_results=chunks_per_resume,
                        where={"resume_id": resume_id},
                        include=['metadatas', 'documents', 'distances']
                    )
                except TypeError:
                    # older chroma client may not support 'where' arg in this method signature
                    # fallback: full query then filter
                    res_full = self.collection.query(
                        query_embeddings=[q_emb],
                        n_results=top_n_resumes * chunks_per_resume,
                        include=['metadatas', 'documents', 'distances']
                    )
                    ids = res_full['ids'][0]
                    metadatas = res_full['metadatas'][0]
                    documents = res_full['documents'][0]
                    distances = res_full.get('distances', [[]])[0]
                    # filter by resume_id
                    filtered = []
                    for i, mid in enumerate(ids):
                        meta = metadatas[i] if i < len(metadatas) else {}
                        if meta.get('resume_id') == resume_id:
                            filtered.append((meta, documents[i] if i < len(documents) else '', distances[i] if i < len(distances) else None))
                    # build a pseudo result
                    res = {'metadatas': [ [m for m,_,_ in filtered] ], 'documents': [[d for _,d,_ in filtered]], 'distances': [[dist for _,_,dist in filtered]]}

                chunk_matches: List[ChunkMatch] = []
                if res and res['ids'] and len(res['ids']) > 0:
                    metadatas = res['metadatas'][0]
                    documents = res['documents'][0]
                    distances = res.get('distances', [[]])[0]
                    for i, meta in enumerate(metadatas):
                        doc_text = documents[i] if i < len(documents) else ''
                        distance = distances[i] if i < len(distances) else None
                        similarity = 1.0 / (1.0 + (distance or 0)) if distance is not None else None
                        cm = ChunkMatch(
                            chunk_id=meta.get('chunk_id') or meta.get('id') or f"{resume_id}_chunk_{i}",
                            resume_id=resume_id,
                            candidate_name=candidate_name,
                            chunk_text=meta.get('chunk_text', doc_text),
                            similarity_score=similarity,
                            start_char=meta.get('start_char'),
                            end_char=meta.get('end_char')
                        )
                        chunk_matches.append(cm)

                # 3. Optionally rerank: simple approach using reranker embedder cosine similarity over concatenated chunk texts
                if self.rerank_embedder and chunk_matches:
                    try:
                        import numpy as _np
                        q_r = self.rerank_embedder.get_text_embedding(query)
                        # compute embedding for each resume summary (concatenate top chunk texts)
                        texts = [c.chunk_text for c in chunk_matches]
                        emb_list = [self.rerank_embedder.get_text_embedding(t) for t in texts]
                        # compute cosine similarities
                        def cos(a,b):
                            a_arr = _np.array(a, dtype=float)
                            b_arr = _np.array(b, dtype=float)
                            denom = (_np.linalg.norm(a_arr) * _np.linalg.norm(b_arr))
                            return float(_np.dot(a_arr, b_arr) / denom) if denom > 0 else 0.0

                        for idx, cm in enumerate(chunk_matches):
                            cm.similarity_score = cos(q_r, emb_list[idx])

                    except Exception as e:
                        logger.debug(f"Reranking failed for resume {resume_id}: {e}")

                # compute aggregate score: combine resume_sim and top chunk avg
                top_chunks_sorted = sorted(chunk_matches, key=lambda c: c.similarity_score or 0, reverse=True)[:chunks_per_resume]
                scores = [c.similarity_score for c in top_chunks_sorted if c.similarity_score is not None]
                agg = (sum(scores) / len(scores)) if scores else resume_sim

                ranking = ResumeRanking(
                    resume_id=resume_id,
                    candidate_name=candidate_name,
                    top_chunks=top_chunks_sorted,
                    aggregate_score=agg or 0.0,
                )
                rankings.append(ranking)

            rankings.sort(key=lambda r: r.aggregate_score, reverse=True)
            return rankings
        except Exception as e:
            logger.error(f"search_resumes_v2 failed: {e}")
            raise
    
    def rank_by_resume(
        self,
        chunk_matches: List[ChunkMatch],
        chunks_per_resume: int = 3
    ) -> List[ResumeRanking]:
        """
        Group and rank chunks by resume.
        
        Args:
            chunk_matches: List of chunk matches from search
            chunks_per_resume: Max chunks to include per resume
        
        Returns:
            List of ResumeRanking objects sorted by aggregate score
        """
        # Group by resume_id
        resume_groups: Dict[str, List[ChunkMatch]] = {}
        for match in chunk_matches:
            resume_id = match.resume_id
            if resume_id not in resume_groups:
                resume_groups[resume_id] = []
            resume_groups[resume_id].append(match)
        
        # Rank each resume by aggregate score
        rankings = []
        for resume_id, chunks in resume_groups.items():
            # Sort chunks by similarity within this resume
            chunks_sorted = sorted(
                chunks,
                key=lambda c: c.similarity_score or 0,
                reverse=True
            )
            top_chunks = chunks_sorted[:chunks_per_resume]
            
            # Aggregate score: average of top chunk similarities
            scores = [c.similarity_score for c in top_chunks if c.similarity_score is not None]
            agg_score = sum(scores) / len(scores) if scores else 0.0
            
            candidate_name = top_chunks[0].candidate_name if top_chunks else None
            
            ranking = ResumeRanking(
                resume_id=resume_id,
                candidate_name=candidate_name,
                top_chunks=top_chunks,
                aggregate_score=agg_score,
            )
            rankings.append(ranking)
        
        # Sort by aggregate score
        rankings.sort(key=lambda r: r.aggregate_score, reverse=True)
        
        return rankings


# Global instance (lazy-loaded)
_retriever: Optional[ChromaRetriever] = None


def get_retriever() -> ChromaRetriever:
    """Get or create global retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = ChromaRetriever()
    return _retriever


def search_resumes(query: str, top_k: int = 10) -> List[ResumeRanking]:
    """
    High-level search function: query → chunks → ranked resumes.
    
    Args:
        query: Search query
        top_k: Number of chunks to retrieve
    
    Returns:
        List of ranked resumes with their top matching chunks
    """
    import time
    try:
        retriever = get_retriever()
        logger.info(f"Starting resume-first search for query='{query}' top_k={top_k}")
        start = time.time()
        # By default do NOT enable the reranker (it is expensive). Make reranking opt-in.
        rankings = retriever.search_resumes_v2(query, top_n_resumes=top_k, chunks_per_resume=3, rerank_model=None)
        elapsed = time.time() - start
        logger.info(f"Resume-first search completed in {elapsed:.2f}s, returned {len(rankings)} resumes")
        return rankings
    except Exception as e:
        logger.error(f"Resume search failed: {e}")
        raise
