#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interception DLL驱动模块
纯DLL调用，替换所有PyAutoGUI功能
"""

import os
import sys
import time
import ctypes
import logging
from ctypes import wintypes, Structure, c_int, c_void_p, c_ushort
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 获取DLL路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL_PATH = os.path.join(PROJECT_ROOT, "Interception", "library", "x64", "interception.dll")

# Interception常量
INTERCEPTION_MAX_KEYBOARD = 10
INTERCEPTION_MAX_MOUSE = 10

# 过滤器常量
INTERCEPTION_FILTER_KEY_ALL = 0xFFFF
INTERCEPTION_FILTER_MOUSE_ALL = 0xFFFF

# 键盘状态
INTERCEPTION_KEY_DOWN = 0x00
INTERCEPTION_KEY_UP = 0x01

# 鼠标状态（state字段）
INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN = 0x001
INTERCEPTION_MOUSE_LEFT_BUTTON_UP = 0x002
INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN = 0x004
INTERCEPTION_MOUSE_RIGHT_BUTTON_UP = 0x008
INTERCEPTION_MOUSE_MIDDLE_BUTTON_DOWN = 0x010
INTERCEPTION_MOUSE_MIDDLE_BUTTON_UP = 0x020
INTERCEPTION_MOUSE_WHEEL = 0x400

# 鼠标状态（state字段）
INTERCEPTION_MOUSE_MOVE = 0x000

# 鼠标移动标志（flags字段）
INTERCEPTION_MOUSE_MOVE_RELATIVE = 0x000
INTERCEPTION_MOUSE_MOVE_ABSOLUTE = 0x001

# 结构体定义
class InterceptionKeyStroke(Structure):
    _fields_ = [
        ("code", wintypes.WORD),
        ("state", wintypes.WORD),
        ("information", wintypes.DWORD)
    ]

class InterceptionMouseStroke(Structure):
    _fields_ = [
        ("state", wintypes.WORD),      # unsigned short state
        ("flags", wintypes.WORD),      # unsigned short flags
        ("rolling", wintypes.SHORT),   # short rolling
        ("x", c_int),                  # int x
        ("y", c_int),                  # int y
        ("information", wintypes.DWORD) # unsigned int information
    ]

class InterceptionDriver:
    """Interception DLL驱动类"""
    
    # 按键扫描码映射
    KEY_CODES = {
        'a': 30, 'b': 48, 'c': 46, 'd': 32, 'e': 18, 'f': 33, 'g': 34, 'h': 35,
        'i': 23, 'j': 36, 'k': 37, 'l': 38, 'm': 50, 'n': 49, 'o': 24, 'p': 25,
        'q': 16, 'r': 19, 's': 31, 't': 20, 'u': 22, 'v': 47, 'w': 17, 'x': 45,
        'y': 21, 'z': 44,
        '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7, '7': 8, '8': 9, '9': 10, '0': 11,
        'enter': 28, 'space': 57, 'tab': 15, 'shift': 42, 'ctrl': 29, 'alt': 56,
        'esc': 1, 'escape': 1, 'backspace': 14, 'delete': 83, 
        'up': 72, 'down': 80, 'left': 75, 'right': 77,
        'f1': 59, 'f2': 60, 'f3': 61, 'f4': 62, 'f5': 63, 'f6': 64,
        'f7': 65, 'f8': 66, 'f9': 67, 'f10': 68, 'f11': 87, 'f12': 88,
        # 特殊字符
        '!': 2, '@': 3, '#': 4, '$': 5, '%': 6, '^': 7, '&': 8, '*': 9, '(': 10, ')': 11,
        '-': 12, '=': 13, '[': 26, ']': 27, '\\': 43, ';': 39, "'": 40, '`': 41,
        ',': 51, '.': 52, '/': 53
    }
    
    def __init__(self):
        """初始化驱动"""
        self.dll = None
        self.context = None
        self.keyboard_device = 1
        self.mouse_device = 11
        self.initialized = False
        
    def initialize(self) -> bool:
        """初始化DLL驱动"""
        if self.initialized:
            return True

        try:
            # 检查DLL文件
            if not os.path.exists(DLL_PATH):
                logger.error(f"❌ 驱动文件不存在: {DLL_PATH}")
                logger.error("请确保驱动已正确安装在项目目录中")
                return False

            logger.debug(f"✓ 找到驱动文件")

            # 检查管理员权限
            try:
                import ctypes
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
                if not is_admin:
                    logger.warning("⚠ 当前未以管理员权限运行，驱动可能无法正常工作")
                    logger.warning("建议：以管理员身份运行程序以启用完整的前台模式功能")
                else:
                    logger.debug("✓ 检测到管理员权限")
            except Exception as admin_check_error:
                logger.debug(f"无法检查管理员权限: {admin_check_error}")

            # 加载DLL
            logger.debug("正在加载驱动...")
            self.dll = ctypes.CDLL(DLL_PATH)
            logger.debug("✓ 驱动加载成功")

            # 设置函数原型
            self.dll.interception_create_context.restype = c_void_p
            self.dll.interception_destroy_context.argtypes = [c_void_p]
            self.dll.interception_set_filter.argtypes = [c_void_p, ctypes.CFUNCTYPE(c_int, c_int), c_ushort]
            self.dll.interception_send.argtypes = [c_void_p, c_int, ctypes.c_void_p, c_int]
            self.dll.interception_send.restype = c_int

            # 创建上下文
            logger.debug("正在创建驱动上下文...")
            self.context = self.dll.interception_create_context()

            if not self.context:
                logger.error("❌ 无法创建驱动上下文")
                logger.error("")
                logger.error("可能的原因：")
                logger.error("  1. 驱动未安装")
                logger.error("  2. 需要管理员权限运行程序")
                logger.error("  3. 驱动被安全软件拦截")
                logger.error("  4. Windows版本不兼容")
                logger.error("")
                logger.error("解决方案：")
                logger.error("  → 运行驱动安装程序")
                logger.error("  → 重启计算机使驱动生效")
                logger.error("  → 以管理员身份运行本程序")
                logger.error("  → 临时关闭安全软件后再试")
                logger.error("")
                logger.error("注意：前台模式将自动回退到兼容模式")
                return False

            self.initialized = True
            logger.info("✓ 驱动初始化成功")
            return True

        except FileNotFoundError as e:
            logger.error(f"❌ 找不到驱动文件或依赖库: {e}")
            logger.error("请确保所有文件都在正确的位置")
            return False
        except OSError as e:
            logger.error(f"❌ 加载驱动时发生系统错误: {e}")
            logger.error("可能是文件损坏或版本不匹配")
            return False
        except Exception as e:
            logger.error(f"❌ 驱动初始化失败: {e}")
            logger.error("前台模式将自动回退到兼容模式")
            return False
    
    def _get_current_mouse_pos(self) -> Tuple[int, int]:
        """获取当前鼠标位置（像素坐标）"""
        try:
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return point.x, point.y
        except:
            return 0, 0

    def _pixel_to_interception(self, x: int, y: int) -> Tuple[int, int]:
        """将像素坐标转换为内部坐标格式"""
        try:
            screen_width = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN

            # 转换为内部坐标系统
            interception_x = int((x * 65535) / screen_width)
            interception_y = int((y * 65535) / screen_height)

            # 确保坐标在有效范围内
            interception_x = max(0, min(65535, interception_x))
            interception_y = max(0, min(65535, interception_y))

            return interception_x, interception_y
        except Exception as e:
            logger.error(f"坐标转换失败: {e}")
            return x, y  # 失败时返回原坐标

    def _interception_to_pixel(self, x: int, y: int) -> Tuple[int, int]:
        """将内部坐标格式转换为像素坐标"""
        try:
            screen_width = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN

            # 从内部坐标系统转换为像素
            pixel_x = int((x * screen_width) / 65535)
            pixel_y = int((y * screen_height) / 65535)

            return pixel_x, pixel_y
        except Exception as e:
            logger.error(f"坐标转换失败: {e}")
            return x, y  # 失败时返回原坐标
    
    def _send_key_event(self, scan_code: int, key_down: bool) -> bool:
        """发送键盘事件"""
        if not self.initialized:
            if not self.initialize():
                return False
        
        try:
            stroke = InterceptionKeyStroke()
            stroke.code = scan_code
            stroke.state = INTERCEPTION_KEY_DOWN if key_down else INTERCEPTION_KEY_UP
            stroke.information = 0
            
            result = self.dll.interception_send(
                self.context, 
                self.keyboard_device, 
                ctypes.byref(stroke), 
                1
            )
            
            return result > 0
            
        except Exception as e:
            logger.error(f"发送键盘事件失败: {e}")
            return False
    
    def _send_mouse_event(self, x: int = 0, y: int = 0, flags: int = 0, state: int = 0, rolling: int = 0) -> bool:
        """发送鼠标事件"""
        if not self.initialized:
            if not self.initialize():
                return False
        
        try:
            stroke = InterceptionMouseStroke()
            stroke.x = x
            stroke.y = y
            stroke.flags = flags
            stroke.state = state
            stroke.rolling = rolling
            stroke.information = 0
            
            result = self.dll.interception_send(
                self.context,
                self.mouse_device,
                ctypes.byref(stroke),
                1
            )
            
            return result > 0
            
        except Exception as e:
            logger.error(f"发送鼠标事件失败: {e}")
            return False
    
    def press_key(self, key: str, duration: float = 0.05) -> bool:
        """按下并释放按键"""
        scan_code = self.KEY_CODES.get(key.lower())
        if not scan_code:
            logger.warning(f"未知按键: {key}")
            return False
        
        # 按下
        if not self._send_key_event(scan_code, True):
            return False
        
        time.sleep(duration)
        
        # 释放
        return self._send_key_event(scan_code, False)
    
    def key_down(self, key: str) -> bool:
        """按下按键（不释放）"""
        scan_code = self.KEY_CODES.get(key.lower())
        if not scan_code:
            logger.warning(f"未知按键: {key}")
            return False
        
        return self._send_key_event(scan_code, True)
    
    def key_up(self, key: str) -> bool:
        """释放按键"""
        scan_code = self.KEY_CODES.get(key.lower())
        if not scan_code:
            logger.warning(f"未知按键: {key}")
            return False
        
        return self._send_key_event(scan_code, False)
    
    def type_text(self, text: str, delay: float = 0.05) -> bool:
        """输入文本"""
        for char in text:
            if char == ' ':
                key = 'space'
            elif char == '\n':
                key = 'enter'
            elif char == '\t':
                key = 'tab'
            elif char.lower() in self.KEY_CODES:
                key = char.lower()
            else:
                logger.warning(f"无法输入字符: {char}")
                continue
            
            if not self.press_key(key, delay):
                return False
            time.sleep(delay)
        
        return True
    
    def hotkey(self, *keys) -> bool:
        """组合键"""
        scan_codes = []
        
        for key in keys:
            scan_code = self.KEY_CODES.get(key.lower())
            if scan_code is None:
                logger.warning(f"未知按键: {key}")
                return False
            scan_codes.append(scan_code)
        
        # 按下所有键
        for scan_code in scan_codes:
            self._send_key_event(scan_code, True)
            time.sleep(0.01)
        
        time.sleep(0.05)
        
        # 释放所有键（逆序）
        for scan_code in reversed(scan_codes):
            self._send_key_event(scan_code, False)
            time.sleep(0.01)
        
        return True
    
    def move_mouse(self, x: int, y: int, absolute: bool = True) -> bool:
        """移动鼠标（输入像素坐标）"""
        if absolute:
            # 绝对坐标：转换像素坐标为内部格式
            interception_x, interception_y = self._pixel_to_interception(x, y)
            flags = INTERCEPTION_MOUSE_MOVE_ABSOLUTE
            return self._send_mouse_event(interception_x, interception_y, flags, INTERCEPTION_MOUSE_MOVE, 0)
        else:
            # 相对坐标：直接使用像素偏移
            flags = INTERCEPTION_MOUSE_MOVE_RELATIVE
            return self._send_mouse_event(x, y, flags, INTERCEPTION_MOUSE_MOVE, 0)
    
    def click_mouse(self, x: Optional[int] = None, y: Optional[int] = None,
                   button: str = 'left', clicks: int = 1, interval: float = 0.0,
                   duration: float = 0.05) -> bool:
        """鼠标点击（输入像素坐标）"""
        # 确定点击位置
        if x is not None and y is not None:
            if not self.move_mouse(x, y):
                logger.error(f"移动鼠标到({x}, {y})失败")
                return False
            time.sleep(0.01)

        # 确定按键状态
        if button.lower() == 'left':
            down_state = INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN
            up_state = INTERCEPTION_MOUSE_LEFT_BUTTON_UP
        elif button.lower() == 'right':
            down_state = INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN
            up_state = INTERCEPTION_MOUSE_RIGHT_BUTTON_UP
        elif button.lower() == 'middle':
            down_state = INTERCEPTION_MOUSE_MIDDLE_BUTTON_DOWN
            up_state = INTERCEPTION_MOUSE_MIDDLE_BUTTON_UP
        else:
            logger.warning(f"未知鼠标按键: {button}")
            return False

        # 执行点击
        for i in range(clicks):
            if i > 0 and interval > 0:
                time.sleep(interval)

            # 按下
            if not self._send_mouse_event(0, 0, 0, down_state, 0):
                return False

            time.sleep(duration)

            # 释放
            if not self._send_mouse_event(0, 0, 0, up_state, 0):
                return False

        return True
    
    def drag_mouse(self, start_x: int, start_y: int, end_x: int, end_y: int,
                  button: str = 'left', duration: float = 1.0) -> bool:
        """鼠标拖拽（输入像素坐标）"""
        # 移动到起始位置
        if not self.move_mouse(start_x, start_y):
            logger.error(f"移动到起始位置({start_x}, {start_y})失败")
            return False
        time.sleep(0.1)
        
        # 确定按键状态
        if button.lower() == 'left':
            down_state = INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN
            up_state = INTERCEPTION_MOUSE_LEFT_BUTTON_UP
        elif button.lower() == 'right':
            down_state = INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN
            up_state = INTERCEPTION_MOUSE_RIGHT_BUTTON_UP
        else:
            logger.warning(f"未知鼠标按键: {button}")
            return False
        
        # 按下鼠标（不发送坐标，只发送按钮状态）
        if not self._send_mouse_event(0, 0, 0, down_state, 0):
            return False

        time.sleep(0.1)

        # 拖拽到目标位置
        if duration > 0:
            steps = max(10, int(duration * 100))
            for i in range(steps + 1):
                progress = i / steps
                current_pixel_x = int(start_x + (end_x - start_x) * progress)
                current_pixel_y = int(start_y + (end_y - start_y) * progress)
                self.move_mouse(current_pixel_x, current_pixel_y)
                time.sleep(duration / steps)
        else:
            self.move_mouse(end_x, end_y)

        # 释放鼠标（不发送坐标，只发送按钮状态）
        return self._send_mouse_event(0, 0, 0, up_state, 0)
    
    def scroll_mouse(self, direction: str, clicks: int = 1, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """鼠标滚轮（输入像素坐标）"""
        if x is not None and y is not None:
            if not self.move_mouse(x, y):
                logger.error(f"移动鼠标到({x}, {y})失败")
                return False

        # 获取当前像素坐标
        current_x, current_y = self._get_current_mouse_pos()

        if direction.lower() == 'up':
            rolling = 120 * clicks
        elif direction.lower() == 'down':
            rolling = -120 * clicks
        else:
            logger.warning(f"未知滚动方向: {direction}")
            return False

        return self._send_mouse_event(current_x, current_y, 0, INTERCEPTION_MOUSE_WHEEL, rolling)
    
    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸"""
        try:
            return (
                ctypes.windll.user32.GetSystemMetrics(0),  # SM_CXSCREEN
                ctypes.windll.user32.GetSystemMetrics(1)   # SM_CYSCREEN
            )
        except:
            return (1920, 1080)  # 默认值
    
    def get_mouse_position(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        return self._get_current_mouse_pos()
    
    def close(self) -> None:
        """清理资源"""
        if self.context and self.dll:
            try:
                self.dll.interception_destroy_context(self.context)
            except:
                pass
        self.context = None
        self.initialized = False
        logger.info("Interception驱动已关闭")


# 全局驱动实例
_driver_instance = None

def get_driver() -> InterceptionDriver:
    """获取全局驱动实例"""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = InterceptionDriver()
    return _driver_instance
