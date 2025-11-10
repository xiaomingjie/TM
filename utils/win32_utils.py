import win32gui
import win32ui
import win32con
import win32api
import numpy as np
import time
import random
import logging
from typing import Optional, Tuple
import cv2 # Required for image format conversion

# Ensure pywin32 is available
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    # Let the calling task handle the warning/error if background mode is attempted

import ctypes # 确保导入了 ctypes
import cv2
import numpy as np
import win32gui
import win32ui
import win32con
import logging

# 其他现有的导入保持不变...

def capture_window_background(hwnd: int) -> Optional[np.ndarray]:
    """
    Captures the content of a window's client area specified by its handle (HWND) using background methods.
    工具 Bug修复：添加DPI感知处理，确保捕获的图像尺寸与窗口客户区匹配
    # 先尝试BitBlt，如果失败或返回黑屏，则回退到PrintWindow

    Args:
        hwnd: The window handle (HWND).

    Returns:
        A NumPy array representing the window's client area content in BGR format, or None if capture fails.
    """
    if not PYWIN32_AVAILABLE:
        logging.error("capture_window_background: pywin32 未安装。")
        return None

    if not hwnd or not win32gui.IsWindow(hwnd):
        logging.error(f"capture_window_background: 无效的窗口句柄 {hwnd}")
        return None

    # 工具 Bug修复：获取窗口DPI信息
    try:
        import ctypes
        user32 = ctypes.windll.user32
        dpi = 96  # 默认DPI
        scale_factor = 1.0

        try:
            if hasattr(user32, 'GetDpiForWindow'):
                dpi = user32.GetDpiForWindow(hwnd)
                scale_factor = dpi / 96.0
            else:
                # 回退方法：获取系统DPI
                hdc = user32.GetDC(0)
                if hdc:
                    dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                    scale_factor = dpi / 96.0
                    user32.ReleaseDC(0, hdc)
        except Exception as e:
            logging.debug(f"获取DPI失败，使用默认值: {e}")

        logging.debug(f"窗口DPI: {dpi}, 缩放因子: {scale_factor:.3f}")
    except Exception as e:
        logging.debug(f"DPI检测失败: {e}")
        scale_factor = 1.0

    # 第一步尝试：使用 BitBlt 方法（原有实现，几乎不变）
    img_from_bitblt = _try_capture_with_bitblt(hwnd)

    # 检查 BitBlt 结果
    if img_from_bitblt is not None:
        # 检查图像是否全黑或几乎全黑（可能的黑屏情况）
        if _is_image_mostly_black(img_from_bitblt):
            # logging.info("BitBlt 捕获成功，但图像几乎全黑，尝试使用 PrintWindow...")
            # BitBlt 返回了全黑图像，尝试 PrintWindow
            img_from_printwindow = _try_capture_with_printwindow(hwnd)
            if img_from_printwindow is not None:
                # logging.info("PrintWindow 捕获成功，使用 PrintWindow 结果。")
                return img_from_printwindow
            else:
                # logging.warning("PrintWindow 捕获失败，回退使用 BitBlt 结果（可能是黑屏）。")
                return img_from_bitblt
        else:
            # BitBlt 结果看起来正常（不是全黑）
            # logging.debug("BitBlt 捕获成功，图像看起来正常。")
            return img_from_bitblt
    else:
        # BitBlt 完全失败了，尝试 PrintWindow
        # logging.warning("BitBlt 捕获失败，尝试使用 PrintWindow...")
        img_from_printwindow = _try_capture_with_printwindow(hwnd)
        if img_from_printwindow is not None:
            # logging.info("PrintWindow 捕获成功。")
            return img_from_printwindow
        else:
            # logging.error("所有截图方法都失败了。")
            return None

