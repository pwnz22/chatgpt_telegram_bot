# database.py - С поддержкой групповых настроек
from typing import Optional, Any
import pymongo
import uuid
from datetime import datetime, timedelta
import config


class Database:
    def __init__(self):
        self.client = pymongo.MongoClient(config.mongodb_uri)
        self.db = self.client["chatgpt_telegram_bot"]

        self.user_collection = self.db["user"]
        self.dialog_collection = self.db["dialog"]
        self.group_collection = self.db["group"]  # Новая коллекция для групп

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if self.user_collection.count_documents({"_id": user_id}) > 0:
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False

    def check_if_group_exists(self, group_id: int):
        """Проверить существование группы"""
        return self.group_collection.count_documents({"_id": group_id}) > 0

    def add_new_group(self, group_id: int, group_title: str = ""):
        """Добавить новую группу"""
        if not self.check_if_group_exists(group_id):
            group_dict = {
                "_id": group_id,
                "title": group_title,
                "current_chat_mode": "assistant",  # Режим по умолчанию для группы
                "created_at": datetime.now(),
                "last_interaction": datetime.now()
            }
            self.group_collection.insert_one(group_dict)

    def get_group_attribute(self, group_id: int, key: str):
        """Получить атрибут группы"""
        if not self.check_if_group_exists(group_id):
            return None

        group_dict = self.group_collection.find_one({"_id": group_id})
        return group_dict.get(key, None)

    def set_group_attribute(self, group_id: int, key: str, value: Any):
        """Установить атрибут группы"""
        if not self.check_if_group_exists(group_id):
            return False

        self.group_collection.update_one(
            {"_id": group_id},
            {"$set": {key: value}}
        )
        return True

    def get_chat_mode(self, user_id: int, chat_id: int = None):
        """Получить режим чата в зависимости от контекста (группа или приватный чат)"""
        if chat_id and chat_id < 0:  # Групповой чат (отрицательный ID)
            if self.check_if_group_exists(chat_id):
                return self.get_group_attribute(chat_id, "current_chat_mode") or "assistant"
            else:
                # Если группа не существует, создаем её с режимом по умолчанию
                self.add_new_group(chat_id)
                return "assistant"
        else:
            # Приватный чат - используем настройки пользователя
            return self.get_user_attribute(user_id, "current_chat_mode")

    def set_chat_mode(self, user_id: int, chat_mode: str, chat_id: int = None):
        """Установить режим чата в зависимости от контекста"""
        if chat_id and chat_id < 0:  # Групповой чат
            if not self.check_if_group_exists(chat_id):
                self.add_new_group(chat_id)
            self.set_group_attribute(chat_id, "current_chat_mode", chat_mode)
            self.set_group_attribute(chat_id, "last_interaction", datetime.now())
        else:
            # Приватный чат
            self.set_user_attribute(user_id, "current_chat_mode", chat_mode)

    def add_new_user(
            self,
            user_id: int,
            chat_id: int,
            username: str = "",
            first_name: str = "",
            last_name: str = "",
        ):
            user_dict = {
                "_id": user_id,
                "chat_id": chat_id,

                "username": username,
                "first_name": first_name,
                "last_name": last_name,

                "last_interaction": datetime.now(),
                "first_seen": datetime.now(),

                "current_dialog_id": None,
                "current_chat_mode": "assistant",
                "current_model": config.models["available_text_models"][0],
                "language": None,

                "n_used_tokens": {},

                "n_generated_images": 0,
                "n_transcribed_seconds": 0.0  # voice message transcription
            }

            if not self.check_if_user_exists(user_id):
                self.user_collection.insert_one(user_dict)

    def start_new_dialog(self, user_id: int, chat_id: int = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())

        # Получаем режим чата в зависимости от контекста
        chat_mode = self.get_chat_mode(user_id, chat_id)

        dialog_dict = {
            "_id": dialog_id,
            "user_id": user_id,
            "chat_id": chat_id,  # Добавляем chat_id для связи с группой
            "chat_mode": chat_mode,
            "start_time": datetime.now(),
            "model": self.get_user_attribute(user_id, "current_model"),
            "messages": []
        }

        # add new dialog
        self.dialog_collection.insert_one(dialog_dict)

        # update user's current dialog
        self.user_collection.update_one(
            {"_id": user_id},
            {"$set": {"current_dialog_id": dialog_id}}
        )

        return dialog_id

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        user_dict = self.user_collection.find_one({"_id": user_id})

        if key not in user_dict:
            # Для поля language возвращаем "en" по умолчанию
            if key == "language":
                return "en"
            return None

        return user_dict[key]

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        self.user_collection.update_one({"_id": user_id}, {"$set": {key: value}})

    def update_n_used_tokens(self, user_id: int, model: str, n_input_tokens: int, n_output_tokens: int):
        n_used_tokens_dict = self.get_user_attribute(user_id, "n_used_tokens")

        if model in n_used_tokens_dict:
            n_used_tokens_dict[model]["n_input_tokens"] += n_input_tokens
            n_used_tokens_dict[model]["n_output_tokens"] += n_output_tokens
        else:
            n_used_tokens_dict[model] = {
                "n_input_tokens": n_input_tokens,
                "n_output_tokens": n_output_tokens
            }

        self.set_user_attribute(user_id, "n_used_tokens", n_used_tokens_dict)

    def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        dialog_dict = self.dialog_collection.find_one({"_id": dialog_id, "user_id": user_id})
        return dialog_dict["messages"]

    def set_dialog_messages(self, user_id: int, dialog_messages: list, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        self.dialog_collection.update_one(
            {"_id": dialog_id, "user_id": user_id},
            {"$set": {"messages": dialog_messages}}
        )

    # ========================
    # МЕТОДЫ ДЛЯ ПОДПИСОК
    # ========================

    def get_user_subscription_status(self, user_id: int):
        """Получить статус подписки пользователя"""
        subscription = self.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })

        return subscription is not None

    def add_daily_usage(self, user_id: int, usage_type: str, amount: int = 1):
        """Добавить использование за день"""
        today = datetime.now().strftime("%Y-%m-%d")

        key = f"daily_usage.{today}.{usage_type}"
        self.user_collection.update_one(
            {"_id": user_id},
            {"$inc": {key: amount}},
            upsert=True
        )

    def get_daily_usage(self, user_id: int, usage_type: str) -> int:
        """Получить использование за сегодня"""
        today = datetime.now().strftime("%Y-%m-%d")

        user = self.user_collection.find_one({"_id": user_id})
        if not user:
            return 0

        daily_usage = user.get("daily_usage", {})
        return daily_usage.get(today, {}).get(usage_type, 0)

    def create_subscription(self, user_id: int, plan: str, duration_days: int):
        """Создать новую подписку"""
        subscription_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(days=duration_days)

        subscription = {
            "_id": subscription_id,
            "user_id": user_id,
            "plan": plan,
            "status": "active",
            "created_at": datetime.now(),
            "expires_at": expires_at,
            "payment_id": "test_payment"
        }

        self.db["subscriptions"].insert_one(subscription)
        return subscription_id

    def record_payment(self, user_id: int, amount: float, currency: str, subscription_id: str):
        """Записать платеж"""
        payment_id = str(uuid.uuid4())

        payment = {
            "_id": payment_id,
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
            "subscription_id": subscription_id,
            "telegram_payment_id": "test_charge_id",
            "created_at": datetime.now()
        }

        self.db["payments"].insert_one(payment)
        return payment_id

    def get_user_subscription_info(self, user_id: int):
        """Получить информацию о подписке пользователя"""
        return self.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })

    def cancel_subscription(self, user_id: int):
        """Отменить подписку"""
        self.db["subscriptions"].update_one(
            {
                "user_id": user_id,
                "status": "active"
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.now()
                }
            }
        )

    def get_subscription_stats(self):
        """Получить статистику по подпискам (для админа)"""
        total_subscriptions = self.db["subscriptions"].count_documents({"status": "active"})
        total_revenue = list(self.db["payments"].aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]))

        return {
            "active_subscriptions": total_subscriptions,
            "total_revenue": total_revenue[0]["total"] if total_revenue else 0
        }
