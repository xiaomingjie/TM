import logging
import time
import math
import os
from typing import Dict, Any, List, Optional, Tuple

# Try importing necessary libraries
try:
    import pyautogui
    import numpy as np
    # Pillow is needed by pyautogui for screenshots, cv2 for processing
    from PIL import Image, ImageGrab # Import ImageGrab for potential fallback/comparison
    import cv2
    import mss # <-- Import mss
    import mss.tools
except ImportError:
    print("错误：缺少必要的库。请运行 'pip install pyautogui numpy opencv-python Pillow mss' 来安装。") # <-- Updated message
    raise

# --- UPDATED: pywin32 imports for background mode ---
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    import ctypes # Needed for PrintWindow
    PYWIN32_AVAILABLE = True
    # --- Define VK Key Map ---
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
        '[':0xDB, '\\\\':0xDC, ']':0xDD, "'":0xDE # Escaped backslash
    }
    # ----------------------
except ImportError:
    PYWIN32_AVAILABLE = False
    VK_CODE = {} # Define as empty if pywin32 not available
    logger = logging.getLogger(__name__)

# 任务类型标识
TASK_TYPE = "找色功能" # Need logger even if pywin32 fails
if not PYWIN32_AVAILABLE:
    logger.warning("pywin32 库未安装，后台模式将不可用。")

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
# ---------------------------------------------

logger = logging.getLogger(__name__)

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

