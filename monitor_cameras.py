import requests
from concurrent.futures import ThreadPoolExecutor
from requests.auth import HTTPDigestAuth
import logging
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import time, os
from datetime import timedelta

# Налаштування журналювання
logging.basicConfig(filename='camera_log.txt', level=logging.INFO,
                     format='%(asctime)s - %(levelname)s - %(message)s')

# Словник для кількох DVR
with open('dvr_config.json', 'r') as file:
    dvrs = json.load(file)

# Структура для зберігання стану камер
camera_status = {dvr_name: {} for dvr_name in dvrs.keys()}
connection_lost_time = {dvr_name: None for dvr_name in dvrs.keys()}
dvr_status = {dvr_name: {} for dvr_name in dvrs.keys()}
dvr_connection_lost_time = {dvr_name: None for dvr_name in dvrs.keys()}

timer = None

# Скидання глобальних змінних
def reset_status():
    global camera_status, connection_lost_time, dvr_status, dvr_connection_lost_time
    camera_status = {dvr_name: {} for dvr_name in dvrs.keys()}
    connection_lost_time = {dvr_name: None for dvr_name in dvrs.keys()}
    dvr_status = {dvr_name: {} for dvr_name in dvrs.keys()}
    dvr_connection_lost_time = {dvr_name: None for dvr_name in dvrs.keys()}
    
    logging.info("Statuses have been reset.")

# Очищення консолі
def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def save_offline_info_to_file(dvr_name, camera_type, camera_identifier, start_time, end_time, duration, file_path='offline_cameras_log.txt'):
    """
    Зберігає інформацію про відключення камери в окремий файл.

    :param dvr_name: Назва DVR.
    :param camera_type: Тип камери ('Digital' або 'Analog').
    :param camera_identifier: Ідентифікатор камери (ім'я для цифрових, номер для аналогових).
    :param start_time: Час початку відключення.
    :param end_time: Час відновлення роботи.
    :param duration: Тривалість відключення.
    :param file_path: Шлях до файлу, де буде зберігатись інформація (за замовчуванням offline_cameras_log.txt).
    """
    with open(file_path, 'a') as file:
        file.write(f"DVR: {dvr_name}, {camera_identifier} was OFFLINE from {start_time} to {end_time} "
                   f"(Duration: {duration})\n")


def save_dvr_offline_info_to_file(dvr_name, start_time, end_time, duration, file_path='offline_cameras_log.txt'):
    """
    Зберігає інформацію про відключення DVR у окремий файл.

    :param dvr_name: Назва DVR.
    :param start_time: Час початку відключення DVR.
    :param end_time: Час відновлення роботи DVR.
    :param duration: Тривалість відключення DVR.
    :param file_path: Шлях до файлу, де буде зберігатись інформація (за замовчуванням offline_cameras_log.txt).
    """
    # Перевірка чи duration є об'єктом timedelta, якщо ні, конвертуємо
    if isinstance(duration, timedelta):
        duration_str = str(duration)
    else:
        duration_str = str(timedelta(seconds=duration))

    # Відкриваємо файл для запису
    with open(file_path, 'a') as file:
        file.write(f"DVR: {dvr_name} was OFFLINE from {start_time} to {end_time} "
                   f"(Duration: {duration_str})\n")

# Змінні для зберігання статусу та часу
dvr_status = {}

# Функція для перевірки статусу DVR
def check_dvr_status(dvr_name, dvr_data):
    ip, port = dvr_data['ip'], dvr_data['port']
    username, password = dvr_data['username'], dvr_data['password']
    url = f"http://{ip}:{port}/ISAPI/System/Status"
    
    try:
        response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=8)
        
        current_time = datetime.now()

        if response.status_code == 200:
            # Якщо DVR працює, перевіряємо, чи був він оффлайн
            if dvr_name in dvr_status and dvr_status[dvr_name]['status'] == 'offline':
                # DVR відновився, логуємо час відновлення
                downtime_duration = current_time - dvr_status[dvr_name]['start_time']
                logging.info(f"DVR {dvr_name} is back ONLINE at {current_time}, downtime duration: {downtime_duration}")
                save_dvr_offline_info_to_file(dvr_name, dvr_status[dvr_name]['start_time'], current_time, downtime_duration)      
                
                # Оновлюємо статус
                dvr_status[dvr_name] = {'status': 'online', 'start_time': None}
        else:
            # Якщо DVR не відповідає зі статусом не 200
            if dvr_name not in dvr_status or dvr_status[dvr_name]['status'] == 'online':
                # DVR став оффлайн, логуємо час втрати
                logging.warning(f"DVR {dvr_name} is OFFLINE at {current_time}")
                
                # Оновлюємо статус
                dvr_status[dvr_name] = {'status': 'offline', 'start_time': current_time}
            else:
                # Логуємо, що DVR все ще оффлайн
                offline_duration = current_time - dvr_status[dvr_name]['start_time']
                logging.warning(f"DVR {dvr_name} is STILL OFFLINE (Duration: {offline_duration}) at {current_time}")
                
    except requests.exceptions.RequestException as e:
        # Логуємо помилку підключення
        current_time = datetime.now()
        #logging.error(f"Error checking {dvr_name}: {e}")
        
        # Якщо DVR ще не оффлайн, фіксуємо час
        if dvr_name not in dvr_status or dvr_status[dvr_name]['status'] == 'online':
            logging.warning(f"DVR {dvr_name} is OFFLINE due to connection error at {current_time}")
            dvr_status[dvr_name] = {'status': 'offline', 'start_time': current_time}
        else:
            # Логуємо, що DVR все ще оффлайн через помилку
            offline_duration = current_time - dvr_status[dvr_name]['start_time']
            logging.warning(f"DVR {dvr_name} is STILL OFFLINE (Duration: {offline_duration}) due to error at {current_time}")

