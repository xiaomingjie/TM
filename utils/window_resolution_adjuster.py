"""
窗口分辨率调整器 - 专门用于调整窗口分辨率
基于通用分辨率适配器，提供简化的窗口分辨率调整接口

功能：
1. 调整单个窗口分辨率
2. 支持普通窗口和子窗口
3. 自动处理DPI缩放
4. 提供详细的调整结果反馈
"""

import logging
import ctypes
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)

try:
    from .universal_resolution_adapter import get_universal_adapter, REFERENCE_WIDTH, REFERENCE_HEIGHT
except ImportError:
    # 如果适配器不可用，使用默认值
    REFERENCE_WIDTH = 1280
    REFERENCE_HEIGHT = 720
    
    def get_universal_adapter():
        class MockAdapter:
            def get_window_state(self, hwnd):
                return None
            def adjust_window_resolution(self, hwnd, width, height):
                return False
        return MockAdapter()

class WindowResolutionAdjuster:
    """窗口分辨率调整器"""
    
    def __init__(self):
        self.adapter = get_universal_adapter()
        self.user32 = ctypes.windll.user32
        logger.debug("窗口分辨率调整器初始化完成")
    
    def adjust_window_resolution(self, hwnd: int, target_width: int = REFERENCE_WIDTH, 
                               target_height: int = REFERENCE_HEIGHT) -> bool:
        """
        调整窗口分辨率到指定尺寸
        
        Args:
            hwnd: 窗口句柄
            target_width: 目标宽度
            target_height: 目标高度
            
        Returns:
            bool: 调整是否成功
        """
        try:
            if not hwnd or not self.user32.IsWindow(hwnd):
                logger.error(f"无效的窗口句柄: {hwnd}")
                return False
            
            # 获取窗口标题用于日志
            try:
                title_length = self.user32.GetWindowTextLengthW(hwnd)
                if title_length > 0:
                    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
                    self.user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
                    window_title = title_buffer.value
                else:
                    window_title = "未知窗口"
            except:
                window_title = "未知窗口"
            
            logger.info(f"开始调整窗口分辨率: {window_title} (HWND: {hwnd}) -> {target_width}x{target_height}")
            
            # 使用通用分辨率适配器进行调整
            success = self.adapter.adjust_window_resolution(hwnd, target_width, target_height)
            
            if success:
                logger.info(f"窗口分辨率调整成功: {window_title}")
            else:
                logger.error(f"窗口分辨率调整失败: {window_title}")
                
            return success
            
        except Exception as e:
            logger.error(f"调整窗口分辨率时发生异常: {e}", exc_info=True)
            return False
    
    def get_window_resolution(self, hwnd: int) -> Optional[Tuple[int, int]]:
        """
        获取窗口当前分辨率
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            Optional[Tuple[int, int]]: 窗口分辨率 (宽度, 高度)，失败时返回None
        """
        try:
            if not hwnd or not self.user32.IsWindow(hwnd):
                logger.error(f"无效的窗口句柄: {hwnd}")
                return None
            
            window_state = self.adapter.get_window_state(hwnd, force_refresh=True)
            if window_state:
                return (window_state.width, window_state.height)
            else:
                logger.error(f"无法获取窗口状态: {hwnd}")
                return None
                
        except Exception as e:
            logger.error(f"获取窗口分辨率时发生异常: {e}", exc_info=True)
            return None
    
    def is_window_valid(self, hwnd: int) -> bool:
        """
        检查窗口句柄是否有效
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            bool: 窗口句柄是否有效
        """
        try:
            return bool(hwnd and self.user32.IsWindow(hwnd))
        except Exception as e:
            logger.error(f"检查窗口有效性时发生异常: {e}")
            return False

# 全局实例
_adjuster_instance = None

def get_window_resolution_adjuster() -> WindowResolutionAdjuster:
    """获取窗口分辨率调整器的全局实例"""
    global _adjuster_instance
    if _adjuster_instance is None:
        _adjuster_instance = WindowResolutionAdjuster()
    return _adjuster_instance