class FindColorTask:
    """
    查找指定颜色区域并控制角色向反方向移动进行躲避。
    (已更新) 可选：先查找指定图片是否存在，根据结果决定是否执行找色躲避逻辑。
    支持前台和后台模式。
    """

    # --- ADDED: Helper method for background capture and cropping ---
    def _capture_and_crop_for_color_search(self, hwnd: int, search_percentage: int) -> Optional[np.ndarray]:
        """
        执行后台截图并根据指定的百分比裁剪中心区域。

        Args:
            hwnd: 目标窗口句柄。
            search_percentage: 从窗口中心算起，用于搜索颜色的区域占窗口宽/高的百分比 (10-100)。

        Returns:
            裁剪后的截图 (NumPy BGR array) 或 None 如果失败。
        """
        if not PYWIN32_AVAILABLE:
            logger.error("(截图裁剪助手) pywin32 不可用。")
            return None
        if not hwnd:
            logger.error("(截图裁剪助手) 无效的窗口句柄。")
            return None
            
        logger.debug(f"(截图裁剪助手) 尝试为 HWND {hwnd} 截图并裁剪 {search_percentage}% 区域...")
        try:
            if capture_window_background is None:
                logger.error("(截图裁剪助手) capture_window_background 函数不可用")
                return None
            full_screenshot = capture_window_background(hwnd) # Use the utility directly
            if full_screenshot is None:
                logger.error("(截图裁剪助手) capture_window_background 返回 None。")
                return None
            
            # --- Cropping Logic (Moved from execute) ---
            full_h, full_w = full_screenshot.shape[:2]
            if full_h == 0 or full_w == 0:
                logger.error("(截图裁剪助手) 获取到的截图尺寸无效。")
                return None
                
            center_x, center_y = full_w // 2, full_h // 2
            search_ratio = max(0.1, min(1.0, search_percentage / 100.0)) # Clamp percentage
            search_half_w = int(center_x * search_ratio)
            search_half_h = int(center_y * search_ratio)

            # Calculate crop coordinates (relative to full screenshot)
            crop_y_start = max(0, center_y - search_half_h)
            crop_y_end = min(full_h, center_y + search_half_h)
            crop_x_start = max(0, center_x - search_half_w)
            crop_x_end = min(full_w, center_x + search_half_w)
            logger.debug(f"(截图裁剪助手) 裁剪坐标 (相对完整截图): y={crop_y_start}:{crop_y_end}, x={crop_x_start}:{crop_x_end}")

            # Perform cropping
            if crop_y_end > crop_y_start and crop_x_end > crop_x_start:
                cropped_screenshot = full_screenshot[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
                logger.info(f"(截图裁剪助手) 裁剪成功，尺寸: {cropped_screenshot.shape}")
                return cropped_screenshot
            else:
                logger.error(f"(截图裁剪助手) 计算得到的裁剪坐标无效 ({crop_y_start}:{crop_y_end}, {crop_x_start}:{crop_x_end})。")
                return None
        except Exception as e:
            logger.exception(f"(截图裁剪助手) 执行截图或裁剪时出错: {e}")
            return None
    # --- END ADDED Helper ---

    @staticmethod
    def get_params_definition() -> List[Dict[str, Any]]:
        """定义任务所需的参数。"""
        base_params = [
            # 颜色设置
            {"type": "separator", "label": "颜色设置"},
            {
                "name": "target_color_input", # Renamed parameter
                "type": "text",
                "label": "目标颜色",
                "default": "255,0,0", # Default RGB (Red)
                "tooltip": "单个颜色：255,0,0 | 多颜色组合：255,0,0;0,255,0;0,0,255 (用分号分隔)",
                "widget_hint": "colorpicker" # Special hint for the UI
            },
            {
                "name": "color_match_mode",
                "type": "select",
                "label": "颜色匹配模式",
                "default": "单颜色精确",
                "options": [
                    "单颜色精确",
                    "多颜色组合",
                    "颜色范围模糊",
                    "智能区域识别"
                ],
                "tooltip": "单颜色精确：传统HSV范围匹配 | 多颜色组合：匹配多个颜色的并集 | 颜色范围模糊：扩大容差范围 | 智能区域识别：基于颜色聚类"
            },
            # --- 添加高级设置复选框 ---
            {
                "name": "show_advanced_color_settings",
                "type": "bool",
                "label": "显示高级颜色设置",
                "default": False,
                "tooltip": "勾选以显示并修改 HSV 容差参数。"
            },
            # --- 修改后的容差参数，增加条件 ---
            {
                "name": "h_tolerance", "type": "int", "label": "色相容差 (H ±)",
                "default": 10, "min": 0, "max": 90, # Max 90, half circle
                "tooltip": "自动转换 HSV 范围时使用的色相 (Hue) 容差。范围: [H-tol, H+tol]",
                # "advanced": True, # Removed
                "condition": {"param": "show_advanced_color_settings", "value": True} # Added condition
            },
            {
                "name": "s_tolerance", "type": "int", "label": "饱和度容差 (S ±)",
                "default": 40, "min": 0, "max": 127,
                "tooltip": "自动转换 HSV 范围时使用的饱和度 (Saturation) 容差。范围: [S-tol, S+tol]",
                # "advanced": True, # Removed
                "condition": {"param": "show_advanced_color_settings", "value": True} # Added condition
            },
            {
                "name": "v_tolerance", "type": "int", "label": "明度容差 (V ±)",
                "default": 40, "min": 0, "max": 127,
                "tooltip": "自动转换 HSV 范围时使用的明度 (Value) 容差。范围: [V-tol, V+tol]",
                # "advanced": True, # Removed
                "condition": {"param": "show_advanced_color_settings", "value": True} # Added condition
            },

            # 搜索设置
            {"type": "separator", "label": "搜索设置"},
            {
                "name": "search_area_percentage",
                "type": "int",
                "label": "搜索区域比例 (%)",
                "default": 60, # Changed from 45 to 60
                "min": 10,
                "max": 100,
                "tooltip": "从窗口中心算起，用于搜索颜色的区域占窗口宽/高的百分比。"
            },
            # --- ADDED Inner Pixel Threshold --- 
            {
                "name": "inner_pixel_threshold",
                "type": "int",
                "label": "内圈触发阈值 (像素)",
                "default": 500, # Changed from 30 to 200
                "min": 1,
                "tooltip": "内圈检测到的颜色像素数量超过此值时，触发移动/停止逻辑。"
            },
            # --- END ADDED ---

            # 角色设置
            {"type": "separator", "label": "角色设置"},
            {
                "name": "use_character_dimensions",
                "type": "bool",
                "label": "考虑角色尺寸", 
                "default": False,
                "tooltip": "勾选以启用并设置角色尺寸参数，用于未来更精确的计算。"
            },
            # -----------------------------------------------------------
            # --- ADDED Character Dimensions ---
            {
                "name": "character_width",
                "type": "int",
                "label": "角色模型宽度 (像素)",
                "default": 180,
                "min": 1,
                "tooltip": "角色的近似宽度，用于未来更精确的计算。",
                # --- ADDED condition ---
                "condition": {"param": "use_character_dimensions", "value": True}
            },
            {
                "name": "character_height",
                "type": "int",
                "label": "角色模型高度 (像素)",
                "default": 150,
                "min": 1,
                "tooltip": "角色的近似高度，用于未来更精确的计算。",
                # --- ADDED condition ---
                "condition": {"param": "use_character_dimensions", "value": True}
            },
            # --- END ADDED ---
            {
                "name": "escape_buffer",
                "type": "int",
                "label": "躲避缓冲距离 (像素)",
                "default": 10,
                "min": 0,
                "tooltip": "角色模型边缘与颜色区域边缘之间保持的额外距离。 (当前简化)"
            },
            {
                "name": "movement_strategy",
                "type": "select",
                "label": "移动策略",
                "default": "远离颜色",
                "options": ["远离颜色", "靠近颜色"],
                "tooltip": "远离颜色：向颜色最少的方向移动（躲避） | 靠近颜色：向颜色最多的方向移动（追踪）"
            },
            {
                "name": "movement_type",
                "type": "combo",
                "label": "移动方式",
                "options": ["按键"], # Start with key press only
                "default": "按键",
                "tooltip": "使用何种方式控制角色移动。"
            },
            # --- ADDED Checkbox to control key visibility ---
            {
                "name": "modify_movement_keys",
                "type": "bool",
                "label": "修改移动按键",
                "default": False,
                "tooltip": "勾选以显示并修改用于移动的按键。",
                "condition": {"param": "movement_type", "value": "按键"} # Only show if movement type is 按键
            },
            # -----------------------------------------------
            # --- Parameters for "按键" movement ---
            {
                "name": "key_up",
                "type": "text",
                "label": "向上移动按键",
                "default": "w",
                "tooltip": "控制角色向上的按键 (例如 'w', 'up')。",
                # --- ADDED condition ---
                "condition": {"param": "modify_movement_keys", "value": True}
            },
            {
                "name": "key_down",
                "type": "text",
                "label": "向下移动按键",
                "default": "s",
                "tooltip": "控制角色向下的按键 (例如 's', 'down')。",
                # --- ADDED condition ---
                "condition": {"param": "modify_movement_keys", "value": True}
            },
            {
                "name": "key_left",
                "type": "text",
                "label": "向左移动按键",
                "default": "a",
                "tooltip": "控制角色向左的按键 (例如 'a', 'left')。",
                # --- ADDED condition ---
                "condition": {"param": "modify_movement_keys", "value": True}
            },
            {
                "name": "key_right",
                "type": "text",
                "label": "向右移动按键",
                "default": "d",
                "tooltip": "控制角色向右的按键 (例如 'd', 'right')。",
                # --- ADDED condition ---
                "condition": {"param": "modify_movement_keys", "value": True}
            },
            # --- ADDED Conditional Image Parameters ---
            {"type": "separator", "label": "(可选) 图片存在条件"},
            {
                "name": "condition_image_path",
                "type": "file",
                "label": "条件图片路径",
                "default": "",
                "required": False,
                "tooltip": "(可选) 指定一个图片文件路径。如果提供了此路径，任务将先查找此图片。"
            },
            {
                "name": "image_confidence",
                "type": "float",
                "label": "图片匹配置信度",
                "default": 0.6,
                "min": 0.1, "max": 1.0, "decimals": 2,
                "tooltip": "图片匹配的相似度阈值 (0.1 - 1.0)。仅当提供了条件图片路径时生效。",
            },
            {
                "name": "on_image_found",
                "type": "select",
                "label": "找到图片时",
                "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
                "default": "继续执行本步骤",
                "tooltip": "找到条件图片后的操作。",
            },
            # --- ADDED widget_hint ---
            {
                "name": "image_found_jump_target_id",
                "type": "int",
                "label": "找到图片跳转ID",
                "required": False,
                "widget_hint": "card_selector", # <<< Specify combo box widget
                "condition": {"param": "on_image_found", "value": "跳转到步骤"} # Show only if jump is selected
            },
            {
                "name": "on_image_not_found",
                "type": "select",
                "label": "未找到图片时",
                "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
                "default": "执行下一步",
                "tooltip": "未找到条件图片时的操作。",
            },
            # --- ADDED widget_hint ---
            {
                "name": "image_not_found_jump_target_id",
                "type": "int",
                "label": "未找到图片跳转ID",
                "required": False,
                "widget_hint": "card_selector", # <<< Specify combo box widget
                "condition": {"param": "on_image_not_found", "value": "跳转到步骤"} # Show only if jump is selected
            }
            # -----------------------------------------
        ]

        # 添加预处理参数（仅在提供条件图片时显示）
        try:
            import importlib
            preprocessing_module = importlib.import_module('utils.image_preprocessing')
            get_preprocessing_params = getattr(preprocessing_module, 'get_preprocessing_params')
            preprocessing_params = get_preprocessing_params()

            for param_name, param_def in preprocessing_params.items():
                # 为预处理参数添加条件显示
                param_config = {
                    'name': param_name,
                    'type': param_def['type'],
                    'label': param_def['label'],
                    'default': param_def['default'],
                    'tooltip': param_def['tooltip'],
                    'condition': {"param": "condition_image_path", "value": "!="} # 只在提供图片路径时显示
                }

                # 复制其他属性
                for key, value in param_def.items():
                    if key not in ['label', 'type', 'default', 'tooltip']:
                        if key == 'condition':
                            # 如果原本有条件，需要组合条件
                            param_config['condition'] = [
                                {"param": "condition_image_path", "value": "!="},
                                value
                            ]
                        else:
                            param_config[key] = value

                base_params.append(param_config)
        except ImportError:
            pass

        return base_params

    # --- ADDED HSV Parameter parsing helper ---
    def _parse_hsv_params(self, params: Dict[str, Any]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """解析字典中的 HSV 参数并返回 NumPy 格式的 lower 和 upper bounds。"""
        try:
            h_min = int(params.get("h_min", 0))
            h_max = int(params.get("h_max", 179))
            s_min = int(params.get("s_min", 0))
            s_max = int(params.get("s_max", 255))
            v_min = int(params.get("v_min", 0))
            v_max = int(params.get("v_max", 255))

            # Clamp values to valid ranges
            h_min = max(0, min(h_min, 179))
            h_max = max(0, min(h_max, 179))
            s_min = max(0, min(s_min, 255))
            s_max = max(0, min(s_max, 255))
            v_min = max(0, min(v_min, 255))
            v_max = max(0, min(v_max, 255))

            lower_bound = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper_bound = np.array([h_max, s_max, v_max], dtype=np.uint8)

            logger.debug(f"解析得到的 HSV 范围: Lower={lower_bound}, Upper={upper_bound}")
            return lower_bound, upper_bound
        except (ValueError, TypeError) as e:
            logger.error(f"解析 HSV 参数时出错: {e}。请检查参数是否为有效的整数。参数: {params}")
            return None
    # --- END ADDED HSV Helper ---

    def _parse_multi_colors(self, color_input: str) -> List[Tuple[int, int, int]]:
        """解析多颜色输入字符串，支持单个颜色或多个颜色组合"""
        colors = []
        try:
            # 分号分隔多个颜色
            color_parts = color_input.split(';')
            for color_str in color_parts:
                color_str = color_str.strip()
                if color_str:
                    parts = [int(c.strip()) for c in color_str.split(',')]
                    if len(parts) == 3 and all(0 <= c <= 255 for c in parts):
                        colors.append(tuple(parts))
                    else:
                        logger.warning(f"无效的颜色格式: '{color_str}'，跳过")

            if not colors:
                logger.warning("未解析到有效颜色，使用默认红色")
                colors = [(255, 0, 0)]

            logger.info(f"解析到 {len(colors)} 个颜色: {colors}")
            return colors
        except Exception as e:
            logger.error(f"解析颜色时出错: {e}，使用默认红色")
            return [(255, 0, 0)]

    def _find_multi_colors_in_area(self,
                                   screenshot_area_bgr: np.ndarray,
                                   target_colors: List[Tuple[int, int, int]],
                                   match_mode: str,
                                   h_tolerance: int = 10,
                                   s_tolerance: int = 40,
                                   v_tolerance: int = 40,
                                   area_tag: str = "区域") -> Tuple[int, Optional[np.ndarray], Optional[Tuple[int, int, int]]]:
        """
        在截图区域中查找多个颜色，支持不同的匹配模式

        Args:
            screenshot_area_bgr: 截图区域 (BGR格式)
            target_colors: 目标颜色列表 [(R,G,B), ...]
            match_mode: 匹配模式
            h_tolerance, s_tolerance, v_tolerance: HSV容差
            area_tag: 区域标签

        Returns:
            Tuple[匹配像素总数, 组合掩码, 平均颜色]
        """
        if screenshot_area_bgr is None or screenshot_area_bgr.size == 0:
            logger.warning(f"({area_tag}检测) 提供的截图区域无效或为空。")
            return 0, None, None

        try:
            combined_mask = None
            total_matches = 0

            if match_mode == "单颜色精确":
                # 只使用第一个颜色
                target_rgb = target_colors[0]
                target_bgr_arr = np.uint8([[target_rgb[::-1]]])
                target_hsv_arr = cv2.cvtColor(target_bgr_arr, cv2.COLOR_BGR2HSV)
                h, s, v = map(int, target_hsv_arr[0][0])

                hsv_lower = np.array([max(0, h-h_tolerance), max(0, s-s_tolerance), max(0, v-v_tolerance)], dtype=np.uint8)
                hsv_upper = np.array([min(179, h+h_tolerance), min(255, s+s_tolerance), min(255, v+v_tolerance)], dtype=np.uint8)

                hsv_image = cv2.cvtColor(screenshot_area_bgr, cv2.COLOR_BGR2HSV)
                combined_mask = cv2.inRange(hsv_image, hsv_lower, hsv_upper)

            elif match_mode == "多颜色组合":
                # 匹配所有颜色的并集
                hsv_image = cv2.cvtColor(screenshot_area_bgr, cv2.COLOR_BGR2HSV)
                masks = []

                for target_rgb in target_colors:
                    target_bgr_arr = np.uint8([[target_rgb[::-1]]])
                    target_hsv_arr = cv2.cvtColor(target_bgr_arr, cv2.COLOR_BGR2HSV)
                    h, s, v = map(int, target_hsv_arr[0][0])

                    hsv_lower = np.array([max(0, h-h_tolerance), max(0, s-s_tolerance), max(0, v-v_tolerance)], dtype=np.uint8)
                    hsv_upper = np.array([min(179, h+h_tolerance), min(255, s+s_tolerance), min(255, v+v_tolerance)], dtype=np.uint8)

                    mask = cv2.inRange(hsv_image, hsv_lower, hsv_upper)
                    masks.append(mask)
                    logger.debug(f"颜色 {target_rgb} 匹配到 {cv2.countNonZero(mask)} 像素")

                # 合并所有掩码
                combined_mask = masks[0]
                for mask in masks[1:]:
                    combined_mask = cv2.bitwise_or(combined_mask, mask)

            elif match_mode == "颜色范围模糊":
                # 扩大容差范围
                expanded_h_tol = min(30, h_tolerance * 2)
                expanded_s_tol = min(80, s_tolerance * 2)
                expanded_v_tol = min(80, v_tolerance * 2)

                return self._find_multi_colors_in_area(
                    screenshot_area_bgr, target_colors, "多颜色组合",
                    expanded_h_tol, expanded_s_tol, expanded_v_tol, area_tag
                )

            elif match_mode == "智能区域识别":
                # 基于颜色聚类的智能识别
                return self._smart_color_clustering(screenshot_area_bgr, target_colors, area_tag)

            if combined_mask is not None:
                total_matches = cv2.countNonZero(combined_mask)
                logger.info(f"[{area_tag}检测] {match_mode}模式找到 {total_matches} 像素。")

                # 计算平均颜色
                average_color_bgr = None
                if total_matches > 0:
                    average_color_bgr_raw = cv2.mean(screenshot_area_bgr, mask=combined_mask)[:3]
                    average_color_bgr = (int(average_color_bgr_raw[0]), int(average_color_bgr_raw[1]), int(average_color_bgr_raw[2]))

                return total_matches, combined_mask, average_color_bgr

        except Exception as e:
            logger.error(f"({area_tag}检测) 多颜色匹配时出错: {e}")

        return 0, None, None

    def _smart_color_clustering(self, screenshot_area_bgr: np.ndarray, target_colors: List[Tuple[int, int, int]], area_tag: str) -> Tuple[int, Optional[np.ndarray], Optional[Tuple[int, int, int]]]:
        """智能颜色聚类识别，适用于复杂场景如道路、草地等"""
        try:
            # 将图像转换为LAB颜色空间，更适合颜色聚类
            lab_image = cv2.cvtColor(screenshot_area_bgr, cv2.COLOR_BGR2LAB)

            # 重塑为像素列表
            pixels = lab_image.reshape(-1, 3).astype(np.float32)

            # 将目标颜色也转换为LAB空间
            target_lab_colors = []
            for rgb_color in target_colors:
                bgr_color = np.uint8([[rgb_color[::-1]]])
                lab_color = cv2.cvtColor(bgr_color, cv2.COLOR_BGR2LAB)[0][0]
                target_lab_colors.append(lab_color)

            # 使用K-means聚类
            k = min(8, len(np.unique(pixels.reshape(-1, 3), axis=0)))  # 最多8个聚类
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
            _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

            # 找到与目标颜色最接近的聚类
            matched_clusters = []
            for target_lab in target_lab_colors:
                min_distance = float('inf')
                best_cluster = -1

                for i, center in enumerate(centers):
                    # 计算LAB空间中的欧几里得距离
                    distance = np.linalg.norm(center - target_lab)
                    if distance < min_distance and distance < 50:  # 距离阈值
                        min_distance = distance
                        best_cluster = i

                if best_cluster != -1 and best_cluster not in matched_clusters:
                    matched_clusters.append(best_cluster)
                    logger.debug(f"目标颜色 {target_colors[target_lab_colors.index(target_lab)]} 匹配到聚类 {best_cluster}，距离: {min_distance:.2f}")

            if not matched_clusters:
                logger.info(f"[{area_tag}检测] 智能聚类未找到匹配的颜色区域")
                return 0, None, None

            # 创建匹配聚类的掩码
            h, w = screenshot_area_bgr.shape[:2]
            combined_mask = np.zeros((h, w), dtype=np.uint8)

            labels_reshaped = labels.reshape(h, w)
            for cluster_id in matched_clusters:
                cluster_mask = (labels_reshaped == cluster_id).astype(np.uint8) * 255
                combined_mask = cv2.bitwise_or(combined_mask, cluster_mask)

            total_matches = cv2.countNonZero(combined_mask)

            # 计算平均颜色
            average_color_bgr = None
            if total_matches > 0:
                average_color_bgr_raw = cv2.mean(screenshot_area_bgr, mask=combined_mask)[:3]
                average_color_bgr = (int(average_color_bgr_raw[0]), int(average_color_bgr_raw[1]), int(average_color_bgr_raw[2]))

            logger.info(f"[{area_tag}检测] 智能聚类找到 {total_matches} 像素，匹配 {len(matched_clusters)} 个聚类")
            return total_matches, combined_mask, average_color_bgr

        except Exception as e:
            logger.error(f"({area_tag}检测) 智能聚类时出错: {e}")
            return 0, None, None

    # --- Renamed and modified for HSV ---
    def _find_color_in_area_hsv(self,
                                screenshot_area_bgr: np.ndarray,
                                hsv_lower: np.ndarray,
                                hsv_upper: np.ndarray,
                                area_tag: str = "区域"
                               ) -> Tuple[int, Optional[np.ndarray], Optional[Tuple[int, int, int]]]:
        """
        在提供的截图区域 (BGR) 中查找指定 HSV 范围内的颜色。

        Args:
            screenshot_area_bgr: 要搜索的截图区域 (NumPy BGR array)。
            hsv_lower: HSV 颜色下界 (NumPy array [H, S, V])。
            hsv_upper: HSV 颜色上界 (NumPy array [H, S, V])。
            area_tag: 用于日志记录的区域标签 (例如 "外层", "内层")。

        Returns:
            Tuple[匹配像素总数, 颜色掩码 (或 None), 平均 BGR 颜色 (或 None)]
        """
        average_color_bgr_tuple = None # Initialize
        color_mask = None # Initialize
        total_match_count = 0 # Initialize

        if screenshot_area_bgr is None or screenshot_area_bgr.size == 0:
            logger.warning(f"({area_tag}检测) 提供的截图区域无效或为空。")
            return 0, None, None

        try:
            # 1. Convert BGR to HSV
            hsv_image = cv2.cvtColor(screenshot_area_bgr, cv2.COLOR_BGR2HSV)

            # 2. Create mask using HSV range
            # Handle Hue wrap-around (e.g., for reds)
            if hsv_lower[0] > hsv_upper[0]:
                # If H_min > H_max, it means the range crosses 0
                # Example: H_min=170, H_max=10 => ranges are [170, 179] and [0, 10]
                hsv_upper_part1 = hsv_upper.copy()
                hsv_upper_part1[0] = 179 # Range 1: [H_min, 179]
                mask1 = cv2.inRange(hsv_image, hsv_lower, hsv_upper_part1)

                hsv_lower_part2 = hsv_lower.copy()
                hsv_lower_part2[0] = 0 # Range 2: [0, H_max]
                mask2 = cv2.inRange(hsv_image, hsv_lower_part2, hsv_upper)

                # Combine the two masks
                color_mask = cv2.bitwise_or(mask1, mask2)
                logger.debug(f"({area_tag}检测) 处理了 H 色相环绕。范围1: [{hsv_lower[0]}, 179], 范围2: [0, {hsv_upper[0]}]")
            else:
                # Normal case where H_min <= H_max
                color_mask = cv2.inRange(hsv_image, hsv_lower, hsv_upper)

            # 3. Count matched pixels
            total_match_count = cv2.countNonZero(color_mask)
            logger.info(f"[{area_tag}检测] 找到 {total_match_count} 像素。")

            # 4. Calculate average BGR color of matched pixels (if any)
            if total_match_count > 0:
                # Use the ORIGINAL BGR image and the generated mask
                average_color_bgr_raw = cv2.mean(screenshot_area_bgr, mask=color_mask)[:3]
                # Convert BGR means to integer tuple (still logging BGR, but derived from HSV mask)
                average_color_bgr_tuple = (int(average_color_bgr_raw[0]), int(average_color_bgr_raw[1]), int(average_color_bgr_raw[2]))
                # Keep RGB conversion for user-friendliness in logs if needed
                average_color_rgb_tuple = (average_color_bgr_tuple[2], average_color_bgr_tuple[1], average_color_bgr_tuple[0])

                logger.info(f"[{area_tag}检测] 匹配到像素的平均颜色 (BGR): {average_color_bgr_tuple} -> (RGB: {average_color_rgb_tuple}) ")

                # --- DEBUG LOGGING (Optional: keep BGR/RGB float/rounded logs if helpful) ---
                average_color_rgb_rounded = (round(average_color_bgr_raw[2]), round(average_color_bgr_raw[1]), round(average_color_bgr_raw[0]))
                raw_bgr_float_str = f"({average_color_bgr_raw[0]:.2f}, {average_color_bgr_raw[1]:.2f}, {average_color_bgr_raw[2]:.2f})"
                logger.info(f"[{area_tag}检测] 匹配像素 {total_match_count} 个。 原始平均 BGR (float): {raw_bgr_float_str}, 截断平均 RGB (int): {average_color_rgb_tuple}, 四舍五入平均 RGB (round): {average_color_rgb_rounded}")
                # --- END DEBUG ---

        except cv2.error as e:
            logger.error(f"({area_tag}检测) OpenCV 处理时出错: {e}")
            return 0, None, None
        except Exception as e:
            logger.exception(f"({area_tag}检测) 查找颜色时发生意外错误: {e}")
            return 0, None, None

        return total_match_count, color_mask, average_color_bgr_tuple
    # --- END Renamed ---

    # --- ADDED: Helper function for background screenshot ---
    def _screenshot_background(self, hwnd: int, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[np.ndarray]:
        """
        Takes a screenshot of a specific window using its handle (HWND) in the background.
        Returns an OpenCV image (NumPy array in RGB) or None if failed.
        Region is relative to the window's client area if provided.
        """
        if not PYWIN32_AVAILABLE:
            logger.error("无法执行后台截图：pywin32 库不可用。")
            return None
        if not hwnd:
             logger.error("无法执行后台截图：无效的窗口句柄 (HWND)。")
             return None

        saveDC = None
        mfcDC = None
        saveBitMap = None
        hwndDC = None

        try:
            hwndDC = win32gui.GetWindowDC(hwnd)
            if not hwndDC:
                 logger.error(f"后台截图错误：无法获取窗口句柄 {hwnd} 的设备上下文 (DC)。")
                 return None
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            if not mfcDC:
                 logger.error(f"后台截图错误：无法从窗口 DC 创建 mfcDC。")
                 return None # hwndDC will be released in finally
            saveDC = mfcDC.CreateCompatibleDC()
            if not saveDC:
                 logger.error(f"后台截图错误：无法创建兼容 DC。")
                 return None # mfcDC, hwndDC released in finally

            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            width = right - left
            height = bottom - top

            if region:
                x, y, w, h = region
                x = max(0, x)
                y = max(0, y)
                w = min(w, width - x)
                h = min(h, height - y)
                if w <= 0 or h <= 0:
                     logger.error(f"后台截图错误：提供的区域 {region} 无效或在窗口客户区之外。")
                     return None # Resources released in finally
                target_width, target_height = w, h
                source_x, source_y = x, y
            else:
                target_width, target_height = width, height
                source_x, source_y = 0, 0

            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, target_width, target_height)
            saveDC.SelectObject(saveBitMap)

            # Use PrintWindow for better compatibility with obscured/offscreen windows
            # PW_CLIENTONLY = 1 (seems unreliable/doesn't work)
            # PW_RENDERFULLCONTENT = 2 (Windows 8.1+) - might be best?
            result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
            logger.debug(f"PrintWindow result: {result}")

            # Fallback to BitBlt if PrintWindow fails (result is 0 on failure)
            if not result:
                # logger.warning("PrintWindow failed (result=0), attempting BitBlt...")
                try:
                    saveDC.BitBlt((0, 0), (target_width, target_height), mfcDC, (source_x, source_y), win32con.SRCCOPY)
                    # logger.info("BitBlt fallback executed.")
                except Exception as bitblt_error:
                    # logger.error(f"BitBlt fallback failed: {bitblt_error}")
                    return None # Resources released in finally


            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)

            im = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1)

            open_cv_image_rgb = np.array(im)
            logger.info(f"后台截图成功，尺寸: {open_cv_image_rgb.shape}")
            return open_cv_image_rgb

        except Exception as e:
            logger.exception(f"后台截图时发生意外错误: {e}")
            return None
        finally:
            # Ensure resources are released
            if saveBitMap:
                try: win32gui.DeleteObject(saveBitMap.GetHandle())
                except: pass
            if saveDC:
                try: saveDC.DeleteDC()
                except: pass
            if mfcDC:
                try: mfcDC.DeleteDC()
                except: pass
            if hwndDC:
                try: win32gui.ReleaseDC(hwnd, hwndDC)
                except: pass
    # -------------------------------------------------------

    # --- MODIFIED: Split into key down and key up ---
    # --- REVERTED to simple PostMessage lParam=0 based on user confirmation ---
    def _press_key_down_background(self, hwnd: int, key: str) -> bool:
        """Sends a key down event using PostMessage with a more standard lParam.""" # Modified docstring
        if not PYWIN32_AVAILABLE or not hwnd:
            logger.error(f"无法后台按下键 '{key}': pywin32 不可用或 HWND 无效 ({hwnd})")
            return False
        key_lower = key.lower()
        vk_code = VK_CODE.get(key_lower)
        if vk_code is None:
            logger.error(f"无法后台按下键：未知键名 '{key}'")
            return False
        try:
            # Construct a more standard lParam for WM_KEYDOWN
            # MAPVK_VK_TO_VSC = 0
            scan_code = win32api.MapVirtualKey(vk_code, 0)
            # lParam format: | 31 | 30 | 29 | 28-24 | 23-16 | 15-0 |
            #               | UP | Prev | --- | ---   | Scan  | Rep |
            # For WM_KEYDOWN: UP=0, Prev=0, Rep=1
            lParam = (scan_code << 16) | 1
            win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lParam)
            logger.debug(f"  后台按下键 (PostMessage, standard lParam): Key='{key}', VK={vk_code}, lParam={lParam}, HWND={hwnd}")
            return True
        except Exception as e:
            logger.exception(f"后台按下键 (PostMessage, standard lParam) '{key}' 时出错: {e}")
            return False

    def _release_key_up_background(self, hwnd: int, key: str) -> bool:
        """Sends a key up event using PostMessage with a more standard lParam.""" # Modified docstring
        if not PYWIN32_AVAILABLE or not hwnd:
            logger.error(f"无法后台松开键 '{key}': pywin32 不可用或 HWND 无效 ({hwnd})")
            return False
        key_lower = key.lower()
        vk_code = VK_CODE.get(key_lower)
        if vk_code is None:
            logger.error(f"无法后台松开键：未知键名 '{key}'")
            return False
        try:
            # Construct a more standard lParam for WM_KEYUP
            # MAPVK_VK_TO_VSC = 0
            scan_code = win32api.MapVirtualKey(vk_code, 0)
            # lParam format: | 31 | 30 | 29 | 28-24 | 23-16 | 15-0 |
            #               | UP | Prev | --- | ---   | Scan  | Rep |
            # For WM_KEYUP: UP=1, Prev=1, Rep=1
            lParam = (1 << 31) | (1 << 30) | (scan_code << 16) | 1
            win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lParam)
            logger.debug(f"  后台松开键 (PostMessage, standard lParam): Key='{key}', VK={vk_code}, lParam={lParam}, HWND={hwnd}")
            return True
        except Exception as e:
            logger.exception(f"后台松开键 (PostMessage, standard lParam) '{key}' 时出错: {e}")
            return False
    # ------------------------------------------------------

    def _calculate_direction_counts_and_ratios(self, mask: np.ndarray, weighted: bool) -> Tuple[Dict[str, int], Dict[str, float]]:
        """计算给定掩码的像素方向分布（计数和比例）。

        Args:
            mask: 输入的二值掩码图像。
            weighted: 是否对内层区域使用加权计算（远处像素权重为2）。

        Returns:
            一个元组，包含两个字典：
            - direction_counts: 每个方向 ('up', 'down', 'left', 'right') 的（加权）像素计数。
            - direction_ratios: 每个方向的像素比例 (0-1)。
        """
        counts = {'up': 0, 'down': 0, 'left': 0, 'right': 0}
        ratios = {'up': 0.25, 'down': 0.25, 'left': 0.25, 'right': 0.25} # Default
        total_pixels = mask.size
        if total_pixels == 0:
            return counts, ratios

        height, width = mask.shape[:2]
        half_height = height // 2
        half_width = width // 2
        quarter_height = height // 4
        quarter_width = width // 4

        total_weighted_matches = 0

        if weighted:
            # 内层加权逻辑 (near=1, far=2)
            areas = {
                'up': {'near': mask[quarter_height:half_height, :], 'far': mask[:quarter_height, :]},
                'down': {'near': mask[half_height:(half_height + quarter_height), :], 'far': mask[(half_height + quarter_height):, :]},
                'left': {'near': mask[:, quarter_width:half_width], 'far': mask[:, :quarter_width]},
                'right': {'near': mask[:, half_width:(half_width + quarter_width)], 'far': mask[:, (half_width + quarter_width):]}
            }
            for direction, parts in areas.items():
                near_matches = cv2.countNonZero(parts['near'])
                far_matches = cv2.countNonZero(parts['far'])
                weighted_matches = near_matches + far_matches * 2
                counts[direction] = weighted_matches
                total_weighted_matches += weighted_matches
            if total_weighted_matches > 0:
                for direction in counts:
                    ratios[direction] = counts[direction] / total_weighted_matches
        else:
            # 外层简单逻辑 (按半分割)
            masks_parts = {
                'up': mask[:half_height, :],
                'down': mask[half_height:, :],
                'left': mask[:, :half_width],
                'right': mask[:, half_width:]
            }
            total_matches = 0
            for direction, mask_part in masks_parts.items():
                count = cv2.countNonZero(mask_part)
                counts[direction] = count
                total_matches += count
            if total_matches > 0:
                for direction in counts:
                    ratios[direction] = counts[direction] / total_matches

        return counts, ratios

    def execute(self,
                parameters: Dict[str, Any],
                counters: Dict[str, int],
                execution_mode: str,
                target_hwnd: Optional[int],
                window_region: Optional[Tuple[int, int, int, int]] = None,
                get_image_data=None,
                stop_checker=None) -> Tuple[bool, str, Optional[int]]:
        """
        主执行逻辑。
        (已更新) 使用 HSV 颜色空间进行检测。
        (已更新) 先检查条件图片（如果提供）。
        """
        current_card_id = parameters.get('__current_card_id__', '未知') # Get current card ID if passed
        # 执行模式中文映射
        mode_names = {'foreground': '前台', 'background': '后台'}
        mode_name = mode_names.get(execution_mode, execution_mode)
        logger.info(f"执行找色任务: 模式={mode_name}, 窗口={target_hwnd}")
        logger.debug(f"任务接收到的完整参数: {parameters}")

        # --- 新的多颜色参数解析 ---
        target_color_str = parameters.get("target_color_input", "255,0,0")
        color_match_mode = parameters.get("color_match_mode", "单颜色精确")
        h_tolerance = int(parameters.get("h_tolerance", 10))
        s_tolerance = int(parameters.get("s_tolerance", 40))
        v_tolerance = int(parameters.get("v_tolerance", 40))

        # 解析多颜色输入
        target_colors = self._parse_multi_colors(target_color_str)
        logger.info(f"颜色匹配模式: {color_match_mode}, 目标颜色: {target_colors}")

        # 兼容旧的HSV参数（如果UI提供了预计算的HSV范围）
        h_min = parameters.get("h_min")
        h_max = parameters.get("h_max")
        s_min = parameters.get("s_min")
        s_max = parameters.get("s_max")
        v_min = parameters.get("v_min")
        v_max = parameters.get("v_max")

        # 初始化HSV变量
        hsv_lower = None
        hsv_upper = None

        use_legacy_hsv = all(p is not None for p in [h_min, h_max, s_min, s_max, v_min, v_max])
        if use_legacy_hsv and color_match_mode == "单颜色精确":
            try:
                hsv_lower = np.array([int(h_min), int(s_min), int(v_min)], dtype=np.uint8)
                hsv_upper = np.array([int(h_max), int(s_max), int(v_max)], dtype=np.uint8)
                logger.info("使用 UI 提供的预计算 HSV 范围（兼容模式）")
                # 为了兼容，将HSV转换回RGB用于新的多颜色系统
                target_colors = [(255, 0, 0)]  # 使用默认颜色，实际匹配由HSV范围控制
            except (ValueError, TypeError):
                logger.warning("提供的 HSV 参数无效，使用新的多颜色系统")
                use_legacy_hsv = False
        else:
            use_legacy_hsv = False

        # --- End 新的多颜色参数解析 ---

        # Parse other parameters
        search_percentage = int(parameters.get("search_area_percentage", 60))
        movement_type = parameters.get("movement_type", "按键")
        movement_strategy = parameters.get("movement_strategy", "远离颜色")
        key_up = parameters.get("key_up", "w")
        key_down = parameters.get("key_down", "s")
        key_left = parameters.get("key_left", "a")
        key_right = parameters.get("key_right", "d")
        # --- USE PARAMETER for inner threshold --- 
        inner_min_pixel_count = int(parameters.get("inner_pixel_threshold", 200))
        # inner_threshold_percentage = 0.3 # Percentage of inner ring area for movement threshold (REMOVED, using pixel count)
        # --- END USE PARAMETER --- 
        image_path = parameters.get("condition_image_path", "")
        image_confidence = float(parameters.get("image_confidence", 0.6))
        on_image_found_action = parameters.get("on_image_found", "继续执行本步骤")
        image_found_jump_id_str = parameters.get("image_found_jump_target_id")
        on_image_not_found_action = parameters.get("on_image_not_found", "执行下一步")
        image_not_found_jump_id_str = parameters.get("image_not_found_jump_target_id")
        # ------------------------

        # Validate window handle for background mode
        if execution_mode == 'background' and (not target_hwnd or (PYWIN32_AVAILABLE and not win32gui.IsWindow(target_hwnd))):
             logger.error(f"后台模式需要有效的目标窗口句柄 (HWND), 但收到 {target_hwnd}。")
             return False, "窗口无效", None

        # Get window rectangle (required for background, optional for foreground)
        window_rect = None
        if execution_mode == 'background' and target_hwnd:
             # Use cached window_region if provided by executor, otherwise get it
             if window_region and len(window_region) == 4:
                 # Ensure it's client coordinates if possible (may need adjustment)
                 # Assuming executor provides screen coords, let's get client rect for BitBlt size
                  try:
                      left, top, right, bottom = win32gui.GetClientRect(target_hwnd)
                      width = right - left
                      height = bottom - top
                      client_left, client_top = win32gui.ClientToScreen(target_hwnd, (0, 0))
                      window_rect = (client_left, client_top, width, height) # Screen coords of top-left, plus width/height
                      logger.info(f"通过 HWND 获取窗口区域 (屏幕坐标): {window_rect}")
                  except Exception as e:
                      logger.error(f"通过 HWND 获取窗口客户区失败: {e}, 无法执行后台截图。")
                      return False, "窗口无效", None
             else:
                 logger.warning("后台模式未收到窗口区域 (window_rect)，尝试通过 HWND 获取...")
                 try:
                      # --- 正确缩进 ---
                      left, top, right, bottom = win32gui.GetClientRect(target_hwnd)
                      width = right - left
                      height = bottom - top
                      client_left, client_top = win32gui.ClientToScreen(target_hwnd, (0, 0))
                      window_rect = (client_left, client_top, width, height) # Screen coords of top-left, plus width/height
                      # --- 正确缩进 logger.info ---
                      logger.info(f"通过 HWND 获取窗口区域 (屏幕坐标): {window_rect}")
                 # --- except 与 try 对齐 ---
                 except Exception as e:
                      # --- 正确缩进 ---
                      logger.error(f"通过 HWND 获取窗口客户区失败: {e}, 无法执行后台截图。")
                      return False, "窗口无效", None

         # --- Define Search Areas based on mode and rect ---
        screen_w, screen_h = 0, 0
        outer_search_region = None # Initialize
        if execution_mode == 'foreground':
            screen_w, screen_h = pyautogui.size()
            # For foreground, calculate search region based on primary monitor size
            center_x, center_y = screen_w // 2, screen_h // 2
            search_ratio = max(0.1, min(1.0, search_percentage / 100.0))
            search_half_w = int(center_x * search_ratio)
            search_half_h = int(center_y * search_ratio)
            outer_search_region = (
                center_x - search_half_w, center_y - search_half_h,
                search_half_w * 2, search_half_h * 2
            )
            logger.info(f"查找颜色: {target_colors} (模式: {color_match_mode}) 于外层屏幕区域: {outer_search_region}")
        elif execution_mode == 'background' and window_rect:
            win_x, win_y, win_w, win_h = window_rect
            screen_w, screen_h = win_w, win_h # Use window dimensions for background
            # Background mode uses coordinates relative to the window (handled by capture/crop helper)
            logger.info(f"查找颜色: {target_colors} (模式: {color_match_mode}) 于外层窗口区域 (通过截图助手裁剪 {search_percentage}%)")
            outer_search_region = None # Not needed directly, handled by helper
        else:
            logger.error("无法确定搜索区域。")
            return False, "配置错误", None
        # -------------------------------------------------

        # --- Optional Image Condition Check ---
        image_check_passed = False # Assume it needs to pass or is not used
        image_check_performed = False
        if image_path and os.path.exists(image_path):
            image_check_performed = True
            logger.info(f"条件图片检查: 路径 '{image_path}'")
            try:
                # --- MODIFIED: Use imdecode for path handling ---
                # template = cv2.imread(image_path, cv2.IMREAD_COLOR)
                img_bytes = np.fromfile(image_path, dtype=np.uint8)
                template = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
                # --- END MODIFICATION ---

                if template is None:
                    logger.warning(f"无法加载条件图片 (imdecode 失败): '{image_path}'")
                    image_check_passed = False # Treat as not found if load fails
                else:
                    logger.debug(f"加载条件图片成功, 尺寸: {template.shape[:2]}")
                    screenshot_for_image = None
                    location = None
                    max_val = 0

                    # --- 工具 统一使用后台识别方法 ---
                    # 不再区分前台后台模式，统一使用后台识别方法以提高稳定性和准确性
                    logger.debug("统一使用后台识别方法进行条件图片查找...")
                    if target_hwnd:
                        screenshot_for_image = capture_window_background(target_hwnd) # Capture full client area
                        if screenshot_for_image is None:
                             logger.warning("统一后台截图失败，无法进行条件图片查找。")
                             image_check_passed = False # Treat as not found
                        else:
                             logger.debug(f"统一后台截图成功，尺寸: {screenshot_for_image.shape}")
                    else:
                        logger.warning("缺少窗口句柄，无法进行统一后台截图。")
                        image_check_passed = False

                    if screenshot_for_image is not None:
                        # 应用预处理
                        try:
                            import importlib
                            preprocessing_module = importlib.import_module('utils.image_preprocessing')
                            apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                            processed_template = apply_preprocessing(template, parameters)
                            processed_screenshot = apply_preprocessing(screenshot_for_image, parameters)
                        except (ImportError, ModuleNotFoundError, AttributeError):
                            processed_template = template
                            processed_screenshot = screenshot_for_image

                        if processed_template is not None and processed_screenshot is not None:
                            result = cv2.matchTemplate(processed_screenshot, processed_template, cv2.TM_CCOEFF_NORMED)
                            _, max_val, _, max_loc = cv2.minMaxLoc(result)
                            logger.debug(f"{execution_mode} 图片匹配最大置信度: {max_val:.4f} (阈值: {image_confidence})")
                        else:
                            max_val = 0.0
                            max_loc = (0, 0)

                        if max_val >= image_confidence:
                            image_check_passed = True
                            h, w = template.shape[:2]
                            # Convert location if needed (max_loc is relative to screenshot_for_image)
                            # For background, max_loc IS client area coordinates.
                            # For foreground, max_loc IS screen coordinates.
                            location = max_loc
                            logger.info(f"{execution_mode} 找到条件图片! 位置 (截图内坐标): {location}, 置信度: {max_val:.4f}")
                        else:
                            image_check_passed = False
                            logger.info(f"{execution_mode} 未找到条件图片 (置信度 {max_val:.4f} < {image_confidence})。")
                        # --- REMOVED Misplaced except block ---
            # --- 正确缩进 except, 使其与 try (line 896) 对齐 ---
            except Exception as e:
                logger.exception(f"执行条件图片查找时出错: {e}")
                image_check_passed = False # Treat as not found on error
        elif image_path:
            logger.warning(f"条件图片路径 '{image_path}' 不存在，跳过检查。")
            image_check_performed = True
            image_check_passed = False # File not found means image not found

        # --- Decide Action Based on Image Check ---
        if image_check_performed:
            action = on_image_found_action if image_check_passed else on_image_not_found_action
            jump_id_str = image_found_jump_id_str if image_check_passed else image_not_found_jump_id_str
            jump_id = safe_parse_jump_id(jump_id_str)

            logger.info(f"图片 {'找到' if image_check_passed else '未找到'}，执行操作: '{action}'")

            if action == '执行下一步':
                return True, action, None # Standard success, continue sequence
            elif action == '跳转到步骤':
                if jump_id is not None:
                    return True, action, jump_id
                else:
                    logger.warning(f"动作是 '跳转到步骤' 但目标 ID 无效 ({jump_id_str})，将执行下一步。")
                    return True, '执行下一步', None
            elif action == '停止工作流':
                return False, action, None # Stop the workflow
            elif action == '继续执行本步骤':
                logger.info("继续执行找色躲避逻辑 (因图片条件为 '继续执行本步骤')...")
                pass # Fall through to color detection logic
            else: # Should not happen with validation
                logger.warning(f"未知的图片条件动作: {action}。将执行下一步。")
                return True, '执行下一步', None
        # --- End Image Condition Check ---

        # --- Main Color Detection Logic ---
        outer_screenshot_bgr = None
        if execution_mode == 'foreground':
            try:
                _activate_window_foreground(target_hwnd, logger) # Ensure active for foreground
                time.sleep(0.1)
                outer_screenshot_pil = pyautogui.screenshot(region=outer_search_region)
                outer_screenshot_bgr = cv2.cvtColor(np.array(outer_screenshot_pil), cv2.COLOR_RGB2BGR)
            # --- 正确缩进 except, 使其与 try (line 984) 对齐 ---
            except Exception as e:
                logger.exception(f"前台截图失败: {e}")
                return False, "截图失败", None
        elif execution_mode == 'background' and target_hwnd:
            # Use the helper for background capture and crop
            outer_screenshot_bgr = self._capture_and_crop_for_color_search(target_hwnd, search_percentage)
            if outer_screenshot_bgr is None:
                logger.error("后台截图或裁剪失败，无法进行颜色检测。")
                return False, "截图失败", None

        if outer_screenshot_bgr is None:
             logger.error(f"未能获取用于颜色查找的截图 ({execution_mode} 模式)。")
             return False, "截图失败", None

        logger.debug(f"(颜色查找) 使用的截图实际尺寸: H={outer_screenshot_bgr.shape[0]}, W={outer_screenshot_bgr.shape[1]}")

        # 执行颜色搜索 - 使用新的多颜色匹配或兼容旧的HSV方式
        if use_legacy_hsv and hsv_lower is not None and hsv_upper is not None:
            # 兼容旧的HSV方式
            outer_total_match_count, outer_color_mask_full, _ = self._find_color_in_area_hsv(
                outer_screenshot_bgr, hsv_lower, hsv_upper, "外层"
            )
        else:
            # 使用新的多颜色匹配
            outer_total_match_count, outer_color_mask_full, _ = self._find_multi_colors_in_area(
                outer_screenshot_bgr, target_colors, color_match_mode,
                h_tolerance, s_tolerance, v_tolerance, "外层"
            )

        # === Main Logic Branch: Outer Color Found? === # --- 修正缩进: 整体左移一层 ---
        if outer_total_match_count > 0: # --- 修正缩进 ---
            logger.info("外层区域找到目标颜色。计算最优方向并检查内层...")

            # --- COMMENTED OUT: Debug Save intermediate images ---
            # # --- UNCOMMENTED DEBUG IMAGE SAVING START ---
            # debug_counter_key = f"__find_color_debug_save_counter_{current_card_id}"
            # save_counter = counters.get(debug_counter_key, 0) + 1
            # counters[debug_counter_key] = save_counter
            # try:
            #     save_path_outer_crop = f"_debug_outer_cropped_{save_counter}.png"
            #     save_path_outer_mask = f"_debug_outer_mask_{save_counter}.png"
            #     # Outer cropped screenshot (already BGR)
            #     if outer_screenshot_bgr is not None and cv2.imwrite(save_path_outer_crop, outer_screenshot_bgr):
            #         logger.debug(f"调试图片已保存: {save_path_outer_crop}")
            #     else: logger.warning(f"保存调试图片失败: {save_path_outer_crop}")
            #     # Outer mask
            #     if outer_color_mask_full is not None and cv2.imwrite(save_path_outer_mask, outer_color_mask_full):
            #         logger.debug(f"调试图片已保存: {save_path_outer_mask}")
            #     else: logger.warning(f"保存调试图片失败: {save_path_outer_mask}")
            # except Exception as e:
            #     logger.warning(f"保存外层调试图片时出错: {e}", exc_info=False) # Keep log concise
            # # --- UNCOMMENTED DEBUG IMAGE SAVING END ---
            # --- END COMMENTED OUT ---

            # --- Calculate Optimal Direction (Based on Outer Ring) ---
            direction_counts, direction_ratios = self._calculate_direction_counts_and_ratios(
                outer_color_mask_full, weighted=False # Keep weighted=False for now
            )
            logger.debug(f"外层颜色分布比例: Up={direction_ratios.get('up', 0):.2f}, Down={direction_ratios.get('down', 0):.2f}, Left={direction_ratios.get('left', 0):.2f}, Right={direction_ratios.get('right', 0):.2f}")

            # 根据移动策略选择目标方向
            target_directions = set()
            if direction_counts: # Ensure there are counts
                if movement_strategy == "远离颜色":
                    # 选择颜色最少的方向（原逻辑）
                    min_count = min(direction_counts.values()) if direction_counts else 0
                    target_directions = {k for k, v in direction_counts.items() if v == min_count}
                    strategy_desc = "颜色最少"
                elif movement_strategy == "靠近颜色":
                    # 选择颜色最多的方向（新逻辑）
                    max_count = max(direction_counts.values()) if direction_counts else 0
                    target_directions = {k for k, v in direction_counts.items() if v == max_count}
                    strategy_desc = "颜色最多"
                else:
                    # 默认远离颜色
                    min_count = min(direction_counts.values()) if direction_counts else 0
                    target_directions = {k for k, v in direction_counts.items() if v == min_count}
                    strategy_desc = "颜色最少(默认)"

                # 智能方向选择优化
                if len(target_directions) > 2:
                    # 如果有超过2个方向都符合条件，优先选择对角线组合
                    vertical_dirs = {'up', 'down'} & target_directions
                    horizontal_dirs = {'left', 'right'} & target_directions

                    if vertical_dirs and horizontal_dirs:
                        # 选择一个垂直方向和一个水平方向组成对角线
                        target_directions = {list(vertical_dirs)[0], list(horizontal_dirs)[0]}
                        logger.debug(f"优化为对角线移动: {target_directions}")
                    elif len(target_directions) == 4:
                        # 如果四个方向都相等，根据策略选择默认方向
                        if movement_strategy == "靠近颜色":
                            target_directions = {'up', 'right'}  # 靠近时向右上
                        else:
                            target_directions = {'down', 'left'}  # 远离时向左下
                        logger.debug(f"四方向相等，{movement_strategy}策略选择: {target_directions}")

            # --- 方向到按键的映射 ---
            direction_to_key_map_direct = {'up': key_up, 'down': key_down, 'left': key_left, 'right': key_right}
            # --- 调试日志 ---
            logger.debug(f"    [Move Calc Debug] target_directions: {target_directions}")
            logger.debug(f"    [Move Calc Debug] direction_to_key_map_direct: {direction_to_key_map_direct}")
            # --- END ADDED ---
            keys_to_press = {direction_to_key_map_direct[d] for d in target_directions if d in direction_to_key_map_direct}
            # --- 调试日志 ---
            logger.debug(f"    [Move Calc Debug] keys_to_press calculated: {keys_to_press}")
            # --- END ADDED ---

            # --- 更新日志信息 ---
            logger.info(f"{strategy_desc}区域方向: {target_directions}, {movement_strategy}策略计算得到移动方向键: {keys_to_press if keys_to_press else '无'}")
            # --- END UPDATED LOG ---
            # --- END Direction Calculation ---

            # --- Inner Ring Check ---
            h, w = outer_screenshot_bgr.shape[:2]
            inner_ring_thickness_ratio = 0.25 # Define how thick the inner ring is (e.g., 25% of half-width/height)

            inner_left = int(w * inner_ring_thickness_ratio)
            inner_right = int(w * (1 - inner_ring_thickness_ratio))
            inner_top = int(h * inner_ring_thickness_ratio)
            inner_bottom = int(h * (1 - inner_ring_thickness_ratio))

            # Crop the inner region from the original outer screenshot BGR
            inner_screenshot_bgr = outer_screenshot_bgr[inner_top:inner_bottom, inner_left:inner_right]

            # 在内层区域执行颜色搜索
            if use_legacy_hsv and hsv_lower is not None and hsv_upper is not None:
                # 兼容旧的HSV方式
                inner_match_count, inner_color_mask, _ = self._find_color_in_area_hsv(
                    inner_screenshot_bgr, hsv_lower, hsv_upper, "内层"
                )
            else:
                # 使用新的多颜色匹配
                inner_match_count, inner_color_mask, _ = self._find_multi_colors_in_area(
                    inner_screenshot_bgr, target_colors, color_match_mode,
                    h_tolerance, s_tolerance, v_tolerance, "内层"
                )

            # --- COMMENTED OUT: Debug Save inner images ---
            # # --- UNCOMMENTED DEBUG IMAGE SAVING START ---
            # # Retrieve save_counter calculated earlier, assuming outer block was executed
            # # If outer block might be skipped, this needs adjustment (but currently it's not)
            # save_counter = counters.get(f"__find_color_debug_save_counter_{current_card_id}", 0)
            # try:
            #     if save_counter > 0: # Only save if outer images were attempted
            #         save_path_inner_crop = f"_debug_inner_cropped_{save_counter}.png"
            #         save_path_inner_mask = f"_debug_inner_mask_{save_counter}.png"
            #         if inner_screenshot_bgr is not None and cv2.imwrite(save_path_inner_crop, inner_screenshot_bgr):
            #             logger.debug(f"调试图片已保存: {save_path_inner_crop}")
            #         else: logger.warning(f"保存调试图片失败: {save_path_inner_crop}")
            #         if inner_color_mask is not None and cv2.imwrite(save_path_inner_mask, inner_color_mask):
            #             logger.debug(f"调试图片已保存: {save_path_inner_mask}")
            #         else: logger.warning(f"保存调试图片失败: {save_path_inner_mask}")
            # except Exception as e:
            #     logger.warning(f"保存内层调试图片时出错: {e}", exc_info=False)
            # # --- UNCOMMENTED DEBUG IMAGE SAVING END ---
            # --- END COMMENTED OUT ---

            # Decide whether to move based on inner ring color presence
            # --- USE PARAMETER for threshold comparison --- 
            threshold_pixels = inner_min_pixel_count # Use the parameter value
            # --- END USE PARAMETER --- 

            if inner_match_count > threshold_pixels:
                logger.info(f"内层颜色超过阈值 ({inner_match_count} > {threshold_pixels})。执行躲避移动: {keys_to_press}")
                # --- Movement Logic ---
                currently_pressed_key = counters.get('__find_color_last_pressed_key__')

                # Stop holding the previous key if it's different from the new ones
                if currently_pressed_key and currently_pressed_key not in keys_to_press:
                    logger.info(f"  停止按住之前的键: {currently_pressed_key}")

                    # 处理组合键释放
                    if "+" in currently_pressed_key:
                        keys = currently_pressed_key.split("+")
                        for key in keys:
                            if execution_mode == 'background' and target_hwnd:
                                self._release_key_up_background(target_hwnd, key)
                            elif execution_mode == 'foreground':
                                pyautogui.keyUp(key)
                    else:
                        # 单个键释放
                        if execution_mode == 'background' and target_hwnd:
                            self._release_key_up_background(target_hwnd, currently_pressed_key)
                        elif execution_mode == 'foreground':
                            pyautogui.keyUp(currently_pressed_key)

                    counters['__find_color_last_pressed_key__'] = None # Reset held key

                # 处理多个按键同时按下（斜向移动）
                if len(keys_to_press) > 1:
                    # 多个方向，支持斜向移动
                    logger.info(f"  检测到多方向移动需求: {keys_to_press}")
                    # 优先处理对角线移动（上下+左右的组合）
                    vertical_keys = {k for k in keys_to_press if k in [key_up, key_down]}
                    horizontal_keys = {k for k in keys_to_press if k in [key_left, key_right]}

                    if vertical_keys and horizontal_keys:
                        # 对角线移动：选择一个垂直方向和一个水平方向
                        key_to_press_this_time = list(vertical_keys)[0] + "+" + list(horizontal_keys)[0]
                        logger.info(f"  执行对角线移动: {key_to_press_this_time}")
                    else:
                        # 同一轴上的多个方向，选择第一个
                        key_to_press_this_time = next(iter(keys_to_press), None)
                else:
                    # 单个方向
                    key_to_press_this_time = next(iter(keys_to_press), None)

                if key_to_press_this_time:
                    if key_to_press_this_time != currently_pressed_key:
                         logger.info(f"  按住新的躲避键: {key_to_press_this_time}")

                         # 处理组合键（对角线移动）
                         if "+" in key_to_press_this_time:
                             keys = key_to_press_this_time.split("+")
                             for key in keys:
                                 if execution_mode == 'background' and target_hwnd:
                                     self._press_key_down_background(target_hwnd, key)
                                 elif execution_mode == 'foreground':
                                     pyautogui.keyDown(key)
                         else:
                             # 单个键
                             if execution_mode == 'background' and target_hwnd:
                                 self._press_key_down_background(target_hwnd, key_to_press_this_time)
                             elif execution_mode == 'foreground':
                                 pyautogui.keyDown(key_to_press_this_time)

                         counters['__find_color_last_pressed_key__'] = key_to_press_this_time # Record held key
                    else:
                         logger.debug(f"  继续按住键: {key_to_press_this_time} (与上次相同)")
                else: # key_to_press_this_time is None
                    logger.warning("计算得到需要按下的键为空，无法移动。")
                    # Ensure previous key is released if no new key is determined
                    if currently_pressed_key:
                        logger.info(f"  没有新的移动方向，停止按住之前的键: {currently_pressed_key}")

                        # 处理组合键释放
                        if "+" in currently_pressed_key:
                            keys = currently_pressed_key.split("+")
                            for key in keys:
                                if execution_mode == 'background' and target_hwnd:
                                    self._release_key_up_background(target_hwnd, key)
                                elif execution_mode == 'foreground':
                                    pyautogui.keyUp(key)
                        else:
                            # 单个键释放
                            if execution_mode == 'background' and target_hwnd:
                                self._release_key_up_background(target_hwnd, currently_pressed_key)
                            elif execution_mode == 'foreground':
                                pyautogui.keyUp(currently_pressed_key)

                        counters['__find_color_last_pressed_key__'] = None
                # --- End Movement ---
            else: # inner_match_count <= threshold_pixels
                logger.info(f"内层颜色不足 ({inner_match_count} <= {threshold_pixels})。尝试停止移动。")
                # Stop pressing keys if inner area is clear
                currently_pressed_key = counters.get('__find_color_last_pressed_key__')
                if currently_pressed_key:
                    logger.info(f"  停止按住之前的键: {currently_pressed_key}")

                    # 处理组合键释放
                    if "+" in currently_pressed_key:
                        keys = currently_pressed_key.split("+")
                        for key in keys:
                            if execution_mode == 'background' and target_hwnd:
                                self._release_key_up_background(target_hwnd, key)
                            elif execution_mode == 'foreground':
                                pyautogui.keyUp(key)
                    else:
                        # 单个键释放
                        if execution_mode == 'background' and target_hwnd:
                            self._release_key_up_background(target_hwnd, currently_pressed_key)
                        elif execution_mode == 'foreground':
                            pyautogui.keyUp(currently_pressed_key)
                    counters['__find_color_last_pressed_key__'] = None # Clear held key state
                else:
                    logger.info("  之前未移动，无需松开。")
            # --- End Inner Ring Check ---

        # === Logic Branch: Outer Color NOT Found ===
        else: # outer_total_match_count == 0
            logger.info("外层区域未找到目标颜色。尝试停止移动。")
            # Stop pressing keys if outer area is clear
            currently_pressed_key = counters.get('__find_color_last_pressed_key__')
            if currently_pressed_key:
                logger.info(f"  停止按住之前的键: {currently_pressed_key}")
                if execution_mode == 'background' and target_hwnd:
                    self._release_key_up_background(target_hwnd, currently_pressed_key)
                elif execution_mode == 'foreground':
                    pyautogui.keyUp(currently_pressed_key)
                counters['__find_color_last_pressed_key__'] = None # Clear held key state
            else:
                 logger.info("  之前未移动，无需松开。")
        # === End Logic Branches ===

        # --- Task Result ---
        # This task usually runs in a loop or is controlled externally,
        # so success=True means it completed an iteration without critical error.
        # The action '继续执行本步骤' is returned unless overridden by image condition logic.
        final_action = '继续执行本步骤'
        final_jump_id = None
        # If image condition check happened and decided an action, use that
        if image_check_performed:
             final_action = on_image_found_action if image_check_passed else on_image_not_found_action
             jump_id_str = image_found_jump_id_str if image_check_passed else image_not_found_jump_id_str
             final_jump_id = safe_parse_jump_id(jump_id_str)
             # Handle potential inconsistencies if jump ID invalid
             if final_action == '跳转到步骤' and final_jump_id is None:
                  logger.warning(f"图片条件动作是跳转但 ID 无效，强制改为 '执行下一步'")
                  final_action = '执行下一步'

        # 在返回"继续执行本步骤"前检查停止信号
        if final_action == '继续执行本步骤':
            if stop_checker and stop_checker():
                logger.info("用户按下停止按钮，终止找色任务循环")
                # 停止时释放所有按键
                self._release_all_movement_keys(counters, execution_mode, target_hwnd)
                return False, '停止工作流', None

        # 使用统一的成功处理（包含延迟）
        # 处理延迟
        if parameters.get('enable_next_step_delay', False):
            from .task_utils import handle_next_step_delay
            handle_next_step_delay(parameters, stop_checker)

        return True, final_action, final_jump_id
        # --- END Task Result ---

    def _release_all_movement_keys(self, counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int]):
        """
        释放所有正在按下的移动按键，用于任务停止时的清理
        """
        currently_pressed_key = counters.get('__find_color_last_pressed_key__')
        if currently_pressed_key:
            logger.info(f"任务停止，释放所有移动按键: {currently_pressed_key}")

            try:
                # 处理组合键释放
                if "+" in currently_pressed_key:
                    keys = currently_pressed_key.split("+")
                    for key in keys:
                        key = key.strip()
                        if execution_mode == 'background' and target_hwnd:
                            self._release_key_up_background(target_hwnd, key)
                        elif execution_mode == 'foreground':
                            pyautogui.keyUp(key)
                        logger.debug(f"  释放组合键中的单键: {key}")
                else:
                    # 单个按键释放
                    if execution_mode == 'background' and target_hwnd:
                        self._release_key_up_background(target_hwnd, currently_pressed_key)
                    elif execution_mode == 'foreground':
                        pyautogui.keyUp(currently_pressed_key)
                    logger.debug(f"  释放单个按键: {currently_pressed_key}")

                # 清除按键状态
                counters['__find_color_last_pressed_key__'] = None
                logger.info("所有移动按键已释放，状态已清除")

            except Exception as e:
                logger.error(f"释放按键时发生错误: {e}")
                # 即使出错也要清除状态，避免按键卡住
                counters['__find_color_last_pressed_key__'] = None
        else:
            logger.debug("没有正在按下的移动按键，无需释放")


