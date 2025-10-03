import requests
import time
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton
import threading
import asyncio
import re
from datetime import datetime, timedelta
import json
import os

# === НАСТРОЙКИ ===
DISCORD_CHANNEL_ID = "1407975317682917457"
DISCORD_USER_TOKEN = os.getenv("DISCORD_USER_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# === НАСТРОЙКИ ДЛЯ ПОДПИСКИ ===
CHANNEL_ID = "-1003166042604"

# Растения
PLANTS_RARITY = {
    "Cactus": "RARE", "Strawberry": "RARE", "Pumpkin": "EPIC", "Sunflower": "EPIC",
    "Dragon Fruit": "LEGENDARY", "Eggplant": "LEGENDARY", "Watermelon": "MYTHIC",
    "Grape": "MYTHIC", "Cocotank": "GODLY", "Carnivorous Plant": "GODLY",
    "Mr Carrot": "SECRET", "Tomatrio": "SECRET", "Shroombino": "SECRET"
}

# Эмодзи для растений
PLANTS_EMOJI = {
    "Cactus": "🌵", "Strawberry": "🍓", "Pumpkin": "🎃", "Sunflower": "🌻",
    "Dragon Fruit": "🐉", "Eggplant": "🍆", "Watermelon": "🍉", "Grape": "🍇",
    "Cocotank": "🥥", "Carnivorous Plant": "🌿", "Mr Carrot": "🥕",
    "Tomatrio": "🍅", "Shroombino": "🍄"
}

# Эмодзи для редкостей
RARITY_EMOJI = {
    "RARE": "🔵",
    "EPIC": "🟣", 
    "LEGENDARY": "🟡",
    "MYTHIC": "🔴",
    "GODLY": "🌈",
    "SECRET": "🔲"
}

# Порядок редкостей для меню
RARITY_ORDER = ["RARE", "EPIC", "LEGENDARY", "MYTHIC", "GODLY", "SECRET"]

# Глобальные переменные
current_stock = {}
last_restock_time = None
last_message_id = None
last_stock_message_id = None  # ID последнего сообщения о стоке
user_chat_ids = set()

# Файлы для сохранения данных
USERS_FILE = "users.json"
SETTINGS_FILE = "user_settings.json"

# === TELEGRAM БОТ ===
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
telegram_bot = telegram_app.bot

# Основная клавиатура
keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎯УЗНАТЬ СТОК🎯")],
        [KeyboardButton("⚙️ НАСТРОЙКИ")]
    ],
    resize_keyboard=True
)

# === СИСТЕМА НАСТРОЕК ПОЛЬЗОВАТЕЛЕЙ ===
def load_settings():
    """Загружает настройки пользователей из файла"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки настроек: {e}")
    return {}

def save_settings(settings):
    """Сохраняет настройки пользователей в файл"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения настроек: {e}")

def get_user_settings(user_id):
    """Получает настройки пользователя"""
    settings = load_settings()
    if str(user_id) not in settings:
        settings[str(user_id)] = {
            "ignored_rarities": [],
            "created_at": datetime.now().isoformat()
        }
        save_settings(settings)
    return settings[str(user_id)]

def update_user_settings(user_id, new_settings):
    """Обновляет настройки пользователя"""
    settings = load_settings()
    settings[str(user_id)] = new_settings
    save_settings(settings)

def filter_stock_by_settings(stock_data, ignored_rarities):
    """Фильтрует сток по игнорируемым редкостям"""
    if not ignored_rarities:
        return stock_data
    
    filtered_stock = {}
    for plant, stock in stock_data.items():
        rarity = PLANTS_RARITY.get(plant)
        if rarity not in ignored_rarities:
            filtered_stock[plant] = stock
    
    return filtered_stock

def should_notify_user(stock_data, ignored_rarities):
    """Определяет, нужно ли уведомлять пользователя"""
    if not stock_data:
        return False
    
    if not ignored_rarities:
        return True
    
    # Проверяем, есть ли хоть одно растение с неигнорируемой редкостью
    for plant in stock_data.keys():
        rarity = PLANTS_RARITY.get(plant)
        if rarity not in ignored_rarities:
            return True
    
    return False

# === ВРЕМЕННЫЕ НАСТРОЙКИ ДЛЯ РЕДАКТИРОВАНИЯ ===
temp_settings = {}