# 添加一个辅助函数来检测图像是否几乎全黑
def _is_image_mostly_black(img: np.ndarray, threshold: int = 10, black_percentage: float = 0.95) -> bool:
    """
    检查图像是否几乎全黑（可能是黑屏）
    
    Args:
        img: 要检查的图像（NumPy 数组）
        threshold: 像素值低于此阈值被视为"黑色"（0-255）
        black_percentage: 黑色像素占比高于此值时，认为图像"几乎全黑"
        
    Returns:
        如果图像几乎全黑，返回 True；否则返回 False
    """
    if img is None or img.size == 0:
        return True  # 空图像视为黑屏
        
    try:
        # 转换为灰度图（如果不是的话）
        if len(img.shape) == 3:
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray_img = img  # 已经是灰度图
            
        # 计算暗像素（值 < threshold）的数量
        dark_pixels = np.sum(gray_img < threshold)
        total_pixels = gray_img.size
        
        # 计算暗像素占比
        dark_ratio = dark_pixels / total_pixels
        
        logging.debug(f"图像暗像素占比: {dark_ratio:.4f} (阈值: {black_percentage:.4f})")
        
        return dark_ratio >= black_percentage
    except Exception as e:
        logging.error(f"检查图像是否全黑时出错: {e}")
        return False  # 出错时保守地假设图像不是全黑

# 提取原 capture_window_background 函数中的 BitBlt 逻辑到单独的函数
def _try_capture_with_bitblt(hwnd: int) -> Optional[np.ndarray]:
    """使用 BitBlt 方法尝试捕获窗口内容"""
    img = None
    hwnd_dc = None
    mfc_dc = None
    save_dc = None
    save_bitmap = None

    try:
        # Get client area dimensions
        left, top, right, bot = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bot - top

        client_rect_valid = (width > 0 and height > 0)

        if not client_rect_valid:
            # logging.warning(f"_try_capture_with_bitblt: 客户区尺寸无效 ({width}x{height}) for HWND {hwnd}.")
            return None

        # Create device contexts
        hwnd_dc = win32gui.GetDC(hwnd)
        if not hwnd_dc:
             # logging.error(f"_try_capture_with_bitblt: 无法获取窗口 {hwnd} 的客户区设备上下文 (GetDC)。")
             return None
             
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        # Create bitmap
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(save_bitmap)

        # Copy window content to bitmap using BitBlt directly
        # logging.info(f"尝试使用 BitBlt 捕获 HWND {hwnd} 的客户区...")
        result = 0 # Initialize result to failure
        try:
            # Source DC is mfc_dc (derived from GetDC), source point is (0,0) for client area
            save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)
            # logging.info("BitBlt 尝试完成。")
            result = 1 # Assume success if BitBlt didn't raise exception
        except Exception as bitblt_err:
             # logging.error(f"_try_capture_with_bitblt: BitBlt 失败: {bitblt_err}", exc_info=True)
             result = 0 # Mark as failed

        # Get bitmap data only if BitBlt potentially succeeded
        if result:
            try:
                bmp_info = save_bitmap.GetInfo()
                bmp_str = save_bitmap.GetBitmapBits(True)
                
                # Convert to NumPy array
                # Shape needs to be (height, width, 4) for BGRA data from GetBitmapBits
                img = np.frombuffer(bmp_str, dtype=np.uint8).reshape(bmp_info['bmHeight'], bmp_info['bmWidth'], 4)

                # Convert BGRA to BGR (common format for OpenCV)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception as bmp_err:
                logging.error(f"处理位图数据时出错: {bmp_err}", exc_info=True)
                img = None # Failed to process bitmap data
                result = 0 # Mark as overall failure
        
        if not result or img is None:
             # logging.error(f"_try_capture_with_bitblt: BitBlt 未能成功捕获并处理窗口 {hwnd} 的图像。")
             img = None

    except Exception as e:
        # logging.error(f"_try_capture_with_bitblt: 捕获窗口 {hwnd} 时发生异常: {e}", exc_info=True)
        img = None
    finally:
        # Ensure resources are released
        try:
            if save_bitmap and save_bitmap.GetHandle():
                win32gui.DeleteObject(save_bitmap.GetHandle())
        except Exception as cleanup_err: logging.warning(f"清理 save_bitmap 时出错: {cleanup_err}")
        try:
            if save_dc:
                save_dc.DeleteDC()
        except Exception as cleanup_err: logging.warning(f"清理 save_dc 时出错: {cleanup_err}")
        try:
            if mfc_dc:
                mfc_dc.DeleteDC()
        except Exception as cleanup_err: logging.warning(f"清理 mfc_dc 时出错: {cleanup_err}")
        try:
            if hwnd_dc:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception as cleanup_err: logging.warning(f"清理 hwnd_dc 时出错: {cleanup_err}")
             
    return img

