import requests
import time
import os
from datetime import datetime
import websocket
import json
import threading

# Конфигурация из переменных окружения
QB_URL = os.getenv('QB_URL', 'http://qbittorrent:8080')
QB_USER = os.getenv('QB_USER', 'admin')
QB_PASS = os.getenv('QB_PASS', 'adminadmin')
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
DELETE_FILES = os.getenv('DELETE_FILES', 'false').lower() == 'true'
USE_WEBSOCKET = os.getenv('USE_WEBSOCKET', 'true').lower() == 'true'
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # fallback если WebSocket не работает

class TorrentMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.ws = None
        self.ws_thread = None
        self.should_stop = False
        
    def login(self):
        r = self.session.post(f'{QB_URL}/api/v2/auth/login', data={'username': QB_USER, 'password': QB_PASS})
        if r.status_code != 200:
            raise Exception(f"Не удалось войти в qBittorrent Web UI: {r.text}")
        return r.cookies
    
    def get_torrents(self):
        r = self.session.get(f'{QB_URL}/api/v2/torrents/info')
        return r.json()
    
    def delete_torrent(self, torrent_hash):
        r = self.session.post(f'{QB_URL}/api/v2/torrents/delete', data={
            'hashes': torrent_hash,
            'deleteFiles': DELETE_FILES
        })
        return r.status_code == 200
    
    def get_torrent_name_key(self, torrent):
        """Получает ключ для группировки торрентов по имени папки"""
        save_path = torrent['save_path'].rstrip('/')
        torrent_name = torrent['name']
        return f"{save_path}/{torrent_name}"
    
    def format_timestamp(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    
    def cleanup_old_torrents(self):
        """Основная функция очистки"""
        try:
            torrents = self.get_torrents()
            
            # Группируем торренты по имени папки внутри save_path
            torrents_by_name = {}
            
            for t in torrents:
                torrent_key = self.get_torrent_name_key(t)
                
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
                        torrent_info = f"Torrent: {old_torrent['name']} | Added: {self.format_timestamp(old_torrent['added_on'])} | Key: {torrent_key}"
                        
                        if DRY_RUN:
                            print(f"[DRY RUN] Будет удален: {torrent_info}")
                        else:
                            print(f"[УДАЛЕНИЕ] Удаляем: {torrent_info}")
                            if self.delete_torrent(old_torrent['hash']):
                                deleted_count += 1
                            else:
                                print(f"[ОШИБКА] Не удалось удалить торрент: {old_torrent['name']}")
            
            if deleted_count > 0:
                print(f"[ОЧИСТКА] Удалено торрентов: {deleted_count}")
            elif not DRY_RUN and len(torrents) > 0:
                print("[ОЧИСТКА] Нет торрентов для удаления")
                
            return deleted_count
            
        except Exception as e:
            print(f"[ОШИБКА ОЧИСТКИ] {str(e)}")
            return 0
    
    def on_websocket_message(self, ws, message):
        """Обработчик сообщений WebSocket"""
        try:
            data = json.loads(message)
            if data.get('type') == 'torrentAdded':
                torrent_name = data.get('torrentName', 'Unknown')
                print(f"[WEBSOCKET] Обнаружен новый торрент: {torrent_name}")
                print("[ТРИГГЕР] Запускаем очистку...")
                time.sleep(2)  # Небольшая задержка чтобы торрент полностью добавился
                self.cleanup_old_torrents()
        except Exception as e:
            print(f"[WEBSOCKET ОШИБКА] {str(e)}")
    
    def on_websocket_error(self, ws, error):
        """Обработчик ошибок WebSocket"""
        print(f"[WEBSOCKET ОШИБКА] {error}")
    
    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработчик закрытия WebSocket"""
        print("[WEBSOCKET] Соединение закрыто")
        if not self.should_stop:
            print("[WEBSOCKET] Попытка переподключения через 10 секунд...")
            time.sleep(10)
            if not self.should_stop:
                self.start_websocket()
    
    def on_websocket_open(self, ws):
        """Обработчик открытия WebSocket"""
        print("[WEBSOCKET] Подключено к qBittorrent")
        # Выполняем начальную очистку при первом подключении
        try:
            self.cleanup_old_torrents()
        except Exception as e:
            print(f"[ОШИБКА НАЧАЛЬНОЙ ОЧИСТКИ] {str(e)}")
    
    def start_websocket(self):
        """Запуск WebSocket соединения"""
        try:
            # Получаем cookies для WebSocket аутентификации
            cookies = self.login()
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            
            # Формируем WebSocket URL
            ws_url = QB_URL.replace('http://', 'ws://').replace('https://', 'wss://') + '/api/v2/app/websocket'
            
            # Создаем WebSocket соединение
            self.ws = websocket.WebSocketApp(ws_url,
                                           on_message=self.on_websocket_message,
                                           on_error=self.on_websocket_error,
                                           on_close=self.on_websocket_close,
                                           on_open=self.on_websocket_open,
                                           header={"Cookie": cookie_str})
            
            # Запускаем в отдельном потоке
            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()
            
            print(f"[WEBSOCKET] Подключение к {ws_url}")
            
        except Exception as e:
            print(f"[WEBSOCKET ОШИБКА ПОДКЛЮЧЕНИЯ] {str(e)}")
            print("[FALLBACK] Используем режим polling...")
            self.fallback_polling()
    
    def fallback_polling(self):
        """Fallback режим с polling'ом"""
        print(f"[POLLING] Запуск fallback режима с интервалом {CHECK_INTERVAL} секунд")
        last_count = len(self.get_torrents()) if not self.should_stop else 0
        self.cleanup_old_torrents()  # Начальная очистка
        
        while not self.should_stop:
            try:
                time.sleep(CHECK_INTERVAL)
                if self.should_stop:
                    break
                    
                current_torrents = self.get_torrents()
                current_count = len(current_torrents)
                
                if current_count > last_count:
                    print(f"[POLLING] Обнаружено добавление торрентов: {last_count} → {current_count}")
                    self.cleanup_old_torrents()
                
                last_count = current_count
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[POLLING ОШИБКА] {str(e)}")
                time.sleep(CHECK_INTERVAL)
    
    def run(self):
        """Основной метод запуска"""
        print(f"=== qBittorrent Cleanup Service ===")
        print(f"QB_URL: {QB_URL}")
        print(f"DRY_RUN: {DRY_RUN}")
        print(f"DELETE_FILES: {DELETE_FILES}")
        print(f"USE_WEBSOCKET: {USE_WEBSOCKET}")
        print(f"================================")
        
        if DRY_RUN:
            print("[РЕЖИМ ПРОСМОТРА] Никакие торренты не будут удалены!")
        else:
            print("[АКТИВНЫЙ РЕЖИМ] Торренты будут удаляться!")
        
        try:
            if USE_WEBSOCKET:
                self.start_websocket()
                # Держим основной поток живым
                while not self.should_stop:
                    time.sleep(1)
            else:
                self.fallback_polling()
                
        except KeyboardInterrupt:
            print("[ИНФО] Сервис остановлен пользователем")
        finally:
            self.should_stop = True
            if self.ws:
                self.ws.close()

def main():
    monitor = TorrentMonitor()
    monitor.run()

if __name__ == '__main__':
    main()