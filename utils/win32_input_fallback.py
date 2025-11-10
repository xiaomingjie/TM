#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Win32 API 输入回退模块
当 Interception 驱动不可用时，使用 win32api 作为后备方案
"""

import time
import logging
from typing import Optional, Tuple

try:
    import win32api
    import win32con
    import win32gui
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)


class Win32InputFallback:
    """Win32 API 输入回退类"""

    def __init__(self):
        """初始化"""
        self.initialized = False

    def initialize(self) -> bool:
        """初始化回退模块"""
        if self.initialized:
            return True

        if not PYWIN32_AVAILABLE:
            logger.error("❌ 系统库不可用，无法使用备用输入方法")
            return False

        self.initialized = True
        logger.info("✓ 备用输入方法已初始化")
        return True

    def move_mouse(self, x: int, y: int, absolute: bool = True) -> bool:
        """
        移动鼠标

        Args:
            x: X坐标（屏幕坐标）
            y: Y坐标（屏幕坐标）
            absolute: 是否为绝对坐标

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            if absolute:
                # 使用 SetCursorPos 设置绝对位置
                win32api.SetCursorPos((x, y))
                return True
            else:
                # 相对移动：先获取当前位置，再移动
                current_x, current_y = win32api.GetCursorPos()
                new_x = current_x + x
                new_y = current_y + y
                win32api.SetCursorPos((new_x, new_y))
                return True
        except Exception as e:
            logger.error(f"鼠标移动失败: {e}")
            return False

    def click_mouse(self, x: Optional[int] = None, y: Optional[int] = None,
                   button: str = 'left', clicks: int = 1, interval: float = 0.0,
                   duration: float = 0.05) -> bool:
        """
        鼠标点击

        Args:
            x: X坐标（屏幕坐标，None表示当前位置）
            y: Y坐标（屏幕坐标，None表示当前位置）
            button: 按钮类型 ('left', 'right', 'middle')
            clicks: 点击次数
            interval: 多次点击间隔
            duration: 单次点击按下时长

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            # 移动到目标位置
            if x is not None and y is not None:
                if not self.move_mouse(x, y):
                    return False
                time.sleep(0.01)  # 等待鼠标移动完成

            # 确定按钮事件
            if button.lower() == 'left':
                down_event = win32con.MOUSEEVENTF_LEFTDOWN
                up_event = win32con.MOUSEEVENTF_LEFTUP
            elif button.lower() == 'right':
                down_event = win32con.MOUSEEVENTF_RIGHTDOWN
                up_event = win32con.MOUSEEVENTF_RIGHTUP
            elif button.lower() == 'middle':
                down_event = win32con.MOUSEEVENTF_MIDDLEDOWN
                up_event = win32con.MOUSEEVENTF_MIDDLEUP
            else:
                logger.error(f"不支持的按钮类型: {button}")
                return False

            # 执行点击
            for i in range(clicks):
                if i > 0 and interval > 0:
                    time.sleep(interval)

                # 按下
                win32api.mouse_event(down_event, 0, 0, 0, 0)
                time.sleep(duration)

                # 释放
                win32api.mouse_event(up_event, 0, 0, 0, 0)

            return True

        except Exception as e:
            logger.error(f"点击失败: {e}")
            return False

    def drag_mouse(self, start_x: int, start_y: int, end_x: int, end_y: int,
                  button: str = 'left', duration: float = 1.0) -> bool:
        """
        鼠标拖拽

        Args:
            start_x: 起始X坐标（屏幕坐标）
            start_y: 起始Y坐标（屏幕坐标）
            end_x: 结束X坐标（屏幕坐标）
            end_y: 结束Y坐标（屏幕坐标）
            button: 按钮类型
            duration: 拖拽持续时间

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            # 移动到起始位置
            if not self.move_mouse(start_x, start_y):
                return False
            time.sleep(0.1)

            # 确定按钮事件
            if button.lower() == 'left':
                down_event = win32con.MOUSEEVENTF_LEFTDOWN
                up_event = win32con.MOUSEEVENTF_LEFTUP
            elif button.lower() == 'right':
                down_event = win32con.MOUSEEVENTF_RIGHTDOWN
                up_event = win32con.MOUSEEVENTF_RIGHTUP
            else:
                logger.error(f"拖拽不支持的按钮类型: {button}")
                return False

            # 按下鼠标
            win32api.mouse_event(down_event, 0, 0, 0, 0)
            time.sleep(0.05)

            # 拖拽到目标位置
            if duration > 0:
                steps = max(10, int(duration * 100))
                for i in range(steps + 1):
                    progress = i / steps
                    current_x = int(start_x + (end_x - start_x) * progress)
                    current_y = int(start_y + (end_y - start_y) * progress)
                    self.move_mouse(current_x, current_y)
                    time.sleep(duration / steps)
            else:
                self.move_mouse(end_x, end_y)

            # 释放鼠标
            win32api.mouse_event(up_event, 0, 0, 0, 0)
            return True

        except Exception as e:
            logger.error(f"拖拽失败: {e}")
            return False

    def scroll_mouse(self, direction: str, clicks: int = 1, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """
        鼠标滚轮

        Args:
            direction: 滚动方向 ('up' 或 'down')
            clicks: 滚动次数
            x: X坐标（None表示当前位置）
            y: Y坐标（None表示当前位置）

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            # 移动到目标位置
            if x is not None and y is not None:
                if not self.move_mouse(x, y):
                    return False

            # 确定滚动方向
            if direction.lower() == 'up':
                scroll_amount = win32con.WHEEL_DELTA * clicks
            elif direction.lower() == 'down':
                scroll_amount = -win32con.WHEEL_DELTA * clicks
            else:
                logger.error(f"不支持的滚动方向: {direction}")
                return False

            # 执行滚动
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, scroll_amount, 0)
            return True

        except Exception as e:
            logger.error(f"滚轮滚动失败: {e}")
            return False

    def press_key(self, key: str, duration: float = 0.05) -> bool:
        """
        按下并释放按键

        Args:
            key: 按键名称（如 'a', 'enter', 'ctrl'等）
            duration: 按键持续时间

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            vk_code = self._get_vk_code(key)
            if vk_code is None:
                logger.error(f"不支持的按键: {key}")
                return False

            # 按下
            win32api.keybd_event(vk_code, 0, 0, 0)
            time.sleep(duration)

            # 释放
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True

        except Exception as e:
            logger.error(f"按键操作失败: {e}")
            return False

    def press_key_down(self, key: str) -> bool:
        """
        按下按键（不释放）

        Args:
            key: 按键名称

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            vk_code = self._get_vk_code(key)
            if vk_code is None:
                logger.error(f"不支持的按键: {key}")
                return False

            win32api.keybd_event(vk_code, 0, 0, 0)
            return True

        except Exception as e:
            logger.error(f"按键按下失败: {e}")
            return False

    def press_key_up(self, key: str) -> bool:
        """
        释放按键

        Args:
            key: 按键名称

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            vk_code = self._get_vk_code(key)
            if vk_code is None:
                logger.error(f"不支持的按键: {key}")
                return False

            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True

        except Exception as e:
            logger.error(f"按键释放失败: {e}")
            return False

    def press_keys_combo(self, keys: list, duration: float = 0.05) -> bool:
        """
        按下组合键

        Args:
            keys: 按键列表（如 ['ctrl', 'c']）
            duration: 按键持续时间

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        try:
            # 按下所有键
            for key in keys:
                if not self.press_key_down(key):
                    # 失败时释放已按下的键
                    for prev_key in keys[:keys.index(key)]:
                        self.press_key_up(prev_key)
                    return False
                time.sleep(0.01)

            time.sleep(duration)

            # 释放所有键（倒序）
            for key in reversed(keys):
                self.press_key_up(key)
                time.sleep(0.01)

            return True

        except Exception as e:
            logger.error(f"组合键操作失败: {e}")
            return False

    def _get_vk_code(self, key: str):
        """
        获取按键的虚拟键码

        Args:
            key: 按键名称

        Returns:
            虚拟键码，如果不支持则返回None
        """
        # 转换为小写统一处理
        key = key.lower()

        # 字母和数字键
        if len(key) == 1:
            if 'a' <= key <= 'z':
                return ord(key.upper())
            elif '0' <= key <= '9':
                return ord(key)

        # 功能键和特殊键映射
        key_map = {
            'enter': win32con.VK_RETURN,
            'return': win32con.VK_RETURN,
            'esc': win32con.VK_ESCAPE,
            'escape': win32con.VK_ESCAPE,
            'backspace': win32con.VK_BACK,
            'tab': win32con.VK_TAB,
            'space': win32con.VK_SPACE,
            'shift': win32con.VK_SHIFT,
            'ctrl': win32con.VK_CONTROL,
            'control': win32con.VK_CONTROL,
            'alt': win32con.VK_MENU,
            'win': win32con.VK_LWIN,
            'windows': win32con.VK_LWIN,
            'capslock': win32con.VK_CAPITAL,
            'numlock': win32con.VK_NUMLOCK,
            'scrolllock': win32con.VK_SCROLL,

            # 功能键
            'f1': win32con.VK_F1,
            'f2': win32con.VK_F2,
            'f3': win32con.VK_F3,
            'f4': win32con.VK_F4,
            'f5': win32con.VK_F5,
            'f6': win32con.VK_F6,
            'f7': win32con.VK_F7,
            'f8': win32con.VK_F8,
            'f9': win32con.VK_F9,
            'f10': win32con.VK_F10,
            'f11': win32con.VK_F11,
            'f12': win32con.VK_F12,

            # 方向键
            'left': win32con.VK_LEFT,
            'right': win32con.VK_RIGHT,
            'up': win32con.VK_UP,
            'down': win32con.VK_DOWN,

            # 其他常用键
            'home': win32con.VK_HOME,
            'end': win32con.VK_END,
            'pageup': win32con.VK_PRIOR,
            'pagedown': win32con.VK_NEXT,
            'insert': win32con.VK_INSERT,
            'delete': win32con.VK_DELETE,
            'printscreen': win32con.VK_SNAPSHOT,
            'pause': win32con.VK_PAUSE,
        }

        return key_map.get(key)

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸"""
        try:
            import ctypes
            return (
                ctypes.windll.user32.GetSystemMetrics(0),  # SM_CXSCREEN
                ctypes.windll.user32.GetSystemMetrics(1)   # SM_CYSCREEN
            )
        except:
            return (1920, 1080)  # 默认值

    def get_mouse_position(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        try:
            return win32api.GetCursorPos()
        except:
            return (0, 0)

    def close(self) -> None:
        """清理资源"""
        self.initialized = False
        logger.debug("备用输入方法已关闭")


# 全局回退实例
_fallback_instance = None

def get_fallback() -> Win32InputFallback:
    """获取全局回退实例"""
    global _fallback_instance
    if _fallback_instance is None:
        _fallback_instance = Win32InputFallback()
    return _fallback_instance
