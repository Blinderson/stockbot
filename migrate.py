import json
import os
import sys

# Добавляем путь к текущей папке для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import db

def migrate_from_json():
    """Миграция данных из JSON файлов в PostgreSQL"""
    print("🔄 Начинаем миграцию данных из JSON в PostgreSQL...")
    
    # Проверяем подключение к БД
    if not db.conn:
        print("❌ Нет подключения к PostgreSQL!")
        return
    
    # Миграция пользователей
    try:
        if os.path.exists('users.json'):
            with open('users.json', 'r', encoding='utf-8') as f:
                users_data = json.load(f)
            
            user_ids = users_data.get('users', [])
            print(f"📊 Найдено {len(user_ids)} пользователей для миграции")
            
            success_count = 0
            for i, user_id in enumerate(user_ids, 1):
                if db.add_user(user_id):
                    success_count += 1
                if i % 50 == 0:
                    print(f"✅ Мигрировано {i}/{len(user_ids)} пользователей")
            
            print(f"✅ Миграция пользователей завершена: {success_count}/{len(user_ids)}")
        else:
            print("❌ Файл users.json не найден")
    except Exception as e:
        print(f"❌ Ошибка миграции пользователей: {e}")
    
    # Миграция настроек
    try:
        if os.path.exists('user_settings.json'):
            with open('user_settings.json', 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
            
            print(f"📊 Найдено {len(settings_data)} настроек для миграции")
            
            success_count = 0
            for i, (user_id_str, settings) in enumerate(settings_data.items(), 1):
                try:
                    user_id = int(user_id_str)
                    if db.update_user_settings(user_id, settings):
                        success_count += 1
                    if i % 50 == 0:
                        print(f"✅ Мигрировано {i}/{len(settings_data)} настроек")
                except ValueError:
                    print(f"⚠️ Пропущен невалидный user_id: {user_id_str}")
                except Exception as e:
                    print(f"⚠️ Ошибка миграции настроек для {user_id_str}: {e}")
            
            print(f"✅ Миграция настроек завершена: {success_count}/{len(settings_data)}")
        else:
            print("❌ Файл user_settings.json не найден")
    except Exception as e:
        print(f"❌ Ошибка миграции настроек: {e}")
    
    # Показываем статистику
    stats = db.get_user_stats()
    print(f"\n📈 Статистика после миграции:")
    print(f"   Всего пользователей: {stats.get('total_users', 0)}")
    print(f"   С настройками: {stats.get('users_with_settings', 0)}")
    print(f"   Без настроек: {stats.get('users_without_settings', 0)}")
    
    print("\n🎉 Миграция завершена!")

if __name__ == "__main__":
    migrate_from_json()
