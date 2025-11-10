# 查找图片并点击任务模块
import time
# Import Optional and Tuple for older Python versions
from typing import Dict, Any, Optional, Tuple
import cv2 # Import OpenCV
import numpy as np # Import NumPy
import os # Import os for path check
import traceback # Import traceback for printing exception details

# 导入通用坐标系统
from utils.universal_coordinate_system import (
    get_universal_coordinate_system, create_coordinate_from_image_recognition,
    CoordinateType, ClickMode
)
# Import necessary modules for background execution (requires pywin32)
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

try:
    from utils.interception_driver import get_driver
    driver = get_driver()
    INTERCEPTION_AVAILABLE = True
except ImportError:
    INTERCEPTION_AVAILABLE = False

# 使用专门的截图助手
from utils.screenshot_helper import take_screenshot_opencv, is_screenshot_available
    # Print warning only if execution mode requires it later
    # print("警告: pywin32 模块未安装，后台模式将不可用。请运行 'pip install pywin32'")

# Import background utility functions
try:
    # 优先尝试从根目录的utils导入（完整版本）
    from utils.win32_utils import capture_window_background, click_background
except ImportError:
    try:
        # 尝试从utils目录导入
        from utils.win32_utils import capture_window_background, click_background
    except ImportError:
        # 回退到动态导入
        try:
            import importlib
            win32_utils_module = importlib.import_module('utils.win32_utils')
            capture_window_background = getattr(win32_utils_module, 'capture_window_background', None)
            click_background = getattr(win32_utils_module, 'click_background', None)
        except (ImportError, ModuleNotFoundError):
            # 暂时不记录日志，logger还未初始化
            capture_window_background = None
            click_background = None

import logging # <-- ADDED logging import
import random # <-- 添加导入

# 初始化logger
logger = logging.getLogger(__name__)

# 检查后台模式功能是否可用
if capture_window_background is None or click_background is None:
    logger.warning("无法导入 capture_window_background 和 click_background，后台模式可能不可用")

# 高级图像处理功能已移除

# import os # Import os for path normalization - Removed

TASK_NAME = "查找图片并点击"

# Define activation helper function (or assume it's imported from utils)
def _activate_window_foreground(target_hwnd: Optional[int], logger):
    # 工具 修复：简化窗口激活逻辑
    import os
    is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'

    if is_multi_window_mode:
        logger.debug(f"靶心 多窗口模式：跳过窗口激活，窗口 {target_hwnd}")
        return True  # 在多窗口模式下，不激活窗口但返回成功

    # ... (Activation logic as defined above) ...
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

