"""MongoDB connection + Beanie setup."""

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.config import settings
from app.models.account import PasswordReset, VideoStart
from app.models.billing import Payment, StripeEvent
from app.models.icon import Icon
from app.models.job import Job
from app.models.user import User
from app.models.video import Video

DOCUMENT_MODELS = [
    Job,
    Video,
    Icon,
    User,
    VideoStart,
    PasswordReset,
    Payment,
    StripeEvent,
]


class DatabaseError(RuntimeError):
    pass


async def init_db(
    uri: str | None = None, db_name: str | None = None
) -> AsyncMongoClient:
    uri = uri or settings.mongodb_uri
    if not uri:
        raise DatabaseError("MONGODB_URI is empty; fill it in backend/.env")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=8000, tz_aware=True)
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        await client.close()
        raise DatabaseError(
            f"Cannot reach MongoDB ({exc.__class__.__name__}: {str(exc)[:200]}). "
            "For Atlas: check Network Access allows your IP, and the username/password in MONGODB_URI."
        ) from exc
    await init_beanie(
        database=client[db_name or settings.mongodb_db], document_models=DOCUMENT_MODELS
    )
    return client