# 新增 PrintWindow 实现作为备用方法
def _try_capture_with_printwindow(hwnd: int) -> Optional[np.ndarray]:
    """使用 PrintWindow API 尝试捕获窗口内容"""
    img = None
    hwnd_dc = None
    mfc_dc = None
    save_dc = None
    save_bitmap = None

    try:
        # Get client area dimensions (same as BitBlt version)
        left, top, right, bot = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bot - top

        client_rect_valid = (width > 0 and height > 0)

        if not client_rect_valid:
            # logging.warning(f"_try_capture_with_printwindow: 客户区尺寸无效 ({width}x{height}) for HWND {hwnd}.")
            return None

        # Create device contexts (same as BitBlt version)
        hwnd_dc = win32gui.GetDC(hwnd)
        if not hwnd_dc:
             # logging.error(f"_try_capture_with_printwindow: 无法获取窗口 {hwnd} 的客户区设备上下文 (GetDC)。")
             return None
             
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        # Create bitmap (same as BitBlt version)
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(save_bitmap)

        # Use PrintWindow instead of BitBlt
        # logging.info(f"尝试使用 PrintWindow 捕获 HWND {hwnd} 的客户区...")
        result = 0 # Initialize result to failure
        
        try:
            # 直接使用 PW_CLIENTONLY | PW_RENDERFULLCONTENT 标志组合
            # PW_CLIENTONLY = 1
            # PW_RENDERFULLCONTENT = 2 (需要 Windows 8.1+)
            # 组合值为 1 | 2 = 3
            pw_flags = 3  
            
            # PrintWindow(hwnd, hdcBlt, flags)
            # 调用 ctypes.windll.user32.PrintWindow
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), pw_flags)
            
            if result == 1:
                # logging.info(f"PrintWindow 成功 (flags={pw_flags} [PW_CLIENTONLY | PW_RENDERFULLCONTENT])。")
                pass
            else:
                # 如果组合标志失败，记录错误。这里不再尝试其他标志组合，因为我们的目标是实现已验证的策略。
                # logging.error(f"PrintWindow 失败 (flags={pw_flags} [PW_CLIENTONLY | PW_RENDERFULLCONTENT])。错误代码: {ctypes.GetLastError()}")
                pass
        except Exception as pw_err:
            # logging.error(f"_try_capture_with_printwindow: PrintWindow 调用出错: {pw_err}", exc_info=True)
            result = 0

        # Get bitmap data only if PrintWindow potentially succeeded
        if result:
            try:
                bmp_info = save_bitmap.GetInfo()
                bmp_str = save_bitmap.GetBitmapBits(True)
                
                # Convert to NumPy array (same as BitBlt version)
                img = np.frombuffer(bmp_str, dtype=np.uint8).reshape(bmp_info['bmHeight'], bmp_info['bmWidth'], 4)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception as bmp_err:
                logging.error(f"处理 PrintWindow 位图数据时出错: {bmp_err}", exc_info=True)
                img = None
        
        if not result or img is None:
             # logging.error(f"_try_capture_with_printwindow: PrintWindow 未能成功捕获并处理窗口 {hwnd} 的图像。")
             img = None

    except Exception as e:
        # logging.error(f"_try_capture_with_printwindow: 捕获窗口 {hwnd} 时发生异常: {e}", exc_info=True)
        img = None
    finally:
        # Ensure resources are released (same as BitBlt version)
        try:
            if save_bitmap and save_bitmap.GetHandle():
                win32gui.DeleteObject(save_bitmap.GetHandle())
        except Exception as cleanup_err: logging.warning(f"清理 save_bitmap 时出错: {cleanup_err}")
        try:
            if save_dc:
                save_dc.DeleteDC()
        except Exception as cleanup_err: logging.warning(f"清理 save_dc 时出错: {cleanup_err}")
        try:
            if mfc_dc:
                mfc_dc.DeleteDC()
        except Exception as cleanup_err: logging.warning(f"清理 mfc_dc 时出错: {cleanup_err}")
        try:
            if hwnd_dc:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception as cleanup_err: logging.warning(f"清理 hwnd_dc 时出错: {cleanup_err}")
             
    return img

