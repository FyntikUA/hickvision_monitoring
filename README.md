# DVR & Camera Monitoring System  

## Overview  
This Python-based monitoring system **automatically tracks the status of cameras connected to multiple DVRs (Digital Video Recorders)**. It checks the availability of DVRs, camera connection status (online/offline), recording state, and logs all events for further analysis.  

The system is **scalable**, supports **multiple DVRs**, and works with **both analog and IP cameras**.  

---

## Features  
✅ **Real-time camera status monitoring**  
- Fetches camera data from **DVR API (ISAPI)**  
- Identifies **IP address, port, user authentication, connection status, and recording state**  

✅ **Multi-DVR support**  
- Configuration is stored in **`dvr_config.json`**  
- Supports DVRs with **both analog and IP cameras**  

✅ **Change detection & logging**  
- Logs events like **camera disconnection, reconnection, and recording state changes**  
- Tracks **downtime duration**  

✅ **Flexible logging**  
- Logs all events to `camera_log.txt`  
- Example:  

2025-02-02 14:35:12 - INFO - Successfully retrieved camera status for DVR. 
2025-02-02 14:40:45 - WARNING - Camera 2 went offline at 14:40:45 
2025-02-02 14:43:10 - WARNING - Camera 2 restored connection at 14:43:10. Downtime: 2m 25s


✅ **Continuous operation**  
- Runs **every minute** using `schedule`  
- Works **in the background**  

✅ **Parallel processing**  
- Uses `ThreadPoolExecutor` for **faster execution** across multiple DVRs  

---

## Configuration  

1. **Install dependencies:**  
 ```sh
 pip install -r requirements.txt
 ```

## Using

1. **Start script:**

    ```sh
    python monitor_cameras.py
    ```

2. **Check log:**

    The script will create a log file named `camera_log.txt` in the same directory, where it will store logs of camera statuses and connection issues.

## Config

- Update the variables `ip`, `port`, `username`, and `password` in the `dvr_config.json` file according to your DVR connection details.

## Files

```plaintext
.
├── monitor_cameras.py  # main script
├── requirements.txt    # 
├── dvr_config.json     # list DVR
└── README.md           # README


{
    "base": {
        "type": "analog",
        "ip": "11.11.11.11",
        "port": 80,
        "username": "admin",
        "password": "admin",
        "valid_camera_ids": [1, 2, 3, 4, 5, 6, 7, 8]
    },
    "DVR 1": {
        "type": "mixed",
        "ip": "11.11.11.11",
        "port": 80,
        "username": "admin",
        "password": "admin",
        "valid_camera_ids": [1, 2, 3, 5, 6, 7]
    },
    "DVR 2": {
        "type": "ip",
        "ip": "11.11.11.11",
        "port": 81,
        "username": "admin",
        "password": "admin",
    }
