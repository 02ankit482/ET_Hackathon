# database.py
# ─────────────────────────────────────────────────────────────
# Async MongoDB connection using Motor for FastAPI.
# ─────────────────────────────────────────────────────────────

from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URL, MONGODB_DATABASE


class Database:
    """Singleton-style MongoDB connection holder."""
    client: AsyncIOMotorClient = None  # type: ignore


db = Database()


async def connect_to_db():
    """Open the Motor connection pool (call on app startup)."""
    db.client = AsyncIOMotorClient(
        MONGODB_URL,
        minPoolSize=5,
        maxPoolSize=50,
    )
    # Quick ping to verify connectivity
    try:
        await db.client.admin.command("ping")
        print(f"✅ Connected to MongoDB: {MONGODB_DATABASE}")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")


async def close_db_connection():
    """Close the Motor connection pool (call on app shutdown)."""
    if db.client:
        db.client.close()
        print("🔌 MongoDB connection closed")


def get_db():
    """Return the database instance for the configured database name."""
    return db.client[MONGODB_DATABASE]


def get_collection(name: str):
    """Shorthand to get a specific collection."""
    return get_db()[name]


# ── Collection Names ──────────────────────────────────────────
USERS_COLLECTION = "users"
PLANS_COLLECTION = "plans"
CHAT_COLLECTION = "chat_history"