# 任务类型标识
TASK_TYPE = "查找图片并点击" # Get logger instance

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """Returns the parameter definitions for the Find Image and Click task."""
    from .task_utils import get_standard_next_step_delay_params, get_standard_action_params, merge_params_definitions

    # 原有的图像识别点击参数
    image_click_params = {
        # Pre-condition parameters removed as the core task logic handles image finding
        # --- Task Specific Parameters ---
        "---task_params---": {"type": "separator", "label": "主要任务参数"},
        # "window_title": {"label": "目标窗口标题 (可选)", "type": "text", "default": None, "description": "如果指定，将在该标题的窗口内查找图片。留空则全屏查找。"}, # Removed, now global
        "image_path": {"label": "目标图片路径", "type": "file", "required": True, "description": "需要查找并点击的图片文件。"},
        "confidence": {
            "label": "查找置信度",
            "type": "float",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "图片匹配的相似度阈值 (0.1 到 1.0)。"
        },
        "preprocessing_method": {
            "label": "预处理方法",
            "type": "select",
            "options": ["无", "灰度化", "透明图片处理"],
            "default": "无",
            "tooltip": "在查找图片前对其进行的预处理操作。透明图片处理适用于PNG透明图片，将透明区域混合到白色背景。"
        },
        "button": {"label": "鼠标按钮", "type": "select", "options": ["左键", "右键", "中键"], "default": "左键"},
        "clicks": {"label": "点击次数", "type": "int", "default": 1, "min": 1},
        "interval": {"label": "点击间隔(秒)", "type": "float", "default": 0.1, "min": 0.0, "decimals": 2},

        # X and Y are removed as they are determined by the image location

        # --- Retry Mechanism ---
        "---retry---": {"type": "separator", "label": "失败重试设置"},
        "enable_retry": {
            "label": "启用失败重试",
            "type": "bool",
            "default": False,
            "tooltip": "如果查找失败，是否进行重试。"
        },
        "retry_attempts": {
            "label": "最大重试次数",
            "type": "int",
            "default": 3,
            "min": 1,
            "tooltip": "启用重试时，查找失败后最多重试几次。",
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

        # --- Post-Execution Actions ---
        "---post_exec---": {"type": "separator", "label": "执行后操作"},
        # Labels updated to reflect overall task success/failure
        "on_success": {"type": "select", "label": "执行成功时", "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], "default": "执行下一步"},
        "success_jump_target_id": {"type": "int", "label": "成功跳转目标 ID", "required": False,
                                    "widget_hint": "card_selector",
                                    "condition": {"param": "on_success", "value": "跳转到步骤"}},
        "on_failure": {"type": "select", "label": "执行失败时", "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], "default": "执行下一步"},
        "failure_jump_target_id": {"type": "int", "label": "失败跳转目标 ID", "required": False,
                                     "widget_hint": "card_selector",
                                     "condition": {"param": "on_failure", "value": "跳转到步骤"}}
    }

    # 合并所有参数定义
    return merge_params_definitions(
        image_click_params,
        get_standard_next_step_delay_params(),
        get_standard_action_params()
    )

# Modified execute signature to accept execution_mode and target_hwnd
def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int], window_region: Optional[Tuple[int, int, int, int]], card_id: Optional[int], **kwargs) -> Tuple[bool, str, Optional[int]]:
    """Executes the Find Image and Click task in the specified mode."""
    # 从 kwargs 中获取 get_image_data 函数
    get_image_data = kwargs.get('get_image_data', None)
    
    # 1. 参数获取与检查
    # window_title now comes from the executor based on MainWindow settings
    absolute_image_path = params.get('image_path')
    confidence = params.get('confidence', 0.6)
    button_param = params.get('button', '左键')
    clicks = params.get('clicks', 1)
    interval = params.get('interval', 0.1)
    preprocessing_method = params.get('preprocessing_method', '无')
    # --- 新增：获取重试参数 ---
    enable_retry = params.get('enable_retry', False)
    max_attempts = params.get('retry_attempts', 3) if enable_retry else 1 # 如果不启用，只尝试1次
    retry_interval = params.get('retry_interval', 0.5)
    # -------------------------

    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id = params.get('failure_jump_target_id')
    
    # --- ADDED: Construct absolute path and validate ---
    if not absolute_image_path:
        logger.error("参数错误：图片路径无效或解析失败。")
        success = False
    else:
        try:
            # Construct and normalize the absolute path
            # absolute_image_path = os.path.normpath(os.path.join(images_dir, relative_image_path)) # Remove path construction
            # 只显示图片名称，不显示完整路径
            if absolute_image_path.startswith('memory://'):
                image_name = absolute_image_path.replace('memory://', '')
            else:
                # 确保 os 模块可用
                import os
                image_name = os.path.basename(absolute_image_path)
            logger.debug(f"使用图片: {image_name}")
            # Optional: Check existence here, though _resolve_image_paths should have done it
            # if not os.path.exists(absolute_image_path):
            #      logger.error(f"文件未找到: {absolute_image_path}")
            #      success = False
            #      absolute_image_path = None # Ensure it's None if not found
            pass # Assume existence check was done by executor for now
        except Exception as path_e:
            logger.error(f"验证绝对图片路径时出错: {path_e}", exc_info=True)
            # success = False # No need to set success here, path check below handles it
            absolute_image_path = None
            
    # If path resolution failed (absolute_image_path is None), determine failure action immediately
    if absolute_image_path is None:
        logger.debug("图片路径无效，执行失败操作。")
        # 使用统一的失败处理
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)
    # --- END PATH CONSTRUCTION --- 





    # 2. 查找并点击逻辑
    found = False
    location = None
    click_success = False
    needle_image_processed = None  # 初始化变量以避免 UnboundLocalError
    search_scope = params.get('search_scope', '绑定窗口')

    # 根据搜索范围决定是否执行绑定窗口搜索
    if search_scope != '全屏搜索':
        # 绑定窗口搜索或智能搜索的第一阶段
        for attempt in range(1, max_attempts + 1):
            # 只显示图片名称，不显示路径前缀
            if absolute_image_path.startswith('memory://'):
                image_name = absolute_image_path.replace('memory://', '')
            else:
                # 确保 os 模块可用
                import os
                image_name = os.path.basename(absolute_image_path)
            # 执行模式中文映射
            mode_names = {'foreground': '前台', 'background': '后台'}
            mode_name = mode_names.get(execution_mode, execution_mode)
            logger.info(f"[{mode_name}] 第 {attempt}/{max_attempts} 次尝试查找图片: '{image_name}'")
            try:
                # --- Load Needle Image (using absolute path) ---
                logger.debug(f"加载模板图片: {absolute_image_path}")

                # --- MODIFIED: Support both memory and file modes ---
                needle_image_raw = None

                if absolute_image_path.startswith('memory://'):
                    # 纯内存模式：使用 get_image_data 获取图片数据
                    if get_image_data is None:
                        # 确保 os 模块可用
                        import os
                        image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                        logger.error(f"缺少 get_image_data 函数: '{image_name}'")
                        found = False; location = None; click_success = False
                        break
                
                    try:
                        # 获取图片数据
                        image_data = get_image_data(absolute_image_path)
                        if not image_data:
                            # 确保 os 模块可用
                            import os
                            image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                            logger.error(f"无法从内存获取图片数据: '{image_name}'")
                            found = False; location = None; click_success = False
                            break

                        # 使用 cv2.imdecode 从内存数据解码图片
                        image_array = np.frombuffer(image_data, dtype=np.uint8)
                        needle_image_raw = cv2.imdecode(image_array, cv2.IMREAD_UNCHANGED)
                        # 确保 os 模块可用
                        import os
                        image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                        logger.debug(f"成功 图片加载成功: '{image_name}'")

                    except Exception as e:
                        # 确保 os 模块可用
                        import os
                        image_name = absolute_image_path.replace('memory://', '') if absolute_image_path.startswith('memory://') else os.path.basename(absolute_image_path)
                        logger.error(f"图片加载失败: '{image_name}', 错误: {e}")
                        found = False; location = None; click_success = False
                        break
                else:
                    # 传统文件模式：使用 np.fromfile 读取文件（用于编辑器）
                    try:
                        needle_image_raw = cv2.imdecode(np.fromfile(absolute_image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                        # 只显示图片名称，不显示完整路径
                        # 确保 os 模块可用
                        import os
                        image_name = os.path.basename(absolute_image_path)
                        logger.debug(f"从文件加载图片成功: '{image_name}'")
                    except Exception as e:
                        # 只显示图片名称，不显示完整路径
                        # 确保 os 模块可用
                        import os
                        image_name = os.path.basename(absolute_image_path)
                        logger.error(f"从文件加载图片失败: '{image_name}', 错误: {e}")
                        found = False; location = None; click_success = False
                        break

                if needle_image_raw is None:
                    logger.error(f"无法加载模板图片: '{absolute_image_path}'")
                    found = False; location = None; click_success = False
                    break # Exit retry loop if image can't be loaded

                # --- Preprocess Needle Image ---
                logger.debug("预处理模板图片...")
                try:
                    import importlib
                    preprocessing_module = importlib.import_module('utils.image_preprocessing')
                    apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                    needle_image_processed = apply_preprocessing(needle_image_raw, params)
                except (ImportError, ModuleNotFoundError, AttributeError):
                    # 回退到无预处理
                    needle_image_processed = needle_image_raw
                    if len(needle_image_raw.shape) == 3 and needle_image_raw.shape[2] == 4:
                        needle_image_processed = cv2.cvtColor(needle_image_raw, cv2.COLOR_BGRA2BGR)

                if needle_image_processed is None:
                     logger.error(f"模板图片 '{absolute_image_path}' 预处理失败。") # Log absolute path
                     found = False; location = None; click_success = False
                     break # Exit retry loop if preprocessing fails

                template_h, template_w = needle_image_processed.shape[:2]
                if template_h <= 0 or template_w <= 0:
                    logger.error(f"无效的模板图片尺寸: {template_w}x{template_h} ('{absolute_image_path}')") # Log absolute path
                    found = False; location = None; click_success = False
                    break # Exit retry loop for invalid template size

                # --- 工具 统一使用后台识别方法 ---
                # 不再区分前台后台模式，统一使用后台识别方法以提高稳定性和准确性
                logger.debug("统一使用后台识别方法 (Win32 API + OpenCV)")
                if True:  # 原来的前台和后台模式都使用后台识别方法
                    if not PYWIN32_AVAILABLE or not target_hwnd:
                        logger.error("统一后台识别方法需要 pywin32 库和有效的窗口句柄。")
                        found = False; location = None
                        break # Cannot proceed

                logger.debug(f"截取后台窗口 {target_hwnd}...")
                screenshot_img = capture_window_background(target_hwnd)
                if screenshot_img is not None:
                    logger.debug("预处理后台截图...")
                    try:
                        import importlib
                        preprocessing_module = importlib.import_module('utils.image_preprocessing')
                        apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                        haystack_processed = apply_preprocessing(screenshot_img, params)
                    except (ImportError, ModuleNotFoundError, AttributeError):
                        # 回退到无预处理
                        haystack_processed = screenshot_img
                        if len(screenshot_img.shape) == 3 and screenshot_img.shape[2] == 4:
                            haystack_processed = cv2.cvtColor(screenshot_img, cv2.COLOR_BGRA2BGR)
                    if haystack_processed is not None:
                         screenshot_h, screenshot_w = haystack_processed.shape[:2]
                         if screenshot_h >= template_h and screenshot_w >= template_w:
                             # 标准OpenCV匹配
                             logger.debug(f"使用 OpenCV 查找图片 (置信度: {confidence}) ...")
                             match_method = cv2.TM_CCOEFF_NORMED
                             result_matrix = cv2.matchTemplate(haystack_processed, needle_image_processed, match_method)
                             _, max_val, _, max_loc = cv2.minMaxLoc(result_matrix)
                             match_score = max_val
                             match_location_tl = max_loc # Top-left corner
                             logger.debug(f"最高匹配分数: {match_score:.4f} at {match_location_tl}")
                             if match_score >= confidence:
                                 found = True
                                 location = (match_location_tl[0], match_location_tl[1], template_w, template_h)
                                 center_x = match_location_tl[0] + template_w // 2
                                 center_y = match_location_tl[1] + template_h // 2
                                 logger.info(f"[统一后台识别] 尝试 {attempt}: 图片找到! 客户区坐标 (左上角): {location[:2]}, 中心点: ({center_x}, {center_y})")
                                 break # Exit retry loop on success
                             else:
                                 logger.info(f"[统一后台识别] 尝试 {attempt}: 未找到图片 (置信度未达到阈值)。")
                         else: logger.error(f"后台截图尺寸 ({screenshot_w}x{screenshot_h}) 小于模板尺寸 ({template_w}x{template_h})。 ('{absolute_image_path}')") # Log absolute path
                    else: logger.error("后台截图预处理失败。")
                else: logger.error(f"无法捕获目标窗口 {target_hwnd} 的后台截图。")

            except Exception as find_err:
                # 显示错误详细信息
                # 只显示图片名称，不显示路径前缀
                if absolute_image_path.startswith('memory://'):
                    image_name = absolute_image_path.replace('memory://', '')
                else:
                    # 确保 os 模块可用
                    import os
                    image_name = os.path.basename(absolute_image_path)
                mode_name = mode_names.get(execution_mode, execution_mode)
                logger.error(f"[{mode_name}] 第 {attempt} 次尝试查找图片 '{image_name}' 时发生意外错误: {find_err}", exc_info=True)
                found = False # Ensure found is False on error

            # If not found and more attempts remain, wait
            if not found and attempt < max_attempts:
                logger.debug(f"等待 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)
            
    # --- End Retry Loop ---

    # --- 根据搜索范围决定是否进行全屏查找 ---
    search_scope = params.get('search_scope', '绑定窗口')

    if search_scope == '全屏搜索':
        # 使用智能搜索策略，但跳过绑定窗口搜索
        logger.info("使用全屏搜索模式...")

        # 如果还没有加载图片，先加载
        if 'needle_image_processed' not in locals() or needle_image_processed is None:
            logger.debug("全屏搜索模式：加载模板图片...")
            try:
                # 加载图片
                if absolute_image_path.startswith('memory://'):
                    if get_image_data is None:
                        logger.error("全屏搜索模式缺少 get_image_data 函数")
                        found = False
                    else:
                        image_data = get_image_data(absolute_image_path)
                        if image_data:
                            image_array = np.frombuffer(image_data, dtype=np.uint8)
                            needle_image_raw = cv2.imdecode(image_array, cv2.IMREAD_UNCHANGED)
                        else:
                            logger.error("全屏搜索模式：无法从内存获取图片数据")
                            found = False
                else:
                    needle_image_raw = cv2.imdecode(np.fromfile(absolute_image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

                # 预处理图片
                if needle_image_raw is not None:
                    try:
                        import importlib
                        preprocessing_module = importlib.import_module('utils.image_preprocessing')
                        apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                        needle_image_processed = apply_preprocessing(needle_image_raw, params)
                    except (ImportError, ModuleNotFoundError, AttributeError):
                        needle_image_processed = needle_image_raw
                        if len(needle_image_raw.shape) == 3 and needle_image_raw.shape[2] == 4:
                            needle_image_processed = cv2.cvtColor(needle_image_raw, cv2.COLOR_BGRA2BGR)
                else:
                    logger.error("全屏搜索模式：图片加载失败")
                    found = False

            except Exception as e:
                logger.error(f"全屏搜索模式：图片加载时发生错误: {e}")
                found = False

        # 使用智能搜索策略（跳过绑定窗口，直接从策略2开始）
        if needle_image_processed is not None:
            logger.info("全屏搜索：使用智能搜索策略...")

            # 策略1：顶层窗口搜索
            found, location, actual_hwnd = _search_top_level_windows(needle_image_processed, confidence, params)
            if found and actual_hwnd:
                logger.info(f"全屏搜索-顶层窗口搜索成功，找到窗口句柄: {actual_hwnd}")
                target_hwnd = actual_hwnd
            else:
                # 策略2：传统全屏截图搜索（备用）
                found, location, actual_hwnd = _search_image_fullscreen(needle_image_processed, confidence, params)
                if found and actual_hwnd:
                    logger.info(f"全屏搜索-传统全屏搜索成功，找到窗口句柄: {actual_hwnd}")
                    target_hwnd = actual_hwnd
                # 全屏搜索成功后，强制使用前台模式进行点击
                execution_mode = 'foreground'
                logger.info("全屏搜索成功，切换到前台模式进行点击")
    elif search_scope == '智能搜索' and not found and target_hwnd and execution_mode == 'background':
        # 智能搜索：多层级搜索策略
        logger.info("绑定窗口内未找到图片，启动智能搜索...")

        # 检查 needle_image_processed 是否已定义
        if 'needle_image_processed' in locals() and needle_image_processed is not None:
            found, location, actual_hwnd = _smart_search_strategy(needle_image_processed, confidence, params, target_hwnd)
            if found and actual_hwnd:
                logger.info(f"智能搜索成功，图片位于窗口句柄: {actual_hwnd}")
                target_hwnd = actual_hwnd  # 更新目标窗口句柄
        else:
            logger.error("智能搜索失败：图片数据未正确加载")
            found = False
    # 绑定窗口模式：不进行额外处理，使用上面的搜索结果

    # --- Perform Click Action if Found ---
    if found and location:
        click_success = False # Assume failure unless click succeeds

        # --- MODIFIED: Calculate dynamic random offset based on image size ---
        template_w = location[2]
        template_h = location[3]

        # Calculate maximum absolute offset allowed by template size
        max_abs_offset_x = template_w // 2
        max_abs_offset_y = template_h // 2

        # Determine the actual offset range, capped by 5 and template size
        # Ensure the range is valid (min <= max)
        actual_range_x = min(5, max_abs_offset_x)
        actual_range_y = min(5, max_abs_offset_y)

        # Generate offset within the calculated dynamic range
        # Handle cases where range might become negative (e.g., 1px image -> max_abs=0, range=0)
        offset_x = random.randint(-actual_range_x, actual_range_x) if actual_range_x >= 0 else 0
        offset_y = random.randint(-actual_range_y, actual_range_y) if actual_range_y >= 0 else 0
        # --------------------------------------------------------------------

        # --- 工具 点击操作：统一坐标计算 ---
        # location格式: (left, top, width, height) - 左上角坐标
        left_x = location[0]
        top_y = location[1]

        # 计算图片中心点坐标
        center_x = left_x + template_w // 2
        center_y = top_y + template_h // 2

        # 应用随机偏移
        click_x = center_x + offset_x
        click_y = center_y + offset_y

        # 工具 验证坐标计算逻辑
        expected_center_x = left_x + template_w // 2
        expected_center_y = top_y + template_h // 2

        if center_x != expected_center_x or center_y != expected_center_y:
            logger.error(f"错误 坐标计算错误!")
            logger.error(f"   期望中心点: ({expected_center_x}, {expected_center_y})")
            logger.error(f"   实际中心点: ({center_x}, {center_y})")
            logger.error(f"   左上角: ({left_x}, {top_y}), 尺寸: {template_w}x{template_h}")

        # 工具 检查点击位置是否合理
        click_offset_from_center_x = click_x - center_x
        click_offset_from_center_y = click_y - center_y

        logger.info(f"靶心 坐标计算详情:")
        logger.info(f"   📍 图片左上角: ({left_x}, {top_y})")
        logger.info(f"   📍 图片尺寸: {template_w}x{template_h}")
        logger.info(f"   📍 计算中心点: ({center_x}, {center_y})")
        logger.info(f"   📍 随机偏移: ({offset_x}, {offset_y}) [范围: ±{actual_range_x}, ±{actual_range_y}]")
        logger.info(f"   📍 最终点击: ({click_x}, {click_y})")
        logger.info(f"   📍 相对中心偏移: ({click_offset_from_center_x}, {click_offset_from_center_y})")

        # 工具 检查是否点击位置超出图片范围
        if abs(click_offset_from_center_x) > template_w // 2 or abs(click_offset_from_center_y) > template_h // 2:
            logger.warning(f"警告 点击位置可能超出图片范围!")
            logger.warning(f"   图片范围: 中心±({template_w//2}, {template_h//2})")
            logger.warning(f"   实际偏移: ({click_offset_from_center_x}, {click_offset_from_center_y})")

        # 修复前台模式坐标问题：避免双重转换
        logger.info(f"=== 图片点击坐标处理 ===")
        logger.info(f"图片匹配坐标: ({click_x}, {click_y}), 执行模式: {execution_mode}")

        # 检查是否为后台模式（包括所有后台变体）
        is_background_mode = execution_mode.startswith('background')
        # 检查是否为前台模式（包括所有前台变体）
        is_foreground_mode = execution_mode.startswith('foreground')

        if is_background_mode:
            # 后台模式：使用通用坐标系统处理
            try:
                coord_system = get_universal_coordinate_system()
                coord_info = create_coordinate_from_image_recognition(click_x, click_y, target_hwnd)
                click_mode = ClickMode.BACKGROUND
                final_click_x, final_click_y = coord_system.process_click_coordinate(coord_info, target_hwnd, click_mode)
                logger.info(f"后台模式坐标处理: 原始({click_x}, {click_y}) -> 最终({final_click_x}, {final_click_y})")
                dpi_adjusted_click_x, dpi_adjusted_click_y = final_click_x, final_click_y
            except Exception as e:
                logger.error(f"后台模式坐标处理失败，使用原始坐标: {e}")
                dpi_adjusted_click_x, dpi_adjusted_click_y = click_x, click_y
        elif is_foreground_mode:
            # 前台模式：直接使用客户区坐标，避免通用坐标系统的双重转换
            logger.info(f"前台模式：直接使用客户区坐标，避免双重转换")
            dpi_adjusted_click_x, dpi_adjusted_click_y = click_x, click_y
        else:
            # 其他模式（如模拟器模式）：使用原始坐标
            logger.info(f"其他模式：使用原始坐标")
            dpi_adjusted_click_x, dpi_adjusted_click_y = click_x, click_y

        # 添加详细的点击位置诊断
        _diagnose_click_position(target_hwnd, left_x, top_y, center_x, center_y, dpi_adjusted_click_x, dpi_adjusted_click_y, template_w, template_h)

        # 判断执行模式类型
        is_background_click_mode = execution_mode.startswith('background')
        is_foreground_click_mode = execution_mode.startswith('foreground')
        is_emulator_click_mode = execution_mode.startswith('emulator_')

        if is_foreground_click_mode:
            # 前台模式：需要将客户区坐标转换为屏幕坐标
            logger.info(f"[前台点击] 模板尺寸: {template_w}x{template_h}, 动态偏移范围: [+/-{actual_range_x}, +/-{actual_range_y}]")
            logger.info(f"[前台点击] 客户区坐标 - 中心点: ({center_x}, {center_y}), 应用偏移: ({offset_x},{offset_y}), DPI调整后点击坐标: ({dpi_adjusted_click_x}, {dpi_adjusted_click_y})")

            # 工具 关键修复：将客户区坐标转换为屏幕坐标
            try:
                # 使用Windows API进行精确坐标转换
                from ctypes import wintypes
                import ctypes

                point = wintypes.POINT(int(dpi_adjusted_click_x), int(dpi_adjusted_click_y))
                result = ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point))

                if result:
                    screen_click_x, screen_click_y = point.x, point.y
                    logger.info(f"[前台点击] 坐标转换成功: 客户区({dpi_adjusted_click_x}, {dpi_adjusted_click_y}) -> 屏幕({screen_click_x}, {screen_click_y})")
                else:
                    # API失败时的备用计算方法
                    window_rect = win32gui.GetWindowRect(target_hwnd)
                    client_rect = win32gui.GetClientRect(target_hwnd)

                    window_width = window_rect[2] - window_rect[0]
                    window_height = window_rect[3] - window_rect[1]
                    client_width = client_rect[2] - client_rect[0]
                    client_height = client_rect[3] - client_rect[1]

                    border_x = (window_width - client_width) // 2
                    title_height = window_height - client_height - border_x

                    screen_click_x = window_rect[0] + border_x + dpi_adjusted_click_x
                    screen_click_y = window_rect[1] + title_height + dpi_adjusted_click_y

                    logger.info(f"[前台点击] 备用坐标计算: 客户区({dpi_adjusted_click_x}, {dpi_adjusted_click_y}) -> 屏幕({screen_click_x}, {screen_click_y})")

                # 工具 修复：简化窗口激活逻辑
                import os
                is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'

                # 只在前台模式且非多窗口模式下激活窗口
                should_activate = (execution_mode == 'foreground' and not is_multi_window_mode)

                if should_activate:
                    # 激活窗口（前台模式）
                    logger.info("[前台点击] 激活目标窗口...")
                    win32gui.SetForegroundWindow(target_hwnd)
                    time.sleep(0.1)  # 等待窗口激活

                    # 验证窗口激活状态
                    fg_hwnd = win32gui.GetForegroundWindow()
                    if fg_hwnd == target_hwnd:
                        logger.info("[前台点击] 窗口激活成功")
                    else:
                        logger.warning(f"[前台点击] 窗口激活可能失败，当前前台窗口: {fg_hwnd}")
                else:
                    reason = "后台模式" if execution_mode == 'background' else "多窗口模式"
                    logger.info(f"靶心 [{reason}] 跳过窗口激活，直接在窗口 {target_hwnd} 中点击")

                # 执行前台点击 - 根据模式选择不同的点击方法
                button_pyautogui = 'left'
                if button_param == '右键': button_pyautogui = 'right'
                elif button_param == '中键': button_pyautogui = 'middle'

                logger.info(f"[前台点击] 执行点击: 屏幕坐标({screen_click_x}, {screen_click_y}), 按钮={button_param}, 次数={clicks}, 间隔={interval}")

                # 根据execution_mode选择不同的前台点击方法
                if execution_mode == 'foreground_pyautogui':
                    # 前台模式二
                    try:
                        import pyautogui
                        logger.info("[前台模式二] 执行点击操作")
                        for i in range(clicks):
                            pyautogui.click(screen_click_x, screen_click_y, button=button_pyautogui)
                            if clicks > 1 and i < clicks - 1:
                                time.sleep(interval)
                        click_success = True
                        logger.info("[前台点击] 点击操作完成")
                    except ImportError:
                        logger.error("[前台模式二] 缺少必要库，无法执行点击")
                        click_success = False
                    except Exception as e:
                        logger.error(f"[前台模式二] 点击失败: {e}")
                        click_success = False
                else:
                    # 前台模式一/默认
                    if not INTERCEPTION_AVAILABLE:
                        logger.error("[前台模式一] 缺少必要驱动，无法执行点击")
                        click_success = False
                    else:
                        logger.info("[前台模式一] 执行点击操作")
                        driver.click_mouse(x=screen_click_x, y=screen_click_y, clicks=clicks, interval=interval, button=button_pyautogui)
                        click_success = True
                        logger.info("[前台点击] 点击操作完成")


            except Exception as click_err:
                logger.error(f"[前台点击] 点击操作时发生错误: {click_err}", exc_info=True)

        elif is_background_click_mode:
            # 后台模式：使用后台点击（包括所有后台变体：background, background_sendmessage, background_postmessage等）
            button_win32 = 'left'
            if button_param == "右键": button_win32 = "right"
            elif button_param == "中键": button_win32 = "middle"
            logger.info(f"[后台点击] 模板尺寸: {template_w}x{template_h}, 动态偏移范围: [+/-{actual_range_x}, +/-{actual_range_y}]")
            logger.info(f"[后台点击] 计算中心点: ({center_x}, {center_y}), 应用偏移: ({offset_x},{offset_y}), DPI调整后点击坐标: ({dpi_adjusted_click_x}, {dpi_adjusted_click_y}), 按钮={button_param} ({button_win32}), 次数={clicks}, 间隔={interval}")
            logger.info(f"[后台点击] 执行模式: {execution_mode}")
            try:
                # 兼容旧执行器：检查click_background函数是否支持clicks参数
                import inspect
                click_bg_signature = inspect.signature(click_background)

                if 'clicks' in click_bg_signature.parameters:
                    # 新版本：支持clicks参数
                    if click_background(hwnd=target_hwnd, x=dpi_adjusted_click_x, y=dpi_adjusted_click_y, button=button_win32, clicks=clicks, interval=interval):
                        click_success = True
                        logger.info("后台点击操作成功。")
                    else:
                        logger.warning("警告: 后台点击失败 (click_background 返回失败)。")
                else:
                    # 旧版本：不支持clicks参数，需要循环调用
                    logger.info(f"使用兼容模式：循环执行{clicks}次点击")
                    click_success = True
                    for i in range(clicks):
                        if not click_background(target_hwnd, dpi_adjusted_click_x, dpi_adjusted_click_y, button_win32):
                            click_success = False
                            logger.warning(f"第{i+1}次后台点击失败")
                            break
                        if clicks > 1 and i < clicks - 1:
                            time.sleep(interval)

                    if click_success:
                        logger.info(f"后台点击操作成功（兼容模式，{clicks}次点击）。")
                    else:
                        logger.warning("警告: 后台点击失败 (兼容模式)。")

            except Exception as click_err:
                 logger.error(f"[后台点击] 点击操作时发生异常: {click_err}", exc_info=True)

        elif is_emulator_click_mode:
            # 模拟器模式：使用模拟器专用点击方法
            # 翻译按钮名称：中文 -> 英文
            button_emulator = 'left'
            if button_param == "右键": button_emulator = "right"
            elif button_param == "中键": button_emulator = "middle"

            logger.info(f"[模拟器点击] 模板尺寸: {template_w}x{template_h}, 动态偏移范围: [+/-{actual_range_x}, +/-{actual_range_y}]")
            logger.info(f"[模拟器点击] 计算中心点: ({center_x}, {center_y}), 应用偏移: ({offset_x},{offset_y}), DPI调整后点击坐标: ({dpi_adjusted_click_x}, {dpi_adjusted_click_y}), 按钮={button_param} ({button_emulator}), 次数={clicks}, 间隔={interval}")
            logger.info(f"[模拟器点击] 执行模式: {execution_mode}")
            try:
                # 从execution_mode提取模拟器类型 (emulator_mumu -> mumu, emulator_ldplayer -> ldplayer)
                emulator_type = execution_mode.replace('emulator_', '')
                logger.info(f"[模拟器点击] 用户指定模拟器类型: {emulator_type}")

                # 直接创建对应的模拟器，不需要工厂检测
                from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                simulator = EmulatorWindowInputSimulator(target_hwnd, emulator_type=emulator_type, execution_mode=execution_mode)

                if simulator:
                    # 使用模拟器点击（使用翻译后的英文按钮名）
                    if simulator.click(dpi_adjusted_click_x, dpi_adjusted_click_y, button=button_emulator, clicks=clicks, interval=interval):
                        click_success = True
                        logger.info("[模拟器点击] 点击操作成功")
                    else:
                        logger.warning("[模拟器点击] 点击操作失败")
                else:
                    logger.error("[模拟器点击] 无法创建输入模拟器")
            except Exception as click_err:
                logger.error(f"[模拟器点击] 点击操作时发生异常: {click_err}", exc_info=True)

    # Determine final success based on finding AND clicking
    # If not found, click_success remains False
    success = found and click_success 
    
    # 3. 根据结果确定下一步
    if success:
        # 只显示图片名称，不显示完整路径
        if absolute_image_path.startswith('memory://'):
            image_name = absolute_image_path.replace('memory://', '')
        else:
            # 确保 os 模块可用
            import os
            image_name = os.path.basename(absolute_image_path)
        logger.info(f"任务 '{TASK_NAME}' (图片: '{image_name}') 执行成功。")
        # 使用统一的成功处理（包含延迟）
        from .task_utils import handle_success_action
        return handle_success_action(params, card_id, kwargs.get('stop_checker'))
    else: # Handle overall failure (either not found or click failed)
        # 只显示图片名称，不显示完整路径
        if absolute_image_path.startswith('memory://'):
            image_name = absolute_image_path.replace('memory://', '')
        else:
            # 确保 os 模块可用
            import os
            image_name = os.path.basename(absolute_image_path)
        logger.info(f"任务 '{TASK_NAME}' (图片: '{image_name}') 执行失败 (未找到或点击失败)。")
        # 使用统一的失败处理
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)

    # --- ADDED: Store confidence values in counters REGARDLESS of success/failure (if matching occurred) ---
    if card_id is not None:
        req_conf_key = f'__required_confidence_{card_id}'
        act_conf_key = f'__actual_confidence_{card_id}'
        
        # Store required confidence (should always be available if task ran)
        counters[req_conf_key] = confidence 
        logger.debug(f"  Storing required confidence to counters: {req_conf_key} = {confidence}")
        
        # Store actual confidence IF matching was performed (max_val exists)
        if 'max_val' in locals() or 'max_val' in globals(): # Check if max_val was defined
            # Ensure max_val is float before storing
            try:
                 actual_conf_float = float(max_val)
                 counters[act_conf_key] = actual_conf_float
                 logger.debug(f"  Storing actual confidence to counters: {act_conf_key} = {actual_conf_float}")
            except (ValueError, TypeError):
                 logger.warning(f"  未能将实际置信度 ({max_val}) 转换为浮点数存储。")
                 counters[act_conf_key] = -1.0 # Indicate conversion failure
        else:
            # Indicate that matching likely didn't occur or max_val wasn't found
            counters[act_conf_key] = -1.0 # Use -1.0 to signify not available/not found
            logger.debug(f"  Actual confidence (max_val) not found in local scope. Storing {act_conf_key} = -1.0")
    else:
        logger.warning("无法存储置信度到 counters：未提供 card_id。")
    # --- END ADDED ---

# Example (for testing standalone)
if __name__ == '__main__':
    # --- 测试后台截图 ---
    # !!! 重要：修改为你想要测试的窗口标题 或 部分标题 !!!
    # test_target_title = "无标题 - 记事本" # 例如：中文记事本
    # test_target_title = "Untitled - Notepad" # 例如：英文记事本
    test_target_title_part = "剑网3无界" # 使用部分标题查找

    test_hwnd = None

    if PYWIN32_AVAILABLE:
        try:
            # --- MODIFIED: Find window by partial title ---
            logger.info(f"尝试通过部分标题 '{test_target_title_part}' 查找窗口...")
            top_windows = []
            # Define callback function inline or ensure it's defined correctly
            def enum_window_callback(hwnd, param):
                param.append(hwnd)
                return True # Must return True to continue enumeration

            win32gui.EnumWindows(enum_window_callback, top_windows)
            found_title = "" # Store the title of the found window
            for hwnd_item in top_windows:
                window_title = win32gui.GetWindowText(hwnd_item)
                if test_target_title_part in window_title:
                    test_hwnd = hwnd_item
                    found_title = window_title # Store the full title
                    logger.info(f"找到匹配窗口: '{found_title}'，HWND: {test_hwnd}")
                    break # Use the first match
            # --- END MODIFICATION ---

            # Ensure win32gui is imported (should be from top level) - No longer needed FindWindow call

            if test_hwnd:
                # logger.info(f"找到窗口 '{found_title}'，HWND: {test_hwnd}") # Log already happened

                # 1. 执行后台截图
                logger.info("尝试使用 capture_window_background 进行后台截图...")
                # Ensure capture_window_background is imported (should be from top level)
                screenshot = capture_window_background(test_hwnd)

                # 2. 检查并保存截图
                if screenshot is not None and isinstance(screenshot, np.ndarray):
                    logger.info(f"后台截图成功，截图尺寸: {screenshot.shape}")
                    save_path = "_test_find_image_click_screenshot.png"
                    try:
                        # Ensure cv2 and os are imported (should be from top level)
                        cv2.imwrite(save_path, screenshot)
                        # Use os.path.abspath for clearer path reporting
                        # 确保 os 模块可用
                        import os
                        logger.info(f"截图已保存到: {os.path.abspath(save_path)}")
                    except Exception as e:
                        logger.error(f"保存截图 '{save_path}' 失败: {e}", exc_info=True)
                else:
                    logger.error("后台截图失败或返回无效结果 (None 或非 NumPy 数组)。")

            else:
                logger.error(f"找不到标题包含 '{test_target_title_part}' 的窗口。请确保窗口已打开。") # Updated error message
        except Exception as e:
            logger.error(f"查找窗口 '{test_target_title_part}' 或执行截图时发生错误: {e}", exc_info=True) # Updated error message
    else:
        logger.error("pywin32 库未安装，无法执行后台截图测试。请运行: pip install pywin32")

    logger.info("find_image_and_click.py 模块测试结束。")

def _diagnose_click_position(target_hwnd: int, left_x: int, top_y: int, center_x: int, center_y: int,
                           click_x: int, click_y: int, template_w: int, template_h: int):
    """
    诊断点击位置，帮助调试点击偏移问题
    """
    try:
        if not PYWIN32_AVAILABLE:
            return

        import ctypes
        from ctypes import wintypes

        logger.info("搜索 ===== 点击位置诊断开始 =====")

        # 1. 窗口信息
        try:
            window_title = win32gui.GetWindowText(target_hwnd)
            class_name = win32gui.GetClassName(target_hwnd)
            logger.info(f"靶心 目标窗口: '{window_title}' (类名: {class_name}, HWND: {target_hwnd})")
        except Exception as e:
            logger.warning(f"获取窗口信息失败: {e}")

        # 2. 窗口矩形信息
        try:
            window_rect = win32gui.GetWindowRect(target_hwnd)
            client_rect = win32gui.GetClientRect(target_hwnd)

            logger.info(f"📐 窗口矩形: {window_rect} (宽度: {window_rect[2]-window_rect[0]}, 高度: {window_rect[3]-window_rect[1]})")
            logger.info(f"📐 客户区矩形: {client_rect} (宽度: {client_rect[2]}, 高度: {client_rect[3]})")

            # 计算边框大小
            border_x = (window_rect[2] - window_rect[0] - client_rect[2]) // 2
            title_height = window_rect[3] - window_rect[1] - client_rect[3] - border_x
            logger.info(f"📐 边框信息: 左右边框={border_x}px, 标题栏高度={title_height}px")

        except Exception as e:
            logger.warning(f"获取窗口矩形失败: {e}")

        # 3. 图片和点击位置信息
        logger.info(f"🖼 图片信息: 尺寸={template_w}x{template_h}, 左上角=({left_x}, {top_y})")
        logger.info(f"靶心 点击信息: 中心点=({center_x}, {center_y}), 最终点击=({click_x}, {click_y})")

        # 4. 坐标转换验证
        try:
            # 将客户区坐标转换为屏幕坐标
            point = wintypes.POINT(click_x, click_y)
            if ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point)):
                screen_x, screen_y = point.x, point.y
                logger.info(f" 坐标转换: 客户区({click_x}, {click_y}) -> 屏幕({screen_x}, {screen_y})")

                # 验证转换后的屏幕坐标是否在窗口范围内
                if (window_rect[0] <= screen_x <= window_rect[2] and
                    window_rect[1] <= screen_y <= window_rect[3]):
                    logger.info("成功 屏幕坐标在窗口范围内")
                else:
                    logger.warning(f"警告 屏幕坐标超出窗口范围! 窗口范围: {window_rect}")

                # 检查是否在客户区范围内
                if (0 <= click_x <= client_rect[2] and 0 <= click_y <= client_rect[3]):
                    logger.info("成功 客户区坐标在有效范围内")
                else:
                    logger.warning(f"警告 客户区坐标超出范围! 客户区范围: (0, 0, {client_rect[2]}, {client_rect[3]})")

            else:
                logger.warning("错误 客户区到屏幕坐标转换失败")

        except Exception as e:
            logger.warning(f"坐标转换验证失败: {e}")

        # 5. 检查点击位置的窗口
        try:
            point = wintypes.POINT(click_x, click_y)
            if ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point)):
                actual_hwnd = ctypes.windll.user32.WindowFromPoint(point)
                if actual_hwnd:
                    actual_title = win32gui.GetWindowText(actual_hwnd)
                    if actual_hwnd == target_hwnd:
                        logger.info(f"成功 点击位置窗口正确: '{actual_title}' (HWND: {actual_hwnd})")
                    else:
                        logger.warning(f"警告 点击位置窗口不匹配!")
                        logger.warning(f"   目标窗口: {target_hwnd}")
                        logger.warning(f"   实际窗口: {actual_hwnd} ('{actual_title}')")
                        logger.warning("   这可能导致点击穿透到其他窗口!")
        except Exception as e:
            logger.warning(f"检查点击位置窗口失败: {e}")

        logger.info("搜索 ===== 点击位置诊断结束 =====")

    except Exception as e:
        logger.error(f"点击位置诊断失败: {e}")

