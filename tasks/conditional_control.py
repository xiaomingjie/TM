# -*- coding: utf-8 -*-
import logging
import time
import operator # For counter comparison
from typing import Dict, Any, Optional, Tuple, List
import os # <-- ADDED Import

# Try importing image processing libraries
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Try importing pyautogui for image finding & screenshot
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Try importing pywin32 for potential future window/pixel checks
try:
    import win32gui
    import win32con
    WINDOWS_AVAILABLE = True
    PYWIN32_AVAILABLE = True # Add alias for consistency
except ImportError:
    WINDOWS_AVAILABLE = False
    PYWIN32_AVAILABLE = False # Add alias for consistency

# --- ADDED: Import background capture utility ---
try:
    from utils.win32_utils import capture_window_background
except ImportError:
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.win32_utils import capture_window_background
    except ImportError:
        capture_window_background = None
# ---------------------------------------

logger = logging.getLogger(__name__)

# --- Comparison Operators Mapping ---
COMPARISON_OPERATORS = {
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
}

# Define activation helper function (copied for now)
def _activate_window_foreground(target_hwnd: Optional[int], logger):
    if not target_hwnd or not PYWIN32_AVAILABLE:
        if not target_hwnd:
             logger.debug("前台模式执行，但未提供目标窗口句柄，无法激活。")
        elif not PYWIN32_AVAILABLE:
             logger.warning("无法激活目标窗口：缺少 'pywin32' 库。")
        return False
    try:
        if not win32gui.IsWindow(target_hwnd):
            logger.warning(f"无法激活目标窗口：句柄 {target_hwnd} 无效或已销毁。")
            return False
        current_foreground_hwnd = win32gui.GetForegroundWindow()
        if current_foreground_hwnd == target_hwnd:
            logger.debug(f"目标窗口 {target_hwnd} 已是前台窗口，无需激活。")
            return True
        if win32gui.IsIconic(target_hwnd):
            logger.info(f"目标窗口 {target_hwnd} 已最小化，尝试恢复并激活...")
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            time.sleep(0.15)
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.15)
            logger.info(f"窗口 {target_hwnd} 已尝试恢复并设置为前台。")
        else:
            logger.info(f"尝试将窗口 {target_hwnd} 设置为前台...")
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.1)
        return True
    except Exception as e:
        logger.warning(f"设置前台窗口 {target_hwnd} 时出错: {e}。")
        return False

# --- Image Preprocessing Helper ---
def _preprocess_image(img, method: str, threshold_val: int = 128, 
                      canny_thresh1: int = 100, canny_thresh2: int = 200,
                      scale_factor: float = 2.0):
    if not CV2_AVAILABLE:
        logger.warning("无法预处理图像：缺少 'opencv-python' 库。")
        return img # Return original if cv2 not available
        
    if img is None:
        logger.error("无法预处理图像：图像数据为空。")
        return None
        
    processed_img = img
    gray_img = None # Cache grayscale image if needed multiple times

    try:
        # 智能放大处理
        if method == '智能放大':
            h, w = img.shape[:2]
            if h < 50 or w < 50:  # 如果宽或高小于50像素
                new_width = int(w * scale_factor)
                new_height = int(h * scale_factor)
                processed_img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
                logger.debug(f"图片从 {w}x{h} 放大到 {new_width}x{new_height}")
            return processed_img
            
        # Ensure grayscale for methods that need it
        if method in ['灰度化', '二值化', '边缘检测 (Canny)']:
            if len(img.shape) == 3:
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray_img = img # Already grayscale
                
        # Apply selected method
        if method == '灰度化':
            processed_img = gray_img
        elif method == '二值化':
            _, processed_img = cv2.threshold(gray_img, threshold_val, 255, cv2.THRESH_BINARY)
        elif method == '边缘检测 (Canny)':
             # Apply Canny edge detection
             processed_img = cv2.Canny(gray_img, canny_thresh1, canny_thresh2)
        # '无' or unknown method: return original (BGR or original gray/BGRA)
        # If no processing was done, return the original image
        elif method == '无':
             processed_img = img # Return the original color/unchanged image
             
        return processed_img
    except Exception as e:
        logger.exception(f"图像预处理 ('{method}') 时出错: {e}")
        return img # Return original on error

