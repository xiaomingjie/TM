#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyAutoGUI 输入回退模块
使用 PyAutoGUI 作为前台输入的最终备用方案
注意：需要激活窗口才能正常工作
"""

import time
import logging
from typing import Optional, Tuple

try:
    import pyautogui
    # 禁用PyAutoGUI的安全特性（鼠标移动到屏幕角落不会触发异常）
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

logger = logging.getLogger(__name__)


class PyAutoGUIFallback:
    """PyAutoGUI 输入回退类"""

    def __init__(self):
        """初始化"""
        self.initialized = False
        self.target_hwnd = None  # 目标窗口句柄

    def initialize(self) -> bool:
        """初始化回退模块"""
        if self.initialized:
            return True

        if not PYAUTOGUI_AVAILABLE:
            logger.error("❌ PyAutoGUI 库不可用，无法使用此备用方法")
            return False

        self.initialized = True
        logger.info("✓ PyAutoGUI 备用输入方法已初始化")
        logger.warning("⚠️ PyAutoGUI 需要激活目标窗口才能正常工作")
        return True

    def set_target_window(self, hwnd: int) -> None:
        """
        设置目标窗口句柄

        Args:
            hwnd: 窗口句柄
        """
        self.target_hwnd = hwnd

    def activate_target_window(self) -> bool:
        """
        激活目标窗口

        Returns:
            是否成功激活
        """
        if not WIN32_AVAILABLE or not self.target_hwnd:
            return False

        try:
            # 检查窗口是否存在
            if not win32gui.IsWindow(self.target_hwnd):
                logger.error("目标窗口不存在")
                return False

            # 如果窗口最小化，先恢复
            if win32gui.IsIconic(self.target_hwnd):
                win32gui.ShowWindow(self.target_hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)

            # 激活窗口
            win32gui.SetForegroundWindow(self.target_hwnd)
            time.sleep(0.05)  # 等待窗口激活

            return True

        except Exception as e:
            logger.error(f"激活窗口失败: {e}")
            return False

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
                pyautogui.moveTo(x, y, duration=0)
            else:
                pyautogui.moveRel(x, y, duration=0)
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
            duration: 移动到目标位置的时间

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, clicks=clicks, interval=interval, button=button)
            else:
                pyautogui.click(clicks=clicks, interval=interval, button=button)
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

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            # 移动到起始位置
            pyautogui.moveTo(start_x, start_y, duration=0)
            time.sleep(0.05)

            # 拖拽到目标位置
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration, button=button)
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

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            # 移动到目标位置
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0)
                time.sleep(0.01)

            # 确定滚动方向
            if direction.lower() == 'up':
                scroll_amount = clicks * 100
            elif direction.lower() == 'down':
                scroll_amount = -clicks * 100
            else:
                logger.error(f"不支持的滚动方向: {direction}")
                return False

            # 执行滚动
            pyautogui.scroll(scroll_amount)
            return True

        except Exception as e:
            logger.error(f"滚轮滚动失败: {e}")
            return False

    def press_key(self, key: str, duration: float = 0.05) -> bool:
        """
        按下并释放按键

        Args:
            key: 按键名称
            duration: 按键持续时间

        Returns:
            是否成功
        """
        if not self.initialize():
            return False

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            # 转换按键名称
            key_name = self._convert_key_name(key)
            if key_name is None:
                logger.error(f"不支持的按键: {key}")
                return False

            pyautogui.press(key_name)
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

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            key_name = self._convert_key_name(key)
            if key_name is None:
                logger.error(f"不支持的按键: {key}")
                return False

            pyautogui.keyDown(key_name)
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
            key_name = self._convert_key_name(key)
            if key_name is None:
                logger.error(f"不支持的按键: {key}")
                return False

            pyautogui.keyUp(key_name)
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

        # 激活目标窗口
        if self.target_hwnd:
            self.activate_target_window()

        try:
            # 转换按键名称
            converted_keys = []
            for key in keys:
                key_name = self._convert_key_name(key)
                if key_name is None:
                    logger.error(f"不支持的按键: {key}")
                    return False
                converted_keys.append(key_name)

            # 使用hotkey执行组合键
            pyautogui.hotkey(*converted_keys)
            return True

        except Exception as e:
            logger.error(f"组合键操作失败: {e}")
            return False

    def _convert_key_name(self, key: str) -> Optional[str]:
        """
        转换按键名称为PyAutoGUI格式

        Args:
            key: 按键名称

        Returns:
            PyAutoGUI按键名称，如果不支持则返回None
        """
        key = key.lower()

        # 字母和数字键直接返回
        if len(key) == 1 and (key.isalnum()):
            return key

        # 特殊键映射
        key_map = {
            'ctrl': 'ctrl',
            'control': 'ctrl',
            'shift': 'shift',
            'alt': 'alt',
            'win': 'win',
            'windows': 'win',
            'enter': 'enter',
            'return': 'enter',
            'esc': 'esc',
            'escape': 'esc',
            'backspace': 'backspace',
            'tab': 'tab',
            'space': 'space',
            'capslock': 'capslock',
            'numlock': 'numlock',
            'scrolllock': 'scrolllock',

            # 功能键
            'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
            'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
            'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',

            # 方向键
            'left': 'left',
            'right': 'right',
            'up': 'up',
            'down': 'down',

            # 其他常用键
            'home': 'home',
            'end': 'end',
            'pageup': 'pageup',
            'pagedown': 'pagedown',
            'insert': 'insert',
            'delete': 'delete',
            'printscreen': 'printscreen',
            'pause': 'pause',
        }

        return key_map.get(key)

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸"""
        try:
            size = pyautogui.size()
            return (size.width, size.height)
        except:
            return (1920, 1080)  # 默认值

    def get_mouse_position(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        try:
            pos = pyautogui.position()
            return (pos.x, pos.y)
        except:
            return (0, 0)

    def close(self) -> None:
        """清理资源"""
        self.initialized = False
        self.target_hwnd = None
        logger.debug("PyAutoGUI备用输入方法已关闭")


# 全局回退实例
_fallback_instance = None

def get_pyautogui_fallback() -> PyAutoGUIFallback:
    """获取全局PyAutoGUI回退实例"""
    global _fallback_instance
    if _fallback_instance is None:
        _fallback_instance = PyAutoGUIFallback()
    return _fallback_instance
