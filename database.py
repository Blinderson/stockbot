import psycopg2
import os
import json
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn = None
        self.connect()
        self.init_tables()
    
    def connect(self):
        """Подключение к PostgreSQL"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Получаем строку подключения из переменных окружения
                database_url = os.getenv('DATABASE_URL')
                if not database_url:
                    logger.error("❌ DATABASE_URL не найден в переменных окружения")
                    return
                
                self.conn = psycopg2.connect(database_url)
                self.conn.autocommit = False
                logger.info("✅ Успешное подключение к PostgreSQL")
                break
                
            except Exception as e:
                logger.error(f"❌ Попытка {attempt + 1}/{max_retries}: Ошибка подключения к PostgreSQL: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                else:
                    logger.error("❌ Не удалось подключиться к PostgreSQL после всех попыток")
    
    def init_tables(self):
        """Создание таблиц если их нет"""
        if not self.conn:
            logger.error("❌ Нет подключения к БД для создания таблиц")
            return
            
        try:
            with self.conn.cursor() as cur:
                # Таблица пользователей
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица настроек пользователей
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                        ignored_rarities JSONB DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                self.conn.commit()
                logger.info("✅ Таблицы созданы/проверены")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            if self.conn:
                self.conn.rollback()
    
    def add_user(self, user_id):
        """Добавление пользователя"""
        if not self.conn:
            return False
            
        try:
            with self.conn.cursor() as cur:
                # Добавляем пользователя
                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO UPDATE SET last_active = CURRENT_TIMESTAMP",
                    (user_id,)
                )
                # Добавляем/обновляем настройки
                cur.execute(
                    """INSERT INTO user_settings (user_id, ignored_rarities) 
                    VALUES (%s, %s) 
                    ON CONFLICT (user_id) DO NOTHING""",
                    (user_id, json.dumps([]))
                )
                self.conn.commit()
                logger.info(f"✅ Пользователь {user_id} добавлен/обновлен")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя {user_id}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def get_user_settings(self, user_id):
        """Получение настроек пользователя"""
        if not self.conn:
            return self._get_default_settings()
            
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT ignored_rarities, created_at FROM user_settings WHERE user_id = %s",
                    (user_id,)
                )
                result = cur.fetchone()
                
                if result:
                    return {
                        "ignored_rarities": result[0] or [],
                        "created_at": result[1].isoformat() if result[1] else datetime.now().isoformat()
                    }
                else:
                    # Создаем настройки по умолчанию
                    self.add_user(user_id)
                    return self._get_default_settings()
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения настроек пользователя {user_id}: {e}")
            return self._get_default_settings()
    
    def _get_default_settings(self):
        """Настройки по умолчанию"""
        return {
            "ignored_rarities": [],
            "created_at": datetime.now().isoformat()
        }
    
    def update_user_settings(self, user_id, settings):
        """Обновление настроек пользователя"""
        if not self.conn:
            return False
            
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """UPDATE user_settings 
                    SET ignored_rarities = %s, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = %s""",
                    (json.dumps(settings.get("ignored_rarities", [])), user_id)
                )
                self.conn.commit()
                logger.info(f"✅ Настройки пользователя {user_id} обновлены")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления настроек пользователя {user_id}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def get_all_users(self):
        """Получение всех пользователей"""
        if not self.conn:
            return []
            
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users")
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователей: {e}")
            return []
    
    def get_user_stats(self):
        """Статистика пользователей"""
        if not self.conn:
            return {}
            
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total_users = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM user_settings WHERE ignored_rarities != '[]'::jsonb")
                users_with_settings = cur.fetchone()[0]
                
                return {
                    "total_users": total_users,
                    "users_with_settings": users_with_settings,
                    "users_without_settings": total_users - users_with_settings
                }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}

# Глобальный экземпляр БД
db = Database()