# --- ADDED: Helper function for motion detection ---
def _check_motion(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int], prev_image: Optional[np.ndarray]) -> Tuple[bool, Optional[np.ndarray]]:
    """检查指定区域是否有移动。"""
    if not CV2_AVAILABLE:
        logger.error("移动检测失败：缺少 'opencv-python' 库。")
        return False, prev_image

    # 关键修复：标准化执行模式
    original_execution_mode = execution_mode
    if execution_mode and execution_mode.startswith('foreground'):
        execution_mode = 'foreground'
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode}")
    elif execution_mode and execution_mode.startswith('background'):
        execution_mode = 'background'
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode}")
    elif execution_mode and execution_mode.startswith('emulator_'):
        execution_mode = 'background'  # 模拟器使用后台方法
        logger.debug(f"标准化执行模式: {original_execution_mode} -> {execution_mode} (模拟器模式)")

    param_x = params.get('minimap_x', 0)
    param_y = params.get('minimap_y', 0)
    param_width = params.get('minimap_width', 50)
    param_height = params.get('minimap_height', 50)
    motion_threshold = params.get('motion_threshold', 50) # Minimum changed pixel count
    # 工具 修复：降低像素差异阈值，提高敏感度
    diff_threshold = params.get('pixel_diff_threshold', 15)  # 从30降低到15，提高像素变化敏感度

    logger.debug(f"  移动检测参数: x={param_x}, y={param_y}, w={param_width}, h={param_height}")
    logger.debug(f"  像素变化阈值: {motion_threshold}, 灰度差异阈值: {diff_threshold}")

    current_image_np = None
    try:
        # 使用标准化后的执行模式进行判断
        if execution_mode == 'background':  # 此时已经是标准化后的值
            logger.info(f"开始移动检测 (模式: background)")
            if not PYWIN32_AVAILABLE:
                logger.error("后台移动检测失败：缺少 'pywin32' 库。")
                return False, prev_image
            if not target_hwnd:
                logger.error("后台移动检测失败：缺少目标窗口句柄 (HWND)。")
                return False, prev_image

            # 工具 修复：验证窗口句柄有效性
            try:
                if not win32gui.IsWindow(target_hwnd):
                    logger.error(f"后台移动检测失败：窗口句柄 {target_hwnd} 无效或窗口已关闭。")
                    return False, prev_image

                # 获取窗口信息用于调试
                window_title = win32gui.GetWindowText(target_hwnd)
                window_rect = win32gui.GetWindowRect(target_hwnd)
                client_rect = win32gui.GetClientRect(target_hwnd)
                logger.debug(f"  窗口信息: 标题='{window_title}', 窗口矩形={window_rect}, 客户区={client_rect}")

                # 检查客户区是否有效
                client_width = client_rect[2] - client_rect[0]
                client_height = client_rect[3] - client_rect[1]
                if client_width <= 0 or client_height <= 0:
                    logger.error(f"后台移动检测失败：窗口客户区尺寸无效 ({client_width}x{client_height})。")
                    return False, prev_image

            except Exception as e:
                logger.error(f"后台移动检测失败：验证窗口句柄时出错: {e}")
                return False, prev_image

            # --- Background mode uses client coordinates for cropping ---
            client_x, client_y, width, height = param_x, param_y, param_width, param_height
            client_region = (client_x, client_y, width, height)
            logger.debug(f"  使用参数作为客户区坐标: {client_region}")

            logger.debug(f"  调用 capture_window_background, HWND={target_hwnd} (获取完整客户区)")
            if capture_window_background is None:
                logger.error("capture_window_background 函数不可用，无法执行后台截图")
                return False, prev_image
            full_screenshot = capture_window_background(target_hwnd)

            if full_screenshot is None:
                 logger.error("  后台完整截图失败 (capture_window_background 返回 None)。")
                 return False, prev_image
            else:
                 logger.debug(f"  后台完整截图成功，尺寸: {full_screenshot.shape}")
                 full_h, full_w = full_screenshot.shape[:2]
                 # 工具 修复：增强坐标边界检查和自动修正
                 if client_x >= 0 and client_y >= 0 and client_x + width <= full_w and client_y + height <= full_h:
                      current_image_np = full_screenshot[client_y : client_y + height, client_x : client_x + width]
                      logger.debug(f"  已从完整截图中裁剪出区域，尺寸: {current_image_np.shape}")
                 else:
                      logger.warning(f"  裁剪区域 {client_region} 超出完整截图边界 ({full_w}x{full_h})，尝试自动修正...")

                      # 自动修正坐标到有效范围内
                      corrected_x = max(0, min(client_x, full_w - 1))
                      corrected_y = max(0, min(client_y, full_h - 1))
                      corrected_width = min(width, full_w - corrected_x)
                      corrected_height = min(height, full_h - corrected_y)

                      if corrected_width > 0 and corrected_height > 0:
                          current_image_np = full_screenshot[corrected_y : corrected_y + corrected_height, corrected_x : corrected_x + corrected_width]
                          logger.info(f"  已自动修正区域: ({corrected_x}, {corrected_y}, {corrected_width}, {corrected_height})，尺寸: {current_image_np.shape}")
                      else:
                          logger.error(f"  无法修正区域：修正后尺寸仍然无效 ({corrected_width}x{corrected_height})。")
                          return False, prev_image

        else: # Foreground mode
            logger.info(f"开始移动检测 (模式: foreground)")
            if not PYAUTOGUI_AVAILABLE:
                 logger.error("前台移动检测失败：缺少 'pyautogui' 库。")
                 return False, prev_image

            # --- MODIFIED: Calculate screen region based on window position ---
            screen_region_x = param_x
            screen_region_y = param_y
            screen_region_w = param_width
            screen_region_h = param_height

            if target_hwnd and PYWIN32_AVAILABLE:
                try:
                    if win32gui.IsWindow(target_hwnd):
                        window_rect = win32gui.GetWindowRect(target_hwnd)
                        window_left, window_top, _, _ = window_rect
                        logger.debug(f"  目标窗口屏幕坐标 (左上角): ({window_left}, {window_top})")
                        # Assume minimap params are relative to window's client area top-left
                        # For simplicity, using GetWindowRect (includes border). More accurate would be GetClientRect + ClientToScreen
                        # However, GetWindowRect is often sufficient if params target area relative to overall window pos.
                        screen_region_x = window_left + param_x
                        screen_region_y = window_top + param_y
                        # Width and Height remain the same
                        logger.debug(f"  结合窗口位置计算得到截图区域 (屏幕坐标): x={screen_region_x}, y={screen_region_y}, w={screen_region_w}, h={screen_region_h}")
                    else:
                         logger.warning(f"  目标窗口句柄 {target_hwnd} 无效，将使用参数作为屏幕坐标。")
                except Exception as e_rect:
                    logger.warning(f"  获取窗口位置时出错: {e_rect}。将使用参数作为屏幕坐标。")
            else:
                 logger.debug(f"  未提供有效窗口句柄或缺少pywin32，将直接使用参数作为屏幕坐标。")

            final_screen_region = (screen_region_x, screen_region_y, screen_region_w, screen_region_h)
            # ----------------------------------------------------------------

            try:
                 # --- Activate window before screenshot --- 
                 _activate_window_foreground(target_hwnd, logger)
                 # ----------------------------------------
                 logger.debug(f"  调用 pyautogui.screenshot, 屏幕区域={final_screen_region}")
                 screenshot_pil = pyautogui.screenshot(region=final_screen_region) # Use calculated region
                 current_image_np = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)
                 logger.debug(f"  前台截图成功，尺寸: {current_image_np.shape}")
            except Exception as e:
                 # Add more specific error logging for screenshot failure
                 logger.error(f"  前台截图失败 (区域: {final_screen_region}): {e}")
                 # Check if region might be off-screen
                 try:
                      screen_width, screen_height = pyautogui.size()
                      if screen_region_x + screen_region_w > screen_width or screen_region_y + screen_region_h > screen_height or screen_region_x < 0 or screen_region_y < 0:
                           logger.error(f"  截图区域 {final_screen_region} 可能部分或完全超出屏幕范围 ({screen_width}x{screen_height})。")
                 except Exception as size_e:
                      logger.error(f"  获取屏幕尺寸时出错: {size_e}")
                 return False, prev_image


        # --- Image comparison logic (should work for both modes now) ---
        if current_image_np is None: # Double check if capture/crop failed
             logger.error("  图像捕获/裁剪后 current_image_np 仍然为 None。")
             return False, prev_image

        # Convert current image to grayscale
        gray_current = cv2.cvtColor(current_image_np, cv2.COLOR_BGR2GRAY)

        if prev_image is None:
            logger.info("  首次检测，存储当前图像作为基准。")
            return False, gray_current # No motion on first check, return current gray image

        # Compare with previous image
        logger.debug("  与上一帧图像进行比较...")
        # 工具 修复：处理图像尺寸不匹配问题
        if prev_image.shape != gray_current.shape:
             logger.warning(f"  图像尺寸不匹配！ 前一帧: {prev_image.shape}, 当前帧: {gray_current.shape}")

             # 尝试调整当前图像尺寸以匹配基准图像
             try:
                 target_height, target_width = prev_image.shape[:2]
                 gray_current_resized = cv2.resize(gray_current, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                 logger.info(f"  已将当前图像调整为基准尺寸: {gray_current_resized.shape}")
                 gray_current = gray_current_resized
             except Exception as e:
                 logger.error(f"  调整图像尺寸失败: {e}，重新存储基准")
                 return False, gray_current # 重新存储基准图像

        diff = cv2.absdiff(prev_image, gray_current)
        _, thresholded_diff = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)
        changed_pixels = cv2.countNonZero(thresholded_diff)

        # 工具 修复：增强像素变化检测的调试信息
        total_pixels = gray_current.shape[0] * gray_current.shape[1]
        change_percentage = (changed_pixels / total_pixels) * 100 if total_pixels > 0 else 0

        logger.info(f"  像素变化统计: {changed_pixels}/{total_pixels} ({change_percentage:.2f}%)")
        logger.info(f"  检测参数: 像素差异阈值={diff_threshold}, 运动阈值={motion_threshold}")

        # 如果变化像素为0，提供额外的调试信息
        if changed_pixels == 0:
            logger.debug(f"  未检测到像素变化，可能原因:")
            logger.debug(f"    1. 图像完全相同")
            logger.debug(f"    2. 像素差异阈值({diff_threshold})过高")
            logger.debug(f"    3. 图像捕获问题")

            # 计算实际的最大像素差异
            max_diff = np.max(diff) if diff.size > 0 else 0
            mean_diff = np.mean(diff) if diff.size > 0 else 0
            logger.debug(f"    实际像素差异: 最大={max_diff}, 平均={mean_diff:.2f}")

        motion_detected = changed_pixels >= motion_threshold
        logger.info(f"  移动检测结果: {'检测到移动' if motion_detected else '未检测到移动'}")
        return motion_detected, gray_current # Return detection result and current gray image

    except Exception as e:
        logger.exception(f"移动检测过程中发生错误: {e}")
        return False, prev_image # Return failure and keep previous image on error
