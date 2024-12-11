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
        phone_x, phone_y = self.map_coordinates(x, y)
        subprocess.run([ADB_PATH, 'shell', f'input touchscreen tap {phone_x} {phone_y}'])
        
    def touch_move(self, x, y):
        if self.is_dragging:
            phone_x, phone_y = self.map_coordinates(x, y)
            last_phone_x, last_phone_y = self.map_coordinates(self.last_x, self.last_y)
            subprocess.run([ADB_PATH, 'shell', f'input touchscreen swipe {last_phone_x} {last_phone_y} {phone_x} {phone_y} 100'])
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

class FrameGrabber:
    def __init__(self):
        self.frame_queue = Queue(maxsize=2)
        self.stopped = False
        
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
                try:
                    self.frame_queue.put_nowait(frame)
                except:
                    pass
                    
    def _capture_frame(self):
        try:
            process = subprocess.Popen(
                f'"{ADB_PATH}" exec-out screencap -p',
                stdout=subprocess.PIPE,
                shell=True
            )
            screenshot_data = process.stdout.read()
            
            if not screenshot_data:
                return None
                
            nparr = np.frombuffer(screenshot_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return None
                
            return frame
            
        except Exception as e:
            return None
            
    def read(self):
        try:
            return self.frame_queue.get_nowait() if not self.frame_queue.empty() else None
        except:
            return None
            
    def stop(self):
        self.stopped = True

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

def check_adb():
    try:
        if not os.path.exists(ADB_PATH):
            print(f"Error: ADB not found at {ADB_PATH}")
            return False
            
        process = subprocess.run(
            f'"{ADB_PATH}" devices',
            capture_output=True,
            text=True,
            shell=True
        )
        
        if "device" not in process.stdout:
            print("No Android device found")
            return False
            
        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

def main():
    print("Android Screen Mirror with Touch Control")
    print("Press 'q' to exit")
    print("Press 'f' to toggle fullscreen")
    print("Use mouse to control the device:")
    print("- Left click: Tap")
    print("- Left click + drag: Swipe")
    
    if not check_adb():
        return
        
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
    frame_grabber = FrameGrabber().start()
    last_time = time.time()
    fps_counter = 0
    
    try:
        while True:
            frame = frame_grabber.read()
            
            if frame is not None:
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
            
            # التحكم في النافذة
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('f'):
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_FULLSCREEN)
                    # تحديث حجم النافذة في وضع ملء الشاشة
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
    finally:
        frame_grabber.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