def get_temp_settings(user_id):
    """Получает временные настройки пользователя"""
    if user_id not in temp_settings:
        # Копируем текущие настройки во временные
        current_settings = get_user_settings(user_id)
        temp_settings[user_id] = current_settings.copy()
    return temp_settings[user_id]

def save_temp_settings(user_id, new_settings):
    """Сохраняет временные настройки"""
    temp_settings[user_id] = new_settings

def apply_temp_settings(user_id):
    """Применяет временные настройки как постоянные"""
    if user_id in temp_settings:
        update_user_settings(user_id, temp_settings[user_id])
        # Удаляем временные настройки после применения
        del temp_settings[user_id]
        return True
    return False

def toggle_rarity_ignore_temp(user_id, rarity):
    """Переключает игнорирование редкости во временных настройках"""
    user_settings = get_temp_settings(user_id)
    ignored_rarities = user_settings.get("ignored_rarities", [])
    
    if rarity in ignored_rarities:
        ignored_rarities.remove(rarity)
    else:
        ignored_rarities.append(rarity)
    
    user_settings["ignored_rarities"] = ignored_rarities
    save_temp_settings(user_id, user_settings)
    return ignored_rarities

# === МЕНЮ НАСТРОЕК ===
async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню настроек"""
    user_id = update.effective_user.id
    
    # Получаем временные настройки (не сохраняем в файл пока не подтвердят)
    user_settings = get_temp_settings(user_id)
    ignored_rarities = user_settings.get("ignored_rarities", [])
    
    text = "⚙️ *НАСТРОЙКИ УВЕДОМЛЕНИЙ*\n\n"
    text += "🎯 *Выбери редкости которые хочешь игнорировать:*\n\n"
    
    if not ignored_rarities:
        text += "🔕 *Игнорируемые редкости:* Нет\n\n"
    else:
        text += "🔕 *Игнорируемые редкости:*\n"
        for rarity in ignored_rarities:
            emoji = RARITY_EMOJI.get(rarity, "⚪")
            text += f"├─ {emoji} {rarity}\n"
        text += "\n"
    
    text += "💡 *Настройки сохранятся только после нажатия '✅ Подтвердить'*"

    # Создаем клавиатуру для выбора редкостей
    keyboard_buttons = []
    for rarity in RARITY_ORDER:
        emoji = RARITY_EMOJI.get(rarity, "⚪")
        if rarity in ignored_rarities:
            button_text = f"✅ {emoji} {rarity}"
        else:
            button_text = f"❌ {emoji} {rarity}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"toggle_{rarity}")])
    
    keyboard_buttons.append([InlineKeyboardButton("📊 Показать текущий сток с фильтром", callback_data="test_filter")])
    keyboard_buttons.append([InlineKeyboardButton("✅ Подтвердить изменения", callback_data="confirm_changes")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия в меню настроек"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data.startswith("toggle_"):
        rarity = data.replace("toggle_", "")
        ignored_rarities = toggle_rarity_ignore_temp(user_id, rarity)
        
        # Показываем обновленное меню
        await show_settings_menu(update, context)
        
    elif data == "test_filter":
        # Тестируем фильтр на текущем стоке с временными настройками
        await test_user_filter(update, context)
        
    elif data == "confirm_changes":
        # Подтверждаем изменения и сохраняем настройки
        if apply_temp_settings(user_id):
            user_settings = get_user_settings(user_id)
            ignored_count = len(user_settings.get("ignored_rarities", []))
            
            # Удаляем сообщение с настройками
            try:
                await query.message.delete()
            except Exception as e:
                print(f"❌ Не удалось удалить сообщение: {e}")
            
            # Отправляем подтверждение
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Настройки сохранены!*\n\n"
                     f"🔕 Игнорируемых редкостей: {ignored_count}\n\n"
                     f"Теперь ты будешь получать уведомления только о выбранных редкостях!",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Не удалось сохранить настройки", show_alert=True)

async def test_user_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает как будет выглядеть сток с текущими настройками"""
    user_id = update.effective_user.id
    
    # Используем временные настройки для теста
    user_settings = get_temp_settings(user_id)
    ignored_rarities = user_settings.get("ignored_rarities", [])
    
    # Получаем текущий сток
    stock_data, time_info = get_latest_stock()
    
    if stock_data:
        # Применяем фильтр пользователя
        filtered_stock = filter_stock_by_settings(stock_data, ignored_rarities)
        
        if filtered_stock:
            telegram_message = create_telegram_message(filtered_stock, time_info, is_alert=False)
            await update.callback_query.message.reply_text(
                telegram_message,
                parse_mode='Markdown'
            )
        else:
            await update.callback_query.message.reply_text(
                "🌫️ *С твоими настройками этот сток пуст!*\n\n"
                "Все растения в этом стоке находятся в твоем списке игнорируемых редкостей.",
                parse_mode='Markdown'
            )
    else:
        await update.callback_query.message.reply_text("❌ Не удалось получить сток")

# === ОБНОВЛЕННЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ФИЛЬТРАМИ ===
async def send_telegram_alert_to_all(stock_data):
    """Отправляет уведомления всем пользователям с учетом их настроек"""
    if not user_chat_ids:
        print("📭 Нет пользователей для рассылки")
        return
    
    print(f"📤 Начинаем рассылку для {len(user_chat_ids)} пользователей...")
    
    tasks = []
    for chat_id in list(user_chat_ids):
        # Используем только сохраненные настройки (не временные)
        user_settings = get_user_settings(chat_id)
        ignored_rarities = user_settings.get("ignored_rarities", [])
        
        # Проверяем, нужно ли уведомлять этого пользователя
        if should_notify_user(stock_data, ignored_rarities):
            # Фильтруем сток для этого пользователя
            user_stock = filter_stock_by_settings(stock_data, ignored_rarities)
            user_message = create_telegram_message(user_stock, last_restock_time, is_alert=True)
            
            tasks.append(send_single_message(chat_id, user_message))
        else:
            print(f"🔇 Пропускаем пользователя {chat_id} - все редкости игнорируются")
    
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        sent_count = 0
        for i, result in enumerate(results):
            chat_id = list(user_chat_ids)[i]
            if isinstance(result, Exception):
                user_chat_ids.discard(chat_id)
            else:
                sent_count += 1
        
        save_users()
        print(f"📊 Рассылка завершена: отправлено {sent_count} сообщений")
    else:
        print("🔇 Нет пользователей для уведомления")

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает запрос стока с учетом фильтров"""
    print("🎯 Запрос текущего стока от пользователя")
    
    processing_msg = await update.message.reply_text("⏳ Получаем сток...")
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        await processing_msg.delete()
        text, reply_markup = create_subscription_message()
        await update.message.reply_text(text, reply_markup=reply_markup)
        return
    
    add_user(update.message.chat_id)
    
    # Используем только сохраненные настройки (не временные)
    user_settings = get_user_settings(user_id)
    ignored_rarities = user_settings.get("ignored_rarities", [])
    
    # Получаем последний известный сток
    stock_data, time_info = get_latest_stock()
    
    if stock_data:
        # Применяем фильтр пользователя
        filtered_stock = filter_stock_by_settings(stock_data, ignored_rarities)
        
        if filtered_stock:
            telegram_message = create_telegram_message(filtered_stock, time_info, is_alert=False)
            await processing_msg.delete()
            await update.message.reply_text(
                telegram_message, 
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            print("✅ Отправлен отфильтрованный сток")
        else:
            await processing_msg.delete()
            await update.message.reply_text(
                "🌫️ *Ой, а здесь пусто!*\n\n"
                "В текущем стоке только растения с редкостями которые ты игнорируешь.\n\n"
                "Хочешь изменить настройки? Нажми кнопку ⚙️ НАСТРОЙКИ",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    else:
        await processing_msg.delete()
        await update.message.reply_text("❌ Не удалось получить сток", reply_markup=keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        text, reply_markup = create_subscription_message()
        await update.message.reply_text(text, reply_markup=reply_markup)
        return
    
    add_user(update.message.chat_id)
    
    if update.message.text == "🎯УЗНАТЬ СТОК🎯":
        await handle_button_click(update, context)
    elif update.message.text == "⚙️ НАСТРОЙКИ":
        await show_settings_menu(update, context)
    else:
        await update.message.reply_text("Используй кнопки для навигации 🎯", reply_markup=keyboard)

# === ФИКС ДЛЯ ASYNCIO ===
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки"""
    error_msg = str(context.error)
    # Игнорируем ошибки event loop чтобы не засорять логи
    if "event loop" in error_msg.lower() or "runtimeerror" in error_msg.lower():
        return
    print(f"❌ Ошибка бота: {context.error}")

# === НОВАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ПОСЛЕДНЕГО СТОКА ===
def get_latest_stock():
    """Получает последний известный сток (ищет в истории сообщений если нужно)"""
    global current_stock, last_restock_time, last_stock_message_id
    
    # Если у нас уже есть актуальный сток в памяти, возвращаем его
    if current_stock and last_restock_time:
        print("📊 Используем сток из памяти")
        return current_stock, last_restock_time
    
    # Иначе ищем сток в Discord
    print("🔍 Ищем сток в Discord...")
    messages = get_discord_messages(limit=10)  # Смотрим последние 10 сообщений
    
    for message in messages:
        embeds = message.get('embeds', [])
        for embed in embeds:
            if embed.get('title') == 'SEEDS SHOP RESTOCK!':
                message_timestamp = message.get('timestamp')
                stock_data, time_info = extract_stock_info_from_embed(embed, message_timestamp)
                
                if stock_data:
                    print(f"✅ Найден сток в истории: {list(stock_data.keys())}")
                    current_stock = stock_data
                    last_restock_time = time_info
                    last_stock_message_id = message['id']
                    return stock_data, time_info
    
    print("❌ Сток не найден в истории")
    return None, None

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ МОНИТОРИНГА ===
def monitor_discord():
    global current_stock, last_restock_time, last_message_id, last_stock_message_id
    
    print("🕵️ Запускаем мониторинг Discord канала...")
    
    initial_message = get_latest_discord_message()
    if initial_message:
        last_message_id = initial_message['id']
        print(f"📝 Начальное сообщение: {last_message_id}")
    
    while True:
        try:
            message = get_latest_discord_message()
            
            if message:
                current_message_id = message['id']
                
                if current_message_id != last_message_id:
                    print(f"🆕 ОБНАРУЖЕНО НОВОЕ СООБЩЕНИЕ: {current_message_id}")
                    last_message_id = current_message_id
                    
                    embeds = message.get('embeds', [])
                    stock_found = False
                    
                    for embed in embeds:
                        if embed.get('title') == 'SEEDS SHOP RESTOCK!':
                            print("🎯 НАЙДЕН СТОК В EMBED!")
                            stock_found = True
                            
                            message_timestamp = message.get('timestamp')
                            stock_data, time_info = extract_stock_info_from_embed(embed, message_timestamp)
                            
                            if stock_data:
                                print(f"📊 ОБНАРУЖЕН НОВЫЙ СТОК! Растения: {list(stock_data.keys())}")
                                
                                current_stock = stock_data
                                last_restock_time = time_info
                                last_stock_message_id = current_message_id
                                
                                # Запускаем рассылку в отдельном потоке
                                threading.Thread(
                                    target=lambda: asyncio.run(send_telegram_alert_to_all(stock_data)),
                                    daemon=True
                                ).start()
                            break
                    
                    if not stock_found:
                        print("📭 Последнее сообщение не о стоке - игнорируем")
            
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ ===
async def check_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            member = await telegram_bot.get_chat_member(CHANNEL_ID, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                return True
            else:
                return False
        except Exception as e:
            error_msg = str(e)
            # Если это ошибка event loop, пробуем еще раз после задержки
            if "event loop" in error_msg.lower() or "runtimeerror" in error_msg.lower():
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                print(f"⚠️ Ошибка асинхронности для пользователя {user_id} после {max_retries} попыток")
                # Возвращаем True чтобы не блокировать пользователя
                return True
            else:
                print(f"❌ Ошибка проверки подписки для пользователя {user_id}: {e}")
                return True
    return True

def create_subscription_message():
    """Создает сообщение с кнопками для подписки"""
    text = """
🔒 Для доступа к стоку нужно подписаться на канал

📢 Подпишитесь на канал и получайте:
• Уведомления о новом стоке
• Актуальную информацию о растениях
• Обновления первыми
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/PlantsVersusBrainrotsSTOCK")],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_subscription")]
    ])
    
    return text, keyboard

async def handle_subscription_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает проверку подписки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        try:
            await query.message.delete()
        except:
            pass
        
        add_user(user_id)
        await show_current_stock(user_id, context)
    else:
        text, reply_markup = create_subscription_message()
        await query.edit_message_text(
            "❌ Подписка не найдена. Пожалуйста, подпишитесь на канал и попробуйте снова.\n\n" + text,
            reply_markup=reply_markup
        )

async def show_current_stock(user_id, context):
    """Показывает текущий сток пользователю"""
    stock_data, time_info = get_latest_stock()
    
    if stock_data:
        telegram_message = create_telegram_message(stock_data, time_info, is_alert=False)
        await context.bot.send_message(
            chat_id=user_id,
            text=telegram_message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Не удалось получить сток",
            reply_markup=keyboard
        )

def load_users():
    global user_chat_ids
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                user_chat_ids = set(data.get('users', []))
                print(f"📊 Загружено {len(user_chat_ids)} пользователей")
    except:
        user_chat_ids = set()
        print("❌ Ошибка загрузки пользователей")

def save_users():
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump({'users': list(user_chat_ids)}, f)
        print(f"💾 Сохранено {len(user_chat_ids)} пользователей")
    except:
        print("❌ Ошибка сохранения пользователей")

def add_user(chat_id):
    if chat_id not in user_chat_ids:
        user_chat_ids.add(chat_id)
        save_users()
        print(f"👤 Добавлен новый пользователь: {chat_id}")

def get_latest_discord_message():
    headers = {
        'Authorization': DISCORD_USER_TOKEN,
        'Content-Type': 'application/json',
    }
    
    url = f'https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages?limit=1'
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            messages = response.json()
            if messages:
                return messages[0]
        return None
    except Exception as e:
        print(f"❌ Ошибка подключения к Discord: {e}")
        return None

def get_discord_messages(limit=10):
    """Получает несколько последних сообщений из Discord"""
    headers = {
        'Authorization': DISCORD_USER_TOKEN,
        'Content-Type': 'application/json',
    }
    
    url = f'https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages?limit={limit}'
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"❌ Ошибка подключения к Discord: {e}")
        return []

def convert_to_msk(discord_time_str):
    try:
        if "@" in discord_time_str:
            date_part, time_part = discord_time_str.split('@')
            day, month, year = date_part.strip().split('/')
            hour, minute = time_part.strip().replace('GMT', '').strip().split(':')
            
            dt_utc = datetime(int(year), int(month), int(day), int(hour), int(minute))
            dt_msk = dt_utc + timedelta(hours=3)
            return dt_msk.strftime("%d/%m/%Y %H:%M")
        else:
            return discord_time_str
    except:
        return discord_time_str

def extract_stock_info_from_embed(embed, message_timestamp):
    stock_data = {}
    current_time = ""
    
    author = embed.get('author', {})
    if author and 'name' in author:
        author_name = author['name']
        if "⏳" in author_name:
            discord_time = author_name.replace('⏳', '').strip()
            current_time = convert_to_msk(discord_time)
            print(f"⏰ Время из Discord: {discord_time} -> МСК: {current_time}")
    
    if not current_time:
        current_time = datetime.now().strftime("%d/%m/%Y %H:%M")
        print(f"⏰ Используем текущее время МСК: {current_time}")
    
    fields = embed.get('fields', [])
    for field in fields:
        plant_name = field.get('name', '')
        plant_value = field.get('value', '')
        
        clean_plant_name = re.sub(r'[^\w\s]', '', plant_name).strip()
        
        stock_match = re.search(r'\+\d+', plant_value)
        if stock_match:
            stock_count = int(stock_match.group(0).replace('+', ''))
            
            for known_plant in PLANTS_RARITY.keys():
                if known_plant.lower() in clean_plant_name.lower():
                    stock_data[known_plant] = stock_count
                    print(f"✅ {known_plant}: {stock_count} шт")
                    break
    
    return stock_data, current_time

def create_telegram_message(stock_data, time_info, is_alert=False):
    if not stock_data:
        return "📭 В последнем сообщении нет данных о стоке"
    
    if is_alert:
        message_text = "🔥 **НОВЫЙ СТОК ОБНАРУЖЕН!** 🔥\n\n"
    else:
        message_text = "☔️ **АКТУАЛЬНЫЙ СТОК** ☔️\n\n"
    
    message_text += f"⏰ *Обновлено: {time_info} МСК*\n\n"
    message_text += "🎯 **ДОСТУПНЫЕ РАСТЕНИЯ:**\n\n"
    
    rarity_groups = {}
    for plant, stock in stock_data.items():
        rarity = PLANTS_RARITY.get(plant)
        if rarity not in rarity_groups:
            rarity_groups[rarity] = []
        rarity_groups[rarity].append((plant, stock))
    
    rarity_order = ["RARE", "EPIC", "LEGENDARY", "MYTHIC", "GODLY", "SECRET"]
    
    for rarity in rarity_order:
        if rarity in rarity_groups and rarity_groups[rarity]:
            emoji = RARITY_EMOJI.get(rarity, "🌟")
            message_text += f"{emoji} **{rarity}**\n"
            for plant, stock in rarity_groups[rarity]:
                plant_emoji = PLANTS_EMOJI.get(plant, "🌱")
                message_text += f"├─ {plant_emoji} {plant} ×{stock}\n"
            message_text += "\n"
    
    message_text += "⚡ Успей приобрести!\n\n"
    message_text += "📢 *Присоединяйтесь к нашему сообществу:*\n"
    message_text += "👉 Канал: @PlantsVersusBrainrotsSTOCK\n"
    message_text += "💬 Чат: @PlantsVersusBrainrotSTOCKCHAT"
    
    return message_text

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ ОТПРАВКИ ===
async def send_single_message(chat_id, message):
    try:
        # Пропускаем проверку подписки в рассылке чтобы избежать ошибок асинхронности
        await telegram_bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки пользователю {chat_id}: {e}")
        return False

async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Использование: /ALL <сообщение>")
        return
    
    message_text = " ".join(context.args)
    broadcast_message = f"📢 **ОБЪЯВЛЕНИЕ:**\n\n{message_text}"
    
    print(f"🔄 Начинаю рассылку сообщения для {len(user_chat_ids)} пользователей...")
    
    tasks = []
    for chat_id in list(user_chat_ids):
        tasks.append(send_broadcast_message(context, chat_id, broadcast_message))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    sent_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = len(results) - sent_count
    
    await update.message.reply_text(
        f"📊 Рассылка завершена:\n✅ Отправлено: {sent_count}\n❌ Ошибок: {error_count}"
    )

async def send_broadcast_message(context, chat_id, message):
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
        return True
    except:
        return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        text, reply_markup = create_subscription_message()
        await update.message.reply_text(
            "👋 Добро пожаловать!\n\n" + text,
            reply_markup=reply_markup
        )
        return
    
    add_user(update.message.chat_id)
    
    welcome_text = """
🤖 Бот для отслеживания стока Plants Vs Brainrots

🎯 Нажми кнопку чтобы узнать текущий сток
⚙️ Настрой уведомления по редкостям
📢 Канал: @PlantsVersusBrainrotsSTOCK
💬 Чат: @PlantsVersusBrainrotSTOCKCHAT
    """
    await update.message.reply_text(welcome_text, reply_markup=keyboard)

def run_telegram_bot():
    print("📱 Запускаем Telegram бота...")
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("all", admin_broadcast_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(CallbackQueryHandler(handle_subscription_check, pattern="check_subscription"))
    telegram_app.add_handler(CallbackQueryHandler(handle_settings_callback, pattern="^(toggle_|test_filter|confirm_changes)"))
    telegram_app.add_error_handler(error_handler)
    telegram_app.run_polling()

def main():
    print("🚀 ЗАПУСКАЕМ БОТА PLANTS VS BRAINROTS!")
    print("=" * 50)
    print("🤖 Бот для отслеживания стока растений")
    print("⚙️ Система фильтрации по редкостям")
    print("📊 Мониторинг Discord канала")
    print("🔔 Умные уведомления о новом стоке")
    print("=" * 50)
    
    load_users()
    
    print("🌀 Запускаем мониторинг Discord...")
    discord_thread = threading.Thread(target=monitor_discord, daemon=True)
    discord_thread.start()
    
    print("✅ ВСЕ СИСТЕМЫ ЗАПУЩЕНЫ! БОТ РАБОТАЕТ!")
    print("⏳ Ожидаем сообщения от пользователей...")
    
    run_telegram_bot()

if __name__ == "__main__":
    main()