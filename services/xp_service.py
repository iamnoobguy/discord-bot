import logging
import asyncpg

logger = logging.getLogger("bot")


class XPService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_xp(self, user_id: int) -> int:
        query = "SELECT xp FROM users WHERE user_id = $1"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

        return row["xp"] if row else 0

    async def update_xp(self, user_id: int, delta: int):
        """Add XP (positive/negative), clamp to minimum 0"""

        if delta == 0:
            return

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # Lock row FOR UPDATE to avoid race conditions
                row = await conn.fetchrow(
                    "SELECT xp FROM users WHERE user_id = $1 FOR UPDATE", user_id
                )

                current = row["xp"] if row else 0
                new_xp = max(0, current + delta)
                delta = new_xp - current

                if delta == 0:
                    logger.info(f"No change for {user_id} (clamped).")
                    return

                await conn.execute(
                    """
                    INSERT INTO users (user_id, xp)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET xp = EXCLUDED.xp
                """,
                    user_id,
                    new_xp,
                )

        logger.info(f"Adjusted {delta} XP for {user_id} (new: {new_xp}).")

    async def get_leaderboard(self, limit: int = 10):
        query = """
        SELECT user_id, xp
        FROM users
        ORDER BY xp DESC
        LIMIT $1
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)

        return [(r["user_id"], r["xp"]) for r in rows]
