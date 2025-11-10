import time
import logging
import sys
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 任务类型标识
TASK_TYPE = "旋转视角"


def _handle_success(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if action == '跳转到步骤':
        return True, '跳转到步骤', jump_id
    elif action == '停止工作流':
        return True, '停止工作流', None
    elif action == '继续执行本步骤':
        return True, '继续执行本步骤', card_id
    else:  # 执行下一步
        return True, '执行下一步', None


def _handle_failure(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if action == '跳转到步骤':
        return False, '跳转到步骤', jump_id
    elif action == '停止工作流':
        return False, '停止工作流', None
    elif action == '继续执行本步骤':
        return False, '继续执行本步骤', card_id
    else:  # 执行下一步
        return False, '执行下一步', None

# Try importing necessary libraries, provide guidance if missing
try:
    # 前台模式使用Interception驱动，不再使用pyautogui
    from utils.interception_driver import get_driver
    # --- ADDED: Imports for background mode ---
    import win32gui
    import win32api
    import win32con
    # import ctypes # Not needed if not using background SendMessage drag
    # from ctypes import wintypes # For RECT, not needed if rect comes from executor
    PYWIN32_AVAILABLE = True
    INTERCEPTION_AVAILABLE = True
    # ----------------------------------------
except ImportError:
    # --- MODIFIED: Simplified error message slightly ---
    print("错误：缺少必要的库。请运行 'pip install pywin32' 并确保Interception驱动可用。")
    PYWIN32_AVAILABLE = False
    INTERCEPTION_AVAILABLE = False

# Optional: Import OpenCV if needed for more advanced image recognition
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True

    def safe_imread(image_path, flags=cv2.IMREAD_COLOR):
        """安全的图像读取函数，支持中文路径"""
        try:
            # 使用numpy fromfile + imdecode处理中文路径
            img_array = np.fromfile(image_path, dtype=np.uint8)
            if len(img_array) > 0:
                img = cv2.imdecode(img_array, flags)
                if img is not None:
                    return img

            # 备选方法：直接读取
            img = cv2.imread(image_path, flags)
            if img is not None:
                return img

            return None
        except Exception as e:
            logger.error(f"安全图像读取失败 {image_path}: {e}")
            return None

except ImportError:
    cv2 = None
    np = None
    CV2_AVAILABLE = False
    # Log warning if OpenCV is needed for image recognition
    logger.warning("OpenCV (opencv-python) 未安装，图像识别功能将不可用。")

    def safe_imread(image_path, flags=None):
        """OpenCV不可用时的占位函数"""
        logger.error("OpenCV不可用，无法读取图像")
        return None

# --- REMOVED: Background capture utility import (not used) ---
# from utils.win32_utils import capture_window_background
# -----------------------------------------------------------

# Moved get_params_definition out of the class
def get_params_definition() -> List[Dict[str, Any]]:
    # Use raw string (r"...") or double backslashes (\\) for paths in tooltips if needed
    # Example: tooltip: r"C:\path\to\something"
    # Or: tooltip: "C:\\path\\to\\something"
    # Assuming current tooltips don't contain problematic backslashes, focus on docstring format.
    """定义任务所需的参数。"""
    base_params = [
        # 旋转参数
        {"type": "separator", "label": "旋转参数"},
        {
            "name": "mouse_button",
            "type": "combo",
            "label": "使用鼠标按键",
            "options": ["左键", "右键", "中键"], # Added Middle
            "default": "左键", # Changed default to Left
            "tooltip": "按住哪个鼠标按键进行拖动。"
        },
        {
            "name": "direction",
            "type": "combo",
            "label": "旋转方向",
            "options": ["向上", "向下", "向左", "向右"],
            "default": "向右",
            "tooltip": "鼠标拖动的方向。"
        },
        {
            "name": "distance",
            "type": "int",
            "label": "拖动距离 (像素)", # Changed label
            "default": 100,
            "min": 1,
            "tooltip": "模拟拖动时鼠标移动的总像素距离。"
        },
        # --- REMOVED repetitions --- 
        # {
        #     "name": "repetitions",
        #     "type": "int",
        #     "label": "重复次数",
        #     "default": 5,
        #     "min": 1,
        #     "tooltip": "执行拖动操作的总次数。"
        # },
        # --- REMOVED delay_between_reps --- 
        # {
        #     "name": "delay_between_reps",
        #     "type": "float",
        #     "label": "每次重复间隔 (秒)",
        #     "default": 0.1,
        #     "min": 0.0,
        #     "tooltip": "每次拖动操作之间的暂停时间。"
        # },
        # --- ADDED duration --- 
        {
            "name": "duration",
            "type": "float",
            "label": "拖拽持续时间 (秒)",
            "default": 0.5,
            "min": 0.01,
            "decimals": 2,
            "tooltip": "完成拖拽动作的总时间。"
        },
        {
            "name": "smoothness",
            "type": "int",
            "label": "平滑度",
            "default": 60,
            "min": 20,
            "max": 120,
            "tooltip": "控制旋转的平滑程度，数值越高越平滑（20-120）。"
        },
        # 图像识别设置
        {"type": "separator", "label": "图像识别设置"},
        {
            "name": "enable_image_recognition",
            "type": "bool",
            "label": "启用图像识别停止",
            "default": False,
            "tooltip": "勾选后，任务会在旋转时查找指定图像，找到即停止。"
        },
        {
            "name": "target_image_path",
            "type": "file", # ParameterDialog 需要支持 'file' 类型
            "label": "目标图像文件",
            "default": "",
            "tooltip": "要查找的图像文件路径。仅在启用图像识别时生效。",
            "condition": {"param": "enable_image_recognition", "value": True} # 条件显示
        },
        {
            "name": "image_confidence",
            "type": "float",
            "label": "图像识别置信度",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "tooltip": "图像匹配的相似度阈值 (0.1 到 1.0)。仅在启用图像识别时生效。",
             "condition": {"param": "enable_image_recognition", "value": True} # 条件显示
        }
    ]

    # 添加预处理参数（仅在启用图像识别时显示）
    try:
        import importlib
        preprocessing_module = importlib.import_module('utils.image_preprocessing')
        get_preprocessing_params = getattr(preprocessing_module, 'get_preprocessing_params')
        preprocessing_params = get_preprocessing_params()

        for param_name, param_def in preprocessing_params.items():
            # 为预处理参数添加条件显示
            param_config = {
                'name': param_name,
                'label': param_def['label'],
                'type': param_def['type'],
                'default': param_def['default'],
                'tooltip': param_def['tooltip'],
                'condition': {"param": "enable_image_recognition", "value": True}  # 只在启用图像识别时显示
            }

            # 复制其他属性
            for key, value in param_def.items():
                if key not in ['label', 'type', 'default', 'tooltip']:
                    if key == 'condition':
                        # 如果原本有条件，需要组合条件
                        param_config['condition'] = [
                            {"param": "enable_image_recognition", "value": True},
                            value
                        ]
                    else:
                        param_config[key] = value

            base_params.append(param_config)
    except ImportError:
        pass

    return base_params

# Define activation helper function (copied for now)
def _activate_window_foreground(target_hwnd: Optional[int], logger):
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

class RotateViewTask:
    r"""
    模拟鼠标拖动以旋转视角，并可选择在过程中识别图像停止。
    尝试支持后台模式（成功率不高）。
    """

    def execute(self,
                parameters: Dict[str, Any], 
                execution_mode: str, # Parameter still received, but ignored
                target_hwnd: Optional[int],
                window_rect: Optional[Tuple[int, int, int, int]]) -> tuple[bool, str, Optional[int]]: # <<< Corrected return type hint
        r"""执行旋转视角任务 (始终使用前台模式)。""" # <<< Updated docstring
        mouse_button_param = parameters.get("mouse_button", "左键")
        direction = parameters.get("direction", "向右")
        distance = parameters.get("distance", 100)
        duration = parameters.get("duration", 0.5)
        enable_recognition = parameters.get("enable_image_recognition", False)
        image_path = parameters.get("target_image_path", "")
        confidence = parameters.get("image_confidence", 0.6)

        # 获取跳转参数
        on_success_action = parameters.get('on_success', '执行下一步')
        success_jump_id = parameters.get('success_jump_target_id')
        on_failure_action = parameters.get('on_failure', '执行下一步')
        failure_jump_id = parameters.get('failure_jump_target_id')
        card_id = parameters.get('card_id')
        
        # --- MODIFIED: Updated log message, removed mode --- 
        logger.info(f"执行旋转视角 (前台模式): 窗口={target_hwnd}, 方向={direction}, 距离={distance}, 持续={duration}s")

        # --- REMOVED Background/Hybrid Mode Execution Block --- 
        # if execution_mode == 'background':
        #     # ... (entire background block deleted) ...
        #     return success, '执行下一步', None
        # --- END REMOVAL ---

        # --- Foreground Mode Execution (Now the only path) --- 
        # Removed the 'else:' and unindented the following block
        logger.debug("执行前台窗口激活检查...")
        activation_success = _activate_window_foreground(target_hwnd, logger)
        if not activation_success:
             logger.warning("无法激活目标窗口，前台旋转视角可能失败或作用于错误窗口。")

        center_x, center_y = None, None
        if window_rect:
            win_left, win_top, win_width, win_height = window_rect
            center_x = win_left + win_width // 2
            center_y = win_top + win_height // 2
            logger.info(f"目标窗口区域: {window_rect}。将在窗口中心 ({center_x}, {center_y}) 进行操作。")
        else:
             # 使用Interception驱动获取屏幕尺寸
             driver = get_driver()
             screen_width, screen_height = driver.get_screen_size()
             center_x, center_y = screen_width // 2, screen_height // 2
             logger.warning("未提供目标窗口区域，将在屏幕中心 ({center_x}, {center_y}) 进行操作。")

        button_type = 'left'
        if mouse_button_param == "右键":
            button_type = "right"
        elif mouse_button_param == "中键":
             button_type = "middle"
        elif mouse_button_param != "左键":
             logger.warning(f"前台模式不支持的鼠标按钮: {mouse_button_param}。将使用左键。")

        # 加载模板图像（如果启用图像识别）
        template_image = None
        if enable_recognition and image_path:
            template_image = safe_imread(image_path)
            if template_image is None:
                logger.error(f"无法加载模板图像: {image_path}")
                return _handle_failure(on_failure_action, failure_jump_id, card_id)

        try:
            # 使用优化的拖拽方法
            success, image_found = self._execute_optimized_drag(
                center_x, center_y, direction, distance, duration,
                button_type, enable_recognition, template_image, confidence
            )

            if not success:
                logger.error("优化拖拽执行失败")
                return _handle_failure(on_failure_action, failure_jump_id, card_id)

            # 处理拖拽结果和图片识别结果
            if enable_recognition and image_path:
                if image_found:
                    logger.info("🎯 拖拽期间成功识别到目标图片!")
                    # 根据识别成功的处理逻辑
                    if on_success_action == "跳转到步骤":
                        return True, on_success_action, success_jump_id
                    else:
                        return True, on_success_action, None
                else:
                    logger.info("拖拽完成，但未识别到目标图片")
                    # 可以选择继续执行或按失败处理
                    if on_failure_action == "跳转到步骤":
                        return True, on_failure_action, failure_jump_id
                    else:
                        return True, on_failure_action, None
            else:
                # 没有启用图片识别，拖拽成功即为成功
                logger.info("拖拽操作成功完成")
                if on_success_action == "跳转到步骤":
                    return True, on_success_action, success_jump_id
                else:
                    return True, on_success_action, None

        except Exception as e:
            logger.exception(f"执行前台旋转视角时出错: {e}")
            try:
                # 前台模式使用驱动，无需手动释放鼠标（驱动会自动处理）
                logger.info("错误处理：已尝试松开鼠标按键。")
            except Exception as release_err:
                logger.error(f"前台模式下尝试释放鼠标按钮时再次出错: {release_err}")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

    def _execute_optimized_drag(self, start_x: int, start_y: int, direction: str,
                               distance: int, duration: float, button: str,
                               enable_recognition: bool, template_image, confidence: float) -> tuple[bool, bool]:
        """执行优化的拖拽操作 - 使用增强拖拽工具"""
        from utils.enhanced_mouse_drag import get_enhanced_drag

        logger.info(f"🚀 开始优化拖拽: 起点({start_x}, {start_y}), 方向={direction}, 距离={distance}, 时长={duration}s")

        # 计算目标坐标
        x_offset, y_offset = 0, 0
        if direction == "向上": y_offset = -distance
        elif direction == "向下": y_offset = distance
        elif direction == "向左": x_offset = -distance
        elif direction == "向右": x_offset = distance

        end_x = start_x + x_offset
        end_y = start_y + y_offset

        # 获取增强拖拽实例
        enhanced_drag = get_enhanced_drag()

        # 选择合适的缓动函数
        easing_func = 'ease_in_out_cubic'  # 更平滑的三次缓动

        # 执行增强拖拽
        try:
            drag_success, image_found = enhanced_drag.drag_with_recognition(
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                duration=duration,
                button=button,
                easing_func=easing_func,
                template_image=template_image if enable_recognition else None,
                confidence=confidence,
                recognition_interval=0.1
            )

            logger.info(f"✅ 增强拖拽完成: 成功={drag_success}, 找到图片={image_found}")
            return drag_success, image_found

        except Exception as e:
            logger.error(f"增强拖拽执行异常: {e}")
            return False, False



# Wrapper function for executor
# <<< MODIFIED: Added window_region (synonym for window_rect) and **kwargs >>>
def execute_task(params: Dict[str, Any], 
                 counters: Dict[str, int], 
                 execution_mode: str, 
                 target_hwnd: Optional[int],
                 window_region: Optional[Tuple[int, int, int, int]], # Renamed from window_rect
                 **kwargs) -> tuple[bool, str, Optional[int]]:
    """执行器调用的包装函数 (始终使用前台模式)。"""
    task_instance = RotateViewTask()
    # Pass window_region instead of window_rect
    return task_instance.execute(params, execution_mode, target_hwnd, window_region)

# Example usage (for testing outside the main app)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s')

    # --- MODIFIED: Updated Test Params --- 
    test_params = {
        "mouse_button": "右键",
        "direction": "向右",
        "distance": 300, # Increased distance
        "duration": 1.0, # Increased duration
        "enable_image_recognition": False, # Set to True and provide path for testing
        "target_image_path": "", # Example: "C:/path/to/your/image.png"
        "image_confidence": 0.9
    }
    # --- Simulate context expected by module-level execute_task --- 
    test_mode = 'foreground'
    test_hwnd = None
    test_window_rect = None # Simulate no rect initially
    target_title_for_test = "计算器" # <<< CHANGE THIS to a real window title for testing
    
    if PYWIN32_AVAILABLE:
        try:
            test_hwnd = win32gui.FindWindow(None, target_title_for_test)
            if test_hwnd:
                # logger.info(f"测试：找到窗口 '{target_title_for_test}' HWND: {test_hwnd}")
                # Get screen coordinates for window_rect
                rect = win32gui.GetWindowRect(test_hwnd)
                test_window_rect = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
                logger.info(f"测试：获取的窗口区域 (屏幕坐标): {test_window_rect}")
            else:
                logger.error(f"测试错误：找不到窗口 '{target_title_for_test}'。")
        except Exception as e:
             logger.exception(f"测试错误：查找窗口句柄或区域时出错: {e}")
    else:
        logger.warning("pywin32 不可用，无法在测试中获取窗口句柄或区域。")
    # ------------------------------------------------------------

    # --- Test the module-level execute_task function --- 
    print("\n--- 调用模块级 execute_task ---")
    time.sleep(2) # Give time to switch window if needed
    success, action, jump_id = execute_task(test_params, {}, test_mode, test_hwnd, test_window_rect) # <<< Now this function is defined
    print(f"\n--- 模块级 execute_task 结果 --- ")
    print(f"  Success: {success}")
    print(f"  Action: {action}")
    print(f"  JumpID: {jump_id}")
    print("--- 测试结束 ---")

# --- REMOVED: Module-level execute_task function definition from here --- 