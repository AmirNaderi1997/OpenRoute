import argparse
import asyncio
import json

from app.bot import bot
from app.bot.handlers.admin_features import TOPIC_DEFINITIONS
from app.core.topics_manager import clear_topics, get_manager_group_id, set_topic_id


async def main(min_thread_id: int, max_thread_id: int) -> None:
    group_id = get_manager_group_id()
    if group_id is None:
        raise RuntimeError("manager group id is not set")

    for thread_id in range(min_thread_id, max_thread_id + 1):
        try:
            await bot.close_forum_topic(chat_id=group_id, message_thread_id=thread_id)
        except Exception:
            pass

        try:
            await bot.delete_forum_topic(chat_id=group_id, message_thread_id=thread_id)
        except Exception:
            pass

    clear_topics()

    created_topics: dict[str, int] = {}
    for topic_key, topic_name in TOPIC_DEFINITIONS:
        created = await bot.create_forum_topic(chat_id=group_id, name=topic_name)
        set_topic_id(topic_key, created.message_thread_id)
        created_topics[topic_key] = created.message_thread_id

    print(json.dumps({"group_id": group_id, "topics": created_topics}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-thread-id", type=int, default=100)
    parser.add_argument("--max-thread-id", type=int, default=140)
    args = parser.parse_args()

    try:
        asyncio.run(main(args.min_thread_id, args.max_thread_id))
    finally:
        asyncio.run(bot.session.close())
