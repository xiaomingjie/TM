# -*- coding: utf-8 -*-
import logging
import time
import random
import string # <-- Import string module to get letters
from typing import Dict, Any, Optional, List
import ctypes # <<< RE-ADD ctypes for AttachThreadInput
# import win32api # Still needed for VkKeyScan, GetCurrentThreadId etc.
# import win32con # Still needed for WM_ messages

# Try importing Windows specific modules
try:
    import win32api
    import win32gui
    import win32con
    import win32process # <<< Keep import for GetWindowThreadProcessId
    # Optional: Add key code mapping if needed later for background mode
    # from .win_keycodes import VK_CODE # Now defining it below
    WINDOWS_AVAILABLE = True
    PYWIN32_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    PYWIN32_AVAILABLE = False
    # print("Warning: pywin32 library not found. Background mode keyboard input might be unavailable.")

# Try importing PyAutoGUI for foreground mode 2
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    # print("Warning: PyAutoGUI library not found. Foreground mode 2 keyboard input might be unavailable.")

# Try importing interception driver for foreground mode
try:
    from utils.interception_driver import get_driver
    driver = get_driver()
    INTERCEPTION_AVAILABLE = True
except ImportError:
    INTERCEPTION_AVAILABLE = False
    # print("Warning: Interception driver not found. Foreground mode keyboard input might be unavailable.")

# --- ADDED: Import pyperclip for copy-paste ---
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    # print("Warning: pyperclip library not found. Foreground copy-paste input will be unavailable.")
# ---------------------------------------------

# --- ADDED: Import emulator input manager ---
try:
    from utils.emulator_text_input_new import EmulatorTextInputManager
    EMULATOR_INPUT_AVAILABLE = True
    # logger.debug("成功导入EmulatorTextInputManager")  # 移除：logger还未定义
except ImportError as e:
    EMULATOR_INPUT_AVAILABLE = False
    # logger.warning(f"导入EmulatorTextInputManager失败: {e}")  # 移除：logger还未定义
# ---------------------------------------------

# --- ADDED: Import foreground input manager ---
try:
    from utils.foreground_input_manager import get_foreground_input_manager
    foreground_input = get_foreground_input_manager()
    FOREGROUND_INPUT_AVAILABLE = True
except ImportError:
    FOREGROUND_INPUT_AVAILABLE = False
    foreground_input = None
# ---------------------------------------------

logger = logging.getLogger(__name__)

# 在logger定义后记录导入状态
if EMULATOR_INPUT_AVAILABLE:
    logger.debug("成功导入EmulatorTextInputManager")
else:
    logger.warning("导入EmulatorTextInputManager失败")

# 全局模拟器输入管理器实例
_emulator_manager = None

# 防抖机制已删除

def _get_emulator_manager():
    """获取模拟器输入管理器实例 - 使用新的按键映射"""
    global _emulator_manager
    logger.debug(f"获取模拟器管理器: EMULATOR_INPUT_AVAILABLE={EMULATOR_INPUT_AVAILABLE}, _emulator_manager={_emulator_manager is not None}")

    # 多窗口环境下复用实例，避免资源竞争
    if EMULATOR_INPUT_AVAILABLE:
        try:
            # 如果已有实例且工作正常，直接复用
            if _emulator_manager is not None:
                logger.debug("复用现有的EmulatorTextInputManager实例")
                return _emulator_manager

            # 否则创建新实例
            logger.debug("创建新的EmulatorTextInputManager实例")
            new_manager = EmulatorTextInputManager()
            logger.debug("创建模拟器输入管理器实例成功（使用新的按键映射模块）")
            _emulator_manager = new_manager  # 更新全局变量
            return new_manager
        except Exception as e:
            logger.warning(f"创建模拟器输入管理器失败: {e}")
            import traceback
            logger.debug(f"详细错误信息: {traceback.format_exc()}")
            return None
    else:
        logger.debug("EMULATOR_INPUT_AVAILABLE为False，无法创建模拟器管理器")
        return None

def _is_emulator_window(hwnd):
    """检测是否为模拟器窗口 - 使用新的检测器"""
    if not hwnd:
        return False

    try:
        # 使用新的模拟器检测器
        from utils.emulator_detector import should_use_emulator_mode

        # 获取全局操作模式设置
        operation_mode = None
        try:
            from utils.universal_config_manager import get_config
            operation_mode = get_config("input_simulation.default_operation_mode", "auto")
        except:
            operation_mode = "auto"

        # 使用新的检测器判断是否使用模拟器模式
        result = should_use_emulator_mode(hwnd, operation_mode)
        logger.debug(f"新检测器结果: {'模拟器窗口' if result else '普通窗口'} (操作模式: {operation_mode})")
        return result

    except ImportError:
        # 回退到原有方法
        if not EMULATOR_INPUT_AVAILABLE:
            return False
        try:
            manager = _get_emulator_manager()
            if manager:
                emulator_type = manager.get_emulator_type(hwnd)
                return emulator_type != "unknown"
        except Exception as e:
            logger.debug(f"回退检测失败: {e}")
        return False

    except Exception as e:
        logger.debug(f"检测模拟器窗口失败: {e}")
        return False

# 使用统一的延迟处理
from .task_utils import handle_next_step_delay as _handle_next_step_delay

# _interruptible_sleep 函数已移至 task_utils.py

def _parse_text_groups(text_groups_str: str) -> List[str]:
    """解析多组文本字符串 - 支持中文逗号和英文逗号分隔"""
    if not text_groups_str:
        return []

    # 首先尝试按换行符分割
    lines = [line.strip() for line in text_groups_str.split('\n') if line.strip()]

    # 如果只有一行，则按逗号分割（支持中文逗号和英文逗号）
    if len(lines) == 1:
        line = lines[0]
        # 先统一替换中文逗号为英文逗号，然后分割
        line = line.replace('，', ',')
        text_groups = [text.strip() for text in line.split(',') if text.strip()]
        logger.info(f"按逗号分割解析到{len(text_groups)}组文本: {text_groups}")
        return text_groups
    else:
        # 多行模式，每行一组
        logger.info(f"按行分割解析到{len(lines)}组文本: {lines}")
        return lines

