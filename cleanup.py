# cleanup.py
import requests
import time
import os
from datetime import datetime
import hashlib

# Конфигурация из переменных окружения
QB_URL = os.getenv('QB_URL', 'http://qbittorrent:8080')
QB_USER = os.getenv('QB_USER', 'admin')
QB_PASS = os.getenv('QB_PASS', 'adminadmin')
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
DELETE_FILES = os.getenv('DELETE_FILES', 'false').lower() == 'true'
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '30'))

class TorrentCleanup:
    def __init__(self):
        self.session = requests.Session()
        self.authenticated = False
        self.last_state_hash = None

    def login(self):
        """Аутентификация в qBittorrent"""
        r = self.session.post(f'{QB_URL}/api/v2/auth/login', data={'username': QB_USER, 'password': QB_PASS})
        if r.status_code == 200:
            self.authenticated = True
        else:
            raise Exception(f"Ошибка входа: {r.status_code} - {r.text}")

    def get_torrents(self):
        """Получение списка торрентов"""
        if not self.authenticated:
            self.login()
        r = self.session.get(f'{QB_URL}/api/v2/torrents/info')
        if r.status_code == 403:
            self.login()
            r = self.session.get(f'{QB_URL}/api/v2/torrents/info')
        r.raise_for_status()
        return r.json()

    def delete_torrent(self, torrent_hash):
        """Удаление торрента"""
        if not self.authenticated:
            self.login()
        r = self.session.post(f'{QB_URL}/api/v2/torrents/delete', data={
            'hashes': torrent_hash,
            'deleteFiles': DELETE_FILES
        })
        if r.status_code == 403:
            self.login()
            r = self.session.post(f'{QB_URL}/api/v2/torrents/delete', data={
                'hashes': torrent_hash,
                'deleteFiles': DELETE_FILES
            })
        return r.status_code == 200

    def get_torrent_key(self, torrent):
        """Ключ для группировки торрентов: save_path + имя торрента"""
        save_path = torrent['save_path'].rstrip('/')
        torrent_name = torrent['name']
        return f"{save_path}/{torrent_name}"

    def cleanup_old_torrents(self):
        """Основная логика очистки"""
        try:
            torrents = self.get_torrents()
            groups = {}
            for t in torrents:
                key = self.get_torrent_key(t)
                groups.setdefault(key, []).append(t)

            deleted = 0
            for key, group in groups.items():
                if len(group) > 1:
                    # Сортировка по времени добавления
                    group.sort(key=lambda x: x['added_on'])
                    # Удаление всех, кроме последнего
                    for old in group[:-1]:
                        msg = f"Torrent '{old['name']}' | Added: {datetime.fromtimestamp(old['added_on'])}"
                        if DRY_RUN:
                            print(f"[DRY RUN] Будет удален: {msg}")
                        else:
                            print(f"[УДАЛЕНИЕ] {msg}")
                            if self.delete_torrent(old['hash']):
                                deleted += 1
            if deleted > 0:
                print(f"[ОЧИСТКА] Удалено торрентов: {deleted}")
            elif not DRY_RUN and torrents:
                print("[ОЧИСТКА] Нет торрентов для удаления")
        except Exception as e:
            print(f"[ОШИБКА] {e}")

    def get_state_hash(self, torrents):
        """Хэш текущего состояния для сравнения"""
        hashes = sorted([t['hash'] for t in torrents])
        return hashlib.md5(str(hashes).encode()).hexdigest()

    def run(self):
        """Основной цикл"""
        print("=== qBittorrent Cleanup (Polling Mode) ===")
        print(f"QB_URL: {QB_URL}")
        print(f"DRY_RUN: {DRY_RUN}")
        print(f"CHECK_INTERVAL: {CHECK_INTERVAL} секунд")
        print("=" * 45)

        # Начальная очистка
        self.login()
        self.cleanup_old_torrents()
        self.last_state_hash = self.get_state_hash(self.get_torrents())

        # Цикл опроса
        while True:
            try:
                time.sleep(CHECK_INTERVAL)
                torrents = self.get_torrents()
                current_hash = self.get_state_hash(torrents)
                
                if current_hash != self.last_state_hash:
                    print("[ТРИГГЕР] Список торрентов изменился")
                    self.cleanup_old_torrents()
                    self.last_state_hash = current_hash
                    
            except KeyboardInterrupt:
                print("\n[СТОП] Работа завершена")
                break
            except Exception as e:
                print(f"[ОШИБКА ЦИКЛА] {e}")
                time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    TorrentCleanup().run()