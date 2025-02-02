import requests
import threading
import logging
import json, time, os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta
from message import send_to_telegram

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

def check_analog_camera_status(dvr_name, dvr_data):
    global camera_status, connection_lost_time

    ip, port = dvr_data['ip'], dvr_data['port']
    username, password = dvr_data['username'], dvr_data['password']
    valid_camera_ids = dvr_data['valid_camera_ids']
    url = f"http://{ip}:{port}/ISAPI/System/Video/inputs/channels"

    try:
        response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=8)
        if response.status_code == 200:
            print(f"Successfully retrieved data from analog DVR: {dvr_name}, status code: {response.status_code}")
            current_time = datetime.now()
            formatted_current_time = current_time.strftime("%Y-%m-%d %H:%M")
            if connection_lost_time[dvr_name]:
                formatted_connection_lost_time = connection_lost_time[dvr_name].strftime("%Y-%m-%d %H:%M")
                duration_lost_analog_cam = current_time - connection_lost_time[dvr_name]
                formatted_duration_lost_time = f"{duration_lost_analog_cam}".split('.')[0]
                logging.warning(f"Connection {dvr_name} restored") 
                logging.warning(f"Downtime: {formatted_duration_lost_time}. From {formatted_connection_lost_time} to {formatted_current_time}")
                send_to_telegram(f"Connection {dvr_name} restored. Downtime: {formatted_duration_lost_time}. From {formatted_connection_lost_time} to {formatted_current_time}")
                connection_lost_time[dvr_name] = None

            root = ET.fromstring(response.text)

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
                            send_to_telegram(
                                f"DVR: {dvr_name}, {name_cam} - {resolution if resolution == 'NO VIDEO' else 'offline'}, reason: {enabled if enabled == 'false' else 'NO VIDEO'} since {prev_status['start_time']}"
                            )
                        # Камера досі "NO VIDEO" або "offline"
                        elif (resolution == 'NO VIDEO' or enabled == 'false') and prev_status['reason']:
                            formated_prev_status = prev_status['start_time'].strftime("%Y-%m-%d %H:%M")
                            duration = current_time - prev_status['start_time']
                            formate_duration = f"{duration}".split('.')[0]
                            logging.warning(
                                f"DVR: {dvr_name}, Analog {name_cam} - STILL {resolution if resolution == 'NO VIDEO' else 'offline'} (Duration: {formate_duration} from {formated_prev_status})"
                            )
                        # Камера відновила роботу
                        elif (resolution != 'NO VIDEO' and enabled != 'false') and prev_status['reason']:
                            prev_status['reason'] = False
                            formated_prev_status = prev_status['start_time'].strftime("%Y-%m-%d %H:%M")
                            end_time = current_time
                            formated_end_time = end_time.strftime("%Y-%m-%d %H:%M")
                            duration = end_time - prev_status['start_time']
                            formate_duration = f"{duration}".split('.')[0]
                            logging.info(
                                f"DVR: {dvr_name}, Analog {name_cam} was {resolution if resolution == 'NO VIDEO' else 'offline'} from {formated_prev_status} to {formated_end_time} (Duration: {formate_duration})"
                            )
                            send_to_telegram(
                                f"DVR: {dvr_name}, Analog {name_cam} was {resolution if resolution == 'NO VIDEO' else 'offline'} from {formated_prev_status} to {formated_end_time} (Duration: {formate_duration})"
                            )
                            save_offline_info_to_file(dvr_name, 'Analog', name_cam, prev_status['start_time'], formated_end_time, duration)
                    else:
                        # Додавання нової камери до статусів
                        camera_status[dvr_name][camera_id] = {
                            'reason': resolution == 'NO VIDEO' or enabled == 'false',
                            'start_time': current_time if resolution == 'NO VIDEO' or enabled == 'false' else None
                        }
                        if resolution == 'NO VIDEO' or enabled == 'false':
                            send_to_telegram(
                                f"DVR: {dvr_name}, Analog {name_cam}, reason: {resolution if resolution == 'NO VIDEO' else 'offline'} since {formatted_current_time}"
                            )
                            logging.warning(
                                f"DVR: {dvr_name}, Analog {name_cam}, reason: {resolution if resolution == 'NO VIDEO' else 'offline'} since {formatted_current_time}"
                            )

        elif response.status_code in {401, 403}:
            logging.error(f"Authentication {dvr_name} failed. Check your username and password.")
        else:
            logging.error(f"Failed to get {dvr_name} camera list. Status code: {response.status_code}")
            if connection_lost_time[dvr_name] is None:
                connection_lost_time[dvr_name] = datetime.now()
    except Exception as e:
        if connection_lost_time[dvr_name]:
            formated_connection_dvr_lost_time = connection_lost_time[dvr_name].strftime("%Y-%m-%d %H:%M")
            duration_lost_digital_dvr = current_time - connection_lost_time[dvr_name]  
            formatted_duration_lost_time = f"{duration_lost_digital_dvr}".split('.')[0]
            print(f"{dvr_name} still OFFLINE duration {formatted_duration_lost_time} from {formated_connection_dvr_lost_time}")
            logging.warning(f"{dvr_name} still OFFLINE duration {formatted_duration_lost_time} from {formated_connection_dvr_lost_time}")
        if connection_lost_time[dvr_name] is None:
            connection_lost_time[dvr_name] = datetime.now()
            formatted_lost_time_dvr = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"Connection DVR {dvr_name} lost at: {formatted_lost_time_dvr}")
            logging.error(f"Connection DVR {dvr_name} lost at: {formatted_lost_time_dvr}. Error: {e}")
            send_to_telegram(f"Connection DVR {dvr_name} lost at: {formatted_lost_time_dvr}")