def check_analog_camera_status(dvr_name, dvr_data):
    global camera_status, connection_lost_time

    ip, port = dvr_data['ip'], dvr_data['port']
    username, password = dvr_data['username'], dvr_data['password']
    valid_camera_ids = dvr_data['valid_camera_ids']
    url = f"http://{ip}:{port}/ISAPI/System/Video/inputs/channels"

    try:
        #print(f"Sending request to analog DVR {dvr_name} ({ip})...")
        response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=8)
        
        #print(f'{dvr_name} cameras status: {camera_status[dvr_name]}')
        
        if response.status_code == 200:
            print(f"Successfully retrieved data from analog DVR: {dvr_name}, status code: {response.status_code}")

            if connection_lost_time[dvr_name]:
                logging.warning(f"Connection {dvr_name} restored") 
                logging.warning(f"Downtime: {datetime.now() - connection_lost_time[dvr_name]}. From {connection_lost_time[dvr_name]} to {datetime.now()}")
                connection_lost_time[dvr_name] = None

            root = ET.fromstring(response.text)
            current_time = datetime.now()

            for channel in root.findall('.//{http://www.hikvision.com/ver20/XMLSchema}VideoInputChannel'):
                id_elem = channel.find('{http://www.hikvision.com/ver20/XMLSchema}id')
                camera_id = id_elem.text if id_elem is not None else 'N/A'

                if int(camera_id) in valid_camera_ids:
                    name_elem = channel.find('{http://www.hikvision.com/ver20/XMLSchema}name')
                    enabled_elem = channel.find('{http://www.hikvision.com/ver20/XMLSchema}videoInputEnabled')
                    resolution_elem = channel.find('{http://www.hikvision.com/ver20/XMLSchema}resDesc')

                    name_cam = name_elem.text if name_elem is not None else 'N/A'
                    enabled = enabled_elem.text if enabled_elem is not None else 'N/A'
                    resolution = resolution_elem.text if resolution_elem is not None else 'N/A'

                    if camera_id in camera_status[dvr_name]:
                        prev_status = camera_status[dvr_name][camera_id]

                        # Камера стала "NO VIDEO" або "offline"
                        if (resolution == 'NO VIDEO' or enabled == 'false') and not prev_status['reason']:
                            prev_status['reason'] = True
                            prev_status['start_time'] = current_time
                            logging.warning(
                                f"DVR: {dvr_name}, {name_cam} - {resolution if resolution == 'NO VIDEO' else 'offline'}, reason: {enabled if enabled == 'false' else 'NO VIDEO'} since {prev_status['start_time']}"
                            )
                        # Камера досі "NO VIDEO" або "offline"
                        elif (resolution == 'NO VIDEO' or enabled == 'false') and prev_status['reason']:
                            duration = current_time - prev_status['start_time']
                            logging.warning(
                                f"DVR: {dvr_name}, Analog {name_cam} - STILL {resolution if resolution == 'NO VIDEO' else 'offline'} (Duration: {duration} from {prev_status['start_time']})"
                            )
                        # Камера відновила роботу
                        elif (resolution != 'NO VIDEO' and enabled != 'false') and prev_status['reason']:
                            prev_status['reason'] = False
                            end_time = current_time
                            duration = end_time - prev_status['start_time']
                            logging.info(
                                f"DVR: {dvr_name}, Analog {name_cam} was {resolution if resolution == 'NO VIDEO' else 'offline'} from {prev_status['start_time']} to {end_time} (Duration: {duration})"
                            )
                            save_offline_info_to_file(dvr_name, 'Analog', name_cam, prev_status['start_time'], end_time, duration)
                    else:
                        # Додавання нової камери до статусів
                        camera_status[dvr_name][camera_id] = {
                            'reason': resolution == 'NO VIDEO' or enabled == 'false',
                            'start_time': current_time if resolution == 'NO VIDEO' or enabled == 'false' else None
                        }
                        if resolution == 'NO VIDEO' or enabled == 'false':
                            logging.warning(
                                f"DVR: {dvr_name}, Analog {name_cam} - {resolution if resolution == 'NO VIDEO' else 'offline'}, reason: {enabled if enabled == 'false' else 'NO VIDEO'} since {current_time}"
                            )

        elif response.status_code in {401, 403}:
            logging.error(f"Authentication {dvr_name} failed. Check your username and password.")
        else:
            logging.error(f"Failed to get {dvr_name} camera list. Status code: {response.status_code}")
            if connection_lost_time[dvr_name] is None:
                connection_lost_time[dvr_name] = datetime.now()
    except Exception as e:
        #logging.error(f"{dvr_name} Error: {e}")
        
        if connection_lost_time[dvr_name] is None:
            connection_lost_time[dvr_name] = datetime.now()
            logging.error(f"Connection {dvr_name} lost at: {connection_lost_time[dvr_name]}")

