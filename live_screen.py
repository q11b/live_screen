import cv2
import numpy as np
import subprocess
import time
import os
from threading import Thread
from queue import Queue

# تحديد مسار ADB
ADB_PATH = r"C:\platform-tools\adb.exe"

class TouchHandler:
    def __init__(self, window_name):
        self.window_name = window_name
        self.is_dragging = False
        self.last_x = 0
        self.last_y = 0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.screen_width = 0
        self.screen_height = 0
        self.window_width = 0
        self.window_height = 0
        self.last_click_time = 0
        self.double_click_threshold = 0.3  # ثواني
        self.min_drag_distance = 5  # بكسل
        
    def update_screen_size(self, screen_width, screen_height, window_width, window_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.window_width = window_width
        self.window_height = window_height
        self.scale_x = screen_width / window_width
        self.scale_y = screen_height / window_height
        
    def map_coordinates(self, window_x, window_y):
        # تحويل إحداثيات النافذة إلى إحداثيات الهاتف
        phone_x = int(window_x * self.scale_x)
        phone_y = int(window_y * self.scale_y)
        return phone_x, phone_y
        
    def touch_down(self, x, y):
        current_time = time.time()
        if current_time - self.last_click_time < self.double_click_threshold:
            # نقر مزدوج
            phone_x, phone_y = self.map_coordinates(x, y)
            subprocess.run([ADB_PATH, 'shell', f'input touchscreen tap {phone_x} {phone_y} && sleep 0.1 && input touchscreen tap {phone_x} {phone_y}'])
        else:
            # نقرة عادية
            phone_x, phone_y = self.map_coordinates(x, y)
            subprocess.run([ADB_PATH, 'shell', f'input touchscreen tap {phone_x} {phone_y}'])
        self.last_click_time = current_time
        
    def touch_move(self, x, y):
        if self.is_dragging:
            dx = x - self.last_x
            dy = y - self.last_y
            # التحقق من المسافة الدنيا للسحب
            if abs(dx) > self.min_drag_distance or abs(dy) > self.min_drag_distance:
                phone_x, phone_y = self.map_coordinates(x, y)
                last_phone_x, last_phone_y = self.map_coordinates(self.last_x, self.last_y)
                # حساب سرعة السحب بناءً على المسافة
                distance = ((dx * self.scale_x) ** 2 + (dy * self.scale_y) ** 2) ** 0.5
                duration = min(max(100, int(distance)), 500)  # بين 100 و 500 مللي ثانية
                subprocess.run([ADB_PATH, 'shell', f'input touchscreen swipe {last_phone_x} {last_phone_y} {phone_x} {phone_y} {duration}'])
                self.last_x = x
                self.last_y = y
            
    def touch_up(self):
        self.is_dragging = False
        
    def handle_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.is_dragging = True
            self.last_x = x
            self.last_y = y
            self.touch_down(x, y)
        elif event == cv2.EVENT_MOUSEMOVE:
            self.touch_move(x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.touch_up()
        elif event == cv2.EVENT_MOUSEWHEEL:
            # دعم التكبير/التصغير (يتطلب تعديل في OpenCV)
            if flags > 0:
                subprocess.run([ADB_PATH, 'shell', 'input touchscreen swipe 200 200 400 400 300'])
            else:
                subprocess.run([ADB_PATH, 'shell', 'input touchscreen swipe 400 400 200 200 300'])
        
class FrameGrabber:
    def __init__(self):
        self.frame_queue = Queue(maxsize=5)  # زيادة حجم القائمة
        self.stopped = False
        self.last_frame = None  # تخزين الإطار الأخير
        self.error_count = 0
        self.max_errors = 3
        
    def start(self):
        Thread(target=self.grab, daemon=True).start()
        return self
        
    def grab(self):
        while not self.stopped:
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except:
                    pass
                    
            frame = self._capture_frame()
            if frame is not None:
                self.error_count = 0  # إعادة تعيين عداد الأخطاء
                self.last_frame = frame
                try:
                    self.frame_queue.put_nowait(frame)
                except:
                    pass
            else:
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    print("\nWarning: Multiple frame capture failures. Check device connection.")
                    self.error_count = 0
                    time.sleep(1)  # انتظار قبل المحاولة مرة أخرى
                    
    def _capture_frame(self):
        try:
            with subprocess.Popen(
                [ADB_PATH, 'exec-out', 'screencap', '-p'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False
            ) as process:
                screenshot_data, stderr = process.communicate(timeout=2)
                if process.returncode != 0:
                    print(f"Screenshot error: {stderr.decode()}")
                    return None
                    
                if not screenshot_data:
                    return None
                    
                return cv2.imdecode(np.frombuffer(screenshot_data, np.uint8), cv2.IMREAD_COLOR)
                
        except subprocess.TimeoutExpired as e:
            print("Screenshot timeout")
            return None
        except Exception as e:
            print(f"Frame capture error: {e}")
            return None
            
    def read(self):
        try:
            frame = self.frame_queue.get_nowait() if not self.frame_queue.empty() else self.last_frame
            return frame
        except:
            return self.last_frame
            
    def stop(self):
        self.stopped = True
        # تنظيف القائمة
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                pass

def get_screen_resolution():
    try:
        result = subprocess.run(
            [ADB_PATH, 'shell', 'wm size'],
            capture_output=True,
            text=True
        )
        size = result.stdout.strip().split()[-1].split('x')
        return int(size[0]), int(size[1])
    except:
        return 1080, 1920  # قيم افتراضية

def check_adb(max_retries=3):
    for attempt in range(max_retries):
        try:
            if not os.path.exists(ADB_PATH):
                raise FileNotFoundError(f"ADB not found at {ADB_PATH}")
                
            process = subprocess.run(
                [ADB_PATH, 'devices'],
                capture_output=True,
                text=True,
                shell=False,
                timeout=5
            )
            
            if "device" not in process.stdout:
                if attempt < max_retries - 1:
                    print(f"No device found, retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(1)
                    continue
                raise ConnectionError("No Android device found")
                
            # التحقق من حالة USB Debugging
            debug_status = subprocess.run(
                [ADB_PATH, 'shell', 'settings', 'get', 'global', 'adb_enabled'],
                capture_output=True,
                text=True,
                shell=False,
                timeout=5
            )
            
            if debug_status.stdout.strip() != '1':
                print("Warning: USB Debugging might not be properly enabled")
                
            return True
            
        except subprocess.TimeoutExpired:
            print(f"Connection timeout, retrying ({attempt + 1}/{max_retries})...")
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Error: {e}, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"Final error: {e}")
                return False
    return False

def main():
    print("Android Screen Mirror with Touch Control")
    print("Press 'q' to exit")
    print("Press 'f' to toggle fullscreen")
    print("Press 'r' to reconnect if screen freezes")
    print("Use mouse to control the device:")
    print("- Left click: Tap")
    print("- Left click + drag: Swipe")
    
    if not check_adb():
        return
        
    try:
        # الحصول على دقة شاشة الهاتف
        screen_width, screen_height = get_screen_resolution()
        
        # إنشاء نافذة
        window_name = 'Android Screen'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        # حساب حجم النافذة المناسب
        window_height = 800
        window_width = int(screen_width * (window_height / screen_height))
        cv2.resizeWindow(window_name, window_width, window_height)
        
        # إعداد معالج اللمس
        touch_handler = TouchHandler(window_name)
        touch_handler.update_screen_size(screen_width, screen_height, window_width, window_height)
        cv2.setMouseCallback(window_name, touch_handler.handle_mouse)
        
        # تهيئة متغيرات التحكم
        is_fullscreen = False
        frame_grabber = None
        last_time = time.time()
        fps_counter = 0
        connection_attempts = 0
        
        def start_frame_grabber():
            nonlocal frame_grabber
            if frame_grabber:
                frame_grabber.stop()
            frame_grabber = FrameGrabber().start()
            return frame_grabber
            
        frame_grabber = start_frame_grabber()
        
        while True:
            frame = frame_grabber.read()
            
            if frame is not None:
                connection_attempts = 0
                # تحجيم الإطار
                frame = cv2.resize(frame, (window_width, window_height), 
                                interpolation=cv2.INTER_LINEAR)
                
                # عرض الإطار
                cv2.imshow(window_name, frame)
                
                # حساب FPS
                fps_counter += 1
                if fps_counter == 30:
                    current_time = time.time()
                    fps = fps_counter / (current_time - last_time)
                    print(f"\rFPS: {fps:.1f}", end="")
                    fps_counter = 0
                    last_time = current_time
            else:
                connection_attempts += 1
                if connection_attempts >= 5:
                    print("\nConnection lost. Press 'r' to reconnect or 'q' to quit.")
                    connection_attempts = 0
            
            # التحكم في النافذة
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                print("\nReconnecting...")
                if check_adb():
                    frame_grabber = start_frame_grabber()
                    connection_attempts = 0
            elif key == ord('f'):
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_FULLSCREEN)
                    screen_info = cv2.getWindowImageRect(window_name)
                    touch_handler.update_screen_size(screen_width, screen_height, 
                                                  screen_info[2], screen_info[3])
                else:
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(window_name, window_width, window_height)
                    touch_handler.update_screen_size(screen_width, screen_height, 
                                                  window_width, window_height)
    
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if frame_grabber:
            frame_grabber.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
