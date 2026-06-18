from vk_api.keyboard import VkKeyboard, VkKeyboardColor


def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🔍 Проверить подписку", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("🎁 Мой промокод", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📋 Мои промокоды", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🆘 Помощь", color=VkKeyboardColor.SECONDARY)
    return keyboard


def get_chat_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🚪 Выйти из чата", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def get_check_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button("✅ Я подписался", color=VkKeyboardColor.POSITIVE)
    return keyboard


def get_cancel_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    return keyboard