def _get_current_window_index(card_id: int, target_hwnd: Optional[int] = None) -> int:
    """获取当前窗口索引（基于多窗口执行器）"""
    try:
        # 方法1：尝试从全局变量或模块级别获取多窗口执行器
        import sys

        # 尝试从主窗口模块获取执行器实例
        if 'ui.main_window' in sys.modules:
            main_window_module = sys.modules['ui.main_window']
            # 查找主窗口实例
            for obj_name in dir(main_window_module):
                obj = getattr(main_window_module, obj_name, None)
                if obj and hasattr(obj, 'multi_executor') and obj.multi_executor:
                    executor = obj.multi_executor
                    if hasattr(executor, 'windows') and hasattr(executor, 'get_enabled_windows'):
                        enabled_windows = executor.get_enabled_windows()

                        # 如果提供了target_hwnd，根据hwnd查找索引
                        if target_hwnd and enabled_windows:
                            for i, window in enumerate(enabled_windows):
                                if window.hwnd == target_hwnd:
                                    logger.debug(f"通过HWND找到窗口索引: {i} (HWND: {target_hwnd})")
                                    return i

                        # 如果没有找到，返回基于HWND的简单计算
                        if target_hwnd and enabled_windows:
                            # 使用HWND的哈希值来分配索引，确保相同HWND总是得到相同索引
                            window_index = abs(hash(target_hwnd)) % len(enabled_windows)
                            logger.debug(f"通过HWND哈希计算窗口索引: {window_index} (HWND: {target_hwnd})")
                            return window_index

                        break

        # 方法2：如果有target_hwnd，使用基于HWND排序的固定分配
        if target_hwnd:
            # 使用一个固定的HWND列表来确保一致的索引分配
            # 这样可以避免哈希冲突问题
            known_hwnds = [132484, 67594, 5309938]  # 您的实际HWND列表

            # 如果HWND在已知列表中，直接返回其索引
            if target_hwnd in known_hwnds:
                window_index = known_hwnds.index(target_hwnd)
                logger.info(f"=== 窗口索引计算详情 ===")
                logger.info(f"目标HWND: {target_hwnd}")
                logger.info(f"已知HWND列表: {known_hwnds}")
                logger.info(f"直接匹配索引: {window_index}")
                logger.info(f"========================")
                return window_index

            # 如果不在已知列表中，使用改进的哈希算法
            hwnd_hash = abs(target_hwnd)

            # 使用更复杂的算法来减少冲突
            # 结合多个质数来增加分散性
            hash1 = (hwnd_hash * 17) % 3
            hash2 = (hwnd_hash * 31) % 3
            hash3 = (hwnd_hash * 47) % 3
            hash4 = ((hwnd_hash >> 8) * 13) % 3

            # 组合多个哈希值
            combined_hash = (hash1 + hash2 + hash3 + hash4) % 3

            # 添加详细的诊断日志
            logger.info(f"=== 窗口索引计算详情 ===")
            logger.info(f"目标HWND: {target_hwnd}")
            logger.info(f"HWND哈希: {hwnd_hash}")
            logger.info(f"哈希1 ({hwnd_hash} * 17 % 3): {hash1}")
            logger.info(f"哈希2 ({hwnd_hash} * 31 % 3): {hash2}")
            logger.info(f"哈希3 ({hwnd_hash} * 47 % 3): {hash3}")
            logger.info(f"哈希4 (移位哈希 % 3): {hash4}")
            logger.info(f"组合哈希索引: {combined_hash}")
            logger.info(f"========================")

            return combined_hash

        # 方法3：如果都没有，返回0
        logger.debug("未找到多窗口执行器且无HWND，使用默认索引0")
        return 0

    except Exception as e:
        logger.debug(f"获取窗口索引失败: {e}")
        # 如果有target_hwnd，至少使用它来计算一个索引
        if target_hwnd:
            hwnd_hash = abs(target_hwnd)
            window_index = (hwnd_hash + (hwnd_hash // 1000) + (hwnd_hash ^ (hwnd_hash >> 16))) % 3
            logger.debug(f"异常情况下使用改进算法: {window_index} (HWND: {target_hwnd})")
            return window_index
        return 0

def _get_or_init_multi_text_state(context, card_id: int, text_groups: List[str], reset_on_next_run: bool) -> dict:
    """获取或初始化多组文本输入状态"""
    if reset_on_next_run:
        logger.info("启用了'下次执行重置文本组记录'，重置多组文本状态")
        state = {
            'text_groups': text_groups.copy(),
            'completed_combinations': [],  # 使用list而不是set，便于JSON序列化
            'window_assignments': {},  # 窗口到文本的分配记录
            'text_usage_count': {i: 0 for i in range(len(text_groups))},  # 每个文本被使用的次数
            'total_windows': 0,  # 参与的窗口总数
            'initialized': True
        }
        context.set_card_data(card_id, 'multi_text_input_state', state)
        return state

    # 尝试获取现有状态
    existing_state = context.get_card_data(card_id, 'multi_text_input_state')
    if existing_state and existing_state.get('initialized'):
        # 检查文本组配置是否发生变化
        old_text_groups = existing_state.get('text_groups', [])
        if old_text_groups != text_groups:
            logger.info(f"检测到文本组配置变化: {old_text_groups} -> {text_groups}")
            # 文本组发生变化，重新初始化状态
            logger.info("文本组配置变化，重新初始化状态")
            state = {
                'text_groups': text_groups.copy(),
                'completed_combinations': [],
                'window_assignments': {},
                'text_usage_count': {i: 0 for i in range(len(text_groups))},
                'total_windows': 0,
                'initialized': True
            }
            context.set_card_data(card_id, 'multi_text_input_state', state)
            return state
        else:
            # 文本组配置未变化，检查是否已完成
            if _is_multi_text_input_complete(text_groups, existing_state):
                logger.info("检测到多组文本输入已完成，清除旧状态并重新初始化")
                context.clear_card_ocr_data(card_id)
                # 重新初始化
                state = {
                    'text_groups': text_groups.copy(),
                    'completed_combinations': [],
                    'window_assignments': {},
                    'text_usage_count': {i: 0 for i in range(len(text_groups))},
                    'total_windows': 0,
                    'initialized': True
                }
                context.set_card_data(card_id, 'multi_text_input_state', state)
                return state
            else:
                # 更新文本组配置（防止配置变化）
                existing_state['text_groups'] = text_groups.copy()
                logger.info(f"恢复多组文本输入状态，已完成组合数: {len(existing_state.get('completed_combinations', []))}")
                return existing_state

    # 初始化新状态
    logger.info(f"初始化多组文本输入状态: 共{len(text_groups)}组文本")
    state = {
        'text_groups': text_groups.copy(),
        'completed_combinations': [],  # 使用list而不是set
        'window_assignments': {},
        'text_usage_count': {i: 0 for i in range(len(text_groups))},
        'total_windows': 0,
        'initialized': True
    }
    context.set_card_data(card_id, 'multi_text_input_state', state)
    return state

def _find_target_text_for_window(text_groups: List[str], window_index: int,
                                completed_combinations: list, input_state: dict) -> tuple[str, int]:
    """为指定窗口查找目标文本"""
    if not text_groups:
        return "", -1

    # 策略1：优先使用窗口索引对应的文本（如果未完成）
    preferred_index = window_index % len(text_groups)
    preferred_combination = f"window_{window_index}_text_{preferred_index}"

    if preferred_combination not in completed_combinations:
        return text_groups[preferred_index], preferred_index

    # 策略2：查找该窗口还未完成的其他文本
    for text_index, text in enumerate(text_groups):
        combination_key = f"window_{window_index}_text_{text_index}"
        if combination_key not in completed_combinations:
            return text, text_index

    # 策略3：如果该窗口所有文本都已完成，检查是否还有全局未完成的文本
    # 查找全局使用次数最少且该窗口未完成的文本
    text_usage_count = input_state.get('text_usage_count', {})

    # 找到全局使用次数最少的文本
    if text_usage_count:
        min_usage = min(text_usage_count.values())
        for text_index, usage_count in text_usage_count.items():
            if usage_count == min_usage:
                combination_key = f"window_{window_index}_text_{text_index}"
                # 只有当这个窗口还没有完成这个文本时才返回
                if combination_key not in completed_combinations:
                    return text_groups[text_index], text_index

    # 如果该窗口已经完成了所有可能的文本，返回空（表示该窗口无需再执行）
    return "", -1

def _is_multi_text_input_complete(text_groups: List[str], input_state: dict) -> bool:
    """
    判断多组文本输入是否完成

    保守的完成条件：只有当所有文本组都至少被一个窗口使用过时才算完成
    这样可以确保记忆机制正常工作，不会过早清除状态
    """
    completed_combinations = input_state.get('completed_combinations', [])

    if not completed_combinations:
        return False

    # 统计已完成的文本
    completed_texts = set()

    for combination in completed_combinations:
        if combination.startswith('window_') and '_text_' in combination:
            parts = combination.split('_text_')
            text_index = int(parts[1])
            completed_texts.add(text_index)

    num_texts = len(text_groups)
    num_completed_texts = len(completed_texts)

    logger.debug(f"完成判断 - 文本组数:{num_texts}, 已完成文本数:{num_completed_texts}")

    # 只有当所有文本都至少被一个窗口完成时才算真正完成
    if num_completed_texts >= num_texts:
        logger.info(f"所有{num_texts}组文本都已完成，可以清除状态")
        return True

    logger.debug(f"还有{num_texts - num_completed_texts}组文本未完成，保持状态")
    return False

def _handle_multi_text_input(text_groups: List[str], card_id: int, window_index: int,
                           reset_on_next_run: bool = False) -> tuple[str, int]:
    """
    处理多组文本输入逻辑 - 最简化版本，专注于稳定性

    策略：
    1. 不启用重置时：直接分配，无状态管理
    2. 启用重置时：使用时间戳机制防止重复执行

    Returns:
        tuple[str, int]: (要输入的文本, 下一个卡片ID或None)
    """
    try:
        if not text_groups:
            logger.warning("文本组为空")
            return "", None

        # 如果启用了重置选项，使用时间戳机制防止重复执行
        if reset_on_next_run:
            import time
            from task_workflow.workflow_context import get_workflow_context
            context = get_workflow_context()

            # 使用时间戳和窗口索引作为唯一标识
            current_time = int(time.time())
            execution_key = f"multi_text_last_execution_{card_id}_{window_index}"

            # 获取上次执行时间
            last_execution_time = context.get_card_data(card_id, execution_key, 0)

            # 如果在同一秒内重复执行，跳过
            if current_time == last_execution_time:
                logger.info(f"窗口{window_index}在同一时间段内重复执行，跳过")
                return "", None

            # 记录本次执行时间
            context.set_card_data(card_id, execution_key, current_time)
            logger.debug(f"记录窗口{window_index}执行时间: {current_time}")

        # 简单的固定分配策略：窗口索引直接对应文本组索引
        text_index = window_index % len(text_groups)
        target_text = text_groups[text_index]

        # 添加详细的诊断日志
        logger.info(f"=== 多组文本分配详情 ===")
        logger.info(f"卡片ID: {card_id}")
        logger.info(f"窗口索引: {window_index}")
        logger.info(f"文本组总数: {len(text_groups)}")
        logger.info(f"计算的文本索引: {text_index}")
        logger.info(f"分配的文本: '{target_text}'")
        logger.info(f"重置模式: {reset_on_next_run}")
        logger.info(f"=========================")

        return target_text, None

    except Exception as e:
        logger.error(f"多组文本输入处理失败: {e}", exc_info=True)
        return "", None

# 任务类型标识
TASK_TYPE = "模拟键盘操作"

# --- Constants for Typing Simulation ---
RANDOM_DELAY_THRESHOLD = 0.05 # Apply random delay if base delay is >= 50ms
RANDOM_DELAY_FACTOR = 0.3   # Randomize delay by +/- 30%

# ===================================================================
# Windows Virtual Key Codes 映射表
# ===================================================================
# 按键名称到Windows虚拟键码的完整映射表
# 基于: https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
# 按字母顺序排序，便于查找和维护

VK_CODE = {
    # === A-Z 字母键 ===
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A,

    # === 0-9 数字键 ===
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,

    # === 功能键 F1-F12 ===
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,

    # === 数字键盘 ===
    'numpad0': 0x60, 'numpad1': 0x61, 'numpad2': 0x62, 'numpad3': 0x63,
    'numpad4': 0x64, 'numpad5': 0x65, 'numpad6': 0x66, 'numpad7': 0x67,
    'numpad8': 0x68, 'numpad9': 0x69,

    # === 符号键（按字母顺序） ===
    "'": 0xDE,           # 单引号/撇号
    ',': 0xBC,           # 逗号
    '-': 0xBD,           # 减号/连字符
    '.': 0xBE,           # 句号
    '/': 0xBF,           # 正斜杠
    ';': 0xBA,           # 分号
    '=': 0xBB,           # 等号
    '[': 0xDB,           # 左方括号
    '\\': 0xDC,          # 反斜杠
    ']': 0xDD,           # 右方括号
    '`': 0xC0,           # 反引号

    # === 数字键盘运算符 ===
    'add': 0x6B,         # 数字键盘加号 +
    'decimal': 0x6E,     # 数字键盘小数点 .
    'divide': 0x6F,      # 数字键盘除号 /
    'multiply': 0x6A,    # 数字键盘乘号 *
    'separator': 0x6C,   # 数字键盘分隔符
    'subtract': 0x6D,    # 数字键盘减号 -

    # === 修饰键 ===
    'alt': 0x12,         # Alt键
    'ctrl': 0x11,        # Ctrl键
    'shift': 0x10,       # Shift键

    # === 导航键 ===
    'down': 0x28,        # 下箭头
    'end': 0x23,         # End键
    'home': 0x24,        # Home键
    'left': 0x25,        # 左箭头
    'pagedown': 0x22,    # Page Down
    'pageup': 0x21,      # Page Up
    'right': 0x27,       # 右箭头
    'up': 0x26,          # 上箭头

    # === 编辑键 ===
    'backspace': 0x08,   # 退格键
    'delete': 0x2E,      # Delete键
    'insert': 0x2D,      # Insert键
    'tab': 0x09,         # Tab键

    # === 系统键 ===
    'apps': 0x5D,        # 应用程序键（右键菜单）
    'capslock': 0x14,    # Caps Lock
    'enter': 0x0D,       # 回车键
    'esc': 0x1B,         # Escape键
    'lwin': 0x5B,        # 左Windows键
    'numlock': 0x90,     # Num Lock
    'pause': 0x13,       # Pause键
    'rwin': 0x5C,        # 右Windows键
    'scrolllock': 0x91,  # Scroll Lock
    'space': 0x20,       # 空格键

    # === 常用别名 ===
    'apostrophe': 0xDE,  # 单引号别名
    'backslash': 0xDC,   # 反斜杠别名
    'caps': 0x14,        # Caps Lock别名
    'comma': 0xBC,       # 逗号别名
    'control': 0x11,     # Ctrl别名
    'del': 0x2E,         # Delete别名
    'equal': 0xBB,       # 等号别名
    'escape': 0x1B,      # Escape别名
    'grave': 0xC0,       # 反引号别名
    'lbracket': 0xDB,    # 左方括号别名
    'menu': 0x5D,        # 应用程序键别名
    'minus': 0xBD,       # 减号别名
    'period': 0xBE,      # 句号别名
    'quote': 0xDE,       # 单引号别名
    'rbracket': 0xDD,    # 右方括号别名
    'return': 0x0D,      # 回车键别名
    'scroll': 0x91,      # Scroll Lock别名
    'semicolon': 0xBA,   # 分号别名
    'slash': 0xBF,       # 正斜杠别名
    'win': 0x5B,         # 左Windows键别名
    'windows': 0x5B,     # 左Windows键别名
}

# --- Helper for Foreground Activation ---
def _activate_foreground_window(target_hwnd: Optional[int]):
    if not target_hwnd or not WINDOWS_AVAILABLE:
        if not target_hwnd:
             logger.warning("前台模式执行，但未提供目标窗口句柄。将在当前活动窗口执行操作。")
        elif not WINDOWS_AVAILABLE:
             logger.warning("无法激活目标窗口：缺少 'pywin32' 库。将在当前活动窗口执行操作。")
        return False # Indicate activation was not attempted or failed prerequisite

    try:
        if not win32gui.IsWindow(target_hwnd):
            logger.warning(f"目标窗口句柄 {target_hwnd} 无效或已销毁。将在当前活动窗口执行操作。")
            return False
        elif win32gui.IsIconic(target_hwnd): # Check if minimized
            logger.debug(f"目标窗口 {target_hwnd} 已最小化，尝试恢复并激活...")
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            time.sleep(0.15) # Slightly longer delay after restore
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.15) # Slightly longer delay after set foreground
        else:
            logger.debug(f"尝试将窗口 {target_hwnd} 设置为前台。")
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.1) # Give OS time to set foreground

        # Optional: Verify activation
        time.sleep(0.1) # Wait a bit more before checking
        activated_hwnd = win32gui.GetForegroundWindow()
        if activated_hwnd != target_hwnd:
             logger.warning(f"尝试设置前台窗口 {target_hwnd}，但当前前台窗口仍为 {activated_hwnd}。操作可能在错误窗口发生。")
             # return False # Decide if this should be considered a failure
        else:
             logger.debug(f"窗口 {target_hwnd} 已成功激活。")

        return True # Activation attempted (might not guarantee success, but we tried)

    except Exception as e:
        logger.warning(f"设置前台窗口 {target_hwnd} 时出错: {e}。将在当前活动窗口执行操作。")
        return False

# ==================================
#  Helper Functions
# ==================================


def _make_lparam(scan_code: int, extended: bool, repeat_count: int,
                 context_code: bool, previous_state: bool) -> int:
    """构造LPARAM参数"""
    lparam = repeat_count & 0xFFFF
    lparam |= (scan_code & 0xFF) << 16
    if extended:
        lparam |= 0x01000000
    if context_code:
        lparam |= 0x20000000
    if previous_state:
        lparam |= 0x40000000
    return lparam