def _search_image_fullscreen(needle_image: np.ndarray, confidence: float, params: Dict[str, Any]) -> Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]:
    """
    在全屏范围内搜索图片并返回实际窗口句柄

    Args:
        needle_image: 要查找的图片
        confidence: 置信度阈值
        params: 参数字典

    Returns:
        Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]: (是否找到, 位置信息, 窗口句柄)
    """
    if not INTERCEPTION_AVAILABLE or not PYWIN32_AVAILABLE or not is_screenshot_available():
        logger.error("全屏查找需要 Interception驱动、pywin32 库和截图功能")
        return False, None, None

    try:
        # 1. 获取全屏截图 - 使用截图助手（pyautogui效果最好）
        logger.debug("获取全屏截图...")
        screenshot_np = take_screenshot_opencv()
        if screenshot_np is None:
            logger.error("截图失败")
            return False, None, None

        # 2. 应用预处理
        try:
            import importlib
            preprocessing_module = importlib.import_module('utils.image_preprocessing')
            apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
            haystack_processed = apply_preprocessing(screenshot_np, params)
        except (ImportError, ModuleNotFoundError, AttributeError):
            haystack_processed = screenshot_np
            if len(screenshot_np.shape) == 3 and screenshot_np.shape[2] == 4:
                haystack_processed = cv2.cvtColor(screenshot_np, cv2.COLOR_BGRA2BGR)

        if haystack_processed is None:
            logger.error("全屏截图预处理失败")
            return False, None, None

        # 3. 执行图片匹配
        template_h, template_w = needle_image.shape[:2]
        screenshot_h, screenshot_w = haystack_processed.shape[:2]

        if screenshot_h < template_h or screenshot_w < template_w:
            logger.error("全屏截图尺寸小于模板图片")
            return False, None, None

        logger.debug(f"在全屏截图中查找图片 (置信度: {confidence})...")
        match_method = cv2.TM_CCOEFF_NORMED
        result_matrix = cv2.matchTemplate(haystack_processed, needle_image, match_method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result_matrix)

        logger.debug(f"全屏查找最高匹配分数: {max_val:.4f}")

        if max_val >= confidence:
            # 4. 找到图片，计算屏幕坐标
            top_left_x, top_left_y = max_loc
            center_x = top_left_x + template_w // 2
            center_y = top_left_y + template_h // 2

            logger.info(f"全屏查找成功！屏幕坐标 (中心点): ({center_x}, {center_y})")

            # 5. 根据屏幕坐标获取窗口句柄
            actual_hwnd = _get_window_from_point(center_x, center_y)

            if actual_hwnd:
                # 6. 将屏幕坐标转换为该窗口的客户区坐标
                try:
                    from ctypes import wintypes
                    import ctypes

                    point = wintypes.POINT(center_x, center_y)
                    if ctypes.windll.user32.ScreenToClient(actual_hwnd, ctypes.byref(point)):
                        client_x, client_y = point.x, point.y
                        logger.info(f"坐标转换成功: 屏幕({center_x}, {center_y}) -> 客户区({client_x}, {client_y})")

                        # 返回客户区坐标格式的位置信息（左上角坐标）
                        top_left_client_x = client_x - template_w // 2
                        top_left_client_y = client_y - template_h // 2
                        location = (top_left_client_x, top_left_client_y, template_w, template_h)
                        logger.debug(f"全屏搜索坐标转换: 屏幕中心({center_x}, {center_y}) -> 客户区中心({client_x}, {client_y}) -> 客户区左上角({top_left_client_x}, {top_left_client_y})")
                        return True, location, actual_hwnd
                    else:
                        logger.warning("屏幕坐标转换为客户区坐标失败")
                        # 使用屏幕坐标作为备用
                        location = (top_left_x, top_left_y, template_w, template_h)
                        return True, location, actual_hwnd

                except Exception as e:
                    logger.error(f"坐标转换时发生错误: {e}")
                    location = (top_left_x, top_left_y, template_w, template_h)
                    return True, location, actual_hwnd
            else:
                logger.warning("无法获取图片所在的窗口句柄")
                return False, None, None
        else:
            logger.info(f"全屏查找未找到图片 (置信度未达到阈值: {max_val:.4f} < {confidence})")
            return False, None, None

    except Exception as e:
        logger.error(f"全屏查找图片时发生错误: {e}", exc_info=True)
        return False, None, None

