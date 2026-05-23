import json
import logging
import re
import uuid
from src.Config.redis import get_redis
from src.memory.vectordb import chroma_memory
from src.Config.embeddings import get_embedding

logger = logging.getLogger("agent-service")

def tokenize(text: str) -> set[str]:
    # Extract lowercased alphanumeric words
    return set(re.findall(r'\b\w+\b', text.lower()))

class ShortTermMemory:
    async def add_message(self, session_id: str, message_id: str, role: str, text: str):
        try:
            redis = await get_redis()
            redis_key = f"chat_history:{session_id}"
            
            payload = {
                "id": message_id,
                "role": role,
                "message": text
            }
            # Append message to temporary Redis list cache
            await redis.rpush(redis_key, json.dumps(payload))
            # Set a 24-hour expiration on the key as a safety fallback
            await redis.expire(redis_key, 86400)
            
            # Fetch embedding and index in Chroma
            embedding = await get_embedding(text)
            await chroma_memory.add_message(session_id, message_id, role, text, embedding)
            logger.info(f"Successfully cached message {message_id} in Redis and Chroma for session {session_id}")
        except Exception as e:
            logger.error(f"Error in short term memory add_message: {str(e)}")

    async def get_temporary_history(self, session_id: str) -> list[dict]:
        try:
            redis = await get_redis()
            redis_key = f"chat_history:{session_id}"
            items = await redis.lrange(redis_key, 0, -1)
            history = []
            for item in items:
                try:
                    history.append(json.loads(item))
                except Exception:
                    pass
            return history
        except Exception as e:
            logger.error(f"Error in short term memory get_temporary_history: {str(e)}")
            return []

    async def get_context(self, session_id: str, query_text: str, limit: int = 3) -> list[str]:
        try:
            query_embedding = await get_embedding(query_text)
            
            # Fetch larger candidate pool from Chroma for re-ranking
            candidates = await chroma_memory.search_context(
                session_id=session_id,
                query_embedding=query_embedding,
                limit=limit * 3
            )
            
            if not candidates:
                return []

            query_tokens = tokenize(query_text)
            ranked_candidates = []
            
            for cand in candidates:
                # Chroma cosine distance: distance = 1.0 - CosineSimilarity
                # Thus, Cosine Similarity = 1.0 - distance
                cosine_sim = 1.0 - cand["distance"]
                
                # Keyword overlap (Jaccard similarity)
                cand_tokens = tokenize(cand["text"])
                union_len = len(query_tokens.union(cand_tokens))
                jaccard_sim = len(query_tokens.intersection(cand_tokens)) / union_len if union_len > 0 else 0.0
                
                # Combine similarity scores: 70% semantic, 30% keyword overlap
                combined_score = 0.7 * cosine_sim + 0.3 * jaccard_sim
                
                ranked_candidates.append({
                    "text": cand["text"],
                    "score": combined_score
                })
            
            # Sort candidates by combined score in descending order
            ranked_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            # Return top K texts
            top_texts = [cand["text"] for cand in ranked_candidates[:limit]]
            logger.info(f"Retrieved and re-ranked top-{len(top_texts)} short-term context matches for session {session_id}")
            return top_texts
            
        except Exception as e:
            logger.error(f"Error in short term memory get_context: {str(e)}")
            return []

    async def seed_session(self, session_id: str, messages: list[dict]):
        try:
            redis = await get_redis()
            redis_key = f"chat_history:{session_id}"
            
            # Verify if Redis cache is already populated
            length = await redis.llen(redis_key)
            if length == 0:
                logger.info(f"Seeding short term memory for session {session_id} with {len(messages)} past messages")
                for msg in messages:
                    msg_id = str(msg.get("id", uuid.uuid4()))
                    role = msg.get("role")
                    text = msg.get("message")
                    
                    payload = {
                        "id": msg_id,
                        "role": role,
                        "message": text
                    }
                    await redis.rpush(redis_key, json.dumps(payload))
                    
                    # Fetch embedding and add to Chroma
                    embedding = await get_embedding(text)
                    await chroma_memory.add_message(session_id, msg_id, role, text, embedding)
                
                # Set 24h expiration on the Redis key
                await redis.expire(redis_key, 86400)
            else:
                logger.info(f"Redis cache already populated for session {session_id}. Skipping seeding.")
        except Exception as e:
            logger.error(f"Error in short term memory seed_session: {str(e)}")

    def get_all_messages(self, session_id: str) -> list[dict]:
        try:
            return chroma_memory.get_all_messages(session_id)
        except Exception as e:
            logger.error(f"Error in short term memory get_all_messages: {str(e)}")
            return []

    async def clear_session(self, session_id: str):
        try:
            redis = await get_redis()
            redis_key = f"chat_history:{session_id}"
            await redis.delete(redis_key)
            
            # Clear Chroma DB collection
            chroma_memory.clear_session(session_id)
            logger.info(f"Cleared all temporary caches (Redis and Chroma) for session {session_id}")
        except Exception as e:
            logger.error(f"Error in short term memory clear_session: {str(e)}")

short_term_memory = ShortTermMemory()
