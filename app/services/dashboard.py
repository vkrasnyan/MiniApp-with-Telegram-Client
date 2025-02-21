import logging
from telethon import functions, types

logger = logging.getLogger(__name__)


async def get_dialogs_info(user_client):
    try:
        dialogs = await user_client.get_dialogs()
        all_channels, all_groups, all_private_chats = [], [], []

        for dialog in dialogs:
            entity = dialog.entity

            if dialog.is_channel and entity.username:
                all_channels.append({
                    "id": entity.id,
                    "name": f"@{entity.username}",
                    "participants_count": getattr(entity, "participants_count", 0),
                    "unread_count": dialog.unread_count
                })
            elif dialog.is_group:
                group_name = getattr(entity, 'title', f"Группа {entity.id}")
                all_groups.append({
                    "id": entity.id,
                    "name": group_name,
                    "participants_count": getattr(entity, "participants_count", 0),
                    "unread_count": dialog.unread_count
                })
            elif dialog.is_user:
                user_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                all_private_chats.append({
                    "id": entity.id,
                    "name": user_name,
                    "participants_count": 1,
                    "unread_count": dialog.unread_count
                })

        logger.info(f"Найдено {len(all_channels)} каналов, {len(all_groups)} групп и {len(all_private_chats)} личных чатов.")
        return all_channels, all_groups, all_private_chats
    except Exception as e:
        logger.error(f"Ошибка при получении диалогов: {e}")
        return [], [], []


def sort_dialogs(all_channels, all_groups, all_private_chats, sort_by):
    if sort_by == "participants":
        all_channels.sort(key=lambda x: x["participants_count"], reverse=True)
        all_groups.sort(key=lambda x: x["participants_count"], reverse=True)
        all_private_chats.sort(key=lambda x: x["participants_count"], reverse=True)
    elif sort_by == "unread":
        all_channels.sort(key=lambda x: x["unread_count"], reverse=True)
        all_groups.sort(key=lambda x: x["unread_count"], reverse=True)
        all_private_chats.sort(key=lambda x: x["unread_count"], reverse=True)


async def get_dialog_filters(user_client):
    groups_with_channels = []
    try:
        dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
        existing_filters = dialog_filters.filters if dialog_filters.filters else []
        logger.info(f"Получено {len(existing_filters)} фильтров диалогов.")

        for dialog_filter in existing_filters:
            group_channels = []
            filter_title = getattr(dialog_filter, 'title', f"Фильтр {getattr(dialog_filter, 'id', 'unknown')}")
            include_peers = getattr(dialog_filter, 'include_peers', [])

            logger.info(f"Фильтр: {filter_title}, количество include_peers: {len(include_peers)}")

            for included_peer in include_peers:
                try:
                    entity = await get_entity_from_peer(user_client, included_peer)
                    if entity:
                        group_channels.append(entity)
                except Exception as e:
                    logger.error(f"Ошибка при обработке peer {included_peer}: {e}")
                    continue

            groups_with_channels.append({
                "filter_name": filter_title,
                "channels": group_channels
            })
        return groups_with_channels, existing_filters
    except Exception as e:
        logger.error(f"Ошибка при получении фильтров диалогов: {e}")
        return [], []


async def get_entity_from_peer(user_client, included_peer):
    try:
        if isinstance(included_peer, types.InputPeerChannel):
            entity = await user_client.get_input_entity(included_peer)
        elif isinstance(included_peer, types.InputPeerUser):
            entity = await user_client.get_input_entity(included_peer)
        elif isinstance(included_peer, types.InputPeerChat):
            entity = await user_client.get_input_entity(included_peer)
        else:
            logger.warning(f"Неизвестный тип peer: {included_peer}")
            return None

        if isinstance(entity, types.Channel):
            return f"@{entity.username}" if entity.username else f"{entity.title} (ID: {entity.id})"
        elif isinstance(entity, types.User):
            return f"{entity.first_name or ''} {entity.last_name or ''} (ID: {entity.id})"
        elif isinstance(entity, types.Chat):
            return f"{entity.title} (ID: {entity.id})"
        else:
            logger.warning(f"Неизвестный тип сущности: {type(entity)}")
            return None
    except ValueError:
        logger.error(f"Ошибка: не найден entity для {included_peer}. Возможно, отсутствует access_hash.")
    return None