# Адаптація для IP камер
def check_ip_camera_status(dvr_name, dvr_data):
    global camera_status, connection_lost_time

    current_time = datetime.now()
    ip, port = dvr_data['ip'], dvr_data['port']
    username, password = dvr_data['username'], dvr_data['password']
    url_channels = f"http://{ip}:{port}/ISAPI/ContentMgmt/InputProxy/channels"
    url_status = f"http://{ip}:{port}/ISAPI/System/workingstatus?format=json"

    #print(f"Sending request to digital DVR {dvr_name} ({ip})...")

    try:
        
        response_channels = requests.get(url_channels, auth=HTTPDigestAuth(username, password), timeout=8)
        response_status = requests.get(url_status, auth=HTTPDigestAuth(username, password),timeout=8)
        #print(f'{dvr_name} cameras status: {camera_status[dvr_name]}')

        if response_channels.status_code == 200 and response_status.status_code == 200:
            print(f"Successfully retrieved data from digital DVR: {dvr_name}, status code: {response_status.status_code}")
            #logging.info(f"{'-' * 24} Start {dvr_name} {'-' * 24}")
        

            # Відновлення після втрати зв'язку
            if connection_lost_time.get(dvr_name):
                logging.warning(f"Connection restored for DVR: {dvr_name} at: {current_time}. "
                                f"Downtime: {current_time - connection_lost_time[dvr_name]}")
                connection_lost_time[dvr_name] = None

            # Парсинг XML-даних про камери
            namespace = {'ns': 'http://www.hikvision.com/ver20/XMLSchema'}
            root = ET.fromstring(response_channels.text)
            # Перевірка, який формат JSON ви отримали
            if 'WorkingStatus' in response_status.json():
                working_status = response_status.json()['WorkingStatus']
                chan_status = working_status['ChanStatus']
            else:
                chan_status = response_status.json()['ChanStatus']

            # Перевірка кожної камери
            for channel, chan in zip(root.findall('ns:InputProxyChannel', namespace), chan_status):
                camera_info = {
                    'id': channel.find('ns:id', namespace).text,
                    'name': channel.find('ns:name', namespace).text,
                    'ipAddress': channel.find('ns:sourceInputPortDescriptor/ns:ipAddress', namespace).text,
                    'port': channel.find('ns:sourceInputPortDescriptor/ns:managePortNo', namespace).text,
                    'user': channel.find('ns:sourceInputPortDescriptor/ns:userName', namespace).text,
                    #'enableTiming': channel.find('ns:enableTiming', namespace).text if channel.find('ns:enableTiming', namespace) is not None else 'false',
                }

                chanNo = chan['chanNo']
                online = chan['online']
                record = chan['record']
    

                # Виведення стану
                #print(f"DVR: {dvr_name}, ID: {camera_info['id']}, Name: {camera_info['name']}, IP: {camera_info['ipAddress']}, "
                #      f"Status: {'Online' if online else 'Offline'}, Recording: {'Yes' if record else 'No'}")

                # Логіка зміни статусу
                if chanNo in camera_status.get(dvr_name, {}):
                    prev_status = camera_status[dvr_name][chanNo]
                    if online == 0 and not prev_status['issue']:
                        # Камера перейшла в статус "не працює"
                        prev_status['issue'] = True
                        prev_status['start_time'] = current_time
                        logging.warning(f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE since {prev_status['start_time']}")
                    elif online == 0 and prev_status['issue']:
                        # Камера досі не працює - показати тривалість
                        duration = current_time - prev_status['start_time']
                        logging.warning(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - STILL OFFLINE (Duration: {duration} from {prev_status['start_time']})"
                        )
                    # Камера відновила роботу
                    elif online == 1 and prev_status['issue']:
                        prev_status['issue'] = False
                        end_time = current_time
                        duration = end_time - prev_status['start_time']
                        logging.info(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} was OFFLINE from {prev_status['start_time']} to {end_time} (Duration: {duration})"
                        )
                        save_offline_info_to_file(dvr_name, 'Digital', camera_info['name'], prev_status['start_time'], end_time, duration)
                else:
                    # Додавання нової камери до статусів
                    if dvr_name not in camera_status:
                        camera_status[dvr_name] = {}
                    camera_status[dvr_name][chanNo] = {
                        'issue': online == 0,
                        'start_time': current_time if online == 0 else None
                    }
                    if online == 0:
                        logging.warning(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE at {current_time}"
                        )
            #logging.info(f"{'-' * 25} End {dvr_name} {'-' * 25}")
                    
        elif response_channels.status_code in {401, 403} or response_status.status_code in {401, 403}:
            logging.error(f"Authentication {dvr_name} failed. Check your username and password.")
        else:
            logging.error(f"Failed to get {dvr_name} camera status. "
                  f"Status codes: Channels - {response_channels.status_code}, Status - {response_status.status_code}")
            if connection_lost_time[dvr_name] is None:
                connection_lost_time[dvr_name] = datetime.now()
    except Exception as e:
        #logging.error(f"{dvr_name} Error: {e}")
        if connection_lost_time[dvr_name] is None:
            connection_lost_time[dvr_name] = datetime.now()
            logging.error(f"Connection {dvr_name} lost at: {connection_lost_time[dvr_name]}")

