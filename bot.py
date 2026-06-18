#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VK Promo Bot
Основной файл бота для выдачи промокодов подписчикам и поддержки чата.
"""

import vk_api
import time
import logging
import signal
from datetime import datetime
from vk_api.longpoll import VkLongPoll, VkEventType
from functools import wraps

from config import VK_TOKEN, GROUP_ID, PROMO_FILE, MAIN_ADMIN_ID
from database import Database
from keyboards import (
    get_main_keyboard,
    get_chat_keyboard,
    get_check_keyboard,
    get_cancel_keyboard,
)

# ---------- Настройка логирования ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

shutdown_flag = False


def signal_handler(signum, frame):
    global shutdown_flag
    logger.info(f"Получен сигнал {signum}. Завершаем работу...")
    shutdown_flag = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ---------- Декоратор повторных попыток ----------
def retry_on_exception(max_retries=3, delay=2, backoff=2, exceptions=(Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries == max_retries:
                        logger.error(f"Не удалось выполнить {func.__name__}: {e}")
                        raise
                    logger.warning(
                        f"Ошибка в {func.__name__}: {e}. Повтор через {current_delay}с"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None

        return wrapper

    return decorator


class SubscriptionBot:
    """Основной класс бота"""

    def __init__(self):
        self.db = Database()
        # Инициализация сессии и API сразу, чтобы избежать предупреждений IDE
        self.vk_session = vk_api.VkApi(token=VK_TOKEN)
        self.vk = self.vk_session.get_api()
        self.longpoll = None

        self.last_check_time = {}  # защита от спама
        self.user_state = {}  # состояния пользователей
        self.last_help_request_user = None  # последний обратившийся

        # Загрузка администраторов
        self.admin_ids = set(self.db.get_all_admins())
        if MAIN_ADMIN_ID not in self.admin_ids:
            self.db.add_admin(MAIN_ADMIN_ID)
            self.admin_ids.add(MAIN_ADMIN_ID)

        # Кэш активных чатов
        self._refresh_chat_cache()

        # Загрузка промокодов
        self.promocodes = self._load_promocodes()
        self.current_promocode = self.promocodes[0] if self.promocodes else None

    # ---------- Вспомогательные методы ----------
    def _refresh_chat_cache(self):
        """Обновить кэш активных чатов {user_id: admin_id}"""
        self.active_chats = {}
        for user_id, admin_id, _ in self.db.get_active_chats():
            self.active_chats[user_id] = admin_id

    def _load_promocodes(self):
        """Загрузить промокоды из файла"""
        try:
            with open(PROMO_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            logger.error(f"Файл {PROMO_FILE} не найден!")
            return []

    def is_admin(self, user_id):
        return user_id in self.admin_ids

    def is_in_chat(self, user_id):
        return user_id in self.active_chats

    def get_chat_admin(self, user_id):
        return self.active_chats.get(user_id, 0)

    # ---------- Отправка сообщений ----------
    @retry_on_exception(max_retries=3, delay=2)
    def send_message(self, user_id, message, keyboard=None):
        """Отправить сообщение пользователю с автоматическим повтором"""
        self.vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=int(time.time() * 1000),
            keyboard=keyboard.get_keyboard() if keyboard else None,
        )

    def _send_admin_notification(self, user_id, message_text):
        """Уведомить всех администраторов о новой заявке"""
        for admin_id in self.admin_ids:
            try:
                self.vk.messages.send(
                    user_id=admin_id,
                    message=f"📬 Новая заявка!\n👤 vk.com/id{user_id}\n📝 {message_text}\n\nЧтобы ответить, просто напишите текст боту.",
                    random_id=int(time.time() * 1000),
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить админа {admin_id}: {e}")

    # ---------- Проверка подписки ----------
    @retry_on_exception(max_retries=2, delay=1)
    def check_subscription(self, user_id):
        """Проверить, подписан ли пользователь на группу"""
        response = self.vk.groups.isMember(group_id=GROUP_ID, user_id=user_id)
        return response == 1

    # ---------- Обработчики команд пользователя ----------
    def handle_start(self, user_id):
        if self.db.user_already_received(user_id):
            self.send_message(
                user_id,
                "🎁 Вы уже получали промокод! Используйте кнопки ниже.",
                get_main_keyboard(),
            )
        else:
            self.send_message(
                user_id,
                f"🎉 Привет! Я бот для выдачи промокодов!\n\n"
                f"📌 Чтобы получить промокод, подпишитесь на сообщество и нажмите «🔍 Проверить подписку».\n"
                f"🔗 Ссылка: https://vk.com/club{GROUP_ID}",
                get_main_keyboard(),
            )

    def handle_check(self, user_id):
        now = time.time()
        if (
            user_id in self.last_check_time
            and (now - self.last_check_time[user_id]) < 3
        ):
            self.send_message(user_id, "⏳ Подождите пару секунд.", get_main_keyboard())
            return
        self.last_check_time[user_id] = now

        if self.db.user_already_received(user_id):
            self.send_message(
                user_id,
                "🎁 Вы уже получали промокод! Смотрите «Мои промокоды».",
                get_main_keyboard(),
            )
            return

        try:
            subscribed = self.check_subscription(user_id)
        except Exception as e:
            logger.error(f"Ошибка проверки для {user_id}: {e}")
            self.send_message(
                user_id,
                "⚠️ Не удалось проверить подписку. Попробуйте позже.",
                get_main_keyboard(),
            )
            return

        if not subscribed:
            self.send_message(
                user_id,
                f"❌ Вы не подписаны!\n👉 https://vk.com/club{GROUP_ID}\nПосле подписки нажмите «✅ Я подписался»",
                get_check_keyboard(),
            )
            return

        if self.current_promocode:
            self.db.save_promocode(user_id, self.current_promocode)
            self.send_message(
                user_id,
                f"✅ Отлично! Ваш промокод: {self.current_promocode}\n\n"
                f"✅ Скидка 10% на корзину нашей продукции\n"
                f"⚠️ Действителен только один раз!",
                get_main_keyboard(),
            )
        else:
            self.send_message(
                user_id,
                "😔 Промокод пока недоступен. Обратитесь к администратору.",
                get_main_keyboard(),
            )

    def handle_my_promo(self, user_id):
        promo = self.db.get_last_promocode(user_id)
        if promo:
            code, issued_at = promo
            self.send_message(
                user_id,
                f"🎁 Ваш последний промокод: {code}\n📅 Выдан: {issued_at[:10]}",
                get_main_keyboard(),
            )
        else:
            self.send_message(
                user_id, "Вы ещё не получали промокод.", get_main_keyboard()
            )

    def handle_my_promocodes(self, user_id):
        codes = self.db.get_user_promocodes(user_id)
        if not codes:
            self.send_message(user_id, "📭 У вас нет промокодов.", get_main_keyboard())
            return
        msg = "📋 Ваши промокоды:\n\n"
        for code, issued_at in codes[:10]:
            msg += f"• {code} — {issued_at[:10]}\n"
        if len(codes) > 10:
            msg += f"\n... и ещё {len(codes)-10}"
        self.send_message(user_id, msg, get_main_keyboard())

    def handle_help_start(self, user_id):
        if self.is_in_chat(user_id):
            self.send_message(
                user_id,
                "🆘 Вы уже в диалоге с оператором. Напишите вопрос.",
                get_chat_keyboard(),
            )
            return
        self.user_state[user_id] = "waiting_help"
        self.send_message(
            user_id,
            "🆘 Напишите текст обращения (макс. 1000 символов).\nДля отмены напишите «отмена».",
            get_main_keyboard(),
        )

    def handle_help_text(self, user_id, text):
        if text.lower() in ["отмена", "cancel"]:
            del self.user_state[user_id]
            self.send_message(user_id, "❌ Отменено.", get_main_keyboard())
            return
        if len(text) > 1000:
            self.send_message(
                user_id, "❌ Слишком длинное сообщение.", get_main_keyboard()
            )
            return
        self.db.save_help_request(user_id, text)
        self.db.start_chat_session(user_id, 0)
        self._refresh_chat_cache()
        del self.user_state[user_id]
        self._send_admin_notification(user_id, text)
        self.send_message(
            user_id,
            "✅ Заявка принята! Оператор ответит в ближайшее время.",
            get_chat_keyboard(),
        )
        self.last_help_request_user = user_id

    def handle_exit_chat(self, user_id):
        if self.is_in_chat(user_id):
            self.db.end_chat_session(user_id)
            self._refresh_chat_cache()
            self.send_message(user_id, "✅ Вы вышли из чата.", get_main_keyboard())
        else:
            self.send_message(user_id, "Вы не в чате.", get_main_keyboard())

    # ---------- Обработка сообщений администраторов ----------
    def handle_admin_message(self, user_id, text):
        if not self.is_admin(user_id):
            return False

        lower = text.lower()

        # Если админ в режиме ответа (после reply)
        if user_id in self.user_state and self.user_state[user_id].startswith(
            "reply_to_"
        ):
            target_id = int(self.user_state[user_id].split("_")[2])
            self._send_reply(target_id, user_id, text)
            del self.user_state[user_id]
            return True

        # Команды администратора
        if lower in ["заявки", "requests"]:
            self._show_requests(user_id)
            return True

        if lower.startswith("reply "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                self.send_message(
                    user_id, "❌ Формат: reply <user_id> <текст>", get_main_keyboard()
                )
                return True
            try:
                target = int(parts[1])
            except ValueError:
                self.send_message(
                    user_id, "❌ ID должен быть числом.", get_main_keyboard()
                )
                return True
            self._send_reply(target, user_id, parts[2])
            return True

        if lower in ["чаты", "chats"]:
            self._show_chats(user_id)
            return True

        if lower.startswith("endchat "):
            parts = text.split()
            if len(parts) < 2:
                self.send_message(
                    user_id, "❌ Укажите ID: endchat 123", get_main_keyboard()
                )
                return True
            try:
                target = int(parts[1])
            except ValueError:
                self.send_message(
                    user_id, "❌ ID должен быть числом.", get_main_keyboard()
                )
                return True
            if self.is_in_chat(target):
                self.db.end_chat_session(target)
                self._refresh_chat_cache()
                self.send_message(target, "🔒 Чат завершён.", get_main_keyboard())
                self.send_message(
                    user_id, f"✅ Чат с {target} завершён.", get_main_keyboard()
                )
            else:
                self.send_message(
                    user_id, "Пользователь не в чате.", get_main_keyboard()
                )
            return True

        # Управление администраторами (только главный)
        if user_id == MAIN_ADMIN_ID:
            if lower.startswith("addadmin "):
                parts = text.split()
                if len(parts) < 2:
                    self.send_message(
                        user_id, "❌ Укажите ID: addadmin 123", get_main_keyboard()
                    )
                    return True
                try:
                    new_admin = int(parts[1])
                except ValueError:
                    self.send_message(
                        user_id, "❌ ID должен быть числом.", get_main_keyboard()
                    )
                    return True
                self.db.add_admin(new_admin)
                self.admin_ids.add(new_admin)
                self.send_message(
                    user_id,
                    f"✅ Администратор {new_admin} добавлен.",
                    get_main_keyboard(),
                )
                return True
            if lower.startswith("removeadmin "):
                parts = text.split()
                if len(parts) < 2:
                    self.send_message(
                        user_id, "❌ Укажите ID: removeadmin 123", get_main_keyboard()
                    )
                    return True
                try:
                    rem_admin = int(parts[1])
                except ValueError:
                    self.send_message(
                        user_id, "❌ ID должен быть числом.", get_main_keyboard()
                    )
                    return True
                self.db.remove_admin(rem_admin)
                self.admin_ids.discard(rem_admin)
                self.send_message(
                    user_id,
                    f"✅ Администратор {rem_admin} удалён.",
                    get_main_keyboard(),
                )
                return True

        # Если админ просто написал текст — ищем, кому ответить
        target = self._find_chat_for_admin(user_id)
        if target:
            self._send_reply(target, user_id, text)
        else:
            self.send_message(
                user_id,
                "❗ Нет активных заявок. Используйте 'заявки'.",
                get_main_keyboard(),
            )
        return True

    def _find_chat_for_admin(self, admin_id):
        """Найти пользователя для ответа данному админу"""
        # Сначала чат, где этот админ уже назначен
        for uid, aid in self.active_chats.items():
            if aid == admin_id:
                return uid
        # Или последний запрос
        if self.last_help_request_user and self.is_in_chat(self.last_help_request_user):
            return self.last_help_request_user
        # Или любой чат без админа
        for uid, aid in self.active_chats.items():
            if aid == 0:
                return uid
        return None

    def _send_reply(self, target_id, admin_id, reply_text):
        """Отправить ответ пользователю и назначить админа"""
        try:
            self.send_message(
                target_id, f"📩 Ответ оператора:\n{reply_text}", get_chat_keyboard()
            )
            if self.is_in_chat(target_id):
                self.db.set_chat_admin(target_id, admin_id)
            else:
                self.db.start_chat_session(target_id, admin_id)
            self._refresh_chat_cache()
            self.db.mark_request_answered(target_id)
            self.send_message(
                admin_id,
                f"✅ Ответ отправлен пользователю {target_id}.",
                get_main_keyboard(),
            )
            self.last_help_request_user = target_id
        except Exception as e:
            self.send_message(admin_id, f"❌ Ошибка: {e}", get_main_keyboard())

    def _show_requests(self, admin_id):
        """Показать последние заявки"""
        self.db.cursor.execute(
            "SELECT id, user_id, message, created_at, answered FROM help_requests ORDER BY created_at DESC LIMIT 20"
        )
        rows = self.db.cursor.fetchall()
        if not rows:
            self.send_message(admin_id, "📭 Нет заявок.", get_main_keyboard())
            return
        msg = "📋 Последние заявки:\n\n"
        for req_id, uid, msg_text, created, answered in rows:
            status = "✅" if answered else "🆕"
            msg += f"{status} #{req_id} | {created[:16]}\n👤 vk.com/id{uid}\n📝 {msg_text[:100]}\n\n"
        msg += "Чтобы ответить, просто напишите текст боту."
        self.send_message(admin_id, msg, get_main_keyboard())

    def _show_chats(self, admin_id):
        """Показать активные чаты"""
        chats = self.db.get_active_chats()
        if not chats:
            self.send_message(admin_id, "📭 Нет активных чатов.", get_main_keyboard())
            return
        msg = "💬 Активные чаты:\n\n"
        for uid, aid, started_at in chats:
            admin_str = f"админ {aid}" if aid else "ожидает админа"
            msg += f"👤 vk.com/id{uid} — {admin_str}, с {started_at[:16]}\n"
        self.send_message(admin_id, msg, get_main_keyboard())

    # ---------- Основной цикл ----------
    def run(self):
        logger.info("Запуск бота...")
        while not shutdown_flag:
            try:
                self.longpoll = VkLongPoll(self.vk_session)
                logger.info(f"Бот запущен. Группа {GROUP_ID}")
                for event in self.longpoll.listen():
                    if shutdown_flag:
                        break
                    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                        user_id = event.user_id
                        text = event.text.strip()
                        logger.info(f"Сообщение от {user_id}: {text}")

                        # Отмена состояний
                        if (
                            text.lower() in ["отмена", "cancel"]
                            and user_id in self.user_state
                        ):
                            del self.user_state[user_id]
                            self.send_message(
                                user_id, "❌ Отменено.", get_main_keyboard()
                            )
                            continue

                        # Сообщение от админа
                        if self.handle_admin_message(user_id, text):
                            continue

                        # Если пользователь в чате — пересылаем админам
                        if self.is_in_chat(user_id):
                            if text.lower() in ["выйти из чата", "🚪 выйти из чата"]:
                                self.handle_exit_chat(user_id)
                            else:
                                admin_id = self.get_chat_admin(user_id)
                                admins = [admin_id] if admin_id != 0 else self.admin_ids
                                for aid in admins:
                                    try:
                                        self.vk.messages.send(
                                            user_id=aid,
                                            message=f"💬 Сообщение от vk.com/id{user_id}:\n{text}",
                                            random_id=int(time.time() * 1000),
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Ошибка пересылки админу {aid}: {e}"
                                        )
                                self.send_message(
                                    user_id,
                                    "✉️ Сообщение отправлено оператору.",
                                    get_chat_keyboard(),
                                )
                            continue

                        # Ожидание текста заявки
                        if (
                            user_id in self.user_state
                            and self.user_state[user_id] == "waiting_help"
                        ):
                            self.handle_help_text(user_id, text)
                            continue

                        # Обычные команды
                        lower = text.lower()
                        if lower in ["start", "начать", "/start"]:
                            self.handle_start(user_id)
                        elif lower in [
                            "проверить подписку",
                            "🔍 проверить подписку",
                            "я подписался",
                            "✅ я подписался",
                        ]:
                            self.handle_check(user_id)
                        elif lower in ["мой промокод", "промокод", "🎁 мой промокод"]:
                            self.handle_my_promo(user_id)
                        elif lower in ["мои промокоды", "📋 мои промокоды"]:
                            self.handle_my_promocodes(user_id)
                        elif lower in ["помощь", "🆘 помощь", "help"]:
                            self.handle_help_start(user_id)
                        else:
                            if self.db.user_already_received(user_id):
                                self.send_message(
                                    user_id,
                                    "🤔 Неизвестная команда. Используйте кнопки.",
                                    get_main_keyboard(),
                                )
                            else:
                                self.send_message(
                                    user_id,
                                    "Подпишитесь и нажмите «Проверить подписку».",
                                    get_main_keyboard(),
                                )

            except Exception as e:
                logger.error(f"Ошибка в цикле: {e}")
                if shutdown_flag:
                    break
                time.sleep(5)
                # Пересоздаём сессию при ошибке
                try:
                    self.vk_session = vk_api.VkApi(token=VK_TOKEN)
                    self.vk = self.vk_session.get_api()
                except Exception as sess_err:
                    logger.error(f"Ошибка пересоздания сессии: {sess_err}")

        self.db.close()
        logger.info("Бот остановлен")


def main():
    while not shutdown_flag:
        try:
            bot = SubscriptionBot()
            bot.run()
        except Exception as e:
            logger.critical(f"Критическая ошибка: {e}. Перезапуск через 10 сек.")
            time.sleep(10)
            if shutdown_flag:
                break


if __name__ == "__main__":
    main()
