import os
os.environ["ANONYMOUS_TELEMETRY"] = "False"
import logging
from src.Config.chromadb_client import chroma_client

logger = logging.getLogger("agent-service")

class ChromaMemoryManager:
    """
    Manages short-term memory (STM) session-based vector collections in ChromaDB.
    These collections are ephemeral (erased on session end).
    """
    def __init__(self):
        self.client = chroma_client

    def _get_collection_name(self, session_id: str) -> str:
        # Chroma collection names must be 3-63 chars, start/end with alphanumeric, contain only alphanumeric, underscores, hyphens
        clean_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in session_id)
        if clean_id and not clean_id[0].isalnum():
            clean_id = "s" + clean_id
        name = f"session_{clean_id}"[:63]
        return name

    async def add_message(self, session_id: str, message_id: str, role: str, text: str, embedding: list[float]):
        try:
            if not self.client:
                logger.error("Chroma client is not initialized.")
                return
            name = self._get_collection_name(session_id)
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
            logger.info(f"Added message {message_id} to Chroma STM for session {session_id}")
        except Exception as e:
            logger.error(f"Error adding message to Chroma STM: {str(e)}")

    async def search_context(self, session_id: str, query_embedding: list[float], limit: int = 3) -> list[dict]:
        try:
            if not self.client:
                return []
            name = self._get_collection_name(session_id)
            try:
                collection = self.client.get_collection(name=name)
            except Exception:
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
                        "distance": dist
                    })
            return output
        except Exception as e:
            logger.error(f"Error searching Chroma STM context: {str(e)}")
            return []

    def get_all_messages(self, session_id: str) -> list[dict]:
        try:
            if not self.client:
                return []
            name = self._get_collection_name(session_id)
            try:
                collection = self.client.get_collection(name=name)
            except Exception:
                return []
            
            res = collection.get(include=['embeddings', 'documents', 'metadatas'])
            output = []
            if res and "ids" in res and res["ids"]:
                ids = res["ids"]
                docs = res["documents"] if res.get("documents") else [None] * len(ids)
                embeddings = res["embeddings"] if res.get("embeddings") else [None] * len(ids)
                metadatas = res["metadatas"] if res.get("metadatas") else [None] * len(ids)
                for i in range(len(ids)):
                    output.append({
                        "id": ids[i],
                        "text": docs[i] if docs[i] else "",
                        "embedding": embeddings[i] if embeddings[i] else [],
                        "metadata": metadatas[i] if metadatas[i] else {}
                    })
            return output
        except Exception as e:
            logger.error(f"Error getting all messages from Chroma STM: {str(e)}")
            return []

    def clear_session(self, session_id: str):
        try:
            if not self.client:
                return
            name = self._get_collection_name(session_id)
            try:
                self.client.delete_collection(name=name)
                logger.info(f"Deleted Chroma STM collection for session {session_id}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error clearing Chroma STM session: {str(e)}")


class LongTermVectorMemory:
    """
    Manages persistent long-term memory (LTM) vector collections in ChromaDB.
    These collections are persistent and scoped per user (ltm_{user_id}).
    """
    def __init__(self):
        self.client = chroma_client

    def _get_collection_name(self, user_id: str) -> str:
        # Chroma collection names must be 3-63 chars, start/end with alphanumeric, contain only alphanumeric, underscores, hyphens
        clean_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in user_id)
        if clean_id and not clean_id[0].isalnum():
            clean_id = "u" + clean_id
        name = f"ltm_{clean_id}"[:63]
        return name

    async def upsert_message(self, user_id: str, msg_id: str, session_id: str, role: str, text: str, embedding: list[float]):
        try:
            if not self.client:
                return
            name = self._get_collection_name(user_id)
            collection = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            collection.upsert(
                ids=[msg_id],
                embeddings=[embedding],
                metadatas=[{
                    "type": "message",
                    "role": role,
                    "session_id": session_id
                }],
                documents=[text]
            )
            logger.info(f"Upserted message {msg_id} to LTM for user {user_id}")
        except Exception as e:
            logger.error(f"Error upserting message to LTM: {str(e)}")

    async def upsert_summary(self, user_id: str, session_id: str, summary_text: str, embedding: list[float]):
        try:
            if not self.client:
                return
            name = self._get_collection_name(user_id)
            collection = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            # Use session_id as the document ID for summaries so we only store one summary per session
            summary_id = f"summary_{session_id}"
            collection.upsert(
                ids=[summary_id],
                embeddings=[embedding],
                metadatas=[{
                    "type": "summary",
                    "session_id": session_id
                }],
                documents=[summary_text]
            )
            logger.info(f"Upserted session summary {summary_id} to LTM for user {user_id}")
        except Exception as e:
            logger.error(f"Error upserting summary to LTM: {str(e)}")

    async def search(self, user_id: str, query_embedding: list[float], limit: int = 5, filter_type: str = None) -> list[dict]:
        try:
            if not self.client:
                return []
            name = self._get_collection_name(user_id)
            try:
                collection = self.client.get_collection(name=name)
            except Exception:
                # Collection doesn't exist yet
                return []

            where_clause = None
            if filter_type:
                where_clause = {"type": filter_type}

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_clause
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
                        "distance": dist
                    })
            return output
        except Exception as e:
            logger.error(f"Error searching LTM: {str(e)}")
            return []

    def delete_session_from_ltm(self, user_id: str, session_id: str):
        """
        Deletes all LTM vectors (messages + summary) that belong to a given session_id.
        Uses a where filter on the metadata field session_id.
        """
        try:
            if not self.client:
                return
            name = self._get_collection_name(user_id)
            try:
                collection = self.client.get_collection(name=name)
            except Exception:
                logger.info(f"LTM collection for user {user_id} does not exist; nothing to delete.")
                return

            # Fetch all IDs where session_id matches
            res = collection.get(where={"session_id": session_id}, include=[])
            ids_to_delete = res.get("ids", [])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(f"Deleted {len(ids_to_delete)} LTM vectors for session {session_id} (user {user_id})")
            else:
                logger.info(f"No LTM vectors found for session {session_id} (user {user_id})")
        except Exception as e:
            logger.error(f"Error deleting session from LTM: {str(e)}")


chroma_memory = ChromaMemoryManager()
ltm_memory = LongTermVectorMemory()