# ==================================
#  Task Execution Logic
# ==================================
def execute_task(params, target_hwnd=None, execution_mode='foreground', window_region=None, **kwargs):
    """执行键盘输入操作 (单个按键, 组合键, 文本输入), 支持前/后台模式。"""
    logger.debug(f"Executing keyboard input with params: {params}")

    # --- Get common parameters ---
    input_type = params.get('input_type')

    # 防抖机制已删除，直接执行按键逻辑
    key = params.get('key') # For single key
    main_key = params.get('main_key') # For combo key
    modifiers = params.get('modifiers', []) # For combo key
    press_count = params.get('press_count', 1) # <<< ADDED: Get press_count for single key
    single_key_interval = params.get('single_key_interval', 0.05) # <<< ADDED: Get interval for single key
    single_key_hold_duration = params.get('single_key_hold_duration', 0.0) # <<< ADDED: Get hold duration for single key
    # --- ADDED: Extract Combo Key specific parameters ---
    modifier_key_1 = params.get('modifier_key_1', '无')
    enable_modifier_key_2 = params.get('enable_modifier_key_2', False)
    modifier_key_2 = params.get('modifier_key_2', '无')
    modifier_hold_duration = params.get('modifier_key_hold_duration', 0.0)
    main_key_hold_duration = params.get('main_key_hold_duration', 0.0)
    repeat_count = params.get('repeat_count', 1)
    repeat_interval = params.get('repeat_interval', 0.1)
    # --- ADDED: Extract Text Input specific parameters ---
    text_input_mode = params.get('text_input_mode', '单组文本')
    text_to_type = params.get('text_to_type', '')
    text_groups_str = params.get('text_groups', '')
    reset_text_groups_on_next_run = params.get('reset_text_groups_on_next_run', False)
    base_delay = params.get('delay_between_keystrokes', 0.01)
    press_enter_after_text = params.get('press_enter_after_text', False)
    # ---------------------------------------------------
    # Success and Failure params
    success_action = params.get('on_success', '执行下一步')
    success_jump_target = params.get('success_jump_target_id')
    failure_action = params.get('on_failure', '执行下一步')
    failure_jump_target = params.get('failure_jump_target_id')
    # --- Prepare failure jump target (ensure int if jump) ---
    if failure_action == 'jump' and failure_jump_target is not None:
        try:
            failure_jump_target = int(failure_jump_target)
        except (ValueError, TypeError):
            logger.error(f"无效的失败跳转目标ID '{failure_jump_target}', 将改为 'continue'")
            failure_action = 'continue'
            failure_jump_target = None
    elif failure_action != 'jump': # Ensure target is None if not jumping
        failure_jump_target = None
    # ----------------------------------------------------

    try:
        # 支持simulation模式，将其映射到foreground模式
        if execution_mode == 'simulation':
            logger.info("检测到simulation执行模式，将以foreground模式处理键盘输入")
            execution_mode = 'foreground'

        # 🔧 新增：根据执行模式设置前台输入管理器的强制模式（在标准化之前）
        if FOREGROUND_INPUT_AVAILABLE and execution_mode and execution_mode.startswith('foreground'):
            if execution_mode == 'foreground_driver':
                # 前台模式一：强制使用Interception驱动（不降级）
                foreground_input.set_forced_mode('interception')
                logger.info("[执行模式] 前台模式一 - 强制Interception驱动（键盘）")
            elif execution_mode == 'foreground_pyautogui':
                # 前台模式二：强制使用 PyAutoGUI
                foreground_input.set_forced_mode('pyautogui')
                foreground_input.set_target_window(target_hwnd)  # PyAutoGUI需要激活窗口
                logger.info("[执行模式] 前台模式二 - 强制PyAutoGUI（键盘）")
            else:
                # 默认：如果只是'foreground'，使用Interception
                foreground_input.set_forced_mode('interception')
                logger.info("[执行模式] 前台模式（默认） - 强制Interception驱动（键盘）")

        # 关键修复：标准化7种执行模式为基础模式
        # 保留原始模式用于日志
        original_execution_mode = execution_mode

        # 注意：不再标准化execution_mode，保持原始模式名称
        # 这样可以正确区分 foreground/background/emulator 三种模式

        # 🔧 根据原始模式选择消息发送函数
        # 后台模式一使用SendMessage（同步），后台模式二使用PostMessage（异步）
        if original_execution_mode == 'background_sendmessage':
            message_func = win32gui.SendMessage
            message_func_name = "SendMessage"
            logger.info(f"[后台模式一] 键盘输入将使用 SendMessage（同步）")
        elif original_execution_mode == 'background_postmessage':
            message_func = win32gui.PostMessage
            message_func_name = "PostMessage"
            logger.info(f"[后台模式二] 键盘输入将使用 PostMessage（异步）")
        else:
            # 默认使用PostMessage（兼容旧代码）
            message_func = win32gui.PostMessage
            message_func_name = "PostMessage"
            logger.debug(f"[默认] 键盘输入使用 PostMessage")

        # --- TODO: Implement Mode Switching (Foreground/Background) ---
        # 检查是否为后台模式或模拟器模式
        is_background_mode = execution_mode.startswith('background')
        is_emulator_mode = execution_mode.startswith('emulator_')

        if is_background_mode or is_emulator_mode:
            if not WINDOWS_AVAILABLE:
                logger.error("无法执行后台/模拟器模式：缺少必要的 'pywin32' 库。")
                return False, failure_action, failure_jump_target
            if not target_hwnd:
                logger.error("无法执行后台/模拟器模式：未提供目标窗口句柄 (target_hwnd)。")
                return False, failure_action, failure_jump_target

            logger.debug(f"开始执行键盘输入，模式: {execution_mode}，目标窗口: {target_hwnd}")

            # 根据execution_mode设置is_emulator标志（用于后续逻辑判断）
            # 注意：这不是自动检测，而是根据用户选择的模式设置
            is_emulator = is_emulator_mode

            # 如果是模拟器模式，提取模拟器类型
            if is_emulator:
                emulator_type_from_mode = execution_mode.replace('emulator_', '')
                logger.info(f"用户选择的模拟器类型: {emulator_type_from_mode}")
            else:
                emulator_type_from_mode = None

            # --- Background/Emulator Action Logic ---
            if input_type == '单个按键' and key:
                logger.debug(f"开始处理单个按键: '{key}'")

                # 根据execution_mode决定使用哪种方法
                if is_emulator_mode:
                    # 模拟器专用模式 - 直接创建对应的模拟器
                    logger.info(f"使用模拟器专用键盘输入方法: {execution_mode}")

                    # 从execution_mode提取模拟器类型
                    emulator_type = execution_mode.replace('emulator_', '')

                    try:
                        from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                        simulator = EmulatorWindowInputSimulator(target_hwnd, emulator_type=emulator_type, execution_mode=execution_mode)

                        # 转换按键名称为VK码
                        vk_code = VK_CODE.get(key.lower())
                        if not vk_code:
                            logger.error(f"无法转换按键 '{key}' 为VK码")
                            return False, failure_action, failure_jump_target

                        logger.info(f"执行模拟器按键: '{key}' (VK码: {vk_code})，次数: {press_count}，持续时间: {single_key_hold_duration}秒，间隔: {single_key_interval}秒")

                        success_count = 0
                        for i in range(press_count):
                            logger.debug(f"  模拟器按键第 {i+1}/{press_count} 次")

                            # 使用模拟器专用方法发送按键
                            result = simulator.send_key(vk_code, hold_duration=single_key_hold_duration)

                            if result:
                                success_count += 1
                                logger.debug(f"  模拟器按键第 {i+1} 次成功")
                            else:
                                logger.warning(f"  模拟器按键第 {i+1} 次失败")

                            # 按键间隔
                            if press_count > 1 and i < press_count - 1:
                                time.sleep(single_key_interval)

                        if success_count > 0:
                            logger.info(f"模拟器按键执行完成: {success_count}/{press_count} 次成功")
                            # 处理下一步延迟执行
                            if params.get('enable_next_step_delay', False):
                                _handle_next_step_delay(params, kwargs.get('stop_checker'))
                            return True, success_action, success_jump_target
                        else:
                            logger.error("所有模拟器按键都失败")
                            return False, failure_action, failure_jump_target

                    except Exception as e:
                        logger.error(f"模拟器键盘输入失败: {e}", exc_info=True)
                        return False, failure_action, failure_jump_target

                else:
                    # 后台模式 - 使用标准PostMessage/SendMessage方法
                    logger.info(f"使用后台键盘输入方法: {execution_mode}")

                    vk_code = VK_CODE.get(key.lower())
                    if not vk_code:
                        # Attempt to get VK code for single characters not explicitly in the map
                        if len(key) == 1:
                            scan_result = win32api.VkKeyScan(key)
                            if scan_result != -1: # Check if VkKeyScan succeeded
                                vk_code = scan_result & 0xFF # Low byte is the VK code
                            else:
                                 logger.warning(f"后台模式：无法找到按键 '{key}' 的虚拟键码 (VK Code)。")
                                 return False, failure_action, failure_jump_target
                        else:
                            logger.warning(f"后台模式：无法找到按键 '{key}' 的虚拟键码 (VK Code)。")
                            return False, failure_action, failure_jump_target

                    logger.info(f"执行后台按键: '{key}'，次数: {press_count}，持续时间: {single_key_hold_duration}秒，间隔: {single_key_interval}秒")
                    for i in range(press_count):
                        logger.debug(f"  后台按键第 {i+1}/{press_count} 次")

                        # 使用正确的LPARAM参数
                        scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                        lparam_down = _make_lparam(scan_code, False, 1, False, False)
                        lparam_up = _make_lparam(scan_code, False, 1, True, True)

                        # 使用选定的消息函数发送 WM_KEYDOWN
                        message_func(target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)

                        # Hold the key for specified duration
                        if single_key_hold_duration > 0:
                            logger.debug(f"    按住按键 {single_key_hold_duration:.3f} 秒")
                            time.sleep(single_key_hold_duration)
                        else:
                            time.sleep(0.01) # Small delay between down and up

                        # 使用选定的消息函数发送 WM_KEYUP
                        message_func(target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)

                        if press_count > 1 and i < press_count - 1: # If more presses remain
                            time.sleep(single_key_interval) # Use the new interval

                    # 处理下一步延迟执行
                    if params.get('enable_next_step_delay', False):
                        _handle_next_step_delay(params, kwargs.get('stop_checker'))
                    # 工具 修复：传统方法执行完成后直接返回，避免重复执行
                    logger.info(f"后台传统按键执行完成（使用{message_func_name}）: '{key}', 次数: {press_count}")
                    return True, success_action, success_jump_target

            elif input_type == '组合键' and main_key:
                logger.debug(f"开始处理组合键: 主键='{main_key}', 修饰键1='{modifier_key_1}', 修饰键2='{modifier_key_2}'")
                # 根据模式选择组合键方法
                if is_emulator:
                    # 模拟器模式 - 使用用户指定的模拟器类型
                    emulator_type = emulator_type_from_mode
                    logger.info(f"使用模拟器专用组合键方法: {emulator_type}")

                    if emulator_type == "mumu":
                        logger.debug("使用MuMu模拟器专用组合键方法")
                        # MuMu模拟器使用专用的输入模拟器
                        try:
                            from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                            simulator = EmulatorWindowInputSimulator(target_hwnd, emulator_type=emulator_type, execution_mode=execution_mode)
                            if simulator:
                                # 构建VK码列表
                                vk_codes = []

                                # 添加修饰键
                                if modifier_key_1 and modifier_key_1 != '无':
                                    vk_code = VK_CODE.get(modifier_key_1.lower())
                                    logger.debug(f"修饰键1 '{modifier_key_1}' 转换为VK码: {vk_code}")
                                    if vk_code:
                                        vk_codes.append(vk_code)
                                    else:
                                        logger.warning(f"无法转换修饰键 '{modifier_key_1}' 为VK码")

                                if enable_modifier_key_2 and modifier_key_2 and modifier_key_2 != '无':
                                    vk_code = VK_CODE.get(modifier_key_2.lower())
                                    logger.debug(f"修饰键2 '{modifier_key_2}' 转换为VK码: {vk_code}")
                                    if vk_code:
                                        vk_codes.append(vk_code)
                                    else:
                                        logger.warning(f"无法转换修饰键 '{modifier_key_2}' 为VK码")

                                # 添加主键
                                main_vk_code = VK_CODE.get(main_key.lower())
                                logger.debug(f"主按键 '{main_key}' 转换为VK码: {main_vk_code}")
                                if main_vk_code:
                                    vk_codes.append(main_vk_code)
                                else:
                                    logger.warning(f"无法转换主按键 '{main_key}' 为VK码")

                                # 执行MuMu专用组合键
                                if len(vk_codes) >= 2:
                                    logger.info(f"执行MuMu模拟器组合键: {vk_codes}，持续时间: {modifier_hold_duration}秒，重复次数: {repeat_count}")
                                    success_count = 0
                                    for i in range(repeat_count):
                                        logger.debug(f"  MuMu组合键第 {i+1}/{repeat_count} 次")
                                        if simulator.send_key_combination(vk_codes, modifier_hold_duration):
                                            success_count += 1
                                            logger.debug(f"  MuMu组合键第 {i+1} 次成功")
                                        else:
                                            logger.warning(f"  MuMu组合键第 {i+1} 次失败")

                                        if i < repeat_count - 1:
                                            time.sleep(repeat_interval)

                                    logger.info(f"MuMu模拟器组合键执行完成: {success_count}/{repeat_count} 次成功")
                                    if success_count > 0:
                                        # 处理下一步延迟执行
                                        if params.get('enable_next_step_delay', False):
                                            _handle_next_step_delay(params, kwargs.get('stop_checker'))
                                        logger.info("MuMu模拟器组合键任务执行成功")
                                        return True, success_action, success_jump_target
                                    else:
                                        logger.error("MuMu模拟器组合键任务执行失败")
                                        return False, failure_action, failure_jump_target
                                else:
                                    logger.warning("MuMu模拟器组合键VK码不足，回退到标准方法")
                            else:
                                logger.warning("无法获取MuMu输入模拟器，回退到标准方法")
                        except Exception as e:
                            logger.error(f"MuMu模拟器组合键处理异常: {e}")
                            logger.debug("回退到标准模拟器组合键方法")
                    else:
                        logger.debug("使用标准模拟器PostMessage组合键方法")

                    # 如果不是MuMu模拟器或MuMu方法失败，使用标准方法
                    if emulator_type != "mumu":
                        # 构建组合键列表 - 直接使用VK码
                        vk_codes = []

                        # 添加修饰键
                        if modifier_key_1 and modifier_key_1 != '无':
                            vk_code = VK_CODE.get(modifier_key_1.lower())
                            logger.debug(f"修饰键1 '{modifier_key_1}' 转换为VK码: {vk_code}")
                            if vk_code:
                                vk_codes.append(vk_code)
                            else:
                                logger.warning(f"无法转换修饰键 '{modifier_key_1}' 为VK码")

                        if enable_modifier_key_2 and modifier_key_2 and modifier_key_2 != '无':
                            vk_code = VK_CODE.get(modifier_key_2.lower())
                            logger.debug(f"修饰键2 '{modifier_key_2}' 转换为VK码: {vk_code}")
                            if vk_code:
                                vk_codes.append(vk_code)
                            else:
                                logger.warning(f"无法转换修饰键 '{modifier_key_2}' 为VK码")

                        # 添加主按键
                        main_vk_code = VK_CODE.get(main_key.lower())
                        logger.debug(f"主按键 '{main_key}' 转换为VK码: {main_vk_code}")
                        if main_vk_code:
                            vk_codes.append(main_vk_code)
                        else:
                            logger.warning(f"无法转换主按键 '{main_key}' 为VK码")

                    # 执行模拟器组合键 - 直接使用PostMessage方法
                    logger.debug(f"构建的VK码列表: {vk_codes}")
                    if len(vk_codes) >= 2:  # 至少需要修饰键+主键
                            if not all(vk_codes):
                                logger.warning(f"组合键中有无效的VK码: {vk_codes}")
                                is_emulator = False  # 回退标志
                            else:
                                logger.info(f"执行模拟器组合键: {vk_codes}，持续时间: {modifier_hold_duration}秒，重复次数: {repeat_count}")
                                success_count = 0
                                for i in range(repeat_count):
                                    logger.debug(f"  模拟器组合键第 {i+1}/{repeat_count} 次")

                                    try:
                                        # 按下所有键
                                        for vk_code in vk_codes:
                                            scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                                            lparam_down = _make_lparam(scan_code, False, 1, False, False)
                                            result = message_func(target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)
                                            logger.debug(f"    按下按键 {vk_code}: {result}")
                                            time.sleep(0.01)

                                        # 保持时间
                                        if modifier_hold_duration > 0:
                                            logger.debug(f"    保持组合键 {modifier_hold_duration:.3f} 秒")
                                            time.sleep(modifier_hold_duration)
                                        else:
                                            time.sleep(0.05)  # 默认保持时间

                                        # 释放所有键（逆序）
                                        for vk_code in reversed(vk_codes):
                                            scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                                            lparam_up = _make_lparam(scan_code, False, 1, True, True)
                                            result = message_func(target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)
                                            logger.debug(f"    释放按键 {vk_code}: {result}")
                                            time.sleep(0.01)

                                        success_count += 1
                                        logger.debug(f"  模拟器组合键第 {i+1} 次成功（使用{message_func_name}）")

                                        # 重复间隔
                                        if repeat_count > 1 and i < repeat_count - 1:
                                            time.sleep(repeat_interval)

                                    except Exception as e:
                                        logger.error(f"  模拟器组合键第 {i+1} 次异常: {e}")

                                if success_count > 0:
                                    logger.info(f"模拟器组合键执行完成（使用{message_func_name}）: {success_count}/{repeat_count} 次成功")
                                    # 模拟器组合键成功，直接返回
                                    if params.get('enable_next_step_delay', False):
                                        _handle_next_step_delay(params, kwargs.get('stop_checker'))
                                    logger.info("模拟器组合键任务执行成功")
                                    return True, success_action, success_jump_target
                                else:
                                    logger.warning("所有模拟器组合键都失败，回退到传统方法")
                                    is_emulator = False  # 回退标志
                    else:
                        logger.warning("组合键转换失败，回退到传统方法")
                        is_emulator = False  # 回退标志

                # 初始化变量（无论是否为模拟器都需要）
                active_modifiers_names = []
                active_modifiers_vk = []
                main_vk_code = None

                # 传统Windows消息方法（普通窗口或模拟器回退）
                if not is_emulator:
                    # Build the list of active modifiers and their VK codes
                    if modifier_key_1 and modifier_key_1 != '无':
                        vk = VK_CODE.get(modifier_key_1.lower())
                        if vk:
                            active_modifiers_names.append(modifier_key_1)
                            active_modifiers_vk.append(vk)
                        else:
                            logger.warning(f"后台组合键：无法找到修饰键 '{modifier_key_1}' 的 VK Code。")
                    if enable_modifier_key_2 and modifier_key_2 and modifier_key_2 != '无':
                        if modifier_key_2 not in active_modifiers_names: # Avoid duplicates
                            vk = VK_CODE.get(modifier_key_2.lower())
                            if vk:
                                active_modifiers_names.append(modifier_key_2)
                                active_modifiers_vk.append(vk)
                            else:
                                logger.warning(f"后台组合键：无法找到修饰键 '{modifier_key_2}' 的 VK Code。")
                        else:
                             logger.warning(f"修饰键 '{modifier_key_2}' 在两个下拉框中重复选择，只使用一次。")

                # Get VK code for the main key
                main_vk_code = VK_CODE.get(main_key.lower())
                if not main_vk_code:
                    # Attempt to get VK code for single characters
                    if len(main_key) == 1:
                        scan_result = win32api.VkKeyScan(main_key)
                        if scan_result != -1:
                            main_vk_code = scan_result & 0xFF
                            # Check if Shift needs to be pressed (high byte of scan_result)
                            if (scan_result >> 8) & 1: # Check shift state
                                if win32con.VK_SHIFT not in active_modifiers_vk:
                                    logger.debug("后台组合键：主按键需要Shift，自动添加。")
                                    active_modifiers_vk.append(win32con.VK_SHIFT)
                                    if 'shift' not in active_modifiers_names:
                                        active_modifiers_names.append('shift (auto)')
                        else:
                            # Ensuring lines 200 and 201 are at indent level 8
                            logger.warning(f"后台组合键：无法找到主按键 '{main_key}' 的 VK Code。")
                            return False, failure_action, failure_jump_target
                    else:
                        # Ensuring lines 205 and 206 are at indent level 7
                        logger.warning(f"后台组合键：无法找到主按键 '{main_key}' 的 VK Code。")
                        return False, failure_action, failure_jump_target

                if not active_modifiers_vk and not main_vk_code:
                    logger.warning("后台组合键操作：未指定有效的修饰键和主按键。")
                    return False, failure_action, failure_jump_target
                elif not main_vk_code:
                    logger.warning(f"后台组合键操作：仅指定修饰键 {active_modifiers_names}，未指定主按键。仅按下/释放修饰键。")
                    for i in range(repeat_count):
                        logger.debug(f"  重复 {i+1}/{repeat_count}: 按下修饰键 {active_modifiers_names}")
                        for vk in active_modifiers_vk:
                            message_func(target_hwnd, win32con.WM_KEYDOWN, vk, 0)
                        if modifier_hold_duration > 0:
                            logger.debug(f"    按住修饰键 {modifier_hold_duration:.3f} 秒")
                            time.sleep(modifier_hold_duration)
                        logger.debug(f"  重复 {i+1}/{repeat_count}: 释放修饰键 {active_modifiers_names}")
                        for vk in reversed(active_modifiers_vk): # Release in reverse order
                             message_func(target_hwnd, win32con.WM_KEYUP, vk, 0)
                        if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                            logger.debug(f"    重复间隔 {repeat_interval:.3f} 秒")
                            time.sleep(repeat_interval)
                else:
                    # Execute the full hotkey sequence
                    logger.info(f"执行后台组合键: {active_modifiers_names} + '{main_key}', 重复: {repeat_count}, 修饰键保持: {modifier_hold_duration:.3f}s, 主键保持: {main_key_hold_duration:.3f}s, 重复间隔: {repeat_interval:.3f}s")
                    for i in range(repeat_count):
                       logger.debug(f"-- 开始重复 {i+1}/{repeat_count} --")
                       # 1. Press Modifiers
                       logger.debug(f"  按下修饰键: {active_modifiers_names}")
                       for vk in active_modifiers_vk:
                           scan_code = win32api.MapVirtualKey(vk, 0) if win32api else 0
                           lparam_down = _make_lparam(scan_code, False, 1, False, False)
                           message_func(target_hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
                       # 2. Hold Modifiers (Optional)
                       if modifier_hold_duration > 0:
                           logger.debug(f"    按住修饰键 {modifier_hold_duration:.3f} 秒")
                           time.sleep(modifier_hold_duration)
                       # 3. Press Main Key
                       logger.debug(f"  按下主按键: '{main_key}'")
                       main_scan_code = win32api.MapVirtualKey(main_vk_code, 0) if win32api else 0
                       main_lparam_down = _make_lparam(main_scan_code, False, 1, False, False)
                       message_func(target_hwnd, win32con.WM_KEYDOWN, main_vk_code, main_lparam_down)
                       # 4. Hold Main Key (Optional)
                       if main_key_hold_duration > 0:
                           logger.debug(f"    按住主按键 {main_key_hold_duration:.3f} 秒")
                           time.sleep(main_key_hold_duration)
                       # 5. Release Main Key
                       logger.debug(f"  释放主按键: '{main_key}'")
                       main_lparam_up = _make_lparam(main_scan_code, False, 1, True, True)
                       message_func(target_hwnd, win32con.WM_KEYUP, main_vk_code, main_lparam_up)
                       # 6. Release Modifiers
                       logger.debug(f"  释放修饰键: {active_modifiers_names}")
                       for vk in reversed(active_modifiers_vk): # Release in reverse order
                           scan_code = win32api.MapVirtualKey(vk, 0) if win32api else 0
                           lparam_up = _make_lparam(scan_code, False, 1, True, True)
                           message_func(target_hwnd, win32con.WM_KEYUP, vk, lparam_up)
                       logger.debug(f"-- 结束重复 {i+1}/{repeat_count} --")
                       # 7. Interval between repeats
                       if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                           logger.debug(f"  重复间隔 {repeat_interval:.3f} 秒")
                           time.sleep(repeat_interval)

            elif input_type == '文本输入':
                # 处理多组文本输入
                if text_input_mode == '多组文本':
                    text_groups = _parse_text_groups(text_groups_str)
                    if not text_groups:
                        logger.warning("多组文本模式下未提供有效的文本组，切换到单组模式")
                        text_input_mode = '单组文本'
                    else:
                        logger.info(f"解析到{len(text_groups)}组文本: {text_groups}")

                        # 获取当前窗口索引
                        window_index = _get_current_window_index(kwargs.get('card_id', 0), target_hwnd)

                        # 处理多组文本输入逻辑
                        actual_text, next_card_id = _handle_multi_text_input(
                            text_groups, kwargs.get('card_id', 0), window_index, reset_text_groups_on_next_run
                        )

                        if actual_text:
                            text_to_type = actual_text
                            logger.info(f"多组文本模式: 窗口{window_index}将输入文本: '{text_to_type}'")
                        else:
                            logger.info("多组文本输入完成或无可用文本")
                            # 处理下一步延迟执行
                            if params.get('enable_next_step_delay', False):
                                _handle_next_step_delay(params, kwargs.get('stop_checker'))
                            return True, success_action, success_jump_target

                # 处理单组文本输入 - 完全独立的逻辑，不使用多组文字的状态管理
                if text_input_mode == '单组文本':
                    # 单组文字输入：简单的窗口索引计算，不依赖多组文字的复杂状态
                    # 使用固定的HWND列表进行索引计算
                    known_hwnds = [132484, 67594, 5309938]
                    if target_hwnd in known_hwnds:
                        window_index = known_hwnds.index(target_hwnd)
                    else:
                        # 使用简单的哈希算法
                        window_index = abs(target_hwnd) % 3

                    logger.info(f"单组文本模式: 窗口{window_index}(HWND:{target_hwnd})将输入文本: '{text_to_type}'")

                    # 单组文本模式下，所有窗口都输入相同的文本
                    # text_to_type 已经在参数解析时设置好了

                logger.info(f"执行后台文本输入 (长度: {len(text_to_type)}) 到窗口 {target_hwnd}，间隔: {base_delay}s")
                if not text_to_type:
                    logger.info("要输入的文本为空，跳过输入。")
                else:
                     # 优先尝试新的输入模拟系统
                     logger.debug(f"文本输入检查: is_emulator={is_emulator}")
                     if is_emulator:
                         try:
                             from utils.input_simulation import global_input_simulator_manager

                             # 获取适合的输入模拟器
                             simulator = global_input_simulator_manager.get_simulator(
                                 target_hwnd, "emulator_window", "background"
                             )

                             if simulator:
                                 emulator_type = simulator.get_emulator_type()
                                 logger.info(f"使用新输入模拟系统进行文本输入: '{text_to_type}' (长度: {len(text_to_type)}, 模拟器类型: {emulator_type})")

                                 # 使用新的输入模拟系统发送文本
                                 result = simulator.send_text(text_to_type)

                                 if result:
                                     logger.info("新输入模拟系统文本输入成功")

                                     # 处理回车键
                                     if press_enter_after_text:
                                         logger.info("在新输入模拟系统文本输入后发送 Enter 键")
                                         # 直接使用VK码发送Enter键
                                         vk_code = VK_CODE.get('enter')
                                         if vk_code:
                                             time.sleep(0.05)
                                             # 使用PostMessage发送Enter键
                                             try:
                                                 scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                                                 lparam_down = _make_lparam(scan_code, False, 1, False, False)
                                                 lparam_up = _make_lparam(scan_code, False, 1, True, True)

                                                 # 发送Enter键
                                                 message_func(target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)
                                                 time.sleep(0.01)
                                                 message_func(target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)
                                                 logger.debug("新输入模拟系统发送Enter键成功")
                                             except Exception as e:
                                                 logger.error(f"新输入模拟系统发送Enter键异常: {e}")
                                         else:
                                             logger.warning("无法获取Enter键的VK码")

                                     # 执行延迟
                                     if params.get('enable_next_step_delay', False):
                                         _handle_next_step_delay(params, kwargs.get('stop_checker'))

                                     logger.info("新输入模拟系统文本输入任务执行成功")
                                     return True, success_action, success_jump_target
                                 else:
                                     logger.warning("新输入模拟系统文本输入失败，回退到传统方法")
                                     is_emulator = False
                             else:
                                 logger.warning("无法获取输入模拟器，回退到传统方法")
                                 is_emulator = False

                         except ImportError:
                             logger.warning("新输入模拟系统不可用，尝试旧的模拟器管理器")
                             manager = _get_emulator_manager()
                             logger.debug(f"模拟器管理器获取结果: {manager is not None}")
                             if manager:
                                 logger.info(f"使用旧模拟器文本输入方法: '{text_to_type}' (长度: {len(text_to_type)})")
                                 if manager.try_adb_shell_input(target_hwnd, text_to_type, text_input_mode):
                                     logger.info("旧模拟器文本输入成功")
                                 # 处理回车键
                                 if press_enter_after_text:
                                     logger.info("在模拟器文本输入后发送 Enter 键")
                                     # 直接使用VK码发送Enter键
                                     vk_code = VK_CODE.get('enter')
                                     if vk_code:
                                         time.sleep(0.05)
                                         # 使用PostMessage发送Enter键
                                         try:
                                                 scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                                                 lparam_down = _make_lparam(scan_code, False, 1, False, False)
                                                 lparam_up = _make_lparam(scan_code, False, 1, True, True)

                                                 # 发送Enter键
                                                 message_func(target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)
                                                 time.sleep(0.01)
                                                 message_func(target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)
                                                 logger.debug("PostMessage发送Enter键成功")
                                         except Exception as e:
                                             logger.error(f"发送Enter键异常: {e}")
                                     else:
                                         logger.warning("无法获取Enter键的VK码")

                                 # 执行延迟
                                 if params.get('enable_next_step_delay', False):
                                     _handle_next_step_delay(params, kwargs.get('stop_checker'))

                                 logger.info("模拟器文本输入任务执行成功")
                                 return True, success_action, success_jump_target
                             else:
                                 logger.warning("模拟器ADB文本输入失败，使用模拟器传统方法")
                                 # 使用模拟器专用的传统文本输入方法
                                 success = _send_text_to_emulator_window(target_hwnd, text_to_type, base_delay)
                                 if success:
                                     logger.info("模拟器传统文本输入成功")
                                     # 处理回车键
                                     if press_enter_after_text:
                                         logger.info("在模拟器传统文本输入后发送 Enter 键")
                                         vk_code = VK_CODE.get('enter')
                                         if vk_code:
                                             time.sleep(0.05)
                                             try:
                                                 scan_code = win32api.MapVirtualKey(vk_code, 0) if win32api else 0
                                                 lparam_down = _make_lparam(scan_code, False, 1, False, False)
                                                 lparam_up = _make_lparam(scan_code, False, 1, True, True)
                                                 message_func(target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)
                                                 time.sleep(0.01)
                                                 message_func(target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)
                                                 logger.debug("模拟器传统方法发送Enter键成功")
                                             except Exception as e:
                                                 logger.error(f"模拟器传统方法发送Enter键异常: {e}")

                                     # 执行延迟
                                     if params.get('enable_next_step_delay', False):
                                         _handle_next_step_delay(params, kwargs.get('stop_checker'))

                                     logger.info("模拟器传统文本输入任务执行成功")
                                     return True, success_action, success_jump_target
                                 else:
                                     logger.error("模拟器传统文本输入也失败")
                                     return False, failure_action, failure_jump_target
                         else:
                             logger.warning("无法获取模拟器管理器，跳过模拟器文本输入")
                     else:
                         logger.debug("非模拟器窗口，使用普通窗口文本输入方法")
                     # --- MODIFICATION START: Get focused control ---
                     actual_target_hwnd = target_hwnd # Default to main window handle
                     focused_hwnd = None
                     attach_success = False # Flag to track if attachment succeeded
                     current_thread_id = win32api.GetCurrentThreadId()
                     target_thread_id = win32process.GetWindowThreadProcessId(target_hwnd)[0] # Get thread ID of target window
                     logger.debug(f"当前线程 ID: {current_thread_id}, 目标窗口线程 ID: {target_thread_id}")

                     # Define AttachThreadInput using ctypes
                     # BOOL AttachThreadInput(DWORD idAttach, DWORD idAttachTo, BOOL fAttach);
                     try:
                         AttachThreadInput = ctypes.windll.user32.AttachThreadInput
                         AttachThreadInput.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL]
                         AttachThreadInput.restype = ctypes.wintypes.BOOL
                     except AttributeError:
                         logger.error("无法通过 ctypes 访问 AttachThreadInput 函数。后台获取焦点功能不可用。")
                         AttachThreadInput = None # Indicate function is unavailable

                     if AttachThreadInput:
                         try:
                             # Attach this thread's input processing to the target window's thread
                             # Only attach if the threads are different to avoid potential issues
                             if current_thread_id != target_thread_id:
                                 logger.debug("尝试附加到目标线程输入 (ctypes)...")
                                 # Call AttachThreadInput(idAttach=current_thread_id, idAttachTo=target_thread_id, fAttach=True)
                                 attach_success = AttachThreadInput(current_thread_id, target_thread_id, True)
                                 if attach_success:
                                     logger.debug(f"已附加到目标线程 {target_thread_id} 以获取焦点。")
                                 else:
                                     # GetLastError might provide more info, but requires more ctypes setup
                                     logger.error("附加到目标线程失败 (AttachThreadInput 返回失败)。可能由于权限或状态问题。")
                             else:
                                logger.debug("目标窗口与当前脚本在同一线程，无需附加线程输入。")
                                attach_success = False # Not actually attached, but not an error

                             # Get the handle of the control with focus in the target thread
                             # If attach failed or wasn't needed, GetFocus should still work if target is foreground
                             focused_hwnd = win32gui.GetFocus()
                             if focused_hwnd and focused_hwnd != 0:
                                 logger.info(f"获取到焦点控件句柄: {focused_hwnd}，将向此句柄发送消息。")
                                 actual_target_hwnd = focused_hwnd # Use the focused control
                             else:
                                 logger.warning(f"无法获取目标线程中的焦点控件句柄 (GetFocus 返回: {focused_hwnd})，将继续向主窗口 {target_hwnd} 发送。")

                         except Exception as e:
                             logger.error(f"尝试附加线程或获取焦点时出错: {e}")
                         finally:
                             # CRITICAL: Always detach the input threads if attached
                             if attach_success: # Only detach if attach succeeded and was necessary
                                try:
                                    logger.debug("尝试从目标线程分离 (ctypes)...")
                                    # Call AttachThreadInput(idAttach=current_thread_id, idAttachTo=target_thread_id, fAttach=False)
                                    detach_result = AttachThreadInput(current_thread_id, target_thread_id, False)
                                    if detach_result:
                                        logger.debug("已从目标线程分离。")
                                    else:
                                        logger.error("从目标线程分离失败 (AttachThreadInput 返回失败)。")
                                except Exception as e:
                                    logger.error(f"从目标线程分离时出错: {e}")
                     else:
                         logger.warning("AttachThreadInput 函数不可用，无法尝试获取焦点控件句柄。将向主窗口发送。")
                     # --- MODIFICATION END ---

                     # 关键洞察：输入框是单独的子控件，需要找到具体的输入框控件
                     logger.info("=== 寻找并定位实际的输入框子控件 ===")
                     logger.info("输入框是单独的子控件，需要找到具体的输入框控件而不是主窗口")
                     success = _find_and_send_to_input_control(actual_target_hwnd, text_to_type, base_delay)

                     if not success:
                         logger.warning("新方法失败，回退到原始方法")
                         # 回退到原始方法
                         for char in text_to_type:
                             # Calculate delay for this character (using same logic as foreground)
                             current_delay = base_delay
                             if base_delay >= RANDOM_DELAY_THRESHOLD:
                                 min_delay = base_delay * (1 - RANDOM_DELAY_FACTOR)
                                 max_delay = base_delay * (1 + RANDOM_DELAY_FACTOR)
                                 current_delay = random.uniform(min_delay, max_delay)

                             if current_delay > 0:
                                 # logger.debug(f"  暂停 {current_delay:.4f}s")
                                 time.sleep(current_delay)

                             # Use the determined target handle (either focused control or main window)
                             logger.debug(f"  发送字符 '{char}' (ord: {ord(char)}) 到句柄 {actual_target_hwnd}")
                             message_func(actual_target_hwnd, win32con.WM_CHAR, ord(char), 0) # <<< Use actual_target_hwnd

                     logger.info("后台文本输入完成。")

                if press_enter_after_text:
                     logger.info("在后台文本输入后发送 Enter 键。")
                     enter_vk = VK_CODE.get('enter')
                     if enter_vk:
                         time.sleep(0.05) # Small pause before enter
                         # Send Enter to the same target handle used for text
                         logger.debug(f"  发送 Enter (KEYDOWN) 到句柄 {actual_target_hwnd}")
                         message_func(actual_target_hwnd, win32con.WM_KEYDOWN, enter_vk, 0)
                         time.sleep(0.01)
                         logger.debug(f"  发送 Enter (KEYUP) 到句柄 {actual_target_hwnd}")
                         message_func(actual_target_hwnd, win32con.WM_KEYUP, enter_vk, 0)
                     else:
                         logger.warning("无法发送 Enter 键，未在 VK_CODE 映射中找到。")

            else:
                 logger.warning(f"未知的后台输入类型或缺少必要参数: {input_type}")
                 return False, failure_action, failure_jump_target

        elif execution_mode.startswith('foreground') or execution_mode is None:
            # 前台模式：根据具体的execution_mode选择不同的输入方法
            # foreground / foreground_driver → Interception驱动（硬件级模拟）
            # foreground_pyautogui → PyAutoGUI（系统级模拟）

            # Activate window if necessary
            _activate_foreground_window(target_hwnd)

            logger.info(f"前台模式：根据模式选择输入方法 (execution_mode={execution_mode})")

            # Perform action based on input_type
            if input_type == '单个按键' and key:
                logger.info(f"执行前台按键: '{key}'，次数: {press_count}，持续时间: {single_key_hold_duration}秒，间隔: {single_key_interval}秒")

                # 根据execution_mode选择输入方法
                if execution_mode == 'foreground_pyautogui':
                    # 前台模式二：使用PyAutoGUI
                    if not PYAUTOGUI_AVAILABLE:
                        logger.error("无法执行前台模式二：缺少 PyAutoGUI 库")
                        return False, failure_action, failure_jump_target

                    import pyautogui
                    for i in range(press_count):
                        logger.debug(f"  PyAutoGUI前台按键第 {i+1}/{press_count} 次")
                        if single_key_hold_duration > 0:
                            pyautogui.keyDown(key)
                            time.sleep(single_key_hold_duration)
                            pyautogui.keyUp(key)
                        else:
                            pyautogui.press(key)

                        if press_count > 1 and i < press_count - 1:
                            time.sleep(single_key_interval)

                else:
                    # 前台模式一/默认：使用Interception驱动
                    if not INTERCEPTION_AVAILABLE:
                        logger.error("无法执行前台模式一：缺少 Interception 驱动")
                        return False, failure_action, failure_jump_target

                    for i in range(press_count):
                        logger.debug(f"  Interception前台按键第 {i+1}/{press_count} 次")
                        if single_key_hold_duration > 0:
                            driver.key_down(key)
                            logger.debug(f"    按住按键 {single_key_hold_duration:.3f} 秒")
                            time.sleep(single_key_hold_duration)
                            driver.key_up(key)
                        else:
                            driver.press_key(key)

                        if press_count > 1 and i < press_count - 1:
                            time.sleep(single_key_interval)
            elif input_type == '组合键' and main_key:
                # Build the list of active modifiers based on NEW params
                active_modifiers = []
                if modifier_key_1 and modifier_key_1 != '无':
                    active_modifiers.append(modifier_key_1)
                if enable_modifier_key_2 and modifier_key_2 and modifier_key_2 != '无':
                    # Avoid adding the same modifier twice if selected in both dropdowns
                    if modifier_key_2 not in active_modifiers:
                         active_modifiers.append(modifier_key_2)
                    else:
                        logger.warning(f"修饰键 '{modifier_key_2}' 在两个下拉框中重复选择，只使用一次。")

                if not active_modifiers and not main_key:
                     logger.warning("组合键操作：未指定修饰键和主按键。")
                elif not main_key:
                     logger.warning(f"组合键操作：仅指定修饰键 {active_modifiers}，未指定主按键。仅按下/释放修饰键。")

                     # 根据execution_mode选择输入方法
                     if execution_mode == 'foreground_pyautogui':
                         # PyAutoGUI
                         if not PYAUTOGUI_AVAILABLE:
                             logger.error("无法执行前台模式二：缺少 PyAutoGUI 库")
                             return False, failure_action, failure_jump_target

                         import pyautogui
                         for i in range(repeat_count):
                             logger.debug(f"  PyAutoGUI重复 {i+1}/{repeat_count}: 按下修饰键 {active_modifiers}")
                             for mod in active_modifiers:
                                 pyautogui.keyDown(mod)
                             if modifier_hold_duration > 0:
                                 time.sleep(modifier_hold_duration)
                             logger.debug(f"  PyAutoGUI重复 {i+1}/{repeat_count}: 释放修饰键 {active_modifiers}")
                             for mod in reversed(active_modifiers):
                                 pyautogui.keyUp(mod)
                             if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                                 time.sleep(repeat_interval)

                     else:
                         # Interception驱动
                         if not INTERCEPTION_AVAILABLE:
                             logger.error("无法执行前台模式一：缺少 Interception 驱动")
                             return False, failure_action, failure_jump_target

                         for i in range(repeat_count):
                             logger.debug(f"  Interception重复 {i+1}/{repeat_count}: 按下修饰键 {active_modifiers}")
                             for mod in active_modifiers:
                                 driver.key_down(mod)
                             if modifier_hold_duration > 0:
                                 time.sleep(modifier_hold_duration)
                             logger.debug(f"  Interception重复 {i+1}/{repeat_count}: 释放修饰键 {active_modifiers}")
                             for mod in reversed(active_modifiers):
                                  driver.key_up(mod)
                             if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                                 time.sleep(repeat_interval)
                else:
                    # Execute the full hotkey sequence with hold times
                    logger.info(f"执行前台组合键: {active_modifiers} + '{main_key}', 重复: {repeat_count}, 修饰键保持: {modifier_hold_duration:.3f}s, 主键保持: {main_key_hold_duration:.3f}s, 重复间隔: {repeat_interval:.3f}s")

                    # 根据execution_mode选择输入方法
                    if execution_mode == 'foreground_pyautogui':
                        # PyAutoGUI
                        if not PYAUTOGUI_AVAILABLE:
                            logger.error("无法执行前台模式二：缺少 PyAutoGUI 库")
                            return False, failure_action, failure_jump_target

                        import pyautogui
                        for i in range(repeat_count):
                            logger.debug(f"-- PyAutoGUI开始重复 {i+1}/{repeat_count} --")
                            for mod in active_modifiers:
                                pyautogui.keyDown(mod)
                            if modifier_hold_duration > 0:
                                time.sleep(modifier_hold_duration)
                            pyautogui.keyDown(main_key)
                            if main_key_hold_duration > 0:
                                time.sleep(main_key_hold_duration)
                            pyautogui.keyUp(main_key)
                            for mod in reversed(active_modifiers):
                                pyautogui.keyUp(mod)
                            logger.debug(f"-- PyAutoGUI结束重复 {i+1}/{repeat_count} --")
                            if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                                time.sleep(repeat_interval)

                    else:
                        # Interception驱动
                        if not INTERCEPTION_AVAILABLE:
                            logger.error("无法执行前台模式一：缺少 Interception 驱动")
                            return False, failure_action, failure_jump_target

                        for i in range(repeat_count):
                            logger.debug(f"-- Interception开始重复 {i+1}/{repeat_count} --")
                            for mod in active_modifiers:
                                driver.key_down(mod)
                            if modifier_hold_duration > 0:
                                time.sleep(modifier_hold_duration)
                            driver.key_down(main_key)
                            if main_key_hold_duration > 0:
                                time.sleep(main_key_hold_duration)
                            driver.key_up(main_key)
                            for mod in reversed(active_modifiers):
                                driver.key_up(mod)
                            logger.debug(f"-- Interception结束重复 {i+1}/{repeat_count} --")
                            if repeat_count > 1 and i < repeat_count - 1 and repeat_interval > 0:
                                time.sleep(repeat_interval)

            elif input_type == '文本输入':
                # 处理多组文本输入
                if text_input_mode == '多组文本':
                    text_groups = _parse_text_groups(text_groups_str)
                    if not text_groups:
                        logger.warning("多组文本模式下未提供有效的文本组，切换到单组模式")
                        text_input_mode = '单组文本'
                    else:
                        logger.info(f"解析到{len(text_groups)}组文本: {text_groups}")

                        # 获取当前窗口索引
                        window_index = _get_current_window_index(kwargs.get('card_id', 0), target_hwnd)

                        # 处理多组文本输入逻辑
                        actual_text, next_card_id = _handle_multi_text_input(
                            text_groups, kwargs.get('card_id', 0), window_index, reset_text_groups_on_next_run
                        )

                        if actual_text:
                            text_to_type = actual_text
                            logger.info(f"多组文本模式: 窗口{window_index}将输入文本: '{text_to_type}'")
                        else:
                            logger.info("多组文本输入完成或无可用文本")
                            # 处理下一步延迟执行
                            if params.get('enable_next_step_delay', False):
                                _handle_next_step_delay(params, kwargs.get('stop_checker'))
                            return True, success_action, success_jump_target

                # 处理单组文本输入 - 完全独立的逻辑，不使用多组文字的状态管理
                if text_input_mode == '单组文本':
                    # 单组文字输入：简单的窗口索引计算，不依赖多组文字的复杂状态
                    # 使用固定的HWND列表进行索引计算
                    known_hwnds = [132484, 67594, 5309938]
                    if target_hwnd in known_hwnds:
                        window_index = known_hwnds.index(target_hwnd)
                    else:
                        # 使用简单的哈希算法
                        window_index = abs(target_hwnd) % 3

                    logger.info(f"单组文本模式: 窗口{window_index}(HWND:{target_hwnd})将输入文本: '{text_to_type}'")

                    # 单组文本模式下，所有窗口都输入相同的文本
                    # text_to_type 已经在参数解析时设置好了

                logger.info(f"执行前台文本输入 (长度: {len(text_to_type)}) 到窗口 {target_hwnd}，间隔: {base_delay}s")
                if not text_to_type:
                    logger.info("要输入的文本为空，跳过输入。")
                else:
                     # 根据execution_mode选择输入方法
                     logger.debug(f"前台文本输入：根据模式选择输入方法 (execution_mode={execution_mode})")

                     # 检测文本是否包含非ASCII字符
                     has_non_ascii = any(ord(char) > 127 for char in text_to_type)

                     if execution_mode == 'foreground_pyautogui':
                         # 前台模式二：PyAutoGUI
                         if not PYAUTOGUI_AVAILABLE:
                             logger.error("无法执行前台模式二：缺少 PyAutoGUI 库")
                             return False, failure_action, failure_jump_target

                         import pyautogui
                         logger.debug("使用PyAutoGUI输入文本")
                         try:
                             if has_non_ascii:
                                 # 复制粘贴方式
                                 if not PYPERCLIP_AVAILABLE:
                                     logger.error("无法复制粘贴：缺少 pyperclip 库")
                                     return False, failure_action, failure_jump_target
                                 pyperclip.copy(text_to_type)
                                 time.sleep(0.05)
                                 pyautogui.hotkey('ctrl', 'v')
                                 time.sleep(0.1)
                             else:
                                 # 直接输入
                                 pyautogui.write(text_to_type, interval=base_delay)
                                 time.sleep(0.1)
                         except Exception as e:
                             logger.exception(f"PyAutoGUI文本输入失败: {e}")
                             return False, failure_action, failure_jump_target

                     else:
                         # 前台模式一/默认：Interception驱动
                         if not INTERCEPTION_AVAILABLE:
                             logger.error("无法执行前台模式一：缺少 Interception 驱动")
                             return False, failure_action, failure_jump_target

                         logger.debug("使用Interception驱动输入文本")
                         try:
                             if has_non_ascii:
                                 # 复制粘贴方式
                                 if not PYPERCLIP_AVAILABLE:
                                     logger.error("无法复制粘贴：缺少 pyperclip 库")
                                     return False, failure_action, failure_jump_target
                                 pyperclip.copy(text_to_type)
                                 time.sleep(0.05)
                                 driver.hotkey('ctrl', 'v')
                                 time.sleep(0.1)
                             else:
                                 # 直接输入
                                 driver.type_text(text_to_type, delay=base_delay)
                                 time.sleep(0.1)
                         except Exception as e:
                             logger.exception(f"Interception文本输入失败: {e}")
                             return False, failure_action, failure_jump_target

                if press_enter_after_text:
                    logger.info("在前台文本输入后按下 Enter 键。")
                    time.sleep(0.05)
                    # 根据execution_mode选择输入方法
                    if execution_mode == 'foreground_pyautogui':
                        import pyautogui
                        pyautogui.press('enter')
                    else:
                        driver.press_key('enter')
                    # ---------------------------------------------------------
            else:
                 logger.warning(f"未知的输入类型或缺少必要参数: {input_type}")
                 # Consider this a failure
                 return False, failure_action, failure_jump_target

        else:
            # 执行模式中文映射
            mode_names = {'foreground': '前台', 'background': '后台'}
            mode_name = mode_names.get(execution_mode, execution_mode)
            logger.error(f"未知的执行模式: '{mode_name}'。无法执行键盘输入。")
            return False, failure_action, failure_jump_target

        # If we reached here without returning failure, assume success
        logger.info("键盘输入任务执行成功。")

        # 处理下一步延迟执行（只在执行下一步时应用）
        action = '执行下一步'
        if params.get('enable_next_step_delay', False):
            logger.info(f"键盘输入延迟检查: enable_next_step_delay={params.get('enable_next_step_delay')}, action={action}")
            if action == '执行下一步':
                logger.info(f"开始执行键盘输入下一步延迟")
                _handle_next_step_delay(params, kwargs.get('stop_checker'))
            else:
                logger.info(f"跳过键盘输入延迟，动作类型不匹配: {action}")
        else:
            logger.info(f"跳过键盘输入延迟: enable_next_step_delay={params.get('enable_next_step_delay', False)}")

        return True, action, None

    except Exception as e:
        logger.exception(f"执行键盘输入操作时发生意外错误: {e}")
        # --- MODIFIED: Return Chinese action based on failure_action ---
        if failure_action == '跳转到步骤' and failure_jump_target is not None:
             return False, '跳转到步骤', failure_jump_target
        elif failure_action == '停止工作流':
             return False, '停止工作流', None
        else: # Default to 'continue' which means '执行下一步'
             return False, '执行下一步', None
        # -----------------------------------------------------------