def capture_window_content(hwnd: int) -> Tuple[Optional[object], int, int]:
    """
    捕获窗口内容并返回PIL图像和尺寸

    Args:
        hwnd: 窗口句柄

    Returns:
        Tuple[PIL.Image, width, height] 或 (None, 0, 0) 如果失败
    """
    try:
        # 使用现有的capture_window_background函数
        img_array = capture_window_background(hwnd)
        if img_array is None:
            return None, 0, 0

        # 转换numpy数组为PIL图像
        from PIL import Image

        # img_array是BGR格式，需要转换为RGB
        img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

        # 转换为PIL图像
        height, width = img_rgb.shape[:2]
        pil_image = Image.fromarray(img_rgb)

        return pil_image, width, height

    except Exception as e:
        logging.error(f"capture_window_content失败: {e}")
        return None, 0, 0

# --- ADDED: Dictionary for VK codes (copied from find_color_task) ---
VK_CODE = {
    'backspace':0x08, 'tab':0x09, 'clear':0x0C, 'enter':0x0D, 'shift':0x10, 'ctrl':0x11,
    'alt':0x12, 'pause':0x13, 'caps_lock':0x14, 'esc':0x1B, 'spacebar':0x20,
    'page_up':0x21, 'page_down':0x22, 'end':0x23, 'home':0x24, 'left':0x25,
    'up':0x26, 'right':0x27, 'down':0x28, 'select':0x29, 'print':0x2A,
    'execute':0x2B, 'print_screen':0x2C, 'ins':0x2D, 'del':0x2E, 'help':0x2F,
    '0':0x30, '1':0x31, '2':0x32, '3':0x33, '4':0x34, '5':0x35, '6':0x36, '7':0x37, '8':0x38, '9':0x39,
    'a':0x41, 'b':0x42, 'c':0x43, 'd':0x44, 'e':0x45, 'f':0x46, 'g':0x47, 'h':0x48, 'i':0x49, 'j':0x4A,
    'k':0x4B, 'l':0x4C, 'm':0x4D, 'n':0x4E, 'o':0x4F, 'p':0x50, 'q':0x51, 'r':0x52, 's':0x53, 't':0x54,
    'u':0x55, 'v':0x56, 'w':0x57, 'x':0x58, 'y':0x59, 'z':0x5A,
    'numpad_0':0x60, 'numpad_1':0x61, 'numpad_2':0x62, 'numpad_3':0x63, 'numpad_4':0x64,
    'numpad_5':0x65, 'numpad_6':0x66, 'numpad_7':0x67, 'numpad_8':0x68, 'numpad_9':0x69,
    'multiply_key':0x6A, 'add_key':0x6B, 'separator_key':0x6C, 'subtract_key':0x6D,
    'decimal_key':0x6E, 'divide_key':0x6F,
    'F1':0x70, 'F2':0x71, 'F3':0x72, 'F4':0x73, 'F5':0x74, 'F6':0x75, 'F7':0x76, 'F8':0x77,
    'F9':0x78, 'F10':0x79, 'F11':0x7A, 'F12':0x7B, 'F13':0x7C, 'F14':0x7D, 'F15':0x7E, 'F16':0x7F,
    'F17':0x80, 'F18':0x81, 'F19':0x82, 'F20':0x83, 'F21':0x84, 'F22':0x85, 'F23':0x86, 'F24':0x87,
    'num_lock':0x90, 'scroll_lock':0x91, 'left_shift':0xA0, 'right_shift':0xA1,
    'left_control':0xA2, 'right_control':0xA3, 'left_menu':0xA4, 'right_menu':0xA5,
    'browser_back':0xA6, 'browser_forward':0xA7, 'browser_refresh':0xA8, 'browser_stop':0xA9,
    'browser_search':0xAA, 'browser_favorites':0xAB, 'browser_start_and_home':0xAC,
    'volume_mute':0xAD, 'volume_Down':0xAE, 'volume_up':0xAF, 'next_track':0xB0,
    'previous_track':0xB1, 'stop_media':0xB2, 'play/pause_media':0xB3, 'start_mail':0xB4,
    'select_media':0xB5, 'start_application_1':0xB6, 'start_application_2':0xB7,
    'attn_key':0xF6, 'crsel_key':0xF7, 'exsel_key':0xF8, 'play_key':0xFA, 'zoom_key':0xFB,
    'clear_key':0xFE, '+':0xBB, ',':0xBC, '-':0xBD, '.':0xBE, '/':0xBF, '`':0xC0, ';':0xBA,
    '[':0xDB, '\\':0xDC, ']':0xDD, "'":0xDE # Escaped backslash
}
# ---------------------------------------------------------------------

