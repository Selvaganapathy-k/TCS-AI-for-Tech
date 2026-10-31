from typing import Optional

from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.collection import Collection

from .config import MONGODB_DATABASE, MONGODB_URI

PROJECTS_COLLECTION = "projects"

_client: Optional[MongoClient] = None
_projects: Optional[Collection] = None

def init_db():
    global _client, _projects
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI must be set in backend/.env before starting the API.")

    _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    _client.admin.command("ping")
    database = _client[MONGODB_DATABASE]
    if PROJECTS_COLLECTION not in database.list_collection_names():
        database.create_collection(PROJECTS_COLLECTION)
    _projects = database[PROJECTS_COLLECTION]

def _collection() -> Collection:
    if _projects is None:
        raise RuntimeError("MongoDB has not been initialized.")
    return _projects

def save(pid, name, state):
    _collection().replace_one(
        {"_id": pid},
        {
            "_id": pid,
            "name": name,
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        upsert=True,
    )

def get(pid):
    row = _collection().find_one({"_id": pid}, {"_id": 0, "name": 1, "state": 1})
    return {"name": row["name"], "state": row["state"]} if row else None

def ping_db():
    if _client is None:
        raise RuntimeError("MongoDB has not been initialized.")
    _client.admin.command("ping")

def close_db():
    global _client, _projects
    if _client is not None:
        _client.close()
    _client = None
    _projects = None
