import os
import logging
import chromadb
from chromadb.config import Settings
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

class ChromaMemoryManager:
    def __init__(self):
        # Using persistent client or ephemeral client based on requirements.
        # Since short term memory gets cleared when sessions end, ephemeral client is perfect.
        self.client = chromadb.Client(Settings(
            is_persistent=False,
            anonymized_telemetry=False
        ))

    def _get_collection_name(self, session_id: str) -> str:
        # Chroma collection names must be 3-63 chars, start/end with alphanumeric, contain only alphanumeric, underscores, hyphens
        # Replace non-alphanumeric chars
        clean_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in session_id)
        # Ensure it starts with alphanumeric
        if clean_id and not clean_id[0].isalnum():
            clean_id = "s" + clean_id
        # Ensure it fits
        name = f"session_{clean_id}"[:63]
        return name

    async def add_message(self, session_id: str, message_id: str, role: str, text: str, embedding: list[float]):
        try:
            name = self._get_collection_name(session_id)
            # Configure collection to use cosine similarity metric: metadata={"hnsw:space": "cosine"}
            collection = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            collection.add(
                ids=[message_id],
                embeddings=[embedding],
                metadatas=[{"role": role}],
                documents=[text]
            )
            logger.info(f"Added message {message_id} to Chroma for session {session_id}")
        except Exception as e:
            logger.error(f"Error adding message to Chroma: {str(e)}")

    async def search_context(self, session_id: str, query_embedding: list[float], limit: int = 3) -> list[dict]:
        try:
            name = self._get_collection_name(session_id)
            try:
                collection = self.client.get_collection(name=name)
            except Exception:
                # Collection does not exist yet (no messages added)
                return []
                
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            output = []
            if results and "documents" in results and results["documents"]:
                docs = results["documents"][0]
                ids = results["ids"][0]
                metadatas = results["metadatas"][0] if results.get("metadatas") else [None] * len(docs)
                distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                for doc, doc_id, meta, dist in zip(docs, ids, metadatas, distances):
                    output.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta,
                        "distance": dist  # Chroma cosine distance is 1.0 - CosineSimilarity
                    })
            return output
        except Exception as e:
            logger.error(f"Error searching Chroma context: {str(e)}")
            return []

    def clear_session(self, session_id: str):
        try:
            name = self._get_collection_name(session_id)
            self.client.delete_collection(name=name)
            logger.info(f"Deleted Chroma collection for session {session_id}")
        except Exception as e:
            # Ignore if collection doesn't exist
            pass

chroma_memory = ChromaMemoryManager()