# --- ADDED: Function to release a key in the background ---
def release_key_background(hwnd: int, key: str) -> bool:
    """Sends a key up event using PostMessage with a standard lParam."""
    if not PYWIN32_AVAILABLE:
        logging.error(f"无法后台松开键 '{key}': pywin32 不可用。")
        return False
    if not hwnd or not win32gui.IsWindow(hwnd):
        logging.error(f"无法后台松开键 '{key}': 无效的窗口句柄 {hwnd}")
        return False
        
    key_lower = key.lower()
    vk_code = VK_CODE.get(key_lower)
    if vk_code is None:
        logging.error(f"无法后台松开键：未知键名 '{key}'")
        return False
        
    try:
        # Construct a standard lParam for WM_KEYUP
        # MAPVK_VK_TO_VSC = 0
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        # lParam format: | 31 | 30 | 29 | 28-24 | 23-16 | 15-0 |
        #               | UP | Prev | --- | ---   | Scan  | Rep |
        # For WM_KEYUP: UP=1, Prev=1, Rep=1
        lParam = (1 << 31) | (1 << 30) | (scan_code << 16) | 1
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lParam)
        logging.debug(f"工具函数: 后台松开键 (PostMessage, standard lParam): Key='{key}', VK={vk_code}, lParam={lParam}, HWND={hwnd}")
        return True
    except Exception as e:
        logging.exception(f"工具函数: 后台松开键 (PostMessage, standard lParam) '{key}' 时出错: {e}")
        return False
# --- END ADDED --- 

def click_background(hwnd: int, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1, random_range_x: int = 0, random_range_y: int = 0) -> bool:
    """
    Sends mouse click messages to a window at specified client coordinates.
    使用标准的SendMessage/PostMessage方法，适用于普通窗口和部分模拟器。

    Args:
        hwnd: The target window handle (HWND).
        x: The x-coordinate relative to the window's client area.
        y: The y-coordinate relative to the window's client area.
        button: Mouse button ('left', 'right', 'middle').
        clicks: Number of clicks.
        interval: Delay between clicks (in seconds).
        random_range_x: Range for random x-coordinate offset.
        random_range_y: Range for random y-coordinate offset.

    Returns:
        True if messages were sent successfully, False otherwise.
    """
    if not PYWIN32_AVAILABLE:
        logging.error("click_background: pywin32 未安装。")
        return False

    if not hwnd or not win32gui.IsWindow(hwnd):
        logging.error(f"click_background: 无效的窗口句柄 {hwnd}")
        return False

    # 直接使用标准后台点击方法，不做任何窗口类型检测
    # 如果用户需要模拟器专用方法，应该选择emulator_xxx模式
    return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)


def _click_ldplayer_background(hwnd: int, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1, random_range_x: int = 0, random_range_y: int = 0) -> bool:
    """雷电模拟器专用后台点击方法"""
    if button != 'left':
        logging.warning(f"雷电模拟器专用点击暂不支持 '{button}' 按钮，回退到标准方法")
        return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)

    try:
        # 导入雷电模拟器专用点击器
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.window_finder import LDPlayerBackgroundClicker

        # 使用全局缓存避免频繁创建实例
        global _ldplayer_clicker_cache
        if '_ldplayer_clicker_cache' not in globals():
            _ldplayer_clicker_cache = {}

        if hwnd not in _ldplayer_clicker_cache:
            _ldplayer_clicker_cache[hwnd] = LDPlayerBackgroundClicker(hwnd)

        clicker = _ldplayer_clicker_cache[hwnd]

        all_success = True
        for i in range(clicks):
            # 应用随机偏移
            final_x = x + random.randint(-random_range_x, random_range_x)
            final_y = y + random.randint(-random_range_y, random_range_y)

            # 使用雷电模拟器专用点击方法，增加延迟确保消息处理完成
            click_delay = max(0.05, interval * 0.5)  # 至少50ms延迟
            success = clicker.click(final_x, final_y, delay=click_delay)
            if not success:
                all_success = False
                logging.warning(f"雷电模拟器第{i+1}次点击失败")

            if clicks > 1 and i < clicks - 1:
                # 多次点击间增加额外延迟
                multi_click_delay = max(interval, 0.1)  # 至少100ms间隔
                time.sleep(multi_click_delay)

        return all_success

    except Exception as e:
        logging.error(f"雷电模拟器专用点击失败，回退到标准方法: {e}")
        return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)


