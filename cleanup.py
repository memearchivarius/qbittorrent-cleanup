import requests
import time
import os
from datetime import datetime
import posixpath

# Конфигурация из переменных окружения
QB_URL = os.getenv('QB_URL', 'http://qbittorrent:8080')
QB_USER = os.getenv('QB_USER', 'admin')
QB_PASS = os.getenv('QB_PASS', 'adminadmin')
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
DELETE_FILES = os.getenv('DELETE_FILES', 'false').lower() == 'true'
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))

def login(session):
    r = session.post(f'{QB_URL}/api/v2/auth/login', data={'username': QB_USER, 'password': QB_PASS})
    if r.status_code != 200:
        raise Exception(f"Не удалось войти в qBittorrent Web UI: {r.text}")

def get_torrents(session):
    r = session.get(f'{QB_URL}/api/v2/torrents/info')
    return r.json()

def delete_torrent(session, torrent_hash):
    r = session.post(f'{QB_URL}/api/v2/torrents/delete', data={
        'hashes': torrent_hash,
        'deleteFiles': DELETE_FILES
    })
    return r.status_code == 200

def get_torrent_name_key(torrent):
    """
    Получает ключ для группировки торрентов по имени папки.
    Используем имя торрента как идентификатор папки.
    """
    save_path = torrent['save_path'].rstrip('/')  # Убираем слэш в конце если есть
    torrent_name = torrent['name']
    
    # Ключ группировки: путь + имя торрента
    return f"{save_path}/{torrent_name}"

def format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

def remove_old_torrents_with_same_name():
    session = requests.Session()
    try:
        login(session)
        torrents = get_torrents(session)

        # Группируем торренты по имени папки внутри save_path
        torrents_by_name = {}
        
        for t in torrents:
            torrent_key = get_torrent_name_key(t)
            
            if torrent_key not in torrents_by_name:
                torrents_by_name[torrent_key] = []
            torrents_by_name[torrent_key].append(t)

        deleted_count = 0
        
        # Для каждой группы с более чем 1 торрентом
        for torrent_key, torrents_list in torrents_by_name.items():
            if len(torrents_list) > 1:
                # Сортируем по времени добавления (чем меньше added_on, тем старше)
                torrents_list.sort(key=lambda x: x['added_on'])
                
                # Обрабатываем все, кроме последнего (самого нового)
                for old_torrent in torrents_list[:-1]:
                    torrent_info = f"Torrent: {old_torrent['name']} | Added: {format_timestamp(old_torrent['added_on'])} | Key: {torrent_key}"
                    
                    if DRY_RUN:
                        print(f"[DRY RUN] Будет удален: {torrent_info}")
                    else:
                        print(f"[УДАЛЕНИЕ] Удаляем: {torrent_info}")
                        if delete_torrent(session, old_torrent['hash']):
                            deleted_count += 1
                        else:
                            print(f"[ОШИБКА] Не удалось удалить торрент: {old_torrent['name']}")
        
        if DRY_RUN:
            print(f"[DRY RUN] Завершено. В режиме просмотра удалено бы: {deleted_count} торрентов")
        else:
            print(f"[ГОТОВО] Удалено торрентов: {deleted_count}")
            
    except Exception as e:
        print(f"[ОШИБКА] {str(e)}")

def main():
    print(f"=== qBittorrent Cleanup Service ===")
    print(f"QB_URL: {QB_URL}")
    print(f"DRY RUN: {DRY_RUN}")
    print(f"DELETE_FILES: {DELETE_FILES}")
    print(f"CHECK_INTERVAL: {CHECK_INTERVAL} секунд")
    print(f"================================")
    
    if DRY_RUN:
        print("[РЕЖИМ ПРОСМОТРА] Никакие торренты не будут удалены!")
    else:
        print("[АКТИВНЫЙ РЕЖИМ] Торренты будут удаляться!")
    
    # Однократный запуск для Docker
    remove_old_torrents_with_same_name()

if __name__ == '__main__':
    main()
