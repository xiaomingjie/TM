#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
截图助手模块 - 专门用于截图功能
保留pyautogui仅用于截图，所有输入操作使用Interception驱动
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入pyautogui仅用于截图
try:
    import pyautogui
    PYAUTOGUI_SCREENSHOT_AVAILABLE = True
    logger.debug("pyautogui 截图功能可用")
except ImportError:
    PYAUTOGUI_SCREENSHOT_AVAILABLE = False
    logger.warning("pyautogui 不可用，截图功能将受限")

# 尝试导入其他截图相关库
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def get_screen_size():
    """获取屏幕尺寸"""
    if PYAUTOGUI_SCREENSHOT_AVAILABLE:
        return pyautogui.size()
    else:
        # 备用方案：使用Windows API
        import ctypes
        screen_width = ctypes.windll.user32.GetSystemMetrics(0)
        screen_height = ctypes.windll.user32.GetSystemMetrics(1)
        return screen_width, screen_height

def take_screenshot(region=None):
    """
    截图功能 - 仅使用pyautogui截图
    
    Args:
        region: 截图区域 (left, top, width, height)，None表示全屏
        
    Returns:
        PIL.Image: 截图图像，失败返回None
    """
    if not PYAUTOGUI_SCREENSHOT_AVAILABLE:
        logger.error("pyautogui 不可用，无法截图")
        return None
    
    try:
        if region:
            logger.debug(f"区域截图: {region}")
            screenshot = pyautogui.screenshot(region=region)
        else:
            logger.debug("全屏截图")
            screenshot = pyautogui.screenshot()
        
        return screenshot
    except Exception as e:
        logger.error(f"截图失败: {e}")
        return None

def take_screenshot_opencv(region=None):
    """
    截图并转换为OpenCV格式
    
    Args:
        region: 截图区域 (left, top, width, height)，None表示全屏
        
    Returns:
        numpy.ndarray: OpenCV格式的图像，失败返回None
    """
    if not CV2_AVAILABLE:
        logger.error("opencv-python 不可用，无法转换为OpenCV格式")
        return None
    
    screenshot_pil = take_screenshot(region)
    if screenshot_pil is None:
        return None
    
    try:
        # 转换为OpenCV格式 (BGR)
        screenshot_np = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)
        return screenshot_np
    except Exception as e:
        logger.error(f"转换为OpenCV格式失败: {e}")
        return None

def take_window_screenshot(hwnd, client_area_only=True):
    """
    截取指定窗口的截图
    
    Args:
        hwnd: 窗口句柄
        client_area_only: 是否只截取客户区
        
    Returns:
        PIL.Image: 截图图像，失败返回None
    """
    try:
        import win32gui
        import win32con
        
        if client_area_only:
            # 获取客户区坐标
            client_rect = win32gui.GetClientRect(hwnd)
            client_point = win32gui.ClientToScreen(hwnd, (0, 0))
            
            region = (
                client_point[0],
                client_point[1], 
                client_rect[2],
                client_rect[3]
            )
        else:
            # 获取整个窗口坐标
            window_rect = win32gui.GetWindowRect(hwnd)
            region = (
                window_rect[0],
                window_rect[1],
                window_rect[2] - window_rect[0],
                window_rect[3] - window_rect[1]
            )
        
        return take_screenshot(region)
    except Exception as e:
        logger.error(f"窗口截图失败: {e}")
        return None

def is_screenshot_available():
    """检查截图功能是否可用"""
    return PYAUTOGUI_SCREENSHOT_AVAILABLE

def get_screenshot_info():
    """获取截图功能信息"""
    info = {
        'pyautogui_available': PYAUTOGUI_SCREENSHOT_AVAILABLE,
        'cv2_available': CV2_AVAILABLE,
        'pil_available': PIL_AVAILABLE,
    }
    
    if PYAUTOGUI_SCREENSHOT_AVAILABLE:
        try:
            info['screen_size'] = pyautogui.size()
        except:
            info['screen_size'] = None
    
    return info

# 向后兼容的函数名
screenshot = take_screenshot
screenshot_opencv = take_screenshot_opencv

if __name__ == "__main__":
    # 测试截图功能
    print("🔍 测试截图功能")
    print("=" * 50)
    
    info = get_screenshot_info()
    print(f"截图功能信息: {info}")
    
    if is_screenshot_available():
        print("✅ 截图功能可用")
        
        # 测试全屏截图
        screenshot = take_screenshot()
        if screenshot:
            print(f"✅ 全屏截图成功: {screenshot.size}")
        else:
            print("❌ 全屏截图失败")
        
        # 测试OpenCV格式
        if CV2_AVAILABLE:
            screenshot_cv = take_screenshot_opencv()
            if screenshot_cv is not None:
                print(f"✅ OpenCV格式截图成功: {screenshot_cv.shape}")
            else:
                print("❌ OpenCV格式截图失败")
    else:
        print("❌ 截图功能不可用")