def _click_mumu_background(hwnd, x, y, button='left', clicks=1, interval=0.1, random_range_x=0, random_range_y=0):
    """MuMu模拟器专用后台点击方法"""
    try:
        # 导入MuMu输入模拟器
        from utils.mumu_input_simulator import get_mumu_input_simulator
        mumu_simulator = get_mumu_input_simulator()

        if not mumu_simulator:
            logging.warning("MuMu输入模拟器不可用，回退到标准方法")
            return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)

        # 获取MuMu父窗口句柄
        parent_hwnd = _get_mumu_parent_window(hwnd)
        if not parent_hwnd:
            logging.warning("无法找到MuMu父窗口，回退到标准方法")
            return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)

        # 记录窗口信息
        try:
            parent_title = win32gui.GetWindowText(parent_hwnd)
            parent_class = win32gui.GetClassName(parent_hwnd)
            logging.info(f"MuMu后台点击: 渲染窗口({hwnd}) -> 父窗口({parent_hwnd}) '{parent_title}' ({parent_class})")
        except:
            logging.info(f"MuMu后台点击: 渲染窗口({hwnd}) -> 父窗口({parent_hwnd})")

        # 执行点击
        all_success = True
        for i in range(clicks):
            # 应用随机偏移
            final_x = x + random.randint(-random_range_x, random_range_x)
            final_y = y + random.randint(-random_range_y, random_range_y)

            # 使用MuMu专用点击方法
            result = mumu_simulator.mouse_click(parent_hwnd, final_x, final_y, button)
            if not result.success:
                all_success = False
                logging.warning(f"MuMu模拟器第{i+1}次点击失败: {result.message}")

            if clicks > 1 and i < clicks - 1:
                time.sleep(interval)

        if all_success:
            logging.info(f"MuMu模拟器后台点击成功: ({x}, {y}), 次数: {clicks}")

        return all_success

    except ImportError:
        logging.warning("无法导入MuMu输入模拟器，回退到标准方法")
        return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)
    except Exception as e:
        logging.error(f"MuMu模拟器专用点击失败，回退到标准方法: {e}")
        return _click_standard_background(hwnd, x, y, button, clicks, interval, random_range_x, random_range_y)


def _get_mumu_parent_window(hwnd):
    """获取MuMu模拟器的父窗口句柄"""
    try:
        current_hwnd = hwnd
        max_depth = 5  # 限制查找深度

        for _ in range(max_depth):
            parent_hwnd = win32gui.GetParent(current_hwnd)
            if not parent_hwnd:
                break

            try:
                parent_title = win32gui.GetWindowText(parent_hwnd)
                parent_class = win32gui.GetClassName(parent_hwnd)

                # 检查是否是MuMu主窗口
                if (parent_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                    ("mumu" in parent_title.lower() or "安卓设备" in parent_title)):
                    return parent_hwnd

                # 检查是否是MuMuNxDevice窗口
                if "MuMuNxDevice" in parent_title:
                    return parent_hwnd

            except Exception:
                pass

            current_hwnd = parent_hwnd

        return None

    except Exception as e:
        logging.debug(f"获取MuMu父窗口失败: {e}")
        return None