# -------------------------------------------------

# ==================================
#  Task Execution Logic
# ==================================

# --- ADDED: Module-level cache for previous motion images ---
prev_motion_image_cache: Dict[int, Optional[np.ndarray]] = {}
# -----------------------------------------------------------

def execute(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int], card_id: Optional[int], get_image_data=None, stop_checker=None) -> tuple[bool, str, Optional[int]]:
    """评估条件 (图像, 计数器判断->自身执行次数, 移动检测)，并返回指示成功 ('continue') 或失败 ('fail_continue') 的动作。"""
    condition_type = params.get('condition_type', '查找图片')
    # Get current card ID passed by executor
    current_card_id = card_id # Use the passed ID
    if current_card_id is None:
         # Should not happen if executor passes it
         logger.warning("execute 函数未收到有效的 card_id，计数器判断将无法工作。")
         # Log warning instead of error if None is passed somehow
    # --------------------------------------------------

    # Increment and get execution count for this specific card
    current_exec_count = 0
    if current_card_id is not None:
        exec_count_key = f"__card_exec_count_{current_card_id}"
        old_count = counters.get(exec_count_key, 0)
        current_exec_count = old_count + 1
        counters[exec_count_key] = current_exec_count # Update counter

    logger.info(f"评估条件控制: 类型='{condition_type}'")

    # Get post-execution parameters
    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id_str = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id_str = params.get('failure_jump_target_id')

    condition_met = False # Default to condition not met
    actual_confidence_score = None # ADDED: Variable to store actual score for image check
    try:
        if condition_type == '查找图片':
            if not PYAUTOGUI_AVAILABLE:
                raise RuntimeError("查找图片条件需要 'pyautogui' 库。")
            if not CV2_AVAILABLE:
                 raise RuntimeError("图像预处理需要 'opencv-python' 库。")

            # 检查是否为多图识别模式
            multi_image_mode = params.get('multi_image_mode', '单图识别')

            if multi_image_mode == '多图识别':
                condition_met, actual_confidence_score = _evaluate_multi_image_condition(params, execution_mode, target_hwnd, get_image_data)
            else:
                # 单图识别模式（原有逻辑）
                # --- MODIFIED: Use absolute_image_path directly from params ---
                absolute_image_path = params.get('image_path') # Executor should provide absolute path or None

                if absolute_image_path is None:
                    # Path resolution failed in executor, treat as condition not met
                    logger.error(f"评估条件 '{condition_type}' 失败: 图片路径无效或解析失败。")
                    condition_met = False # Explicitly set condition to false
                elif not isinstance(absolute_image_path, str):
                    # Handle cases where it might be something else unexpected
                    logger.error(f"评估条件 '{condition_type}' 失败: 图片路径参数类型错误 (应为 str 或 None)。")
                    condition_met = False
                else:
                    # --- MODIFIED: Call evaluation func and store score ---
                    condition_met, actual_confidence_score = _evaluate_image_condition(params, execution_mode, target_hwnd, get_image_data)
                    # --- END MODIFICATION ---

        elif condition_type == '计数器判断':
            # --- NEW Logic: Check THIS card's execution count ---
            target_count = params.get('target_execution_count', 1) # Get the target count param
            comparison_op_str = params.get('counter_comparison', '>=') # Get comparison operator string
            comparison_op = COMPARISON_OPERATORS.get(comparison_op_str) # Get the actual operator function

            if current_card_id is None:
                 logger.error("计数器判断失败，因为无法获取当前卡片ID。")
                 condition_met = False # Fail explicitly if ID is missing
            elif comparison_op is None:
                 logger.error(f"计数器判断失败：未知的比较运算符 '{comparison_op_str}'。")
                 condition_met = False
            else:
                condition_met = comparison_op(current_exec_count, target_count) # Perform comparison

                # 注意：计数器重置逻辑移到了返回结果的地方，避免变量作用域问题

        elif condition_type == '移动检测':
            # --- Use the global cache ---
            global prev_motion_image_cache

            if current_card_id is None:
                 logger.error("移动检测失败，因为无法获取当前卡片ID。")
                 condition_met = False
            else:
                 # --- Get previous image for this card ID ---
                 prev_image = prev_motion_image_cache.get(current_card_id)

                 # --- Call the updated _check_motion function ---
                 interval = params.get('check_interval', 0.5)
                 # Log moved inside _check_motion
                 # logger.info(f"开始移动检测: 区域=(屏幕 {params.get('minimap_x')},{params.get('minimap_y')}), 间隔={interval}s, 阈值={params.get('motion_threshold')}像素")
                 logger.debug(f"等待间隔: {interval}s")

                 # 可中断的等待
                 elapsed_time = 0.0
                 check_interval = 0.1  # 每100ms检查一次停止信号

                 while elapsed_time < interval:
                     if stop_checker and stop_checker():
                         logger.info("移动检测等待被用户中断")
                         return False, '停止工作流', None

                     sleep_time = min(check_interval, interval - elapsed_time)
                     time.sleep(sleep_time)
                     elapsed_time += sleep_time
                 condition_met, current_gray_image = _check_motion(params, execution_mode, target_hwnd, prev_image)
                 # ---------------------------------------------

                 # --- Store the current image for the next check ---
                 if current_gray_image is not None:
                      prev_motion_image_cache[current_card_id] = current_gray_image
                      logger.debug(f"已更新卡片 {current_card_id} 的移动检测缓存。")
                 else:
                      # If capture failed, remove the old image to force recapture next time
                      if current_card_id in prev_motion_image_cache:
                          del prev_motion_image_cache[current_card_id]
                          logger.debug(f"截图失败，已清除卡片 {current_card_id} 的移动检测缓存。")
                 # -----------------------------------------------

            # Logging moved inside _check_motion
            # if condition_met:
            #      logger.info("条件满足：检测到显著移动。")
            # else:
            #      logger.info("条件不满足：未检测到显著移动。")
                 
        else:
             # This case might still be reachable if params are manually edited or corrupted
             raise ValueError(f"未知的条件类型: '{condition_type}'")

        # --- ADDED: Store confidence after evaluation --- 
        if condition_type == '查找图片' and current_card_id is not None:
             required_conf = params.get('confidence', 0.6) # Get required confidence again
             counters[f"__required_confidence_{current_card_id}"] = required_conf
             counters[f"__actual_confidence_{current_card_id}"] = actual_confidence_score
             logger.debug(f"存储卡片 {current_card_id} 条件置信度: 要求={required_conf}, 实际={actual_confidence_score}")
        # --- END ADDED --- 

        # --- Parse jump targets ---
        success_jump_id = None
        if on_success_action == '跳转到步骤' and success_jump_id_str is not None:
            try:
                success_jump_id = int(success_jump_id_str)
            except (ValueError, TypeError):
                logger.error(f"错误 无效的成功跳转目标ID '{success_jump_id_str}'")
        elif on_success_action == '跳转到步骤':
            logger.error(f"错误 跳转操作但跳转目标ID为空: success_jump_id_str={success_jump_id_str}")
        
        failure_jump_id = None
        if on_failure_action == '跳转到步骤' and failure_jump_id_str is not None:
            try: failure_jump_id = int(failure_jump_id_str)
            except (ValueError, TypeError): logger.error(f"无效的失败跳转目标ID '{failure_jump_id_str}'")

        # --- Return based on condition and actions ---
        if condition_met:
            logger.info("条件满足，执行成功操作。")

            # 工具 修复：计数器判断条件满足后，根据成功操作决定是否重置计数器
            if condition_type == '计数器判断' and current_card_id is not None:
                exec_count_key = f"__card_exec_count_{current_card_id}"

                # 只有在"继续执行本步骤"时不重置计数器，其他情况都重置
                if on_success_action != '继续执行本步骤':
                    # 跳转到步骤、停止工作流、执行下一步 都重置计数器
                    counters[exec_count_key] = 0

            if on_success_action == '跳转到步骤' and success_jump_id is not None:
                # --- ADD DEBUG LOG ---
                result_tuple = (True, '跳转到步骤', success_jump_id)
                logger.debug(f"[COND_CTRL Return Debug] Condition Met, Jump: Returning {result_tuple}")
                # ---------------------
                return result_tuple # Ensure jump ID is returned
            elif on_success_action == '停止工作流':
                # --- ADD DEBUG LOG ---
                result_tuple = (True, '停止工作流', None)
                logger.debug(f"[COND_CTRL Return Debug] Condition Met, Stop: Returning {result_tuple}")
                # ---------------------
                return result_tuple
            elif on_success_action == '继续执行本步骤':
                # --- ADD DEBUG LOG ---
                result_tuple = (True, '继续执行本步骤', card_id)
                logger.debug(f"[COND_CTRL Return Debug] Condition Met, Execute This Step: Returning {result_tuple}")
                # ---------------------
                return result_tuple
            else: # 执行下一步
                # --- ADD DEBUG LOG ---
                result_tuple = (True, '执行下一步', None)
                logger.debug(f"[COND_CTRL Return Debug] Condition Met, Next Step: Returning {result_tuple}")
                # ---------------------
                return result_tuple
        else:
            logger.info("条件不满足，执行失败操作。")
            if on_failure_action == '跳转到步骤' and failure_jump_id is not None:
                # --- ADD DEBUG LOG ---
                result_tuple = (False, '跳转到步骤', failure_jump_id)
                logger.debug(f"[COND_CTRL Return Debug] Condition Failed, Jump: Returning {result_tuple}")
                # ---------------------
                return result_tuple # Ensure jump ID is returned
            elif on_failure_action == '停止工作流':
                # --- ADD DEBUG LOG ---
                result_tuple = (False, '停止工作流', None)
                logger.debug(f"[COND_CTRL Return Debug] Condition Failed, Stop: Returning {result_tuple}")
                # ---------------------
                return result_tuple
            elif on_failure_action == '继续执行本步骤':
                # --- ADD DEBUG LOG ---
                result_tuple = (False, '继续执行本步骤', card_id)
                logger.debug(f"[COND_CTRL Return Debug] Condition Failed, Execute This Step: Returning {result_tuple}")
                # ---------------------
                return result_tuple
            else: # 执行下一步
                # --- ADD DEBUG LOG ---
                result_tuple = (False, '执行下一步', None)
                logger.debug(f"[COND_CTRL Return Debug] Condition Failed, Next Step: Returning {result_tuple}")
                # ---------------------
                return result_tuple

    except Exception as e:
        logger.exception(f"评估条件 '{condition_type}' 时发生错误: {e}")
        # Default to failure action on error
        failure_jump_id = None # Reset just in case
        on_failure_action = params.get('on_failure', '执行下一步') # Get failure action from params
        failure_jump_id_str = params.get('failure_jump_target_id') # Get failure jump ID str from params
        determined_action = '执行下一步' # Default action on error
        determined_jump_id = None

        if on_failure_action == '跳转到步骤' and failure_jump_id_str is not None:
            try: 
                failure_jump_id = int(failure_jump_id_str)
                determined_action = '跳转到步骤'
                determined_jump_id = failure_jump_id
            except (ValueError, TypeError): 
                logger.error(f"错误处理中：无效的失败跳转目标ID '{failure_jump_id_str}'，将执行下一步。")
                determined_action = '执行下一步' # Fallback if jump ID is invalid
                determined_jump_id = None
        elif on_failure_action == '停止工作流':
            determined_action = '停止工作流'
            determined_jump_id = None
        elif on_failure_action == '继续执行本步骤':
            determined_action = '继续执行本步骤'
            determined_jump_id = card_id
        # else: action remains '执行下一步'
        
        # --- ADD DEBUG LOG for exception case --- 
        result_tuple = (False, determined_action, determined_jump_id)
        logger.debug(f"[COND_CTRL Return Debug] Exception Fallback: Returning {result_tuple}")
        # -----------------------------------------
        return result_tuple