def _get_window_from_point(x: int, y: int) -> Optional[int]:
    """
    根据屏幕坐标获取窗口句柄

    Args:
        x: 屏幕X坐标
        y: 屏幕Y坐标

    Returns:
        Optional[int]: 窗口句柄，如果失败返回None
    """
    if not PYWIN32_AVAILABLE:
        return None

    try:
        import ctypes
        from ctypes import wintypes

        # 使用 WindowFromPoint API 获取窗口句柄
        point = wintypes.POINT(x, y)
        hwnd = ctypes.windll.user32.WindowFromPoint(point)

        if hwnd:
            # 获取窗口标题用于日志
            try:
                window_title = win32gui.GetWindowText(hwnd)
                logger.info(f"根据坐标({x}, {y})找到窗口: '{window_title}' (HWND: {hwnd})")
            except Exception:
                logger.info(f"根据坐标({x}, {y})找到窗口 (HWND: {hwnd})")

            return hwnd
        else:
            logger.warning(f"根据坐标({x}, {y})未找到有效窗口")
            return None

    except Exception as e:
        logger.error(f"根据坐标获取窗口句柄时发生错误: {e}")
        return None

def _smart_search_strategy(needle_image: np.ndarray, confidence: float, params: Dict[str, Any], base_hwnd: int) -> Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]:
    """
    智能搜索策略：多层级搜索解决窗口遮挡问题

    搜索顺序：
    1. 子窗口搜索：搜索绑定窗口的所有子窗口
    2. 相关窗口搜索：搜索同进程的其他窗口
    3. 全屏搜索：最后尝试全屏搜索

    Args:
        needle_image: 要查找的图片
        confidence: 置信度阈值
        params: 参数字典
        base_hwnd: 绑定的基础窗口句柄

    Returns:
        Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]: (是否找到, 位置信息, 窗口句柄)
    """
    if not PYWIN32_AVAILABLE:
        logger.error("智能搜索需要 pywin32 库")
        return False, None, None

    try:
        # 策略1：子窗口搜索
        logger.info("策略1：搜索绑定窗口的子窗口...")
        found, location, actual_hwnd = _search_child_windows(needle_image, confidence, params, base_hwnd)
        if found and actual_hwnd:
            logger.info(f"子窗口搜索成功，找到窗口句柄: {actual_hwnd}")
            return found, location, actual_hwnd

        # 策略2：相关窗口搜索（同进程窗口）
        logger.info("策略2：搜索同进程的相关窗口...")
        found, location, actual_hwnd = _search_related_windows(needle_image, confidence, params, base_hwnd)
        if found and actual_hwnd:
            logger.info(f"相关窗口搜索成功，找到窗口句柄: {actual_hwnd}")
            return found, location, actual_hwnd

        # 策略3：顶层窗口搜索
        logger.info("策略3：搜索所有顶层窗口...")
        found, location, actual_hwnd = _search_top_level_windows(needle_image, confidence, params)
        if found and actual_hwnd:
            logger.info(f"顶层窗口搜索成功，找到窗口句柄: {actual_hwnd}")
            return found, location, actual_hwnd

        # 策略4：全屏搜索（最后的备用方案）
        logger.info("策略4：全屏搜索（备用方案）...")
        found, location, actual_hwnd = _search_image_fullscreen(needle_image, confidence, params)
        if found and actual_hwnd:
            logger.info(f"全屏搜索成功，找到窗口句柄: {actual_hwnd}")
            return found, location, actual_hwnd

        logger.info("智能搜索所有策略均未找到目标图片")
        return False, None, None

    except Exception as e:
        logger.error(f"智能搜索策略执行时发生错误: {e}", exc_info=True)
        return False, None, None