# Адаптація для IP камер
def check_ip_camera_status(dvr_name, dvr_data):
    global camera_status

    current_time = datetime.now()
    formatted_current_time = current_time.strftime("%Y-%m-%d %H:%M")
    
    
    ip, port = dvr_data['ip'], dvr_data['port']
    username, password = dvr_data['username'], dvr_data['password']
    url_channels = f"http://{ip}:{port}/ISAPI/ContentMgmt/InputProxy/channels"
    url_status = f"http://{ip}:{port}/ISAPI/System/workingstatus?format=json"

    try:
        
        response_channels = requests.get(url_channels, auth=HTTPDigestAuth(username, password), timeout=8)
        response_status = requests.get(url_status, auth=HTTPDigestAuth(username, password),timeout=8)

        if response_channels.status_code == 200 and response_status.status_code == 200:
            print(f"Successfully retrieved data from digital DVR: {dvr_name}, status code: {response_channels.status_code}")
            # DVR відповідає, обнуляємо статус втрати зв'язку
            if connection_lost_time.get(dvr_name):
                downtime = current_time - connection_lost_time[dvr_name]
                formatted_downtime = str(downtime).split('.')[0]
                logging.info(f"Connection restored for DVR: {dvr_name} at {formatted_current_time}. "
                             f"Downtime: {formatted_downtime}")
                send_to_telegram(f"Connection restored for DVR: {dvr_name} at {formatted_current_time}. "
                                 f"Downtime: {formatted_downtime}")
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
                        formatted_prev_status = prev_status['start_time'].strftime("%Y-%m-%d %H:%M")
                        send_to_telegram(f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE since {formatted_prev_status}")
                        logging.warning(f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE since {formatted_prev_status}")
                    elif online == 0 and prev_status['issue']:
                        # Камера досі не працює - показати тривалість
                        duration = current_time - prev_status['start_time']
                        formatted_duration = str(duration).split('.')[0]
                        start_time = prev_status['start_time'].strftime("%Y-%m-%d %H:%M")
                        logging.warning(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - STILL OFFLINE (Duration: {formatted_duration} from {start_time})"
                        )
                    elif online == 1 and prev_status['issue']:
                        # Камера відновила роботу
                        prev_status['issue'] = False
                        end_time = current_time
                        formatted_end_time = end_time.strftime("%Y-%m-%d %H:%M")
                        duration = end_time - prev_status['start_time']
                        formatted_duration = str(duration).split('.')[0]
                        logging.info(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} now ONLINE. Was OFFLINE from {prev_status['start_time']} to {formatted_end_time} (Duration: {formatted_duration})"
                        )
                        send_to_telegram(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} now ONLINE. Was OFFLINE from {prev_status['start_time']} to {formatted_end_time} (Duration: {formatted_duration})"
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
                        print(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE at {formatted_current_time}"
                        )
                        send_to_telegram(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE at {formatted_current_time}"
                        )
                        logging.warning(
                            f"DVR: {dvr_name}, Digital {camera_info['name']} - OFFLINE at {formatted_current_time}"
                        )
                    
        elif response_channels.status_code in {401, 403} or response_status.status_code in {401, 403}:
            logging.error(f"Authentication {dvr_name} failed. Check your username and password.")
        else:
            logging.error(f"Failed to get {dvr_name} camera status. "
                  f"Status codes: Channels - {response_channels.status_code}, Status - {response_status.status_code}")
            if connection_lost_time[dvr_name] is None:
                connection_lost_time[dvr_name] = datetime.now()
    except Exception as e:
        # Обробка помилок
        if connection_lost_time.get(dvr_name) is None:
            connection_lost_time[dvr_name] = current_time
            logging.error(f"Connection lost for DVR: {dvr_name} at {formatted_current_time}. Error: {e}")
            send_to_telegram(f"Connection lost for DVR: {dvr_name} at {formatted_current_time}")
        else:
            lost_time = connection_lost_time[dvr_name]
            duration = current_time - lost_time
            formatted_duration = str(duration).split('.')[0]
            print((f"DVR: {dvr_name} is still offline. Duration: {formatted_duration} (since {lost_time.strftime('%Y-%m-%d %H:%M')})"))
            logging.warning(f"DVR: {dvr_name} is still offline. Duration: {formatted_duration} (since {lost_time.strftime('%Y-%m-%d %H:%M')})")
        
def auto_start():
    """Функція для автоматичного запуску моніторингу через 30 секунд бездіяльності."""
    global timer
    timer = 180  # Значення за замовчуванням
    print("No input detected for 30 seconds. Starting monitoring with default timer: 180 seconds.")
    logging.info("Auto-starting monitoring with default timer: 180 seconds.")
    main()

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
        print('---------------------------------------------')
        print("Press Ctrl+C to exit the program.")
        logging.info("-" * 25 + 'End checking' + "-" * 25)
        time.sleep(timer)

def menu():
    global timer
    while True:
        clear_console()
        print("========== DVR Monitoring Program ==========")
        print("1. Start Monitoring")
        print("2. Stop Monitoring")
        print("3. Exit")

        # Запускаємо таймер на 30 секунд для автоматичного запуску
        auto_start_timer = threading.Timer(30, auto_start)
        auto_start_timer.start()

        choice = input("Select an option (1-3): ")
        auto_start_timer.cancel()  # Зупиняємо таймер, якщо користувач зробив вибір

        if choice == '1':
            try:
                while True:
                    timer_input = input("Enter the DVRs check period in seconds (default is 180): ").strip()
                    if not timer_input:
                        timer = 180
                        print("No input detected. Using default value: 180 seconds.")
                        break
                    elif timer_input.isdigit() and int(timer_input) > 0:
                        timer = int(timer_input)
                        break
                    else:
                        print("Invalid input. Please enter a positive integer.")

                logging.info("Starting monitoring...")
                main()
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user.")

        elif choice == '2':
            print("Stopping monitoring...")
            logging.info("Monitoring stopped.")
            reset_status()
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