# Renamed from execute to execute_task for consistency with executor expectations
def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int], window_region=None, card_id: Optional[int] = None, **kwargs) -> tuple[bool, str, Optional[int]]:
    """主入口函数，调用内部的 execute logic"""
    logger.debug(f"条件控制 execute_task (card_id={card_id}) called with params: {params}, mode: {execution_mode}, hwnd: {target_hwnd}, region: {window_region}") # Log removed images_dir
    
    # 从 kwargs 中获取 get_image_data 函数
    get_image_data = kwargs.get('get_image_data', None)
    
    try:
        # --- REMOVED images_dir from execute call ---
        # The execute function handles the core logic and returns the jump ID now
        success, action, jump_target_id = execute(
            params=params,
            counters=counters,
            execution_mode=execution_mode,
            target_hwnd=target_hwnd,
            card_id=card_id, # Pass card_id through
            get_image_data=get_image_data, # Pass get_image_data through
            stop_checker=kwargs.get('stop_checker') # Pass stop_checker through
        )
        # ---------------------------------
        logger.debug(f"条件控制 execute_task (card_id={card_id}) returning: success={success}, action='{action}', jump={jump_target_id}")
        return success, action, jump_target_id
    except Exception as e:
        logger.exception(f"执行条件控制任务 (card_id={card_id}) 时发生未预料的错误: {e}")
        # Fallback to failure action
        on_failure_action = params.get('on_failure', '执行下一步')
        failure_jump_id_str = params.get('failure_jump_target_id') # Get failure jump ID str from params
        failure_jump_id = None
        if on_failure_action == '跳转到步骤' and failure_jump_id_str is not None:
            try: failure_jump_id = int(failure_jump_id_str)
            except (ValueError, TypeError): pass
            
        if on_failure_action == '跳转到步骤' and failure_jump_id is not None:
            return False, '跳转到步骤', failure_jump_id
        elif on_failure_action == '停止工作流': 
            return False, '停止工作流', None
        elif on_failure_action == '继续执行本步骤': 
            return False, '继续执行本步骤', card_id
        else: 
            return False, '执行下一步', None