def _search_child_windows(needle_image: np.ndarray, confidence: float, params: Dict[str, Any], parent_hwnd: int) -> Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]:
    """
    搜索父窗口的所有子窗口
    """
    if not PYWIN32_AVAILABLE:
        return False, None, None

    try:
        child_windows = []

        def enum_child_callback(hwnd, param):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                child_windows.append((hwnd, window_title))
            return True

        # 枚举子窗口
        win32gui.EnumChildWindows(parent_hwnd, enum_child_callback, None)

        logger.debug(f"找到 {len(child_windows)} 个子窗口")

        for child_hwnd, title in child_windows:
            try:
                # 尝试在子窗口中搜索
                found, location = _search_in_window(needle_image, confidence, params, child_hwnd)
                if found:
                    logger.info(f"在子窗口中找到图片: '{title}' (HWND: {child_hwnd})")
                    return True, location, child_hwnd
            except Exception as e:
                logger.debug(f"搜索子窗口 {child_hwnd} 时发生错误: {e}")
                continue

        return False, None, None

    except Exception as e:
        logger.error(f"子窗口搜索时发生错误: {e}")
        return False, None, None

def _search_related_windows(needle_image: np.ndarray, confidence: float, params: Dict[str, Any], base_hwnd: int) -> Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]:
    """
    搜索同进程的相关窗口
    """
    if not PYWIN32_AVAILABLE:
        return False, None, None

    try:
        import ctypes

        # 获取基础窗口的进程ID
        base_process_id = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(base_hwnd, ctypes.byref(base_process_id))
        base_pid = base_process_id.value

        related_windows = []

        def enum_windows_callback(hwnd, param):
            if win32gui.IsWindowVisible(hwnd) and hwnd != base_hwnd:
                # 获取窗口的进程ID
                window_process_id = ctypes.wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_process_id))

                # 如果是同一个进程的窗口
                if window_process_id.value == base_pid:
                    window_title = win32gui.GetWindowText(hwnd)
                    related_windows.append((hwnd, window_title))
            return True

        # 枚举所有顶层窗口
        win32gui.EnumWindows(enum_windows_callback, None)

        logger.debug(f"找到 {len(related_windows)} 个同进程相关窗口")

        for related_hwnd, title in related_windows:
            try:
                # 尝试在相关窗口中搜索
                found, location = _search_in_window(needle_image, confidence, params, related_hwnd)
                if found:
                    logger.info(f"在相关窗口中找到图片: '{title}' (HWND: {related_hwnd})")
                    return True, location, related_hwnd
            except Exception as e:
                logger.debug(f"搜索相关窗口 {related_hwnd} 时发生错误: {e}")
                continue

        return False, None, None

    except Exception as e:
        logger.error(f"相关窗口搜索时发生错误: {e}")
        return False, None, None