# Основний цикл з мультипоточністю
def main():
    while True:
        clear_console()
        print('---------------------------------------------')
        logging.info("-" * 24 + 'Start checking' + "-" * 24)
        with ThreadPoolExecutor(max_workers=len(dvrs)) as executor:
            for dvr_name, dvr_data in dvrs.items():
                if dvr_data.get('type') == 'mixed':
                    executor.submit(check_ip_camera_status, dvr_name, dvr_data)
                    executor.submit(check_analog_camera_status, dvr_name, dvr_data)
                if dvr_data.get('type') == 'analog':
                    executor.submit(check_analog_camera_status, dvr_name, dvr_data)
                elif dvr_data.get('type') == 'ip':
                    executor.submit(check_ip_camera_status, dvr_name, dvr_data)
                # Додати виклик для перевірки статусу самого DVR
                executor.submit(check_dvr_status, dvr_name, dvr_data)
        print('---------------------------------------------')
        print("Press Ctrl+C to exit the program.")
        logging.info("-" * 25 + 'End checking' + "-" * 25)
        time.sleep(timer)  # Перевіряти раз на хвилину

# Меню програми
def menu():
    while True:
        clear_console()
        print("========== DVR Monitoring Program ==========")
        print("1. Start Monitoring")
        print("2. Stop Monitoring")
        print("3. Exit")
        choice = input("Select an option (1-3): ")

        if choice == '1':
            try:
                global timer
                while True:
                    timer_input = input("Enter the DVRs check period in seconds (default is 180): ").strip()
                    if not timer_input:  # Якщо нічого не ввели
                        timer = 180  # Значення за замовчуванням
                        print("No input detected. Using default value: 180 seconds.")
                        break
                    elif timer_input.isdigit() and int(timer_input) > 0:  # Перевірка чи це число
                        timer = int(timer_input)
                        break
                    else:  # Некоректне значення
                        print("Invalid input. Please enter a positive integer.")

                logging.info("Starting monitoring...")
                main()
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user.")

        elif choice == '2':
            print("Stopping monitoring...")
            logging.info("Monitoring stopped.")
            reset_status()  # Викликаємо функцію для обнулення
            print("Statuses have been reset.")
            time.sleep(2)
        elif choice == '3':
            print("Exiting the program...")
            logging.info("Program exited.")
            time.sleep(1)
            break
        else:
            print("Invalid choice, please select again.")
            time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    menu()
    #main()
