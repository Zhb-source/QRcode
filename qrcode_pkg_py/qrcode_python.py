import rclpy
from rclpy.node import Node
import cv2
from pyzbar.pyzbar import decode
import time
import re
import csv
import os
import webbrowser
import threading
from pathlib import Path
from datetime import datetime

class QRCodeScanner(Node):
    def __init__(self):
        super().__init__('qrcode_scanner')
        
        # 配置参数
        self.declare_parameter('show_gui', False)  # 默认不显示GUI
        self.declare_parameter('skip_frames', 2)  # 默认跳帧数
        self.declare_parameter('base_save_dir', '~/qrcode_scans')  # 默认保存目录
        self.declare_parameter('open_interval', 5.0)  # 默认网页打开间隔
        
        # 获取参数值
        self.show_gui = self.get_parameter('show_gui').value
        self.skip_frames = self.get_parameter('skip_frames').value
        base_save_dir = self.get_parameter('base_save_dir').value
        self.open_interval = self.get_parameter('open_interval').value
        
        # 创建保存目录
        self.base_save_dir = Path(os.path.expanduser(base_save_dir))
        self.base_save_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化状态变量
        self.last_decoded_data = None
        self.last_open_time = 0
        self.frame_count = 0
        self.fps = 0
        self.start_time = time.time()
        self.decoded_data = []  # 存储所有解码结果
        self.frame_counter = 0
        self.csv_path = self.base_save_dir / 'scan_history.csv'
        
        # 日志记录配置信息
        self.get_logger().info(f"保存目录: {self.base_save_dir}")
        self.get_logger().info(f"显示GUI: {self.show_gui}")
        self.get_logger().info(f"跳帧设置: {self.skip_frames}")
        self.get_logger().info(f"网页打开间隔: {self.open_interval}秒")
        
        # 初始化摄像头
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.get_logger().error("无法打开摄像头")
            raise RuntimeError("无法打开摄像头")
        
        # 设置摄像头分辨率
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.get_logger().info("摄像头已打开，按 'q' 退出，按 's' 截图保存。")
        self.timer = self.create_timer(0.05, self.process_frame)  # 20FPS

    # 判断字符串是否为网址
    def is_url(self, string):
        return re.match(r'^https?://', string) is not None

    # 保存二维码内容到 CSV 文件
    def save_to_csv(self, data):
        try:
            file_exists = self.csv_path.exists()
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists:
                    writer.writerow(['时间', '二维码内容'])
                writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), data])
        except Exception as e:
            self.get_logger().error(f"保存 CSV 失败: {e}")

    # 在画面上绘制二维码信息
    def draw_qr_info(self, frame, qr_data, rect):
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), (200, 0, 200), 2)
        # 限制显示长度，防止内容太长溢出画面
        display_text = qr_data[:40] + "..." if len(qr_data) > 40 else qr_data
        cv2.putText(frame, display_text, (x, y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 打开浏览器的线程函数
    def open_browser_thread(self, url):
        try:
            webbrowser.open(url)
            self.get_logger().info(f"自动打开浏览器: {url}")
        except Exception as e:
            self.get_logger().error(f"打开浏览器失败: {e}")

    # 处理二维码数据
    def handle_qr_data(self, QR_data):
        if QR_data != self.last_decoded_data and QR_data not in self.decoded_data:
            self.decoded_data.append(QR_data)
            self.get_logger().info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 解码内容: {QR_data}")
            self.save_to_csv(QR_data)

            if self.is_url(QR_data):
                current_time = time.time()
                if current_time - self.last_open_time > self.open_interval:
                    # 启动线程打开浏览器
                    threading.Thread(target=self.open_browser_thread, args=(QR_data,)).start()
                    self.last_open_time = current_time
                else:
                    self.get_logger().info("跳转过于频繁，已忽略")
            else:
                self.get_logger().info("非网址内容")
            
            return QR_data
        return self.last_decoded_data

    # 获取当天的截图目录
    def get_daily_screenshot_dir(self):
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = self.base_save_dir / "screenshots" / today
        daily_dir.mkdir(parents=True, exist_ok=True)
        return daily_dir

    def process_frame(self):
        # 跳帧处理
        self.frame_counter = (self.frame_counter + 1) % (self.skip_frames + 1)
        if self.frame_counter != 0:
            return  # 跳过当前帧处理
        
        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.get_logger().error("无法读取摄像头帧")
            return

        # 计算FPS
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.start_time = time.time()

        # 解码二维码
        QR_codes = decode(frame)
        if QR_codes:
            for QR in QR_codes:
                try:
                    QR_data = QR.data.decode('utf-8')
                except UnicodeDecodeError:
                    self.get_logger().warn("二维码内容解码失败")
                    continue
                except Exception as e:
                    self.get_logger().error(f"解码异常: {e}")
                    continue

                rect = QR.rect
                self.last_decoded_data = self.handle_qr_data(QR_data)
                if self.show_gui:
                    self.draw_qr_info(frame, QR_data, rect)

        # 显示画面（可选）
        if self.show_gui:
            # 显示FPS
            cv2.putText(frame, f"FPS: {self.fps}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            # 显示保存路径
            cv2.putText(frame, f"保存路径: {self.base_save_dir}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.imshow("QRCode Scanner", frame)
            
            # 按键检测
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.get_logger().info("退出程序")
                self.destroy_node()
            elif key == ord('s'):
                daily_dir = self.get_daily_screenshot_dir()
                filename = daily_dir / f"screenshot_{int(time.time())}.jpg"
                try:
                    cv2.imwrite(str(filename), frame)
                    self.get_logger().info(f"截图保存为 {filename}")
                except Exception as e:
                    self.get_logger().error(f"截图保存失败: {e}")
            elif key == ord('d'):
                # 调试按键：显示当前配置
                self.get_logger().info(f"当前配置: GUI={self.show_gui}, 跳帧={self.skip_frames}")
                self.get_logger().info(f"保存目录: {self.base_save_dir}")

    def destroy_node(self):
        self.cap.release()
        if self.show_gui:
            cv2.destroyAllWindows()
        self.get_logger().info("摄像头释放，程序结束")
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = QRCodeScanner()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("用户中断程序")
    except Exception as e:
        node.get_logger().error(f"程序运行时发生错误: {e}")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()