def _search_top_level_windows(needle_image: np.ndarray, confidence: float, params: Dict[str, Any]) -> Tuple[bool, Optional[Tuple[int, int, int, int]], Optional[int]]:
    """
    搜索所有顶层窗口
    """
    if not PYWIN32_AVAILABLE:
        return False, None, None

    try:
        top_windows = []

        def enum_windows_callback(hwnd, param):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                # 过滤掉一些系统窗口
                if window_title and not window_title.startswith('Program Manager'):
                    top_windows.append((hwnd, window_title))
            return True

        # 枚举所有顶层窗口
        win32gui.EnumWindows(enum_windows_callback, None)

        logger.debug(f"找到 {len(top_windows)} 个顶层窗口")

        # 按窗口Z序排序，优先搜索前台窗口
        try:
            foreground_hwnd = win32gui.GetForegroundWindow()
            top_windows.sort(key=lambda x: 0 if x[0] == foreground_hwnd else 1)
        except:
            pass

        for window_hwnd, title in top_windows:
            try:
                # 尝试在顶层窗口中搜索
                found, location = _search_in_window(needle_image, confidence, params, window_hwnd)
                if found:
                    logger.info(f"在顶层窗口中找到图片: '{title}' (HWND: {window_hwnd})")
                    return True, location, window_hwnd
            except Exception as e:
                logger.debug(f"搜索顶层窗口 {window_hwnd} 时发生错误: {e}")
                continue

        return False, None, None

    except Exception as e:
        logger.error(f"顶层窗口搜索时发生错误: {e}")
        return False, None, None

