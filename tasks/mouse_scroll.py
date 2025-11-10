# -*- coding: utf-8 -*-
import pyautogui
import logging
import time
from typing import Dict, Any, Optional, Tuple

# Try importing Windows specific modules
try:
    import win32api
    import win32gui
    import win32con
    WHEEL_DELTA = 120 # Standard value for mouse wheel delta
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    # Log warning only once at module level if needed, or let execution fail gracefully
    # print("Warning: pywin32 library not found. Background mode and foreground window activation are unavailable.")

# --- 新增导入 ---
import cv2
import numpy as np
import os # For path checking if needed, though imdecode handles paths
import traceback # For detailed error logging

logger = logging.getLogger(__name__)

try:
    from utils.win32_utils import capture_window_background # 原版本路径
except ImportError:
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.win32_utils import capture_window_background # 模块化版本路径
    except ImportError:
        logger.warning("无法导入 capture_window_background，后台模式可能不可用")
        capture_window_background = None
# --------------

# 任务类型标识
TASK_TYPE = "鼠标滚轮操作"

def _find_image_background(target_hwnd, full_image_path, template_processed_gray, confidence_val, params, kwargs, counters) -> Tuple[bool, Optional[int], Optional[int], Optional[int]]:
    """Helper to find image in background mode. Returns (found, client_x, client_y, specific_scroll_hwnd)."""
    image_found_bg = False
    found_client_x, found_client_y = None, None
    specific_scroll_hwnd = target_hwnd

    if not WINDOWS_AVAILABLE:
        logger.error("后台图片定位需要 pywin32。")
        return False, None, None, target_hwnd
    if not win32gui.IsWindow(target_hwnd):
        logger.error(f"后台模式错误：目标窗口句柄 {target_hwnd} 无效或已销毁。")
        return False, None, None, target_hwnd

    logger.debug("后台模式：截取目标窗口客户区...")
    if capture_window_background is None:
        logger.error("capture_window_background 函数不可用，无法执行后台截图")
        return False, None, None, target_hwnd

    screenshot_img = capture_window_background(target_hwnd)
    if screenshot_img is None:
        logger.error(f"无法捕获目标窗口 {target_hwnd} 的后台截图。")
        return False, None, None, target_hwnd

    try:
        screenshot_processed_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    except cv2.error as cv_err:
        logger.error(f"无法将后台截图转换为灰度图: {cv_err}")
        return False, None, None, target_hwnd
    
    template_h, template_w = template_processed_gray.shape[:2]
    screenshot_h, screenshot_w = screenshot_processed_gray.shape[:2]

    if screenshot_h < template_h or screenshot_w < template_w:
        logger.error(f"后台截图尺寸 ({screenshot_w}x{screenshot_h}) 小于模板尺寸 ({template_w}x{template_h})。")
        return False, None, None, target_hwnd

    logger.debug("后台模式：使用 matchTemplate 查找图片 (灰度图)...")
    result = cv2.matchTemplate(screenshot_processed_gray, template_processed_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    logger.debug(f"后台模式：最高匹配分数: {max_val:.4f} at {max_loc}")

    if max_val >= confidence_val:
        image_found_bg = True
        top_left_x, top_left_y = max_loc
        found_client_x = top_left_x + template_w // 2
        found_client_y = top_left_y + template_h // 2
        logger.info(f"后台图片找到！客户区中心坐标: ({found_client_x}, {found_client_y})")

        try:
            client_coords_for_child = (found_client_x, found_client_y)
            flags = win32con.CWP_SKIPINVISIBLE | win32con.CWP_SKIPDISABLED | win32con.CWP_SKIPTRANSPARENT
            child_hwnd = win32gui.ChildWindowFromPointEx(target_hwnd, client_coords_for_child, flags)
            if child_hwnd:
                specific_scroll_hwnd = child_hwnd
                logger.info(f"  将滚动目标句柄更新为子窗口: {specific_scroll_hwnd}")
        except Exception as hwnd_err:
            logger.warning(f"使用 ChildWindowFromPointEx 获取子窗口句柄时出错: {hwnd_err}。将使用父窗口句柄 {target_hwnd}。", exc_info=True)

        find_location_only = params.get('find_location_only', False)
        if find_location_only:
            card_id = kwargs.get('card_id')
            if card_id is not None:
                counters[f'__found_hwnd_{card_id}'] = specific_scroll_hwnd
                counters[f'__found_client_x_{card_id}'] = found_client_x
                counters[f'__found_client_y_{card_id}'] = found_client_y
                logger.info(f"仅查找模式 (后台)：已存储句柄和客户区坐标。")
            else:
                logger.warning("仅查找模式 (后台)：缺少 card_id，无法存储定位信息。")
                image_found_bg = False
    else:
        logger.warning(f"后台图片未找到 (置信度 {max_val:.4f} < {confidence_val})。")

    return image_found_bg, found_client_x, found_client_y, specific_scroll_hwnd

def _find_image_foreground(target_hwnd, full_image_path, template_processed_gray, confidence_val, params, kwargs, counters) -> Tuple[bool, Optional[int], Optional[int]]:
    """Helper to find image in foreground mode. Returns (found, screen_x, screen_y)."""
    image_found_fg = False
    found_screen_x, found_screen_y = None, None

    logger.debug("前台模式：截取屏幕进行图片定位...")
    screenshot_pil = None
    capture_region_for_pyautogui = None
    region_offset_x, region_offset_y = 0, 0

    if target_hwnd and WINDOWS_AVAILABLE and win32gui.IsWindow(target_hwnd):
        try:
            client_rect = win32gui.GetClientRect(target_hwnd)
            client_left, client_top, client_right, client_bottom = client_rect
            screen_top_left = win32gui.ClientToScreen(target_hwnd, (client_left, client_top))
            client_width = client_right - client_left
            client_height = client_bottom - client_top

            if client_width > 0 and client_height > 0:
                capture_region_for_pyautogui = (screen_top_left[0], screen_top_left[1], client_width, client_height)
                region_offset_x, region_offset_y = screen_top_left[0], screen_top_left[1]
                logger.debug(f"前台图片定位：目标窗口客户区 (屏幕坐标): {capture_region_for_pyautogui}")
                screenshot_pil = pyautogui.screenshot(region=capture_region_for_pyautogui)
            else:
                logger.warning(f"目标窗口 {target_hwnd} 客户区尺寸无效 ({client_width}x{client_height})。将截取全屏。")
        except Exception as e_win_capture:
            logger.warning(f"无法截取目标窗口客户区进行图片定位: {e_win_capture}。将截取全屏。")
    
    if screenshot_pil is None:
        screenshot_pil = pyautogui.screenshot()
        region_offset_x, region_offset_y = 0, 0
        logger.debug("前台图片定位：已截取全屏。")

    screenshot_img_bgr = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)
    screenshot_processed_gray = cv2.cvtColor(screenshot_img_bgr, cv2.COLOR_BGR2GRAY)
    
    template_h, template_w = template_processed_gray.shape[:2]
    screenshot_h, screenshot_w = screenshot_processed_gray.shape[:2]

    if screenshot_h < template_h or screenshot_w < template_w:
        logger.error(f"前台截图尺寸 ({screenshot_w}x{screenshot_h}) 小于模板尺寸 ({template_w}x{template_h})。")
        return False, None, None

    logger.debug("前台模式：使用 matchTemplate 查找图片 (灰度图)...")
    result = cv2.matchTemplate(screenshot_processed_gray, template_processed_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc_in_screenshot = cv2.minMaxLoc(result)
    logger.debug(f"前台模式：最高匹配分数: {max_val:.4f} at {max_loc_in_screenshot}")

    if max_val >= confidence_val:
        image_found_fg = True
        center_x_in_screenshot = max_loc_in_screenshot[0] + template_w // 2
        center_y_in_screenshot = max_loc_in_screenshot[1] + template_h // 2
        found_screen_x = region_offset_x + center_x_in_screenshot
        found_screen_y = region_offset_y + center_y_in_screenshot
        logger.info(f"前台图片找到！屏幕中心坐标: ({found_screen_x}, {found_screen_y})")

        find_location_only = params.get('find_location_only', False)
        if find_location_only:
            card_id = kwargs.get('card_id')
            if card_id is not None:
                counters[f'__found_screen_x_{card_id}'] = found_screen_x
                counters[f'__found_screen_y_{card_id}'] = found_screen_y
                logger.info(f"仅查找模式 (前台)：已存储屏幕坐标。")
            else:
                logger.warning("仅查找模式 (前台)：缺少 card_id，无法存储定位信息。")
                image_found_fg = False
    else:
        logger.warning(f"前台图片未找到 (置信度 {max_val:.4f} < {confidence_val})。")
        
    return image_found_fg, found_screen_x, found_screen_y

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int], window_region: Optional[Tuple[int, int, int, int]], **kwargs) -> Tuple[bool, str, Optional[int]]:
    logger.debug(f"MouseScroll Task: Received kwargs: {kwargs}")
    stop_event = kwargs.get('stop_event')

    direction = params.get('direction', '向下')
    try:
        steps_per_scroll = int(params.get('steps_per_scroll', 1))
        scroll_count = int(params.get('scroll_count', 1))
        interval = float(params.get('interval', 0.1))
    except (ValueError, TypeError) as e:
        logger.error(f"无效的滚动或间隔参数: {e}")
        return False, '执行下一步', None

    location_mode = params.get('location_mode', '窗口中心')

    # 🔧 新增：根据执行模式设置前台输入管理器的强制模式（在标准化之前）
    try:
        from utils.foreground_input_manager import get_foreground_input_manager
        FOREGROUND_INPUT_AVAILABLE = True
        foreground_input = get_foreground_input_manager()
    except ImportError:
        FOREGROUND_INPUT_AVAILABLE = False
        foreground_input = None

    if FOREGROUND_INPUT_AVAILABLE and foreground_input and execution_mode and execution_mode.startswith('foreground'):
        if execution_mode == 'foreground_driver':
            # 前台模式一：强制使用Interception驱动（不降级）
            foreground_input.set_forced_mode('interception')
            logger.info("[执行模式] 前台模式一 - 强制Interception驱动（滚动）")
        elif execution_mode == 'foreground_pyautogui':
            # 前台模式二：强制使用 PyAutoGUI
            foreground_input.set_forced_mode('pyautogui')
            foreground_input.set_target_window(target_hwnd)  # PyAutoGUI需要激活窗口
            logger.info("[执行模式] 前台模式二 - 强制PyAutoGUI（滚动）")
        else:
            # 默认：如果只是'foreground'，使用Interception
            foreground_input.set_forced_mode('interception')
            logger.info("[执行模式] 前台模式（默认） - 强制Interception驱动（滚动）")

    # 关键修复：标准化7种执行模式为基础模式
    original_execution_mode = execution_mode
    if execution_mode and execution_mode.startswith('foreground'):
        # 前台模式一/二/三 -> foreground
        execution_mode = 'foreground'
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode}")
    elif execution_mode and execution_mode.startswith('background'):
        # 后台模式一/二 -> background
        execution_mode = 'background'
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode}")
    elif execution_mode and execution_mode.startswith('emulator_'):
        # 模拟器模式(MuMu/雷电) -> background (模拟器使用后台输入方法)
        execution_mode = 'background'
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode} (模拟器模式)")

    # 执行模式中文映射
    mode_names = {'foreground': '前台', 'background': '后台'}
    mode_name = mode_names.get(execution_mode, execution_mode)
    logger.info(f"准备执行鼠标滚轮: 方向='{direction}', 次数={scroll_count}, 每步刻度={steps_per_scroll}, 起始位置模式='{location_mode}', 模式='{mode_name}' (原始: {original_execution_mode})")

    target_x, target_y = None, None 
    current_scroll_target_hwnd = target_hwnd

    image_path_param = params.get('image_path') # Renamed to avoid conflict with os.path
    confidence_val = float(params.get('confidence', 0.6))

    # --- Location Determination ---
    try:
        if location_mode == "图片位置":
            if not image_path_param: # Use the renamed variable
                logger.error("错误：选择了图片位置模式，但未提供图片路径。")
                return False, '执行下一步', None
            
            images_dir = kwargs.get('images_dir')
            if not images_dir:
                logger.error("图片定位失败：未能获取 images 目录路径。")
                return False, '执行下一步', None
            
            relative_filename = os.path.basename(image_path_param) 
            full_image_path = os.path.join(images_dir, relative_filename)

            try: # Inner try for image processing and finding
                img_np = np.fromfile(full_image_path, dtype=np.uint8)
                template_img_bgr_or_bgra = cv2.imdecode(img_np, cv2.IMREAD_UNCHANGED)
                if template_img_bgr_or_bgra is None:
                    logger.error(f"无法加载或解码模板图片: {full_image_path}")
                    return False, '执行下一步', None
                
                if len(template_img_bgr_or_bgra.shape) == 2: template_processed_gray = template_img_bgr_or_bgra
                elif template_img_bgr_or_bgra.shape[2] == 4: template_processed_gray = cv2.cvtColor(template_img_bgr_or_bgra, cv2.COLOR_BGRA2GRAY)
                else: template_processed_gray = cv2.cvtColor(template_img_bgr_or_bgra, cv2.COLOR_BGR2GRAY)
                
                logger.info(f"准备查找图片: '{relative_filename}' (置信度 >= {confidence_val})")

                image_found_flag = False
                if execution_mode == 'background':
                    if not target_hwnd:
                        logger.error("后台图片定位需要目标窗口句柄。")
                        return False, '执行下一步', None
                    image_found_flag, found_cx, found_cy, specific_hwnd = _find_image_background(
                        target_hwnd, full_image_path, template_processed_gray, confidence_val, params, kwargs, counters
                    )
                    if image_found_flag:
                        target_x, target_y = found_cx, found_cy
                        current_scroll_target_hwnd = specific_hwnd
                else: # Foreground
                    image_found_flag, found_sx, found_sy = _find_image_foreground(
                        target_hwnd, full_image_path, template_processed_gray, confidence_val, params, kwargs, counters
                    )
                    if image_found_flag:
                        target_x, target_y = found_sx, found_sy
                
                if params.get('find_location_only', False) and image_found_flag:
                    logger.info("仅查找模式成功完成。")
                    return True, '执行下一步', None
                if not image_found_flag:
                    logger.error("图片定位失败：未找到指定的图片。")
                    return False, '执行下一步', None

            except Exception as img_proc_err: # Catch errors from image processing/finding
                logger.error(f"处理或查找图片时发生错误: {img_proc_err}", exc_info=True)
                return False, '执行下一步', None
            # End of the inner try-except for image processing

        elif location_mode == "指定坐标":
            # 解析滚动起始位置坐标
            scroll_position = params.get('scroll_start_position', '500,300')
            coordinate_mode = params.get('coordinate_mode', '客户区坐标')  # 获取坐标模式

            # 调试信息：显示所有相关参数
            logger.info(f"调试参数: scroll_start_position='{scroll_position}', coordinate_mode='{coordinate_mode}'")
            logger.info(f"调试参数: scroll_x={params.get('scroll_x')}, scroll_y={params.get('scroll_y')}")
            logger.info(f"调试参数: 所有参数键={list(params.keys())}")

            try:
                if isinstance(scroll_position, str) and ',' in scroll_position:
                    raw_x, raw_y = map(int, scroll_position.split(','))
                    logger.info(f"成功解析scroll_start_position: ({raw_x}, {raw_y})")
                else:
                    # 兼容旧版本的 scroll_x 和 scroll_y 参数
                    raw_x = int(params.get('scroll_x', 500))
                    raw_y = int(params.get('scroll_y', 300))
                    logger.info(f"使用scroll_x/scroll_y参数: ({raw_x}, {raw_y})")
            except (ValueError, TypeError) as e:
                logger.warning(f"无法解析滚动坐标: {scroll_position}，错误: {e}，使用默认值 (500, 300)")
                raw_x, raw_y = 500, 300

            # 直接使用客户区坐标，不进行转换
            target_x, target_y = raw_x, raw_y
            logger.info(f"使用客户区坐标: ({target_x}, {target_y}) (模式: {coordinate_mode}, 执行模式: {execution_mode})")

        elif location_mode == "窗口中心":
            logger.info("起始位置模式：窗口中心。计算窗口中心...")
            if target_hwnd and WINDOWS_AVAILABLE:
                try:
                    if not win32gui.IsWindow(target_hwnd):
                        logger.warning(f"无法移至中心：目标窗口句柄 {target_hwnd} 无效。将在当前位置滚动。")
                    else:
                        if execution_mode == 'background':
                            client_rect = win32gui.GetClientRect(target_hwnd)
                            target_x = (client_rect[2] - client_rect[0]) // 2
                            target_y = (client_rect[3] - client_rect[1]) // 2
                            logger.info(f"后台模式：滚动定位到目标窗口客户区中心: ({target_x}, {target_y})")
                        else: # Foreground
                            rect = win32gui.GetWindowRect(target_hwnd)
                            target_x = (rect[0] + rect[2]) // 2
                            target_y = (rect[1] + rect[3]) // 2
                            logger.info(f"前台模式：滚动定位到目标窗口屏幕中心: ({target_x}, {target_y})")
                except Exception as move_err: # Corrected indent for this except
                    logger.warning(f"计算窗口中心时出错: {move_err}。将在当前位置滚动。")
                    target_x, target_y = None, None
            elif not target_hwnd:
                logger.warning("请求移至中心，但未提供目标窗口句柄。将在当前位置滚动。")
            elif not WINDOWS_AVAILABLE:
                logger.warning("无法移至中心：缺少 'pywin32' 库。将在当前位置滚动。")
        # else: location_mode == "当前位置" (or default if "当前位置" was an option)
            # target_x, target_y remain None, scrolling happens at current mouse pos
    
    except Exception as setup_err: # This is the except for the outer try block for location determination
         logger.error(f"确定滚动位置时发生错误: {setup_err}", exc_info=True)
         return False, '执行下一步', None
    # End of the outer try-except for location determination

    # --- 执行滚动 --- 
    try:
        if execution_mode == 'background':
            if not WINDOWS_AVAILABLE or not current_scroll_target_hwnd:
                logger.error("无法执行后台滚动：缺少 pywin32 或有效的目标窗口句柄。")
                return False, '执行下一步', None
            if not win32gui.IsWindow(current_scroll_target_hwnd):
                logger.error(f"后台滚动错误：目标滚动窗口句柄 {current_scroll_target_hwnd} 无效。")
                return False, '执行下一步', None

            logger.info(f"执行后台鼠标滚轮: 滚动目标句柄={current_scroll_target_hwnd}, 客户区坐标={(target_x, target_y) if target_x is not None else '默认'}, 方向='{direction}', 次数={scroll_count}")
            
            screen_x_for_lparam, screen_y_for_lparam = win32api.GetCursorPos()
            if target_x is not None and target_y is not None:
                try:
                    point_to_convert = (target_x, target_y)
                    screen_coords_tuple = win32gui.ClientToScreen(current_scroll_target_hwnd, point_to_convert)
                    screen_x_for_lparam, screen_y_for_lparam = screen_coords_tuple
                    logger.debug(f"  后台滚动：客户区 ({target_x},{target_y}) on HWND {current_scroll_target_hwnd} -> 屏幕 ({screen_x_for_lparam},{screen_y_for_lparam}) for lParam.")
                except Exception as conv_err:
                     logger.warning(f"无法将客户区坐标 ({target_x}, {target_y}) on HWND {current_scroll_target_hwnd} 转换为屏幕坐标: {conv_err}。使用当前鼠标屏幕坐标 for lParam。")
            else:
                 logger.debug("后台滚动未指定目标客户区坐标，使用当前鼠标屏幕位置 for lParam。")
                 
            lParam = win32api.MAKELONG(screen_x_for_lparam, screen_y_for_lparam)
            delta = WHEEL_DELTA if direction == '向上' else -WHEEL_DELTA
            wheel_rotation = delta * steps_per_scroll
            wParam = (wheel_rotation << 16) | 0

            if target_x is not None and target_y is not None:
                if stop_event and stop_event.is_set(): return False, '任务已停止', None
                try:
                    # 使用简化的后台消息发送（客户区坐标）
                    try:
                        from main import mouse_move_fixer
                        # 直接使用客户区坐标发送后台消息
                        success = mouse_move_fixer.safe_send_background_message(
                            current_scroll_target_hwnd, win32con.WM_MOUSEMOVE, 0, target_x, target_y
                        )
                        logger.info(f"后台滚轮移动: 客户区坐标({target_x}, {target_y})")

                        if not success:
                            logger.warning("使用修复器发送后台鼠标移动失败，回退到原始方法")
                            move_lParam = win32api.MAKELONG(target_x, target_y)
                            move_wParam = 0
                            win32gui.PostMessage(current_scroll_target_hwnd, win32con.WM_MOUSEMOVE, move_wParam, move_lParam)
                    except ImportError:
                        logger.debug("后台鼠标移动修复器不可用，使用原始方法")
                        move_lParam = win32api.MAKELONG(target_x, target_y)
                        move_wParam = 0
                        win32gui.PostMessage(current_scroll_target_hwnd, win32con.WM_MOUSEMOVE, move_wParam, move_lParam)

                    logger.debug(f"  发送 WM_MOUSEMOVE 到 {current_scroll_target_hwnd} (客户区坐标: {target_x},{target_y})")
                    time.sleep(0.05)
                except Exception as move_err:
                     logger.warning(f"发送 WM_MOUSEMOVE 时出错: {move_err}")
            
            for i in range(scroll_count):
                if stop_event and stop_event.is_set(): return False, f'任务已停止 (滚动 {i+1})', None
                logger.debug(f"  发送 WM_MOUSEWHEEL {i+1}/{scroll_count} (wParam={wParam}, lParam={lParam}) 到句柄: {current_scroll_target_hwnd}")
                win32gui.PostMessage(current_scroll_target_hwnd, win32con.WM_MOUSEWHEEL, wParam, lParam)
                if scroll_count > 1 and i < scroll_count - 1 and interval > 0:
                    sleep_chunk = 0.05 
                    remaining_sleep = interval
                    while remaining_sleep > 0:
                        if stop_event and stop_event.is_set():
                            logger.info("后台鼠标滚轮任务在 interval sleep 期间被请求停止。")
                            return False, '任务已停止', None
                        actual_sleep = min(sleep_chunk, remaining_sleep)
                        time.sleep(actual_sleep)
                        remaining_sleep -= actual_sleep
            logger.info("后台鼠标滚轮操作完成。")
            # 使用统一的成功处理（包含延迟）
            from .task_utils import handle_success_action
            return handle_success_action(params, kwargs.get('card_id'), kwargs.get('stop_checker'))

        else: # Foreground
            mode_description = "前台"
            logger.info(f"执行{mode_description}鼠标滚轮: 目标屏幕坐标={(target_x, target_y) if target_x is not None else '当前'}, 方向='{direction}', 次数={scroll_count}")
            
            # 前台模式：激活目标窗口确保滚轮生效
            if target_hwnd and WINDOWS_AVAILABLE:
                try:
                    if win32gui.IsWindow(target_hwnd):
                        logger.debug(f"前台模式：激活目标窗口 {target_hwnd}")
                        win32gui.SetForegroundWindow(target_hwnd)
                        time.sleep(0.1)  # 给窗口激活一点时间
                except Exception as activate_err:
                    logger.debug(f"激活目标窗口时出错: {activate_err}，继续执行滚轮操作")
            
            # 移动到目标位置（如果指定）
            if target_x is not None and target_y is not None:
                if stop_event and stop_event.is_set(): return False, '任务已停止', None
                try:
                    logger.debug(f"前台移动鼠标到目标位置: ({target_x}, {target_y})")

                    # 使用简化的鼠标移动（客户区坐标）
                    try:
                        from main import mouse_move_fixer
                        if coordinate_mode == '客户区坐标':
                            # 直接使用客户区坐标移动
                            success = mouse_move_fixer.safe_move_to_client_coord(target_hwnd, target_x, target_y, duration=0.1)
                            logger.info(f"前台滚轮移动: 客户区坐标({target_x}, {target_y})")
                        else:
                            # 屏幕坐标直接移动
                            pyautogui.moveTo(target_x, target_y, duration=0.1)
                            success = True
                            logger.info(f"前台滚轮移动: 屏幕坐标({target_x}, {target_y})")

                        if not success:
                            logger.warning("使用修复器移动鼠标失败，回退到pyautogui")
                            pyautogui.moveTo(target_x, target_y, duration=0.1)
                    except ImportError:
                        logger.debug("鼠标移动修复器不可用，使用pyautogui")
                        pyautogui.moveTo(target_x, target_y, duration=0.1)

                    time.sleep(0.05)
                except Exception as move_err:
                     logger.warning(f"前台移动鼠标时出错: {move_err}。将在当前位置滚动。")

            # 前台滚轮：调整滚动幅度以匹配后台模式
            # 后台: WHEEL_DELTA * steps_per_scroll = 120 * steps_per_scroll
            # 前台: pyautogui.scroll() 的单位不同，需要匹配后台的120倍数
            # 因此前台需要乘以120来匹配后台的滚动距离
            scroll_value_per_step = steps_per_scroll * 120
            if direction == '向下':
                scroll_value_per_step = -scroll_value_per_step

            logger.debug(f"前台滚轮参数: 方向={direction}, 每步值={scroll_value_per_step} (steps_per_scroll={steps_per_scroll} * 120), 总次数={scroll_count}")
            
            for i in range(scroll_count):
                if stop_event and stop_event.is_set(): return False, f'任务已停止 (滚动 {i+1})', None
                logger.debug(f"执行前台滚轮 {i+1}/{scroll_count}: scroll({scroll_value_per_step})")
                try:
                    pyautogui.scroll(scroll_value_per_step)
                    # 添加小延迟确保滚动生效
                    time.sleep(0.02)
                except Exception as scroll_err:
                    logger.warning(f"前台滚轮第 {i+1} 次操作时出错: {scroll_err}")
                    continue
                
                if scroll_count > 1 and i < scroll_count - 1 and interval > 0:
                    sleep_chunk = 0.05 
                    remaining_sleep = interval
                    while remaining_sleep > 0:
                        if stop_event and stop_event.is_set():
                            logger.info("前台鼠标滚轮任务在 interval sleep 期间被请求停止。")
                            return False, '任务已停止', None
                        actual_sleep = min(sleep_chunk, remaining_sleep)
                        time.sleep(actual_sleep)
                        remaining_sleep -= actual_sleep
            logger.info(f"{mode_description} 鼠标滚轮操作完成。")
            # 使用统一的成功处理（包含延迟）
            from .task_utils import handle_success_action
            return handle_success_action(params, kwargs.get('card_id'), kwargs.get('stop_checker'))
            
    except Exception as scroll_err:
        logger.exception(f"执行鼠标滚轮操作时发生错误: {scroll_err}")
        return False, '执行下一步', None

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    from .task_utils import get_standard_next_step_delay_params, get_standard_action_params, merge_params_definitions

    # 原有的滚动参数
    scroll_params = {
        # 滚动参数
        "---scroll_params---": {"type": "separator", "label": "滚动参数"},
        "direction": {
            "label": "滚动方向",
            "type": "select",
            "options": ["向上", "向下"], 
            "default": "向下",          
            "tooltip": "选择鼠标滚轮向上或向下滚动"
        },
        "steps_per_scroll": {
            "label": "每步滚动刻度",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "设置单次滚动操作模拟的滚轮刻度数 (非像素)"
        },
        "scroll_count": {
            "label": "滚动次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "设置总共执行多少次滚动操作"
        },
        "interval": {
            "label": "滚动间隔(秒)",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "decimals": 2,
            "tooltip": "设置多次滚动之间的时间间隔（秒）",
        },

        "---location_options---": {"type": "separator", "label": "滚动位置选项"}, 
        "location_mode": {
            "label": "滚动起始位置",
            "type": "select",
            "options": ["窗口中心", "图片位置", "指定坐标"],
            "default": "窗口中心",
            "tooltip": "选择鼠标滚动的起始位置。"
        },
        "scroll_coordinate_selector": {
            "label": "坐标获取工具",
            "type": "button",
            "button_text": "点击获取坐标",
            "tooltip": "点击选择滚轮操作的起始坐标位置",
            "widget_hint": "coordinate_selector",
            "condition": {"param": "location_mode", "value": "指定坐标"}
        },
        "scroll_start_position": {
            "label": "滚动起始位置",
            "type": "text",
            "default": "500,300",
            "tooltip": "执行滚轮操作的起始坐标位置",
            "readonly": True,
            "condition": {"param": "location_mode", "value": "指定坐标"}
        },
        "coordinate_mode": {
            "label": "坐标模式",
            "type": "select",
            "options": ["客户区坐标", "屏幕坐标"],
            "default": "客户区坐标",
            "tooltip": "指定坐标的类型：客户区坐标（相对于窗口）或屏幕坐标（绝对位置）",
            "condition": {"param": "location_mode", "value": "指定坐标"}
        },
        "image_path": {
            "label": "定位图片路径",
            "type": "file",
            "required": True, 
            "condition": {"param": "location_mode", "value": "图片位置"}, 
            "tooltip": "需要查找的图片文件，用于确定滚动起始位置。"
        },
        "confidence": {
            "label": "图片查找置信度",
            "type": "float",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "condition": {"param": "location_mode", "value": "图片位置"},
            "tooltip": "图片匹配的相似度阈值 (0.1 到 1.0)。"
        },
        "find_location_only": {
            "label": "仅查找定位信息",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，任务只负责查找图片并获取对应句柄/坐标，不执行实际滚动。",
            "condition": {"param": "location_mode", "value": "图片位置"}
        }
    }

    # 合并所有参数定义
    return merge_params_definitions(
        scroll_params,
        get_standard_next_step_delay_params(),
        get_standard_action_params()
    )

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("开始 MouseScrollTask 模块测试...")
    # ... (Rest of the test block, ensure imports like win32gui are handled if it's run directly)
    logger.info("MouseScrollTask 模块测试结束。") 