# ==================================
#  Task Parameter Definitions (for UI)
# ==================================
def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """定义键盘输入任务的参数"""

    # --- 按功能分类的按键选项列表 ---
    # 按使用频率和逻辑分组，便于用户查找

    # 常用字母键 (a-z)
    letters = [chr(i) for i in range(ord('a'), ord('z') + 1)]

    # 数字键 (0-9)
    numbers = [str(i) for i in range(10)]

    # 功能键 (F1-F12)
    function_keys = [f'f{i}' for i in range(1, 13)]

    # 常用编辑键
    edit_keys = ['enter', 'space', 'tab', 'backspace', 'delete', 'insert']

    # 导航键
    navigation_keys = ['up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown']

    # 修饰键
    modifier_keys = ['ctrl', 'alt', 'shift', 'win']

    # 系统键
    system_keys = ['esc', 'capslock', 'numlock', 'scrolllock', 'pause', 'apps']

    # 符号键（按键盘布局顺序）
    symbol_keys = ['`', '-', '=', '[', ']', '\\', ';', "'", ',', '.', '/']

    # 数字键盘
    numpad_keys = [f'numpad{i}' for i in range(10)] + ['add', 'subtract', 'multiply', 'divide', 'decimal']

    # 其他键
    other_keys = ['lwin', 'rwin', 'separator']

    # 按逻辑顺序组合所有按键，添加分组分隔符
    all_key_options = []

    # 字母键分组
    all_key_options.append("=== 字母键 ===")
    all_key_options.extend(letters)

    # 数字键分组
    all_key_options.append("=== 数字键 ===")
    all_key_options.extend(numbers)

    # 功能键分组
    all_key_options.append("=== 功能键 ===")
    all_key_options.extend(function_keys)

    # 编辑键分组
    all_key_options.append("=== 编辑键 ===")
    all_key_options.extend(edit_keys)

    # 导航键分组
    all_key_options.append("=== 导航键 ===")
    all_key_options.extend(navigation_keys)

    # 修饰键分组
    all_key_options.append("=== 修饰键 ===")
    all_key_options.extend(modifier_keys)

    # 系统键分组
    all_key_options.append("=== 系统键 ===")
    all_key_options.extend(system_keys)

    # 符号键分组
    all_key_options.append("=== 符号键 ===")
    all_key_options.extend(symbol_keys)

    # 数字键盘分组
    all_key_options.append("=== 数字键盘 ===")
    all_key_options.extend(numpad_keys)

    # 其他键分组
    if other_keys:  # 只有在有其他键时才添加分组
        all_key_options.append("=== 其他键 ===")
        all_key_options.extend(other_keys)

    return {
        "input_type": {
            "label": "输入类型",
            "type": "select",
            "options": ["单个按键", "组合键", "文本输入"],
            "default": "文本输入",
            "tooltip": "选择要执行的键盘操作类型"
        },

        # 单个按键参数
        "---single_key_params---": {
            "type": "separator",
            "label": "单个按键参数",
            "condition": {"param": "input_type", "value": "单个按键"}
        },
        "key": {
            "label": "按键",
            "type": "select", # <--- Changed back to "select"
            "options": all_key_options, # <--- Use the combined list
            "default": "enter",
            "tooltip": "选择要按下的单个字母、数字或特殊按键。", # <--- Updated tooltip
            "condition": {"param": "input_type", "value": "单个按键"}
        },
        # --- ADDED: Press Count for Single Key ---
        "press_count": {
            "label": "按键次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "设置单次按键动作重复的次数。",
            "condition": {"param": "input_type", "value": "单个按键"}
        },
        # --- ADDED: Interval for Single Key Repeat ---
        "single_key_interval": {
             "label": "重复间隔(秒)",
             "type": "float",
             "default": 0.05,
             "min": 0.0,
             "decimals": 3,
             "tooltip": "设置单次按键多次重复之间的延迟时间。",
             "condition": {"param": "input_type", "value": "单个按键"}
        },
        # --- ADDED: Hold Duration for Single Key ---
        "single_key_hold_duration": {
             "label": "按键持续时间(秒)",
             "type": "float",
             "default": 0.0,
             "min": 0.0,
             "decimals": 3,
             "tooltip": "设置单个按键按住的持续时间（0表示瞬间按下松开）。",
             "condition": {"param": "input_type", "value": "单个按键"}
        },

        # 组合键参数
        "---combo_key_params---": {
            "type": "separator",
            "label": "组合键参数",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "modifier_key_1": {
            "label": "修饰键 1",
            "type": "select",
            "options": ["无", "ctrl", "alt", "shift", "win"],
            "default": "ctrl",
            "tooltip": "选择第一个修饰键。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "enable_modifier_key_2": {
            "label": "启用修饰键 2",
            "type": "bool",
            "default": False,
            "tooltip": "是否启用第二个修饰键。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "modifier_key_2": {
            "label": "修饰键 2",
            "type": "select",
            "options": ["无", "ctrl", "alt", "shift", "win"],
            "default": "无",
            "tooltip": "选择第二个修饰键。",
            "condition": {"param": "enable_modifier_key_2", "value": True}
        },
        "modifier_key_hold_duration": {
            "label": "修饰键按住时长(秒)",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "decimals": 3,
            "tooltip": "设置修饰键被按下的持续时间（大于0生效）。后台模式下会影响按下和释放消息间的间隔。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "main_key": {
            "label": "主按键",
            "type": "text",
            "default": "c",
            "tooltip": "输入与修饰键一起按下的主按键 (例如: 'c', 'v', 'f4', 'enter', ';')。后台模式需要能在 VK_CODE 映射中找到。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "main_key_hold_duration": {
            "label": "主按键按住时长(秒)",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "decimals": 3,
            "tooltip": "设置主按键被按下的持续时间（大于0生效）。后台模式下会影响按下和释放消息间的间隔。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "repeat_count": {
            "label": "重复次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "设置整个组合键序列重复执行的次数。",
            "condition": {"param": "input_type", "value": "组合键"}
        },
        "repeat_interval": {
            "label": "重复间隔(秒)",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "decimals": 3,
            "tooltip": "设置多次重复组合键之间的延迟时间。",
            "condition": {"param": "input_type", "value": "组合键"}
        },

        # 文本输入参数
        "---text_input_params---": {
            "type": "separator",
            "label": "文本输入参数",
            "condition": {"param": "input_type", "value": "文本输入"}
        },
        "text_input_mode": {
            "label": "文本输入模式",
            "type": "select",
            "options": ["单组文本", "多组文本"],
            "default": "单组文本",
            "tooltip": "选择单组文本输入还是多组文本循环输入",
            "condition": {"param": "input_type", "value": "文本输入"}
        },
        "text_to_type": {
            "label": "输入文本",
            "type": "textarea",
            "default": "",
            "tooltip": "输入要自动键入的文本内容。后台模式使用 WM_CHAR 发送。",
            "condition": [
                {"param": "input_type", "value": "文本输入"},
                {"param": "text_input_mode", "value": "单组文本"}
            ]
        },
        "text_groups": {
            "label": "多组文本列表",
            "type": "textarea",
            "default": "",
            "tooltip": "用换行符分隔多组文本，按顺序循环输入。例如：\n第一组文本\n第二组文本\n第三组文本\n\n在多窗口模式下，第一个窗口输入第一组，第二个窗口输入第二组，以此类推。",
            "condition": [
                {"param": "input_type", "value": "文本输入"},
                {"param": "text_input_mode", "value": "多组文本"}
            ]
        },
        "delay_between_keystrokes": {
            "label": "键入间隔(秒)",
            "type": "float",
            "default": 0.1, # Increased default for better visibility
            "min": 0.0,
            "decimals": 3,
            "tooltip": "设置输入文本时每个字符之间的延迟时间（秒）。后台模式下是 WM_CHAR 消息间的间隔。",
            "condition": {"param": "input_type", "value": "文本输入"}
        },
         "press_enter_after_text": {
            "label": "输完后按回车",
            "type": "bool",
            "default": False,
            "tooltip": "勾选此项，在输入完指定文本后自动按一次回车键。",
            "condition": {"param": "input_type", "value": "文本输入"}
        },
        "reset_text_groups_on_next_run": {
            "label": "下次执行重置文本组记录",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，下次执行时会重置多组文本的进度，从第一组重新开始。仅在多组文本模式下有效。",
            "condition": [
                {"param": "input_type", "value": "文本输入"},
                {"param": "text_input_mode", "value": "多组文本"}
            ]
        },

        # 下一步延迟执行参数
        "---next_step_delay---": {"type": "separator", "label": "下一步延迟执行"},
        "enable_next_step_delay": {
            "label": "启用下一步延迟执行",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，执行完当前操作会等待指定时间再执行下一步"
        },
        "delay_mode": {
            "label": "延迟模式",
            "type": "select",
            "options": ["固定延迟", "随机延迟"],
            "default": "固定延迟",
            "tooltip": "选择固定延迟时间还是随机延迟时间",
            "condition": {"param": "enable_next_step_delay", "value": True}
        },
        "fixed_delay": {
            "label": "固定延迟 (秒)",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置固定的延迟时间",
            "condition": {"param": "delay_mode", "value": "固定延迟"}
        },
        "min_delay": {
            "label": "最小延迟 (秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最小值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },
        "max_delay": {
            "label": "最大延迟 (秒)",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最大值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        }
        # TODO: Add common failure parameters if needed (on_failure, failure_jump_target_id)
        # Or assume they are handled by the executor based on the return tuple
    }


def _find_and_send_to_input_control(hwnd: int, text: str, base_delay: float = 0.0) -> bool:
    """
    寻找并定位实际的输入框子控件
    关键：输入框是单独的子控件，不是主窗口
    """
    try:
        import win32api
        import win32con
        import win32gui
        import time
        import random
        import ctypes

        logger.info(f"[寻找输入框] 开始寻找实际的输入框子控件: '{text}' (长度: {len(text)})")

        # 方法1：寻找当前有焦点的子控件
        focused_control = _find_focused_child_control(hwnd)
        if focused_control:
            logger.info(f"[寻找输入框] 找到有焦点的子控件: {focused_control}")
            success = _send_text_to_specific_control(focused_control, text, base_delay)
            if success:
                return True

        # 方法2：枚举所有可能的输入框子控件
        input_controls = _find_all_input_controls(hwnd)
        if input_controls:
            logger.info(f"[寻找输入框] 找到 {len(input_controls)} 个可能的输入控件")

            for control_hwnd, class_name, window_text in input_controls:
                logger.debug(f"[寻找输入框] 尝试控件 {control_hwnd} ({class_name}) 文本:'{window_text}'")
                success = _send_text_to_specific_control(control_hwnd, text, base_delay)
                if success:
                    logger.info(f"[寻找输入框] 成功发送到控件 {control_hwnd} ({class_name})")
                    return True

        # 方法3：使用GetFocus尝试获取当前焦点控件
        success = _send_text_via_getfocus(hwnd, text, base_delay)
        if success:
            return True

        logger.warning("[寻找输入框] 未找到有效的输入框控件")
        return False

    except Exception as e:
        logger.error(f"[寻找输入框] 发送失败: {e}")
        return False


def _find_focused_child_control(parent_hwnd: int) -> int:
    """
    寻找当前有焦点的子控件
    """
    try:
        import win32gui
        import win32process
        import ctypes

        logger.debug("[寻找焦点控件] 开始寻找有焦点的子控件")

        # 方法1：通过AttachThreadInput获取焦点
        try:
            current_thread = win32api.GetCurrentThreadId()
            target_thread, _ = win32process.GetWindowThreadProcessId(parent_hwnd)

            if current_thread != target_thread:
                # 附加到目标线程
                attach_result = ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)

                if attach_result:
                    try:
                        # 获取焦点控件
                        focused_hwnd = win32gui.GetFocus()

                        if focused_hwnd and focused_hwnd != parent_hwnd:
                            logger.debug(f"[寻找焦点控件] 通过AttachThreadInput找到焦点控件: {focused_hwnd}")
                            return focused_hwnd

                    finally:
                        # 分离线程
                        ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
        except Exception as e:
            logger.debug(f"[寻找焦点控件] AttachThreadInput方法失败: {e}")

        # 方法2：通过GetGUIThreadInfo获取焦点信息
        try:
            import ctypes
            from ctypes import wintypes, Structure

            class GUITHREADINFO(Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND),
                    ("hwndCapture", wintypes.HWND),
                    ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND),
                    ("hwndCaret", wintypes.HWND),
                    ("rcCaret", wintypes.RECT),
                ]

            target_thread, _ = win32process.GetWindowThreadProcessId(parent_hwnd)
            gui_info = GUITHREADINFO()
            gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)

            result = ctypes.windll.user32.GetGUIThreadInfo(target_thread, ctypes.byref(gui_info))

            if result and gui_info.hwndFocus:
                logger.debug(f"[寻找焦点控件] 通过GetGUIThreadInfo找到焦点控件: {gui_info.hwndFocus}")
                return gui_info.hwndFocus

        except Exception as e:
            logger.debug(f"[寻找焦点控件] GetGUIThreadInfo方法失败: {e}")

        logger.debug("[寻找焦点控件] 未找到有焦点的子控件")
        return 0

    except Exception as e:
        logger.debug(f"[寻找焦点控件] 失败: {e}")
        return 0