def _click_standard_background(hwnd: int, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1, random_range_x: int = 0, random_range_y: int = 0) -> bool:
    """标准后台点击方法"""
    # Combine coordinates into lParam for messages
    # Ensure coordinates are integers
    x = int(round(x))
    y = int(round(y))
    lParam = win32api.MAKELONG(x, y)

    # Define message constants
    WM_LBUTTONDOWN = win32con.WM_LBUTTONDOWN
    WM_LBUTTONUP = win32con.WM_LBUTTONUP
    WM_RBUTTONDOWN = win32con.WM_RBUTTONDOWN
    WM_RBUTTONUP = win32con.WM_RBUTTONUP
    WM_MBUTTONDOWN = win32con.WM_MBUTTONDOWN
    WM_MBUTTONUP = win32con.WM_MBUTTONUP
    
    # Define wParam constants (usually 0 for simple clicks, but might need flags)
    wParam = 0
    MK_LBUTTON = win32con.MK_LBUTTON
    MK_RBUTTON = win32con.MK_RBUTTON
    MK_MBUTTON = win32con.MK_MBUTTON

    if button == 'left':
        down_message = WM_LBUTTONDOWN
        up_message = WM_LBUTTONUP
        wParam_down = MK_LBUTTON # Some apps might check this on DOWN message
    elif button == 'right':
        down_message = WM_RBUTTONDOWN
        up_message = WM_RBUTTONUP
        wParam_down = MK_RBUTTON
    elif button == 'middle':
        down_message = WM_MBUTTONDOWN
        up_message = WM_MBUTTONUP
        wParam_down = MK_MBUTTON
    else:
        logging.error(f"click_background: 不支持的按钮 '{button}'")
        return False

    all_success = True
    try:
        for i in range(clicks):
            # Apply random offsets
            final_x = x + random.randint(-random_range_x, random_range_x)
            final_y = y + random.randint(-random_range_y, random_range_y)
            final_lParam = win32api.MAKELONG(final_x, final_y)

            # Send DOWN message
            # Use PostMessage for non-blocking behavior
            win32api.PostMessage(hwnd, down_message, wParam_down, final_lParam)
            time.sleep(0.02) # Small delay, adjust if needed
            # Send UP message (wParam is usually 0 for UP)
            win32api.PostMessage(hwnd, up_message, 0, final_lParam) 
            
            # logging.info(f"后台点击 {i+1}/{clicks} 消息已发送到 HWND {hwnd} at ({final_x},{final_y}) (原始: {x},{y})")
            if clicks > 1 and i < clicks - 1:
                time.sleep(interval) # User-specified interval between clicks
                
    except Exception as e:
        logging.error(f"发送点击消息到窗口 {hwnd} 时发生错误: {e}", exc_info=True)
        all_success = False
        
    return all_success

if __name__ == '__main__':
    # Example Usage (Requires manually finding a target HWND)
    # target_title = "Calculator" # Example
    target_title = "Untitled - Notepad" # Example: English Notepad
    # target_title = "无标题 - 记事本" # Example: Chinese Notepad
    
    # Setup basic logging for testing this module directly
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
        
    if not PYWIN32_AVAILABLE:
         logging.error("Please install pywin32 first: pip install pywin32")
    else:
        hwnd = win32gui.FindWindow(None, target_title)
        if hwnd:
            logging.info(f"Found window '{target_title}' with HWND: {hwnd}")
            
            # Test Capture
            logging.info("Attempting background capture...")
            captured_image = capture_window_background(hwnd)
            if captured_image is not None:
                logging.info("Background capture successful!")
                try:
                    # Display the captured image (optional, requires cv2)
                    window_name = "Background Capture Test"
                    cv2.imshow(window_name, captured_image)
                    logging.info(f"Displaying captured image. Press any key in the '{window_name}' window to close...")
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                    logging.info("Capture window closed.")
                except ImportError:
                    logging.warning("OpenCV not fully available, cannot display image.")
                except Exception as display_err:
                    logging.error(f"Error displaying image: {display_err}", exc_info=True)
            else:
                logging.error("Background capture failed.")

            # Test Click (Use with extreme caution!)
            # logging.info("\nPreparing to test background click in 5 seconds...")
            # logging.info("Click will be sent to client coordinates (20, 20) of the target window.")
            # time.sleep(5)
            # test_x, test_y = 20, 20 
            # logging.info(f"Attempting LEFT click at ({test_x}, {test_y})...")
            # success = click_background(hwnd, test_x, test_y, button='left', clicks=1, random_range_x=5, random_range_y=5) # Example with random range
            # if success:
            #     logging.info("Background click messages sent.")
            # else:
            #     logging.error("Background click message sending failed.")

        else:
            logging.error(f"Window with title '{target_title}' not found.") 