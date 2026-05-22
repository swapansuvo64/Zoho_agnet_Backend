import asyncio
import logging

logger = logging.getLogger("auth-service")

class CronJob:
    def __init__(self, token_manager, redis, db):
        self.token_manager = token_manager
        self.redis = redis
        self.db = db
        self._task = None

    async def _run_rotation_loop(self):
        # We start the loop and immediately wait for the interval
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                logger.info("CronJob: Starting automatic background Zoho access token rotation...")
                await self.token_manager.rotate_all_access_tokens(self.redis, self.db)
                logger.info("CronJob: Successfully completed background Zoho access token rotation.")
            except Exception as e:
                logger.error(f"CronJob: Error occurred during background token rotation: {str(e)}")

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_rotation_loop())
            logger.info("CronJob: Background access token rotation job started.")

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("CronJob: Background access token rotation job stopped.")
            self._task = None
