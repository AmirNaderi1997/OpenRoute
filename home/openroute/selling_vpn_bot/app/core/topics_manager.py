import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

TOPICS_FILE = Path("/app/topics.json")
MANAGER_GROUP_FILE = Path("/app/manager_group.json")

def load_topics() -> dict:
    if not TOPICS_FILE.exists():
        return {}
    try:
        with open(TOPICS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load topics: {e}")
        return {}

def save_topics(topics: dict):
    try:
        with open(TOPICS_FILE, "w") as f:
            json.dump(topics, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save topics: {e}")

def get_topic_id(topic_key: str) -> int | None:
    topics = load_topics()
    return topics.get(topic_key)

def set_topic_id(topic_key: str, thread_id: int):
    topics = load_topics()
    topics[topic_key] = thread_id
    save_topics(topics)

def clear_topics():
    save_topics({})

def get_manager_group_id() -> int | None:
    if MANAGER_GROUP_FILE.exists():
        try:
            with open(MANAGER_GROUP_FILE, "r") as f:
                payload = json.load(f)
            value = payload.get("manager_group_id")
            if value is not None:
                return int(value)
        except Exception as e:
            logger.error(f"Failed to load manager group id: {e}")

    if settings.MANAGER_GROUP_ID is None:
        return None

    try:
        return int(settings.MANAGER_GROUP_ID)
    except (TypeError, ValueError):
        logger.error("Invalid MANAGER_GROUP_ID in settings: %r", settings.MANAGER_GROUP_ID)
        return None

def set_manager_group_id(chat_id: int):
    try:
        with open(MANAGER_GROUP_FILE, "w") as f:
            json.dump({"manager_group_id": int(chat_id)}, f, indent=4)
        settings.MANAGER_GROUP_ID = str(chat_id)
    except Exception as e:
        logger.error(f"Failed to save manager group id: {e}")