# ================================================================
# == Standalone Function Wrappers (for executor integration) ==
# ================================================================

# --- UPDATED Wrapper to match new class structure ---
def get_params_definition() -> List[Dict[str, Any]]:
    """任务参数定义 (外部调用)。"""
    return FindColorTask.get_params_definition()

def execute_task(params: Dict[str, Any],
                 counters: Dict[str, int],
                 execution_mode: str,
                 target_hwnd: Optional[int],
                 window_region: Optional[Tuple[int, int, int, int]] = None,
                 **kwargs) -> Tuple[bool, str, Optional[int]]:
    """
    执行找色任务 (外部调用)。
    现在实例化 FindColorTask 并调用其 execute 方法。
    """
    logger.info(f"--- 开始执行找色功能任务 (接收到的模式参数: '{execution_mode}', HWND: {target_hwnd}) ---")
    task_instance = FindColorTask()

    # Pass necessary context from kwargs (like card_id) into params if needed
    if 'card_id' in kwargs:
        params['__current_card_id__'] = kwargs['card_id'] # Add card_id for logging/debug

    # Execute the main logic via the instance method
    try:
        result = task_instance.execute(
                parameters=params,
                counters=counters,
                execution_mode=execution_mode,
                target_hwnd=target_hwnd,
                window_region=window_region,
                stop_checker=kwargs.get('stop_checker'),
                # 传递额外参数用于延迟处理
                params=params,
                card_id=kwargs.get('card_id')
            )
        logger.info(f"--- 找色功能任务结束 (结果: {result}) ---")
        return result
    except Exception as e:
        logger.error(f"找色任务执行出错: {e}")
        # 出错时也要释放所有按键
        task_instance._release_all_movement_keys(counters, execution_mode, target_hwnd)
        return False, f"任务执行出错: {str(e)}", None

# Helper function for safe jump ID parsing (remains the same)
def safe_parse_jump_id(jump_id_str):
    # ... (existing helper function) ...
    pass

# === Main execution block for standalone testing (remains the same) ===
if __name__ == '__main__':
    # ... (existing standalone test code, might need updates for HSV params) ...
    pass
