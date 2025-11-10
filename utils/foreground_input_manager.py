#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前台输入驱动管理器
自动选择最佳的输入方法：Interception驱动 或 PyAutoGUI
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ForegroundInputManager:
    """前台输入驱动管理器"""

    def __init__(self):
        """初始化"""
        self._interception_driver = None
        self._pyautogui_fallback = None
        self._active_driver = None
        self._driver_type = None  # 'interception' 或 'pyautogui'
        self._initialization_attempted = False
        self._forced_mode = None  # 强制使用的模式

    def set_forced_mode(self, mode: str) -> None:
        """
        设置强制使用的驱动模式

        Args:
            mode: 'interception', 'pyautogui', 'driver'
        """
        self._forced_mode = mode
        # 重置初始化状态，下次调用时会使用新模式
        # 关键修复：不调用close()，只重置引用，避免销毁全局单例的context
        self._active_driver = None
        self._driver_type = None
        self._initialization_attempted = False
        logger.info(f"前台输入强制模式已设置为: {mode}")

    def initialize(self) -> bool:
        """
        初始化驱动
        根据_forced_mode决定初始化策略

        Returns:
            是否成功初始化任何可用的驱动
        """
        if self._initialization_attempted:
            return self._active_driver is not None

        self._initialization_attempted = True

        # 根据强制模式选择初始化策略
        if self._forced_mode == 'interception':
            return self._initialize_interception_only()
        elif self._forced_mode == 'pyautogui':
            return self._initialize_pyautogui_only()
        elif self._forced_mode == 'driver':
            # 保留driver模式用于自动降级（兼容旧代码）
            return self._initialize_auto()
        else:
            # 默认：强制使用Interception（不降级）
            return self._initialize_interception_only()

    def _initialize_interception_only(self) -> bool:
        """强制使用Interception驱动（不降级）"""
        logger.info("正在初始化驱动模式一...")

        try:
            from utils.interception_driver import get_driver
            self._interception_driver = get_driver()

            if self._interception_driver.initialize():
                self._active_driver = self._interception_driver
                self._driver_type = 'interception'
                logger.info("✓ 驱动模式一初始化成功")
                return True
            else:
                logger.error("❌ 驱动模式一初始化失败")
                logger.error("提示：请检查驱动是否正确安装，或选择其他模式")
                return False

        except Exception as e:
            logger.error(f"❌ 驱动模式一初始化失败: {e}")
            logger.error("提示：驱动不可用，请选择模式二")
            return False

    def _initialize_auto(self) -> bool:
        """自动降级初始化：Interception > PyAutoGUI"""
        logger.info("正在初始化前台输入驱动（自动降级模式）...")

        # 1. 尝试初始化 Interception 驱动
        try:
            from utils.interception_driver import get_driver
            self._interception_driver = get_driver()

            if self._interception_driver.initialize():
                self._active_driver = self._interception_driver
                self._driver_type = 'interception'
                logger.info("✓ Interception 驱动初始化成功")
                return True
            else:
                logger.warning("Interception 驱动初始化失败，尝试备用方案...")

        except Exception as e:
            logger.warning(f"无法加载 Interception 驱动: {e}")

        # 2. 尝试 PyAutoGUI
        logger.info("正在启用 PyAutoGUI 备用方案...")
        try:
            from utils.pyautogui_fallback import get_pyautogui_fallback
            self._pyautogui_fallback = get_pyautogui_fallback()

            if self._pyautogui_fallback.initialize():
                self._active_driver = self._pyautogui_fallback
                self._driver_type = 'pyautogui'
                logger.info("✓ PyAutoGUI 备用驱动初始化成功")
                logger.warning("⚠️ 当前使用 PyAutoGUI，需要激活窗口才能正常工作")
                return True

        except Exception as e:
            logger.warning(f"PyAutoGUI 备用方案失败: {e}")

        logger.error("❌ 前台输入驱动初始化完全失败")
        return False

    def _initialize_pyautogui_only(self) -> bool:
        """强制使用PyAutoGUI"""
        logger.info("正在初始化前台输入驱动（强制PyAutoGUI模式）...")

        try:
            from utils.pyautogui_fallback import get_pyautogui_fallback
            self._pyautogui_fallback = get_pyautogui_fallback()

            if self._pyautogui_fallback.initialize():
                self._active_driver = self._pyautogui_fallback
                self._driver_type = 'pyautogui'
                logger.info("✓ PyAutoGUI 驱动初始化成功（强制模式）")
                logger.warning("⚠️ 当前使用 PyAutoGUI，需要激活窗口才能正常工作")
                return True
            else:
                logger.error("❌ PyAutoGUI 初始化失败")
                return False

        except Exception as e:
            logger.error(f"❌ PyAutoGUI 初始化失败: {e}")
            return False

    def move_mouse(self, x: int, y: int, absolute: bool = True) -> bool:
        """移动鼠标"""
        if not self._active_driver:
            if not self.initialize():
                return False

        try:
            return self._active_driver.move_mouse(x, y, absolute)
        except Exception as e:
            logger.error(f"鼠标移动失败: {e}")
            return False

    def click_mouse(self, x: Optional[int] = None, y: Optional[int] = None,
                   button: str = 'left', clicks: int = 1, interval: float = 0.0,
                   duration: float = 0.05) -> bool:
        """鼠标点击"""
        if not self._active_driver:
            if not self.initialize():
                return False

        try:
            logger.info(f"执行点击: ({x}, {y}), 按钮={button}, 次数={clicks}")
            return self._active_driver.click_mouse(x, y, button, clicks, interval, duration)
        except Exception as e:
            logger.error(f"鼠标点击失败: {e}")
            return False

    def drag_mouse(self, start_x: int, start_y: int, end_x: int, end_y: int,
                  button: str = 'left', duration: float = 1.0) -> bool:
        """鼠标拖拽"""
        if not self._active_driver:
            if not self.initialize():
                return False

        try:
            return self._active_driver.drag_mouse(start_x, start_y, end_x, end_y, button, duration)
        except Exception as e:
            logger.error(f"鼠标拖拽失败: {e}")
            return False

    def scroll_mouse(self, direction: str, clicks: int = 1, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """鼠标滚轮"""
        if not self._active_driver:
            if not self.initialize():
                return False

        try:
            return self._active_driver.scroll_mouse(direction, clicks, x, y)
        except Exception as e:
            logger.error(f"鼠标滚轮失败: {e}")
            return False

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸"""
        if not self._active_driver:
            if not self.initialize():
                return (1920, 1080)  # 默认值

        try:
            return self._active_driver.get_screen_size()
        except:
            return (1920, 1080)  # 默认值

    def get_mouse_position(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        if not self._active_driver:
            if not self.initialize():
                return (0, 0)

        try:
            return self._active_driver.get_mouse_position()
        except:
            return (0, 0)

    def get_driver_type(self) -> Optional[str]:
        """
        获取当前使用的驱动类型

        Returns:
            'interception', 'pyautogui' 或 None（未初始化）
        """
        return self._driver_type

    def is_interception_available(self) -> bool:
        """检查 Interception 驱动是否可用"""
        return self._driver_type == 'interception'

    def set_target_window(self, hwnd: int) -> None:
        """
        设置目标窗口（用于PyAutoGUI激活窗口）

        Args:
            hwnd: 窗口句柄
        """
        if self._driver_type == 'pyautogui' and self._pyautogui_fallback:
            self._pyautogui_fallback.set_target_window(hwnd)

    def close(self) -> None:
        """清理资源"""
        if self._active_driver:
            try:
                self._active_driver.close()
            except:
                pass
        self._active_driver = None
        self._driver_type = None
        self._initialization_attempted = False
        logger.info("前台输入驱动管理器已关闭")


# 全局管理器实例
_manager_instance = None

def get_foreground_input_manager() -> ForegroundInputManager:
    """获取全局前台输入驱动管理器"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ForegroundInputManager()
    return _manager_instance