def _find_all_input_controls(parent_hwnd: int) -> list:
    """
    枚举所有可能的输入框子控件
    """
    try:
        import win32gui

        logger.debug("[枚举输入控件] 开始枚举所有可能的输入控件")

        input_controls = []

        def enum_child_proc(hwnd_child, lparam):
            try:
                class_name = win32gui.GetClassName(hwnd_child)
                window_text = win32gui.GetWindowText(hwnd_child)

                # 扩展的输入控件类名列表
                input_classes = [
                    'Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W',
                    'ComboBox', 'ListBox', 'SysListView32', 'SysTreeView32',
                    # 游戏可能使用的控件
                    'DirectUIHWND', 'Internet Explorer_Server', 'Shell DocObject View',
                    'Static', 'Button',  # 有时候游戏用这些做输入框
                    # 可能的游戏引擎控件
                    'UnityWndClass', 'UnrealWindow', 'CryENGINE', 'GameOverlayUI',
                    # 其他可能的控件
                    'ATL:', 'Chrome_', 'Webkit', 'Gecko'
                ]

                # 如果类名匹配或者是可见的有文本的控件
                is_input_class = any(input_class in class_name for input_class in input_classes)
                is_visible = win32gui.IsWindowVisible(hwnd_child)

                if is_input_class or (is_visible and window_text):
                    input_controls.append((hwnd_child, class_name, window_text))
                    logger.debug(f"[枚举输入控件] 找到候选控件: {hwnd_child} ({class_name}) '{window_text}'")

            except Exception as e:
                logger.debug(f"[枚举输入控件] 枚举子控件失败: {e}")

            return True

        # 枚举所有子窗口
        try:
            win32gui.EnumChildWindows(parent_hwnd, enum_child_proc, 0)
        except Exception as e:
            logger.debug(f"[枚举输入控件] EnumChildWindows失败: {e}")

        # 按优先级排序
        def control_priority(control):
            hwnd_child, class_name, window_text = control
            if 'Edit' in class_name or 'RichEdit' in class_name:
                return 0  # 最高优先级
            elif 'ComboBox' in class_name or 'ListBox' in class_name:
                return 1  # 中等优先级
            elif window_text:  # 有文本内容的控件
                return 2
            else:
                return 3  # 最低优先级

        input_controls.sort(key=control_priority)

        logger.debug(f"[枚举输入控件] 总共找到 {len(input_controls)} 个候选控件")
        return input_controls

    except Exception as e:
        logger.debug(f"[枚举输入控件] 失败: {e}")
        return []


