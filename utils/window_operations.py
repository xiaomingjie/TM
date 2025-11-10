# -*- coding: utf-8 -*-
"""
统一窗口操作模块 - 整合所有窗口相关的通用操作
"""
import logging
import time
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import win32gui
    import win32con
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    logger.warning("pywin32 不可用，窗口操作功能受限")


class WindowOperations:
    """统一的窗口操作类"""
    
    @staticmethod
    def activate_window(target_hwnd: int, window_title: str = "") -> bool:
        """
        激活窗口（统一的窗口激活方法）
        
        Args:
            target_hwnd: 目标窗口句柄
            window_title: 窗口标题（用于日志）
            
        Returns:
            bool: 激活是否成功
        """
        if not target_hwnd or not PYWIN32_AVAILABLE:
            if not target_hwnd:
                logger.debug("前台模式执行，但未提供目标窗口句柄，无法激活")
            elif not PYWIN32_AVAILABLE:
                logger.warning("无法激活目标窗口：缺少 'pywin32' 库")
            return False
            
        try:
            if not win32gui.IsWindow(target_hwnd):
                logger.warning(f"无法激活目标窗口：句柄 {target_hwnd} 无效或已销毁")
                return False
                
            current_foreground_hwnd = win32gui.GetForegroundWindow()
            if current_foreground_hwnd == target_hwnd:
                logger.debug(f"目标窗口 {target_hwnd} 已是前台窗口，无需激活")
                return True
                
            # 检查窗口是否最小化
            if win32gui.IsIconic(target_hwnd):
                logger.info(f"目标窗口 {target_hwnd} 已最小化，尝试恢复并激活...")
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                time.sleep(0.15)
            
            # 激活窗口
            logger.info(f"尝试将窗口 {target_hwnd} 设置为前台...")
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.1)
            
            # 验证激活是否成功
            new_foreground = win32gui.GetForegroundWindow()
            if new_foreground == target_hwnd:
                logger.debug(f"窗口激活成功: {target_hwnd}")
                return True
            else:
                logger.warning(f"窗口激活失败: 期望={target_hwnd}, 实际={new_foreground}")
                return False
                
        except Exception as e:
            logger.warning(f"设置前台窗口 {target_hwnd} 时出错: {e}")
            return False
    
    @staticmethod
    def prepare_window_for_execution(target_hwnd: int, execution_mode: str, window_title: str = "") -> bool:
        """
        为执行准备窗口状态
        
        Args:
            target_hwnd: 目标窗口句柄
            execution_mode: 执行模式 ('foreground' 或 'background')
            window_title: 窗口标题（用于日志）
            
        Returns:
            bool: 准备是否成功
        """
        try:
            if execution_mode == 'foreground':
                # 前台模式需要激活窗口
                return WindowOperations.activate_window(target_hwnd, window_title)
            else:
                # 后台模式不需要激活窗口，但需要确保窗口状态正常
                if PYWIN32_AVAILABLE and win32gui.IsIconic(target_hwnd):
                    # 如果窗口最小化，恢复它（但不激活）
                    logger.info(f"恢复最小化窗口: {window_title}")
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.1)
            
            return True
            
        except Exception as e:
            logger.error(f"准备窗口状态时发生异常: {e}")
            return False
    
    @staticmethod
    def convert_client_to_screen_coordinates(target_hwnd: int, client_x: int, client_y: int) -> Tuple[int, int]:
        """
        将客户区坐标转换为屏幕坐标
        
        Args:
            target_hwnd: 目标窗口句柄
            client_x: 客户区X坐标
            client_y: 客户区Y坐标
            
        Returns:
            Tuple[int, int]: 屏幕坐标 (screen_x, screen_y)
        """
        if not target_hwnd or not PYWIN32_AVAILABLE:
            logger.error(f"坐标转换失败: target_hwnd={target_hwnd}, pywin32={PYWIN32_AVAILABLE}")
            return client_x, client_y
            
        try:
            if not win32gui.IsWindow(target_hwnd):
                logger.error(f"坐标转换失败: 无效的窗口句柄 {target_hwnd}")
                return client_x, client_y
                
            point = wintypes.POINT(client_x, client_y)
            if ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point)):
                screen_x, screen_y = point.x, point.y
                logger.debug(f"客户区坐标转换: ({client_x}, {client_y}) -> 屏幕坐标: ({screen_x}, {screen_y})")
                return screen_x, screen_y
            else:
                logger.error("客户区坐标转换为屏幕坐标失败")
                return client_x, client_y
                
        except Exception as e:
            logger.error(f"坐标转换时发生异常: {e}")
            return client_x, client_y
    
    @staticmethod
    def get_window_info(target_hwnd: int) -> dict:
        """
        获取窗口信息
        
        Args:
            target_hwnd: 目标窗口句柄
            
        Returns:
            dict: 窗口信息字典
        """
        info = {
            'hwnd': target_hwnd,
            'title': '',
            'class_name': '',
            'is_visible': False,
            'is_minimized': False,
            'client_rect': (0, 0, 0, 0),
            'window_rect': (0, 0, 0, 0)
        }
        
        if not target_hwnd or not PYWIN32_AVAILABLE:
            return info
            
        try:
            if win32gui.IsWindow(target_hwnd):
                info['title'] = win32gui.GetWindowText(target_hwnd)
                info['class_name'] = win32gui.GetClassName(target_hwnd)
                info['is_visible'] = win32gui.IsWindowVisible(target_hwnd)
                info['is_minimized'] = win32gui.IsIconic(target_hwnd)
                
                # 获取窗口矩形
                window_rect = win32gui.GetWindowRect(target_hwnd)
                info['window_rect'] = window_rect
                
                # 获取客户区矩形
                client_rect = win32gui.GetClientRect(target_hwnd)
                info['client_rect'] = client_rect
                
        except Exception as e:
            logger.error(f"获取窗口信息时发生异常: {e}")
            
        return info
    
    @staticmethod
    def is_window_valid(target_hwnd: int) -> bool:
        """
        检查窗口是否有效
        
        Args:
            target_hwnd: 目标窗口句柄
            
        Returns:
            bool: 窗口是否有效
        """
        if not target_hwnd or not PYWIN32_AVAILABLE:
            return False
            
        try:
            return win32gui.IsWindow(target_hwnd)
        except Exception:
            return False


# 兼容性函数，保持与现有代码的兼容
def activate_window_foreground(target_hwnd: int, logger_instance=None) -> bool:
    """兼容性函数 - 激活窗口"""
    return WindowOperations.activate_window(target_hwnd)


def prepare_window_for_execution(target_hwnd: int, execution_mode: str, window_title: str = "") -> bool:
    """兼容性函数 - 准备窗口执行状态"""
    return WindowOperations.prepare_window_for_execution(target_hwnd, execution_mode, window_title)


def convert_client_to_screen_coordinates(target_hwnd: int, client_x: int, client_y: int) -> Tuple[int, int]:
    """兼容性函数 - 坐标转换"""
    return WindowOperations.convert_client_to_screen_coordinates(target_hwnd, client_x, client_y)