# ==================================
#  Task Parameter Definition
# ==================================
def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """定义条件控制任务的参数"""
    return {
        "condition_type": {
            "label": "条件类型",
            "type": "select",
            "options": ["查找图片", "计数器判断", "移动检测"],
            "default": "查找图片",
            "tooltip": "选择用于决定工作流路径的条件类型。"
        },

        # 查找图片参数
        "---image_condition_params---": {
            "type": "separator",
            "label": "查找图片参数",
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        "multi_image_mode": {
            "label": "多图识别模式",
            "type": "select",
            "options": ["单图识别", "多图识别"],
            "default": "单图识别",
            "tooltip": "单图识别：只配置一张图片；多图识别：配置多张图片，任意一张识别成功即为条件满足",
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        "enable_parallel_recognition": {
            "label": "启用并行识别",
            "type": "checkbox",
            "default": True,
            "tooltip": "启用：多张图片并行识别，速度提升3-5倍；禁用：传统串行识别",
            "condition": [
                {"param": "condition_type", "value": "查找图片"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "image_path": {
            "label": "图片路径",
            "type": "file",
            "default": "",
            "tooltip": "要查找的图片文件路径 (相对于下方指定的基目录或默认 'images' 目录)。",
            "condition": [
                {"param": "condition_type", "value": "查找图片"},
                {"param": "multi_image_mode", "value": "单图识别"}
            ]
        },
        "image_paths": {
            "label": "多图片路径",
            "type": "text",
            "default": "",
            "tooltip": "多张图片路径，每行一个路径。只要识别成功其中一张图片，条件即为满足",
            "multiline": True,
            "condition": [
                {"param": "condition_type", "value": "查找图片"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        # --- ADDED: Optional Base Directory for Image Path ---
        # "image_path_base_dir": {
        #     "label": "指定基目录(选此目录中任意图片)",
        #     "type": "file",     # <<< MODIFIED: Use file selector type
        #     "required": False,   # Make it optional
        #     "default": "",       # Default to empty string
        #     "tooltip": "选择目标基目录中的任意一个图片文件，程序将自动使用该文件所在的文件夹作为基目录。如果留空，则使用默认 'images' 目录。",
        #     "condition": {"param": "condition_type", "value": "查找图片"}
        # },
        "confidence": {
            "label": "置信度",
            "type": "float",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "图片匹配的相似度阈值 (0.1 到 1.0)。",
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        "preprocessing_method": {
            "label": "预处理方法",
            "type": "select",
            "options": ["无", "灰度化", "透明图片处理"],
            "default": "无",
            "tooltip": "在查找图片前对其进行的预处理操作。透明图片处理适用于PNG透明图片，将透明区域混合到白色背景。",
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        # --- 重试机制参数 ---
        "enable_retry": {
            "label": "启用失败重试",
            "type": "bool",
            "default": False,
            "tooltip": "如果图片查找失败，是否进行重试。适用于动态图片识别。",
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        "retry_attempts": {
            "label": "最大重试次数",
            "type": "int",
            "default": 3,
            "min": 1,
            "tooltip": "启用重试时，图片查找失败后最多重试几次。",
            "condition": {"param": "enable_retry", "value": True}
        },
        "retry_interval": {
            "label": "重试间隔(秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.1,
            "decimals": 2,
            "tooltip": "每次重试之间的等待时间。",
            "condition": {"param": "enable_retry", "value": True}
        },

        # 计数器判断参数
        "---counter_condition_params---": {
            "type": "separator",
            "label": "计数器判断参数",
            "condition": {"param": "condition_type", "value": "计数器判断"}
        },
        "target_execution_count": {
            "label": "本步骤执行次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "当此卡片被执行达到该次数时，条件视为满足。",
            "condition": {"param": "condition_type", "value": "计数器判断"}
        },

        # 移动检测参数
        "---motion_detection_params---": {
            "type": "separator",
            "label": "移动检测参数",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "motion_region_selector": {
            "label": "区域获取工具",
            "type": "button",
            "button_text": "选择检测区域",
            "tooltip": "点击选择要监控移动的区域",
            "widget_hint": "motion_region_selector",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "motion_detection_region": {
            "label": "移动识别区域",
            "type": "text",
            "default": "X=1150, Y=40, 宽度=50, 高度=50",
            "tooltip": "当前设置的移动检测区域",
            "readonly": True,
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "minimap_x": {
            "label": "区域 X",
            "type": "hidden",
            "default": 1150,
            "tooltip": "要监控的区域左上角的 X 坐标。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "minimap_y": {
            "label": "区域 Y",
            "type": "hidden",
            "default": 40,
            "tooltip": "要监控的区域左上角的 Y 坐标。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "minimap_width": {
            "label": "区域宽度",
            "type": "hidden",
            "default": 50,
            "min": 1,
            "tooltip": "要监控的区域的宽度 (像素)。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "minimap_height": {
            "label": "区域高度",
            "type": "hidden",
            "default": 50,
            "min": 1,
            "tooltip": "要监控的区域的高度 (像素)。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "check_interval": {
            "label": "检查间隔(秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.05,
            "decimals": 2,
            "tooltip": "捕获两次截图进行比较的时间间隔。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "motion_threshold": {
            "label": "运动阈值(像素数)",
            "type": "int",
            "default": 50,
            "min": 1,
            "tooltip": "区域内有多少像素发生显著变化才算作移动。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        "pixel_diff_threshold": {
            "label": "像素差异阈值",
            "type": "int",
            "default": 15,
            "min": 1,
            "max": 255,
            "tooltip": "单个像素的灰度值变化超过此阈值才算作变化。降低此值可提高敏感度。",
            "condition": {"param": "condition_type", "value": "移动检测"}
        },
        # --- Post-Execution Actions --- 
         "---post_exec---": {"type": "separator", "label": "执行后操作"},
         "on_success": {"type": "select", "label": "条件满足时", "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], "default": "执行下一步", "tooltip": "当条件评估为真时执行的操作。"},
         "success_jump_target_id": {"type": "int", "label": "满足跳转目标 ID", "required": False,
                                    "widget_hint": "card_selector", # Specify combo box should use card IDs
                                    "condition": {"param": "on_success", "value": "跳转到步骤"}},
         "on_failure": {"type": "select", "label": "条件不满足时", "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], "default": "执行下一步", "tooltip": "当条件评估为假时执行的操作。'执行下一步' 将沿 'failure' 连接线执行。"},
         "failure_jump_target_id": {"type": "int", "label": "不满足跳转目标 ID", "required": False,
                                     "widget_hint": "card_selector", # Specify combo box should use card IDs
                                     "condition": {"param": "on_failure", "value": "跳转到步骤"}},
         # --- ADDED Comparison Operator ---
         "counter_comparison": {
             "label": "比较方式",
             "type": "select",
             "options": [">=", ">", "==", "<=", "<", "!="],
             "default": ">=",
             "tooltip": "如何比较当前执行次数与目标次数。",
             "condition": {"param": "condition_type", "value": "计数器判断"}
         }
    } 

# --- Evaluation Functions for Each Condition Type ---
# --- MODIFIED: Removed images_dir parameter, use absolute path from params ---
def _evaluate_image_condition(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int], get_image_data=None) -> Tuple[bool, Optional[float]]:
    """Checks if an image exists on screen (or in window).
       Returns a tuple: (condition_met, actual_match_score)
       actual_match_score will be None if matching could not be performed.
    """
    actual_score = None # Initialize actual score
    # --- ADDED: Input Validation ---
    if not CV2_AVAILABLE or not PYAUTOGUI_AVAILABLE:
        logger.error("图片条件检查失败：缺少必要的库 (opencv-python 或 pyautogui)。")
        return False, actual_score

    # --- MODIFIED: Use absolute_image_path directly ---
    absolute_image_path = params.get('image_path') # Executor provides absolute path or None
    confidence = params.get('confidence', 0.6) # Lowered default
    preprocessing_method = params.get('preprocessing_method', '无')
    threshold_value = params.get('threshold_value', 128)
    canny_threshold1 = params.get('canny_threshold1', 100)
    canny_threshold2 = params.get('canny_threshold2', 200)
    scale_factor = params.get('scale_factor', 2.0)

    # --- 新增：获取重试参数 ---
    enable_retry = params.get('enable_retry', False)
    max_attempts = params.get('retry_attempts', 3) if enable_retry else 1 # 如果不启用，只尝试1次
    retry_interval = params.get('retry_interval', 0.5)
    # -------------------------

    if absolute_image_path is None:
        logger.error("图片条件检查失败：图片路径无效或解析失败。")
        return False, actual_score
    if not isinstance(absolute_image_path, str):
        logger.error("图片条件检查失败：图片路径参数类型错误。")
        return False, actual_score
    # --- END MODIFICATION ---

    # 只显示图片名称，不显示路径前缀
    if absolute_image_path.startswith('memory://'):
        image_name = absolute_image_path.replace('memory://', '')
    else:
        image_name = os.path.basename(absolute_image_path)
    # 执行模式中文映射
    mode_names = {'foreground': '前台', 'background': '后台'}
    mode_name = mode_names.get(execution_mode, execution_mode)

    # 开始重试循环
    for attempt in range(1, max_attempts + 1):
        logger.info(f"[{mode_name}] 第 {attempt}/{max_attempts} 次尝试检查图片条件: '{image_name}' (置信度 >= {confidence})")

        try:
            # --- MODIFIED: Support both memory and file modes ---
            template = None

            if absolute_image_path.startswith('memory://'):
                # 纯内存模式：使用 get_image_data 获取图片数据
                if get_image_data is None:
                    # 只显示图片名称
                    image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                    logger.error(f"缺少 get_image_data 函数: '{image_name}'")
                    return False, actual_score

                try:
                    # 获取图片数据
                    image_data = get_image_data(absolute_image_path)
                    if not image_data:
                        image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                        logger.error(f"无法从内存获取图片数据: '{image_name}'")
                        return False, actual_score

                    # 使用 cv2.imdecode 从内存数据解码图片
                    image_array = np.frombuffer(image_data, dtype=np.uint8)
                    template = cv2.imdecode(image_array, cv2.IMREAD_UNCHANGED)
                    image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                    logger.debug(f"图片加载成功: '{image_name}'")

                except Exception as e:
                    image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                    logger.error(f"图片加载失败: '{image_name}', 错误: {e}")
                    return False, actual_score
            else:
                # 传统文件模式：使用 np.fromfile 读取文件（用于编辑器）
                try:
                    template = cv2.imdecode(np.fromfile(absolute_image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                    logger.debug(f"成功 从文件加载图片成功: '{image_name}'")
                except Exception as e:
                    image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                    logger.error(f"从文件加载图片失败: '{image_name}', 错误: {e}")
                    return False, actual_score

            # --------------------------------------------------
            if template is None:
                image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                logger.error(f"无法加载模板图片: '{image_name}'")
                return False, actual_score
            # --- ADDED: Ensure template is loaded ---
            if template is None:
                image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                logger.error(f"模板图片 '{image_name}' 加载失败。")
                return False, actual_score
            # --- ADDED: Convert template to Grayscale BEFORE preprocessing ---
            logger.debug("将模板转换为灰度图...")
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            # --------------------------------------------------------------

            # Preprocess the template using the new unified preprocessing
            try:
                import importlib
                preprocessing_module = importlib.import_module('utils.image_preprocessing')
                apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                processed_template = apply_preprocessing(template_gray, params)
                if processed_template is None:
                    # Fallback to old preprocessing method
                    processed_template = _preprocess_image(template_gray, preprocessing_method, threshold_value, canny_threshold1, canny_threshold2, scale_factor)
            except (ImportError, ModuleNotFoundError, AttributeError):
                # Fallback to old preprocessing method
                processed_template = _preprocess_image(template_gray, preprocessing_method, threshold_value, canny_threshold1, canny_threshold2, scale_factor)

            if processed_template is None:
                image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                logger.error(f"模板图片预处理失败: '{image_name}'")
                break # Exit retry loop if preprocessing fails
            template_h, template_w = processed_template.shape[:2]

            # --- 工具 统一使用后台识别方法 ---
            # 不再区分前台后台模式，统一使用后台识别方法以提高稳定性和准确性
            screenshot_bgr = None # Added for clarity
            capture_error = False

            logger.debug("统一使用后台识别方法进行图片条件检查")
            if not PYWIN32_AVAILABLE or not target_hwnd:
                logger.error("统一后台图片识别失败：缺少 pywin32 或窗口句柄。")
                return False, actual_score # Return False on missing dependencies/hwnd
            try:
                screenshot_bgr = capture_window_background(target_hwnd)
                if screenshot_bgr is None:
                     logger.error("统一后台截图失败 (capture_window_background 返回 None)。")
                     capture_error = True
            except Exception as e_bg:
                logger.error(f"统一后台截图时出错: {e_bg}")
                capture_error = True

            if capture_error or screenshot_bgr is None:
                logger.info(f"[{mode_name}] 第 {attempt} 次尝试截图失败，无法进行图片条件检查。")
                if attempt < max_attempts:
                    logger.debug(f"等待 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                    continue # Continue to next attempt
                else:
                    return False, actual_score # Return False if all attempts failed

            # --- ADDED: Convert screenshot to Grayscale BEFORE preprocessing ---
            logger.debug("将截图转换为灰度图...")
            screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
            # -----------------------------------------------------------------

            # Preprocess the screenshot using the new unified preprocessing
            try:
                import importlib
                preprocessing_module = importlib.import_module('utils.image_preprocessing')
                apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                processed_screenshot = apply_preprocessing(screenshot_gray, params)
                if processed_screenshot is None:
                    # Fallback to old preprocessing method
                    processed_screenshot = _preprocess_image(screenshot_gray, preprocessing_method, threshold_value, canny_threshold1, canny_threshold2, scale_factor)
            except (ImportError, ModuleNotFoundError, AttributeError):
                # Fallback to old preprocessing method
                processed_screenshot = _preprocess_image(screenshot_gray, preprocessing_method, threshold_value, canny_threshold1, canny_threshold2, scale_factor)

            if processed_screenshot is None:
                logger.info(f"[{mode_name}] 第 {attempt} 次尝试截图预处理失败。")
                if attempt < max_attempts:
                    logger.debug(f"等待 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                    continue # Continue to next attempt
                else:
                    return False, actual_score

            # Ensure screenshot is large enough
            screenshot_h, screenshot_w = processed_screenshot.shape[:2]
            if screenshot_h < template_h or screenshot_w < template_w:
                 logger.error(f"截图尺寸 ({screenshot_w}x{screenshot_h}) 小于模板尺寸 ({template_w}x{template_h})。")
                 return False, actual_score

            # Perform template matching
            match_method = cv2.TM_CCOEFF_NORMED
            result = cv2.matchTemplate(processed_screenshot, processed_template, match_method)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            actual_score = float(max_val) # Store the actual score as float

            logger.info(f"  图片匹配结果: 最高置信度 = {actual_score:.4f}")

            condition_met = actual_score >= confidence
            # 只显示图片名称，不显示路径前缀
            if absolute_image_path:
                if absolute_image_path.startswith('memory://'):
                    image_name = absolute_image_path.replace('memory://', '')
                else:
                    image_name = os.path.basename(absolute_image_path)
            else:
                image_name = '未知图片'

            if condition_met:
                logger.info(f"[{mode_name}] 第 {attempt} 次尝试成功: {image_name} (置信度 {actual_score:.4f} ≥ {confidence}) ✓")
                return condition_met, actual_score # Return success immediately
            else:
                logger.info(f"[{mode_name}] 第 {attempt} 次尝试未找到: {image_name} (置信度 {actual_score:.4f} < {confidence}) ✗")

        except Exception as e:
            logger.error(f"[{mode_name}] 第 {attempt} 次尝试检查图片条件时发生错误: {e}")

        # If not found and more attempts remain, wait
        if attempt < max_attempts:
            logger.debug(f"等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)

    # --- End Retry Loop ---
    # If we reach here, all attempts failed
    logger.info(f"[{mode_name}] 所有 {max_attempts} 次尝试均失败，图片条件检查失败")
    return False, actual_score

def _evaluate_counter_condition(params: Dict[str, Any], counters: Dict[str, int], card_id: Optional[int]) -> bool:
    """Checks if the card has been executed a specific number of times."""
    target_count = params.get('target_execution_count', 1)
    comparison_op_str = params.get('counter_comparison', '>=')
    comparison_op = COMPARISON_OPERATORS.get(comparison_op_str)

    if card_id is None:
        logger.error("计数器条件检查失败：缺少卡片 ID。")
        return False
    if comparison_op is None:
        logger.error(f"计数器条件检查失败：未知的比较运算符 '{comparison_op_str}'。")
        return False

    # --- ADDED: Calculate current_exec_count here ---
    # Note: This check only looks at the *current* count. The increment happens in the execute function.
    exec_count_key = f"__card_exec_count_{card_id}"
    # Use .get() with default 0, no need to increment here, just compare
    # The execute function handles the incrementing before calling this (if called from there)
    # Or the executor handles incrementing if this is called directly (less likely now)
    current_exec_count = counters.get(exec_count_key, 0)
    # -----------------------------------------------

    try:
        condition_met = comparison_op(current_exec_count, target_count)
        return condition_met
    except TypeError as e:
        # Handle potential type errors if counts are not integers
        logger.error(f"比较执行次数时出错: {e} (当前: {current_exec_count}, 目标: {target_count})")
        return False
    except Exception as e:
        logger.exception(f"评估计数器条件时发生意外错误: {e}")
        return False


def _evaluate_multi_image_condition(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int], get_image_data=None) -> Tuple[bool, Optional[float]]:
    """评估多图片条件：只要识别成功其中一张图片，条件即为满足

    Returns:
        Tuple[bool, Optional[float]]: (条件是否满足, 最高置信度分数)
    """
    actual_score = None

    # 检查是否启用并行识别
    enable_parallel = params.get('enable_parallel_recognition', True)

    if enable_parallel:
        try:
            # 使用并行识别进行条件评估
            return _evaluate_multi_image_condition_parallel(params, execution_mode, target_hwnd)
        except ImportError as e:
            logger.warning(f"[多图条件] 并行识别模块不可用，回退到传统模式: {e}")
        except Exception as e:
            logger.error(f"[多图条件] 并行识别执行失败，回退到传统模式: {e}")

    # 传统串行识别模式（原有逻辑）
    logger.info("[多图条件] 使用传统串行识别模式")

    # 获取图片路径列表
    image_paths_text = params.get('image_paths', '').strip()
    if not image_paths_text:
        logger.error("多图识别模式下未配置图片路径")
        return False, actual_score

    # 添加详细的调试日志
    logger.debug(f"[多图路径调试] 原始文本长度: {len(image_paths_text)}")
    logger.debug(f"[多图路径调试] 原始文本repr: {repr(image_paths_text)}")

    # 解析图片路径列表
    split_paths = image_paths_text.split('\n')
    logger.debug(f"[多图路径调试] 分割后路径数: {len(split_paths)}")
    logger.debug(f"[多图路径调试] 分割结果: {split_paths}")

    # 过滤空路径、注释行和不可见字符路径
    def is_valid_path(path):
        """检查路径是否有效（不是空路径、注释行或仅包含不可见字符）"""
        if not path:
            return False
        stripped = path.strip()
        if not stripped:
            return False

        # 过滤注释行（以#开头的行）
        if stripped.startswith('#'):
            return False

        # 检查是否仅包含不可见字符（Unicode控制字符、零宽字符等）
        # 移除常见的不可见字符
        cleaned = stripped.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
        return bool(cleaned.strip())

    raw_image_paths = [path.strip() for path in split_paths if is_valid_path(path)]
    logger.debug(f"[多图路径调试] 过滤后路径数: {len(raw_image_paths)}")
    logger.debug(f"[多图路径调试] 过滤结果: {raw_image_paths}")

    # 额外检查：显示被过滤掉的路径
    filtered_out = [path for path in split_paths if not is_valid_path(path)]
    if filtered_out:
        logger.debug(f"[多图路径调试] 被过滤的路径: {filtered_out}")
        for i, path in enumerate(filtered_out):
            logger.debug(f"[多图路径调试] 被过滤路径{i+1}: repr={repr(path)}, len={len(path)}")

    if not raw_image_paths:
        logger.error("多图识别模式下图片路径列表为空")
        return False, actual_score

    # 智能纠正图片路径
    image_paths = _correct_image_paths_for_condition(raw_image_paths)
    logger.debug(f"[多图路径调试] 纠正后路径数: {len(image_paths)}")
    logger.debug(f"[多图路径调试] 纠正结果: {image_paths}")

    if not image_paths:
        logger.error("多图识别模式下所有图片路径都无效")
        return False, actual_score

    logger.info(f"[多图条件] 开始评估，共{len(image_paths)}张图片")

    # 记录所有图片的识别结果
    found_images = []
    max_confidence = 0.0

    for i, image_path in enumerate(image_paths):
        # 构建单个图片的参数
        single_image_params = params.copy()
        single_image_params['image_path'] = image_path

        # 显示图片名称
        if image_path.startswith('memory://'):
            image_name = image_path.replace('memory://', '')
        else:
            image_name = os.path.basename(image_path) if image_path else f'图片{i+1}'

        logger.info(f"[多图条件] 评估第{i+1}张图片: {image_name}")

        # 评估单张图片
        try:
            condition_met, confidence_score = _evaluate_image_condition(single_image_params, execution_mode, target_hwnd, get_image_data)

            if condition_met:
                logger.info(f"[多图条件] 第{i+1}张图片识别成功: {image_name} (置信度: {confidence_score:.4f})")
                found_images.append(image_path)
                if confidence_score and confidence_score > max_confidence:
                    max_confidence = confidence_score
                    actual_score = confidence_score
            else:
                logger.info(f"[多图条件] 第{i+1}张图片识别失败: {image_name}")

        except Exception as e:
            logger.error(f"评估第{i+1}张图片时发生错误: {e}")
            continue

    # 处理结果
    if found_images:
        logger.info(f"[多图条件] 识别成功{len(found_images)}张图片，条件满足 (最高置信度: {max_confidence:.4f})")
        return True, actual_score
    else:
        logger.info(f"[多图条件] 所有{len(image_paths)}张图片都识别失败，条件不满足")
        return False, actual_score


def _correct_image_paths_for_condition(raw_paths: List[str]) -> List[str]:
    """智能纠正条件控制的图片路径列表

    Args:
        raw_paths: 原始路径列表

    Returns:
        纠正后的有效路径列表
    """
    import os

    corrected_paths = []
    images_dir = "images"  # 默认图片目录

    logger.info(f"[条件路径纠正] 开始纠正{len(raw_paths)}个图片路径")
    logger.debug(f"[条件路径纠正] 输入路径列表: {raw_paths}")

    for i, raw_path in enumerate(raw_paths, 1):
        corrected_path = None

        # 跳过空路径
        if not raw_path or not raw_path.strip():
            logger.info(f"  {i}. 空路径 - 跳过")
            continue

        # 显示原始路径（仅文件名）
        if raw_path.startswith('memory://'):
            display_name = raw_path.replace('memory://', '')
        else:
            display_name = os.path.basename(raw_path) if raw_path else f'路径{i}'

        try:
            # 1. 检查原始路径是否有效
            if raw_path.startswith('memory://'):
                # 内存图片路径，直接使用
                corrected_path = raw_path
                logger.info(f"  {i}. {display_name} - 内存图片，直接使用")

            elif os.path.isabs(raw_path):
                # 绝对路径处理
                if os.path.exists(raw_path):
                    corrected_path = raw_path
                    logger.info(f"  {i}. {display_name} - 绝对路径有效")
                else:
                    # 尝试转换为相对路径
                    filename = os.path.basename(raw_path)
                    relative_path = os.path.join(images_dir, filename)

                    if os.path.exists(relative_path):
                        corrected_path = relative_path
                        logger.info(f"  {i}. {display_name} - 绝对路径无效，已纠正为相对路径: {relative_path}")
                    else:
                        logger.warning(f"  {i}. {display_name} - 绝对路径无效，相对路径也不存在")

            else:
                # 相对路径处理
                if os.path.exists(raw_path):
                    corrected_path = raw_path
                    logger.info(f"  {i}. {display_name} - 相对路径有效")
                else:
                    # 尝试在images目录中查找
                    filename = os.path.basename(raw_path)
                    images_path = os.path.join(images_dir, filename)

                    if os.path.exists(images_path):
                        corrected_path = images_path
                        logger.info(f"  {i}. {display_name} - 在images目录找到: {images_path}")
                    else:
                        # 尝试直接使用文件名
                        if os.path.exists(filename):
                            corrected_path = filename
                            logger.info(f"  {i}. {display_name} - 在当前目录找到: {filename}")
                        else:
                            logger.warning(f"  {i}. {display_name} - 路径无效，未找到文件")

            # 添加有效路径
            if corrected_path:
                corrected_paths.append(corrected_path)

        except Exception as e:
            logger.error(f"  {i}. {display_name} - 路径纠正时发生错误: {e}")

    logger.info(f"[条件路径纠正] 完成，有效路径: {len(corrected_paths)}/{len(raw_paths)}")

    return corrected_paths


# --- Test Block ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("开始 ConditionalControlTask 模块测试...")

    # --- 测试 capture_window_background (如果该任务用到) --- 
    # !!! 重要：修改为你想要测试的窗口标题 或 部分标题 !!!
    test_target_title_part = "剑网3无界" # 使用部分标题查找
    test_hwnd = None
    
    # --- BEGIN: Add project root to sys.path (if needed for direct run) ---
    # import os
    # import sys
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root = os.path.dirname(current_dir)
    # if project_root not in sys.path:
    #     sys.path.insert(0, project_root)
    #     print(f"Added project root: {project_root}")
    # # Re-import if necessary after path change
    # try:
    #     from utils.win32_utils import capture_window_background 
    # except ImportError:
    #      logger.error("Failed to import utils after path mod.")
    #      capture_window_background = None
    # --- END --- 

    # Ensure necessary imports are available
    try:
        import cv2
        import numpy as np
        import os
        from utils.win32_utils import capture_window_background 
        # Check pywin32 availability (assuming defined at module level)
        if PYWIN32_AVAILABLE:
            try:
                # --- MODIFIED: Find window by partial title --- 
                logger.info(f"尝试通过部分标题 '{test_target_title_part}' 查找窗口...")
                top_windows = []
                def enum_window_callback(hwnd, param):
                    param.append(hwnd)
                    return True
                win32gui.EnumWindows(enum_window_callback, top_windows)
                found_title = ""
                for hwnd_item in top_windows:
                    window_title = win32gui.GetWindowText(hwnd_item)
                    if test_target_title_part in window_title:
                        test_hwnd = hwnd_item
                        found_title = window_title
                        logger.info(f"找到匹配窗口: '{found_title}'，HWND: {test_hwnd}")
                        break # Use the first match
                # --- END MODIFICATION ---

                if test_hwnd:
                    # 1. 执行后台截图
                    logger.info("尝试使用 capture_window_background 进行后台截图...")
                    screenshot = capture_window_background(test_hwnd)
                    
                    # 2. 检查截图结果（调试保存已禁用）
                    if screenshot is not None and isinstance(screenshot, np.ndarray):
                        logger.info(f"后台截图成功，截图尺寸: {screenshot.shape}")
                        # 调试截图保存已禁用（减少打包大小）
                        # save_path = "_test_conditional_control_screenshot.png"
                        # cv2.imwrite(save_path, screenshot)
                    else:
                        logger.error("后台截图失败或返回无效结果。")
                        
                else:
                    logger.error(f"找不到标题包含 '{test_target_title_part}' 的窗口。")
            except Exception as e:
                logger.error(f"查找窗口或执行截图时发生错误: {e}", exc_info=True)
        else:
            logger.error("pywin32 库未安装，无法执行后台截图测试。")
    except ImportError as imp_err:
        logger.error(f"测试后台截图所需库导入失败: {imp_err}. 请确保已安装 OpenCV (cv2), NumPy, pywin32.")

    logger.info("ConditionalControlTask 模块测试结束。")

def _evaluate_multi_image_condition_parallel(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int]) -> Tuple[bool, Optional[float]]:
    """使用并行识别评估多图片条件"""
    try:
        from tasks.parallel_image_recognition import get_parallel_recognizer, RecognitionMode

        # 获取图片路径列表
        image_paths_text = params.get('image_paths', '').strip()
        if not image_paths_text:
            logger.error("多图识别模式下未配置图片路径")
            return False, None

        # 解析图片路径
        raw_image_paths = [path.strip() for path in image_paths_text.split('\n') if path.strip()]
        if not raw_image_paths:
            logger.error("多图识别模式下图片路径列表为空")
            return False, None

        # 智能纠正图片路径
        image_paths = _correct_image_paths_for_condition(raw_image_paths)
        if not image_paths:
            logger.error("多图识别模式下所有图片路径都无效")
            return False, None

        logger.info(f"[并行多图条件] 开始评估，共{len(image_paths)}张图片")

        # 执行并行识别
        recognizer = get_parallel_recognizer()
        results = recognizer.recognize_images_parallel(
            image_paths=image_paths,
            params=params,
            execution_mode=execution_mode,
            target_hwnd=target_hwnd,
            mode=RecognitionMode.FIRST_MATCH  # 条件评估只需要找到第一张
        )

        # 分析结果
        successful_results = [r for r in results if r.success]

        if successful_results:
            # 找到最高置信度
            max_confidence = max(r.confidence for r in successful_results)
            best_result = max(successful_results, key=lambda r: r.confidence)

            logger.info(f"[并行多图条件] 条件满足: {best_result.image_name}, 置信度={max_confidence:.4f}")
            return True, max_confidence
        else:
            logger.info(f"[并行多图条件] 条件不满足: 所有{len(image_paths)}张图片都未识别成功")
            return False, None

    except Exception as e:
        logger.error(f"并行多图条件评估失败: {e}")
        raise  # 重新抛出异常，让调用方回退到传统模式