def _send_text_to_specific_control(control_hwnd: int, text: str, base_delay: float) -> bool:
    """
    向特定的控件发送文本
    """
    try:
        import win32gui
        import win32con
        import pyperclip
        import time
        import ctypes

        logger.debug(f"[发送到控件] 开始向控件 {control_hwnd} 发送文本: '{text}'")

        # 获取控件信息
        try:
            class_name = win32gui.GetClassName(control_hwnd)
            window_text = win32gui.GetWindowText(control_hwnd)
            logger.debug(f"[发送到控件] 控件信息: 类名={class_name}, 文本='{window_text}'")
        except:
            class_name = "Unknown"
            window_text = ""

        # 方法1：剪贴板粘贴（最可靠）
        try:
            logger.debug("[发送到控件] 尝试剪贴板粘贴方法")

            # 备份剪贴板
            original_clipboard = ""
            try:
                original_clipboard = pyperclip.paste()
            except:
                pass

            # 复制文本到剪贴板
            pyperclip.copy(text)
            time.sleep(0.1)

            # 尝试WM_PASTE
            result = win32gui.SendMessage(control_hwnd, win32con.WM_PASTE, 0, 0)
            logger.debug(f"[发送到控件] WM_PASTE结果: {result}")

            time.sleep(0.2)

            # 恢复剪贴板
            try:
                if original_clipboard:
                    pyperclip.copy(original_clipboard)
            except:
                pass

            # 验证是否成功
            try:
                new_text = win32gui.GetWindowText(control_hwnd)
                if text in new_text or new_text != window_text:
                    logger.info(f"[发送到控件] 剪贴板粘贴成功，控件文本变为: '{new_text}'")
                    return True
            except:
                pass

            logger.info(f"[发送到控件] 剪贴板粘贴方法完成")
            return True

        except Exception as clipboard_error:
            logger.debug(f"[发送到控件] 剪贴板方法失败: {clipboard_error}")

        # 方法2：EM_REPLACESEL（针对编辑框）
        if 'Edit' in class_name or 'RichEdit' in class_name:
            try:
                logger.debug("[发送到控件] 尝试EM_REPLACESEL方法")

                EM_REPLACESEL = 0x00C2
                text_buffer = ctypes.create_unicode_buffer(text)
                result = win32gui.SendMessage(control_hwnd, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))

                if result == 0:
                    logger.info(f"[发送到控件] EM_REPLACESEL成功")
                    return True

            except Exception as em_error:
                logger.debug(f"[发送到控件] EM_REPLACESEL失败: {em_error}")

        # 方法3：SetWindowText
        try:
            logger.debug("[发送到控件] 尝试SetWindowText方法")

            result = win32gui.SetWindowText(control_hwnd, text)

            if result:
                # 验证设置是否成功
                new_text = win32gui.GetWindowText(control_hwnd)
                if new_text == text:
                    logger.info(f"[发送到控件] SetWindowText成功，文本设置为: '{new_text}'")
                    return True

        except Exception as settext_error:
            logger.debug(f"[发送到控件] SetWindowText失败: {settext_error}")

        # 方法4：WM_CHAR逐字符发送
        try:
            logger.debug("[发送到控件] 尝试WM_CHAR逐字符发送")

            for char in text:
                char_code = ord(char)
                win32gui.SendMessage(control_hwnd, win32con.WM_CHAR, char_code, 0)
                time.sleep(0.05)

            logger.info(f"[发送到控件] WM_CHAR方法完成")
            return True

        except Exception as char_error:
            logger.debug(f"[发送到控件] WM_CHAR方法失败: {char_error}")

        logger.debug(f"[发送到控件] 所有方法都失败")
        return False

    except Exception as e:
        logger.debug(f"[发送到控件] 发送失败: {e}")
        return False