def _search_in_window(needle_image: np.ndarray, confidence: float, params: Dict[str, Any], target_hwnd: int) -> Tuple[bool, Optional[Tuple[int, int, int, int]]]:
    """
    在指定窗口中搜索图片
    """
    if not PYWIN32_AVAILABLE:
        return False, None

    try:
        # 获取窗口截图
        from utils.win32_utils import capture_window_background
        screenshot_img = capture_window_background(target_hwnd)

        if screenshot_img is None:
            return False, None

        # 预处理截图
        try:
            import importlib
            preprocessing_module = importlib.import_module('utils.image_preprocessing')
            apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
            haystack_processed = apply_preprocessing(screenshot_img, params)
        except (ImportError, ModuleNotFoundError, AttributeError):
            haystack_processed = screenshot_img
            if len(screenshot_img.shape) == 3 and screenshot_img.shape[2] == 4:
                haystack_processed = cv2.cvtColor(screenshot_img, cv2.COLOR_BGRA2BGR)

        if haystack_processed is None:
            return False, None

        # 检查尺寸
        template_h, template_w = needle_image.shape[:2]
        screenshot_h, screenshot_w = haystack_processed.shape[:2]

        if screenshot_h < template_h or screenshot_w < template_w:
            return False, None

        # 执行图片匹配
        match_method = cv2.TM_CCOEFF_NORMED
        result_matrix = cv2.matchTemplate(haystack_processed, needle_image, match_method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result_matrix)

        if max_val >= confidence:
            # 找到图片
            top_left_x, top_left_y = max_loc
            location = (top_left_x, top_left_y, template_w, template_h)
            logger.debug(f"在窗口 {target_hwnd} 中找到图片，匹配分数: {max_val:.4f}")
            return True, location
        else:
            logger.debug(f"在窗口 {target_hwnd} 中未找到图片，匹配分数: {max_val:.4f}")
            return False, None

    except Exception as e:
        logger.debug(f"在窗口 {target_hwnd} 中搜索时发生错误: {e}")
        return False, None

# 旧的DPI处理函数已移除，现在使用统一DPI处理器