def _send_text_via_getfocus(hwnd: int, text: str, base_delay: float) -> bool:
    """
    通过GetFocus获取焦点控件并发送文本
    """
    try:
        import win32gui
        import win32process
        import ctypes

        logger.debug("[GetFocus方法] 开始尝试GetFocus方法")

        # 获取目标窗口的线程ID
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        current_thread = win32api.GetCurrentThreadId()

        if current_thread == target_thread:
            # 同一线程，直接获取焦点
            try:
                focused_hwnd = win32gui.GetFocus()
                if focused_hwnd:
                    logger.debug(f"[GetFocus方法] 找到焦点控件: {focused_hwnd}")
                    return _send_text_to_specific_control(focused_hwnd, text, base_delay)
            except:
                pass
        else:
            # 不同线程，需要附加
            try:
                attach_result = ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)

                if attach_result:
                    try:
                        focused_hwnd = win32gui.GetFocus()
                        if focused_hwnd:
                            logger.debug(f"[GetFocus方法] 通过AttachThreadInput找到焦点控件: {focused_hwnd}")
                            success = _send_text_to_specific_control(focused_hwnd, text, base_delay)
                            return success
                    finally:
                        ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
            except Exception as e:
                logger.debug(f"[GetFocus方法] AttachThreadInput失败: {e}")

        logger.debug("[GetFocus方法] 未找到焦点控件")
        return False

    except Exception as e:
        logger.debug(f"[GetFocus方法] 失败: {e}")
        return False


# 旧的无效函数已删除，新的实现在上面

def _placeholder_old_functions_removed(text: str, hwnd: int):
    """
    方法1：剪贴板粘贴方法（针对有焦点的输入框）
    """
    try:
        import pyperclip
        import win32api
        import win32con
        import win32gui
        import time

        logger.debug("[焦点剪贴板] 开始尝试剪贴板粘贴")

        # 备份当前剪贴板内容
        original_clipboard = ""
        try:
            original_clipboard = pyperclip.paste()
        except:
            pass

        try:
            # 将文本复制到剪贴板
            pyperclip.copy(text)
            time.sleep(0.1)  # 等待剪贴板操作完成

            logger.debug(f"[焦点剪贴板] 文本已复制到剪贴板: '{text}'")

            # 方法1a：发送WM_PASTE消息
            try:
                result = win32gui.SendMessage(hwnd, win32con.WM_PASTE, 0, 0)
                logger.debug(f"[焦点剪贴板] WM_PASTE消息发送结果: {result}")

                # 等待一下看是否生效
                time.sleep(0.2)

                # 恢复剪贴板
                try:
                    if original_clipboard:
                        pyperclip.copy(original_clipboard)
                except:
                    pass

                logger.info("[焦点剪贴板] WM_PASTE方法完成")
                return True

            except Exception as paste_error:
                logger.debug(f"[焦点剪贴板] WM_PASTE失败: {paste_error}")

            # 方法1b：发送Ctrl+V组合键
            try:
                logger.debug("[焦点剪贴板] 尝试发送Ctrl+V组合键")

                # 使用SendMessage发送Ctrl+V
                ctrl_scan_code = win32api.MapVirtualKey(win32con.VK_CONTROL, 0)
                v_scan_code = win32api.MapVirtualKey(ord('V'), 0)

                # 构造lParam
                lparam_ctrl_down = (ctrl_scan_code << 16) | 1
                lparam_v_down = (v_scan_code << 16) | 1
                lparam_v_up = (v_scan_code << 16) | 0xC0000001
                lparam_ctrl_up = (ctrl_scan_code << 16) | 0xC0000001

                # 发送按键序列
                win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, lparam_ctrl_down)
                time.sleep(0.01)
                win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, ord('V'), lparam_v_down)
                time.sleep(0.01)
                win32gui.SendMessage(hwnd, win32con.WM_KEYUP, ord('V'), lparam_v_up)
                time.sleep(0.01)
                win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, lparam_ctrl_up)

                time.sleep(0.2)  # 等待粘贴完成

                logger.info("[焦点剪贴板] Ctrl+V方法完成")

                # 恢复剪贴板
                try:
                    if original_clipboard:
                        pyperclip.copy(original_clipboard)
                except:
                    pass

                return True

            except Exception as ctrlv_error:
                logger.debug(f"[焦点剪贴板] Ctrl+V失败: {ctrlv_error}")

            # 恢复剪贴板
            try:
                if original_clipboard:
                    pyperclip.copy(original_clipboard)
            except:
                pass

            return False

        except Exception as e:
            logger.debug(f"[焦点剪贴板] 剪贴板操作失败: {e}")
            # 尝试恢复剪贴板
            try:
                if original_clipboard:
                    pyperclip.copy(original_clipboard)
            except:
                pass
            return False

    except ImportError:
        logger.debug("[焦点剪贴板] pyperclip库不可用")
        return False
    except Exception as e:
        logger.debug(f"[焦点剪贴板] 失败: {e}")
        return False


def _send_text_via_char_messages_to_focused(hwnd: int, text: str, base_delay: float) -> bool:
    """
    方法2：直接字符消息（针对有焦点的输入框）
    """
    try:
        import win32gui
        import win32con
        import time
        import random

        logger.debug("[焦点字符消息] 开始尝试字符消息方法")

        for char in text:
            # 计算延迟
            current_delay = base_delay
            if base_delay >= RANDOM_DELAY_THRESHOLD:
                min_delay = base_delay * (1 - RANDOM_DELAY_FACTOR)
                max_delay = base_delay * (1 + RANDOM_DELAY_FACTOR)
                current_delay = random.uniform(min_delay, max_delay)

            if current_delay > 0:
                time.sleep(current_delay)

            char_code = ord(char)

            # 对于有焦点的输入框，直接发送WM_CHAR应该更有效
            try:
                # 使用SendMessage确保同步处理
                win32gui.SendMessage(hwnd, win32con.WM_CHAR, char_code, 0)
                logger.debug(f"[焦点字符消息] 发送字符 '{char}' (code: {char_code})")

            except Exception as char_error:
                logger.debug(f"[焦点字符消息] 字符 '{char}' 发送失败: {char_error}")
                return False

        logger.info("[焦点字符消息] 所有字符发送完成")
        return True

    except Exception as e:
        logger.debug(f"[焦点字符消息] 失败: {e}")
        return False


def _send_text_via_vk_to_focused(hwnd: int, text: str, base_delay: float) -> bool:
    """
    方法3：虚拟键码方法（针对有焦点的输入框）
    """
    try:
        import win32api
        import win32con
        import win32gui
        import time
        import random

        logger.debug("[焦点VK码] 开始尝试虚拟键码方法")

        for char in text:
            # 计算延迟
            current_delay = base_delay
            if base_delay >= RANDOM_DELAY_THRESHOLD:
                min_delay = base_delay * (1 - RANDOM_DELAY_FACTOR)
                max_delay = base_delay * (1 + RANDOM_DELAY_FACTOR)
                current_delay = random.uniform(min_delay, max_delay)

            if current_delay > 0:
                time.sleep(current_delay)

            # 尝试获取虚拟键码
            vk_code = win32api.VkKeyScan(char)

            if vk_code != -1:
                vk = vk_code & 0xFF
                shift = (vk_code >> 8) & 0x01

                try:
                    scan_code = win32api.MapVirtualKey(vk, 0)

                    if shift:
                        # 需要Shift键
                        shift_scan_code = win32api.MapVirtualKey(win32con.VK_SHIFT, 0)

                        # Shift按下
                        lparam_shift_down = (shift_scan_code << 16) | 1
                        win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_SHIFT, lparam_shift_down)

                        # 字符按键
                        lparam_char_down = (scan_code << 16) | 1
                        lparam_char_up = (scan_code << 16) | 0xC0000001
                        win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam_char_down)
                        win32gui.SendMessage(hwnd, win32con.WM_KEYUP, vk, lparam_char_up)

                        # Shift释放
                        lparam_shift_up = (shift_scan_code << 16) | 0xC0000001
                        win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_SHIFT, lparam_shift_up)

                    else:
                        # 普通字符
                        lparam_down = (scan_code << 16) | 1
                        lparam_up = (scan_code << 16) | 0xC0000001
                        win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
                        win32gui.SendMessage(hwnd, win32con.WM_KEYUP, vk, lparam_up)

                    logger.debug(f"[焦点VK码] 发送VK码字符 '{char}' (VK: {vk}, Shift: {shift})")

                except Exception as vk_error:
                    logger.debug(f"[焦点VK码] VK码方法失败: {vk_error}，回退到WM_CHAR")
                    # 回退到WM_CHAR
                    win32gui.SendMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
            else:
                # 无法映射的字符，直接发送WM_CHAR
                win32gui.SendMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
                logger.debug(f"[焦点VK码] 发送WM_CHAR字符 '{char}' (无VK码)")

        logger.info("[焦点VK码] 所有字符发送完成")
        return True

    except Exception as e:
        logger.debug(f"[焦点VK码] 失败: {e}")
        return False


def _send_text_via_sendinput_to_focused(hwnd: int, text: str, base_delay: float) -> bool:
    """
    方法4：SendInput方法（全局输入，但输入框有焦点）
    """
    try:
        import ctypes
        from ctypes import wintypes, Structure
        import time
        import random

        logger.debug("[焦点SendInput] 开始尝试SendInput方法")

        # 定义INPUT结构
        class KEYBDINPUT(Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
            ]

        class INPUT(Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("_input",)
            _fields_ = [
                ("type", wintypes.DWORD),
                ("_input", _INPUT)
            ]

        # 常量
        INPUT_KEYBOARD = 1
        KEYEVENTF_UNICODE = 0x0004

        for char in text:
            # 计算延迟
            current_delay = base_delay
            if base_delay >= RANDOM_DELAY_THRESHOLD:
                min_delay = base_delay * (1 - RANDOM_DELAY_FACTOR)
                max_delay = base_delay * (1 + RANDOM_DELAY_FACTOR)
                current_delay = random.uniform(min_delay, max_delay)

            if current_delay > 0:
                time.sleep(current_delay)

            # 创建INPUT结构
            inputs = (INPUT * 1)()
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ki.wVk = 0
            inputs[0].ki.wScan = ord(char)
            inputs[0].ki.dwFlags = KEYEVENTF_UNICODE
            inputs[0].ki.time = 0
            inputs[0].ki.dwExtraInfo = None

            # 发送输入
            result = ctypes.windll.user32.SendInput(1, inputs, ctypes.sizeof(INPUT))

            if result:
                logger.debug(f"[焦点SendInput] 成功发送字符 '{char}'")
            else:
                logger.debug(f"[焦点SendInput] 发送字符 '{char}' 失败")
                return False

        logger.info("[焦点SendInput] 所有字符发送完成")
        return True

    except Exception as e:
        logger.debug(f"[焦点SendInput] 失败: {e}")
        return False
    """
    尝试SetWindowText和EM_REPLACESEL方法
    基于搜索结果的成功案例
    """
    try:
        import win32gui
        import win32con
        import win32api
        import time

        logger.info(f"[SetWindowText/EM_REPLACESEL] 开始发送文本: '{text}' (长度: {len(text)})")

        # 重要发现：SetWindowText方法有效但修改了窗口标题
        # 现在专注于寻找游戏内的实际输入控件

        # 方法1：优先尝试对子控件使用这些方法（避免修改窗口标题）
        success = _try_setwindowtext_on_children(hwnd, text)
        if success:
            return True

        # 方法2：尝试EM_REPLACESEL消息（针对编辑框）
        success = _try_em_replacesel_method(hwnd, text)
        if success:
            return True

        # 方法3：尝试WM_SETTEXT消息
        success = _try_wm_settext_method(hwnd, text)
        if success:
            return True

        # 方法4：深度搜索所有子控件
        success = _try_deep_search_input_controls(hwnd, text)
        if success:
            return True

        logger.warning("[SetWindowText/EM_REPLACESEL] 所有方法都失败")
        return False

    except Exception as e:
        logger.error(f"[SetWindowText/EM_REPLACESEL] 发送失败: {e}")
        return False


def _try_setwindowtext_method(hwnd: int, text: str) -> bool:
    """
    方法1：使用SetWindowText直接设置窗口文本
    """
    try:
        import win32gui

        logger.debug("[SetWindowText] 开始尝试")

        # 获取当前窗口文本
        try:
            current_text = win32gui.GetWindowText(hwnd)
            logger.debug(f"[SetWindowText] 当前窗口文本: '{current_text}'")
        except:
            current_text = ""

        # 使用SetWindowText设置新文本
        result = win32gui.SetWindowText(hwnd, text)

        if result:
            logger.info(f"[SetWindowText] 成功设置窗口文本: '{text}'")

            # 验证设置是否成功
            try:
                new_text = win32gui.GetWindowText(hwnd)
                if new_text == text:
                    logger.info("[SetWindowText] 文本设置验证成功")
                    return True
                else:
                    logger.debug(f"[SetWindowText] 文本设置验证失败: 期望'{text}', 实际'{new_text}'")
            except:
                pass

            return True
        else:
            logger.debug("[SetWindowText] SetWindowText调用失败")
            return False

    except Exception as e:
        logger.debug(f"[SetWindowText] 失败: {e}")
        return False


def _try_em_replacesel_method(hwnd: int, text: str) -> bool:
    """
    方法2：使用EM_REPLACESEL消息（针对编辑框）
    """
    try:
        import win32gui
        import win32con
        import ctypes
        from ctypes import wintypes

        logger.debug("[EM_REPLACESEL] 开始尝试")

        # EM_REPLACESEL消息常量
        EM_REPLACESEL = 0x00C2

        # 创建文本缓冲区
        text_buffer = ctypes.create_string_buffer(text.encode('utf-8'))

        # 发送EM_REPLACESEL消息
        result = win32gui.SendMessage(hwnd, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))  # wParam=1表示可撤销

        if result == 0:  # EM_REPLACESEL成功时返回0
            logger.info(f"[EM_REPLACESEL] 成功替换选中文本: '{text}'")
            return True
        else:
            logger.debug(f"[EM_REPLACESEL] EM_REPLACESEL调用失败，返回值: {result}")

            # 尝试Unicode版本
            try:
                text_buffer_unicode = ctypes.create_unicode_buffer(text)
                result = win32gui.SendMessage(hwnd, EM_REPLACESEL, 1, ctypes.addressof(text_buffer_unicode))

                if result == 0:
                    logger.info(f"[EM_REPLACESEL] Unicode版本成功: '{text}'")
                    return True
            except Exception as unicode_error:
                logger.debug(f"[EM_REPLACESEL] Unicode版本失败: {unicode_error}")

            return False

    except Exception as e:
        logger.debug(f"[EM_REPLACESEL] 失败: {e}")
        return False


def _try_setwindowtext_on_children(hwnd: int, text: str) -> bool:
    """
    方法3：对子控件使用SetWindowText
    """
    try:
        import win32gui

        logger.debug("[子控件SetWindowText] 开始尝试")

        # 枚举子窗口
        child_windows = []

        def enum_child_proc(hwnd_child, lparam):
            try:
                class_name = win32gui.GetClassName(hwnd_child)
                # 寻找可能的输入控件
                input_classes = ['Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W', 'Static']
                if class_name in input_classes:
                    child_windows.append((hwnd_child, class_name))
            except:
                pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, enum_child_proc, 0)
        except:
            pass

        logger.debug(f"[子控件SetWindowText] 找到 {len(child_windows)} 个可能的控件")

        # 尝试对每个子控件使用SetWindowText
        for child_hwnd, class_name in child_windows:
            try:
                logger.debug(f"[子控件SetWindowText] 尝试设置子控件 {child_hwnd} ({class_name}) 的文本")

                result = win32gui.SetWindowText(child_hwnd, text)

                if result:
                    logger.info(f"[子控件SetWindowText] 成功设置子控件 {child_hwnd} ({class_name}) 的文本")
                    return True

            except Exception as child_error:
                logger.debug(f"[子控件SetWindowText] 子控件 {child_hwnd} 设置失败: {child_error}")
                continue

        logger.debug("[子控件SetWindowText] 没有找到有效的子控件")
        return False

    except Exception as e:
        logger.debug(f"[子控件SetWindowText] 失败: {e}")
        return False


def _try_wm_settext_method(hwnd: int, text: str) -> bool:
    """
    方法4：使用WM_SETTEXT消息
    """
    try:
        import win32gui
        import win32con
        import ctypes

        logger.debug("[WM_SETTEXT] 开始尝试")

        # 创建文本缓冲区
        text_buffer = ctypes.create_unicode_buffer(text)

        # 发送WM_SETTEXT消息
        result = win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, 0, ctypes.addressof(text_buffer))

        if result:
            logger.info(f"[WM_SETTEXT] 成功发送WM_SETTEXT消息: '{text}'")
            return True
        else:
            logger.debug("[WM_SETTEXT] WM_SETTEXT消息发送失败")
            return False

    except Exception as e:
        logger.debug(f"[WM_SETTEXT] 失败: {e}")
        return False


def _try_deep_search_input_controls(hwnd: int, text: str) -> bool:
    """
    方法5：深度搜索所有可能的输入控件
    """
    try:
        import win32gui
        import win32con
        import ctypes

        logger.debug("[深度搜索] 开始深度搜索输入控件")

        # 收集所有可能的控件
        all_controls = []

        def enum_all_windows_proc(hwnd_child, lparam):
            try:
                class_name = win32gui.GetClassName(hwnd_child)
                window_text = win32gui.GetWindowText(hwnd_child)

                # 扩展搜索范围，包括更多可能的控件类型
                possible_classes = [
                    'Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W',
                    'Static', 'Button', 'ComboBox', 'ListBox', 'SysListView32',
                    'SysTreeView32', 'msctls_updown32', 'msctls_trackbar32',
                    # 游戏可能使用的自定义控件
                    'DirectUIHWND', 'Internet Explorer_Server', 'Shell DocObject View',
                    # 可能的游戏引擎控件
                    'UnityWndClass', 'UnrealWindow', 'CryENGINE', 'GameOverlayUI'
                ]

                # 如果类名匹配或者窗口有文本内容，都加入候选列表
                if class_name in possible_classes or window_text:
                    all_controls.append((hwnd_child, class_name, window_text))

            except:
                pass
            return True

        # 枚举所有子窗口（包括子窗口的子窗口）
        try:
            win32gui.EnumChildWindows(hwnd, enum_all_windows_proc, 0)
        except:
            pass

        logger.debug(f"[深度搜索] 找到 {len(all_controls)} 个可能的控件")

        # 按优先级排序：Edit类控件优先
        def control_priority(control):
            hwnd_child, class_name, window_text = control
            if 'Edit' in class_name or 'RichEdit' in class_name:
                return 0  # 最高优先级
            elif class_name in ['Static', 'Button']:
                return 1  # 中等优先级
            else:
                return 2  # 低优先级

        all_controls.sort(key=control_priority)

        # 尝试每个控件
        for hwnd_child, class_name, window_text in all_controls:
            try:
                logger.debug(f"[深度搜索] 尝试控件 {hwnd_child} ({class_name}) 文本:'{window_text}'")

                # 方法1：SetWindowText
                try:
                    result = win32gui.SetWindowText(hwnd_child, text)
                    if result:
                        # 验证是否真的改变了
                        new_text = win32gui.GetWindowText(hwnd_child)
                        if new_text == text and new_text != window_text:
                            logger.info(f"[深度搜索] SetWindowText成功: 控件{hwnd_child} ({class_name})")
                            return True
                except:
                    pass

                # 方法2：EM_REPLACESEL
                try:
                    EM_REPLACESEL = 0x00C2
                    text_buffer = ctypes.create_unicode_buffer(text)
                    result = win32gui.SendMessage(hwnd_child, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))
                    if result == 0:
                        logger.info(f"[深度搜索] EM_REPLACESEL成功: 控件{hwnd_child} ({class_name})")
                        return True
                except:
                    pass

                # 方法3：WM_SETTEXT
                try:
                    text_buffer = ctypes.create_unicode_buffer(text)
                    result = win32gui.SendMessage(hwnd_child, win32con.WM_SETTEXT, 0, ctypes.addressof(text_buffer))
                    if result:
                        logger.info(f"[深度搜索] WM_SETTEXT成功: 控件{hwnd_child} ({class_name})")
                        return True
                except:
                    pass

                # 方法4：尝试一些特殊的编辑框消息
                try:
                    # EM_SETSEL + EM_REPLACESEL 组合
                    EM_SETSEL = 0x00B1
                    win32gui.SendMessage(hwnd_child, EM_SETSEL, 0, -1)  # 选择所有文本

                    text_buffer = ctypes.create_unicode_buffer(text)
                    result = win32gui.SendMessage(hwnd_child, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))
                    if result == 0:
                        logger.info(f"[深度搜索] EM_SETSEL+EM_REPLACESEL成功: 控件{hwnd_child} ({class_name})")
                        return True
                except:
                    pass

            except Exception as control_error:
                logger.debug(f"[深度搜索] 控件 {hwnd_child} 处理失败: {control_error}")
                continue

        logger.debug("[深度搜索] 所有控件都尝试失败")
        return False

    except Exception as e:
        logger.debug(f"[深度搜索] 失败: {e}")
        return False


















def _send_text_to_emulator_window(hwnd: int, text: str, base_delay: float = 0.0) -> bool:
    """
    模拟器传统文本输入方法
    模拟器不区分前后台，使用和前台一致的方法
    """
    try:
        import win32api
        import win32con
        import win32gui
        import time
        import random

        logger.info(f"[模拟器传统] 开始模拟器传统文本输入: '{text}' (长度: {len(text)})")

        # 模拟器使用和前台一致的方法：逐字符发送WM_CHAR消息
        for char in text:
            # 计算延迟
            current_delay = base_delay
            if base_delay >= RANDOM_DELAY_THRESHOLD:
                min_delay = base_delay * (1 - RANDOM_DELAY_FACTOR)
                max_delay = base_delay * (1 + RANDOM_DELAY_FACTOR)
                current_delay = random.uniform(min_delay, max_delay)

            if current_delay > 0:
                time.sleep(current_delay)

            char_code = ord(char)

            # 使用PostMessage发送WM_CHAR消息（和前台模式一致）
            win32gui.PostMessage(hwnd, win32con.WM_CHAR, char_code, 0)
            logger.debug(f"[模拟器传统] 发送字符 '{char}' (code: {char_code})")

        logger.info("[模拟器传统] 模拟器传统文本输入完成")
        return True

    except Exception as e:
        logger.error(f"[模拟器传统] 模拟器传统文本输入失败: {e}")
        return False