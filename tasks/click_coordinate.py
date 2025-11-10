# -*- coding: utf-8 -*-

"""
点击绑定窗口的指定坐标任务模块
支持前台和后台模式，可以精确点击指定的坐标位置
"""

import logging
import time
import random
import ctypes
from typing import Dict, Any, Optional, Tuple

# 安全导入 wintypes
try:
    from ctypes import wintypes
    WINTYPES_AVAILABLE = True
except ImportError:
    WINTYPES_AVAILABLE = False
    # 创建一个简单的 POINT 类作为备用
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                   ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    # 创建一个模拟的 wintypes 模块
    class MockWinTypes:
        POINT = POINT
        RECT = RECT

    wintypes = MockWinTypes()

# 导入通用坐标系统
from utils.universal_coordinate_system import (
    get_universal_coordinate_system, CoordinateInfo, CoordinateType, ClickMode
)

# Windows API 相关导入
try:
    import win32api
    import win32gui
    import win32con
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# 前台输入驱动管理器导入（自动处理 Interception/Win32 回退）
try:
    from utils.foreground_input_manager import get_foreground_input_manager
    foreground_input = get_foreground_input_manager()
    FOREGROUND_INPUT_AVAILABLE = True
except ImportError:
    FOREGROUND_INPUT_AVAILABLE = False

# Interception Driver 导入（保留兼容性）
try:
    from utils.interception_driver import get_driver
    driver = get_driver()
    INTERCEPTION_AVAILABLE = True
except ImportError:
    INTERCEPTION_AVAILABLE = False



logger = logging.getLogger(__name__)

# 任务类型标识
TASK_TYPE = "点击指定坐标"
TASK_NAME = "点击指定坐标"

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
                target_hwnd: Optional[int], window_region: Optional[Tuple[int, int, int, int]],
                card_id: Optional[int] = None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """
    执行点击指定坐标任务

    Args:
        params: 任务参数
        counters: 计数器
        execution_mode: 执行模式 ('foreground' 或 'background'，可能包含具体模式如 'foreground_driver')
        target_hwnd: 目标窗口句柄
        window_region: 窗口区域
        card_id: 卡片ID
        **kwargs: 其他参数

    Returns:
        Tuple[bool, str, Optional[int]]: (成功状态, 动作, 下一个卡片ID)
    """

    # 根据执行模式设置前台输入管理器的强制模式
    if FOREGROUND_INPUT_AVAILABLE and execution_mode.startswith('foreground'):
        if execution_mode == 'foreground_driver':
            # 前台模式一：强制使用Interception驱动（不降级）
            foreground_input.set_forced_mode('interception')
            logger.info("[执行模式] 前台模式一 - 强制Interception驱动")
        elif execution_mode == 'foreground_pyautogui':
            # 前台模式二：强制使用 PyAutoGUI
            foreground_input.set_forced_mode('pyautogui')
            foreground_input.set_target_window(target_hwnd)  # PyAutoGUI需要激活窗口
            logger.info("[执行模式] 前台模式二 - 强制PyAutoGUI")
        else:
            # 默认：如果只是'foreground'，使用Interception
            foreground_input.set_forced_mode('interception')
            logger.info("[执行模式] 前台模式（默认） - 强制Interception驱动")

    # 根据执行模式设置模拟器类型（用于模拟器专用模式）
    _forced_emulator_type = None
    if execution_mode.startswith('emulator_'):
        if execution_mode == 'emulator_mumu':
            _forced_emulator_type = 'mumu'
            logger.info("[执行模式] 模拟器模式 - 强制MuMu模拟器")
        elif execution_mode == 'emulator_ldplayer':
            _forced_emulator_type = 'ldplayer'
            logger.info("[执行模式] 模拟器模式 - 强制雷电模拟器")
        else:
            logger.info("[执行模式] 模拟器模式 - 自动检测")

    # 获取参数
    coordinate_x = params.get('coordinate_x', 0)
    coordinate_y = params.get('coordinate_y', 0)
    coordinate_mode = params.get('coordinate_mode', '客户区坐标')
    button = params.get('button', '左键')
    clicks = params.get('clicks', 1)
    interval = params.get('interval', 0.1)
    disable_random_offset = params.get('disable_random_offset', False)
    random_offset = 0 if disable_random_offset else params.get('random_offset', 5)  # 根据禁止随机偏移设置
    
    # 获取执行后操作参数
    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id = params.get('failure_jump_target_id')
    
    # 参数验证
    try:
        coordinate_x = int(coordinate_x)
        coordinate_y = int(coordinate_y)
        clicks = int(clicks)
        interval = float(interval)
        random_offset = int(random_offset)
    except (ValueError, TypeError) as e:
        logger.error(f"参数类型错误: {e}")
        return _handle_failure(on_failure_action, failure_jump_id, card_id)
    
    if coordinate_x < 0 or coordinate_y < 0:
        logger.error(f"坐标值不能为负数: ({coordinate_x}, {coordinate_y})")
        return _handle_failure(on_failure_action, failure_jump_id, card_id)
    
    # 执行模式中文映射
    mode_names = {'foreground': '前台', 'background': '后台'}
    mode_name = mode_names.get(execution_mode, execution_mode)
    
    logger.info(f"准备执行点击坐标: ({coordinate_x}, {coordinate_y}), 坐标模式='{coordinate_mode}', "
                f"按钮='{button}', 次数={clicks}, 模式='{mode_name}', 随机偏移={'禁用' if disable_random_offset else '启用'}")
    
    try:
        # 使用通用坐标系统处理坐标
        coord_system = get_universal_coordinate_system()

        # 根据坐标模式创建正确的坐标信息
        if coordinate_mode == '客户区坐标':
            # 客户区坐标是基于窗口的物理坐标，不需要转换
            coord_info = CoordinateInfo(
                x=coordinate_x, y=coordinate_y,
                coord_type=CoordinateType.PHYSICAL,  # 客户区坐标是物理坐标
                source_window=target_hwnd
            )
            logger.info(f"创建客户区坐标: ({coordinate_x}, {coordinate_y}) - 物理坐标")
        else:
            # 屏幕坐标需要转换为客户区坐标
            if target_hwnd and PYWIN32_AVAILABLE:
                try:
                    if not PYWIN32_AVAILABLE:
                        logger.error("pywin32不可用，无法进行坐标转换")
                        return _handle_failure(on_failure_action, failure_jump_id, card_id)

                    point = wintypes.POINT(coordinate_x, coordinate_y)
                    if ctypes.windll.user32.ScreenToClient(target_hwnd, ctypes.byref(point)):
                        client_x, client_y = point.x, point.y
                        coord_info = CoordinateInfo(
                            x=client_x, y=client_y,
                            coord_type=CoordinateType.PHYSICAL,
                            source_window=target_hwnd
                        )
                        logger.info(f"屏幕坐标转换: ({coordinate_x}, {coordinate_y}) -> 客户区({client_x}, {client_y})")
                    else:
                        logger.error("屏幕坐标转换为客户区坐标失败")
                        return _handle_failure(on_failure_action, failure_jump_id, card_id)
                except Exception as e:
                    logger.error(f"坐标转换失败: {e}")
                    return _handle_failure(on_failure_action, failure_jump_id, card_id)
            else:
                # 如果没有窗口句柄，直接使用屏幕坐标
                coord_info = CoordinateInfo(
                    x=coordinate_x, y=coordinate_y,
                    coord_type=CoordinateType.PHYSICAL
                )
                logger.warning("没有窗口句柄，直接使用屏幕坐标")

        # 应用随机偏移
        if not disable_random_offset and random_offset > 0:
            coord_info = coord_system.apply_random_offset(coord_info, random_offset)
            logger.info(f"应用随机偏移: 原始({coordinate_x}, {coordinate_y}) -> 偏移后({coord_info.x}, {coord_info.y})")

        # 确定点击模式 - 使用标准化的执行模式判断
        normalized_mode = execution_mode
        if execution_mode.startswith('foreground'):
            normalized_mode = 'foreground'
        elif execution_mode.startswith('background'):
            normalized_mode = 'background'
        elif execution_mode.startswith('emulator_'):
            normalized_mode = 'emulator'

        click_mode = ClickMode.BACKGROUND if normalized_mode == 'background' else ClickMode.FOREGROUND

        # 关键修复：前台模式下参考图片点击的处理方式
        if normalized_mode == 'foreground':
            # 前台模式：直接使用客户区坐标，避免通用坐标系统的双重转换
            logger.info(f"[前台模式] 直接使用客户区坐标，避免双重转换")
            client_x, client_y = coord_info.x, coord_info.y

            # 手动转换为屏幕坐标（参考图片点击的实现）
            if target_hwnd and PYWIN32_AVAILABLE:
                try:
                    # 模块已在文件顶部导入

                    if win32gui.IsWindow(target_hwnd):
                        # 获取窗口信息用于调试
                        try:
                            if PYWIN32_AVAILABLE:
                                window_rect = wintypes.RECT()
                                client_rect = wintypes.RECT()
                                ctypes.windll.user32.GetWindowRect(target_hwnd, ctypes.byref(window_rect))
                                ctypes.windll.user32.GetClientRect(target_hwnd, ctypes.byref(client_rect))

                            logger.debug(f"[前台模式] 窗口矩形: ({window_rect.left}, {window_rect.top}, {window_rect.right}, {window_rect.bottom})")
                            logger.debug(f"[前台模式] 客户区矩形: ({client_rect.left}, {client_rect.top}, {client_rect.right}, {client_rect.bottom})")

                            # 检查坐标是否在客户区范围内
                            if client_x < 0 or client_y < 0 or client_x > client_rect.right or client_y > client_rect.bottom:
                                logger.warning(f"[前台模式] 坐标超出客户区范围: ({client_x}, {client_y}), 客户区大小: {client_rect.right}x{client_rect.bottom}")
                        except Exception as debug_error:
                            logger.debug(f"[前台模式] 获取窗口信息失败: {debug_error}")

                        if not PYWIN32_AVAILABLE:
                            logger.error("pywin32不可用，无法进行坐标转换")
                            final_x, final_y = client_x, client_y
                        else:
                            point = wintypes.POINT(int(client_x), int(client_y))
                            result = ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point))

                        if result:
                            final_x, final_y = point.x, point.y
                            logger.info(f"[前台模式] 坐标转换成功: 客户区({client_x}, {client_y}) -> 屏幕({final_x}, {final_y})")

                            # 验证屏幕坐标是否合理
                            screen_width, screen_height = driver.get_screen_size()
                            if final_x < 0 or final_y < 0 or final_x > screen_width or final_y > screen_height:
                                logger.error(f"[前台模式] 转换后的屏幕坐标超出屏幕范围: ({final_x}, {final_y}), 屏幕大小: {screen_width}x{screen_height}")
                                logger.error("[前台模式] 使用原始客户区坐标作为屏幕坐标")
                                final_x, final_y = client_x, client_y
                        else:
                            logger.error("[前台模式] ClientToScreen转换失败，使用原始坐标")
                            final_x, final_y = client_x, client_y
                    else:
                        logger.warning("[前台模式] 窗口句柄无效，直接使用客户区坐标")
                        final_x, final_y = client_x, client_y

                except Exception as e:
                    logger.error(f"[前台模式] 坐标转换异常: {e}")
                    final_x, final_y = client_x, client_y
            else:
                logger.warning("[前台模式] 无有效窗口句柄，直接使用客户区坐标")
                final_x, final_y = client_x, client_y
        elif normalized_mode == 'emulator':
            # 模拟器模式：直接使用客户区坐标，不进行转换
            # 关键修复：模拟器专用方法需要的是客户区坐标，不是屏幕坐标
            final_x, final_y = coord_info.x, coord_info.y
            logger.info(f"[模拟器模式] 直接使用客户区坐标: ({final_x}, {final_y})")
        else:
            # 后台模式：使用通用坐标系统处理
            final_x, final_y = coord_system.process_click_coordinate(coord_info, target_hwnd, click_mode)

        logger.info(f"=== 坐标处理完成 ===")
        logger.info(f"最终点击坐标: ({final_x}, {final_y}), 模式: {execution_mode}")

        # 执行点击 - 优先使用新的输入模拟模块
        success = _click_with_new_simulator(target_hwnd, final_x, final_y, button, clicks, interval, execution_mode, _forced_emulator_type)

        # 如果新模拟器不可用，回退到传统方法
        if success is None:
            # 使用标准化的模式判断
            if normalized_mode == 'background' or normalized_mode == 'emulator':
                success = _click_background_universal(target_hwnd, final_x, final_y, button, clicks, interval)
            else:
                success = _click_foreground_universal(target_hwnd, final_x, final_y, button, clicks, interval)

        if success:
            logger.info(f"坐标点击成功: ({final_x}, {final_y})")
            # 使用统一的成功处理（包含延迟）
            from .task_utils import handle_success_action
            return handle_success_action(params, card_id, kwargs.get('stop_checker'))
        else:
            logger.error(f"坐标点击失败: ({final_x}, {final_y})")
            # 使用统一的失败处理
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)
            
    except Exception as e:
        logger.error(f"执行点击坐标时发生错误: {e}", exc_info=True)
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)

def _apply_random_offset(x: int, y: int, offset: int) -> Tuple[int, int]:
    """应用随机偏移"""
    if offset <= 0:
        return x, y
    
    offset_x = random.randint(-offset, offset)
    offset_y = random.randint(-offset, offset)
    
    final_x = max(0, x + offset_x)
    final_y = max(0, y + offset_y)
    
    if offset_x != 0 or offset_y != 0:
        logger.debug(f"应用随机偏移: ({x}, {y}) + ({offset_x}, {offset_y}) = ({final_x}, {final_y})")
    
    return final_x, final_y

def _click_background(target_hwnd: Optional[int], x: int, y: int, coordinate_mode: str, 
                     button: str, clicks: int, interval: float) -> bool:
    """后台模式点击"""
    if not PYWIN32_AVAILABLE:
        logger.error("后台点击需要 pywin32 库")
        return False
    
    if not target_hwnd:
        logger.error("后台模式需要有效的窗口句柄")
        return False
    
    if not win32gui.IsWindow(target_hwnd):
        logger.error(f"窗口句柄 {target_hwnd} 无效")
        return False
    
    try:
        # 坐标转换 - 确保使用物理坐标
        if coordinate_mode == '屏幕坐标':
            # 屏幕坐标转换为客户区坐标
            if not PYWIN32_AVAILABLE:
                logger.error("pywin32不可用，无法进行坐标转换")
                return False
            point = wintypes.POINT(x, y)
            if not ctypes.windll.user32.ScreenToClient(target_hwnd, ctypes.byref(point)):
                logger.error("屏幕坐标转换为客户区坐标失败")
                return False
            client_x, client_y = point.x, point.y
        else:
            # 直接使用客户区坐标（物理坐标）
            client_x, client_y = x, y

        logger.info(f"[后台点击] 客户区坐标: ({client_x}, {client_y}), 按钮={button}, 次数={clicks}")

        # 执行点击 - 使用简化的后台坐标处理
        try:
            from main import mouse_move_fixer
            # 验证并修正客户区坐标
            corrected_x, corrected_y = mouse_move_fixer.validate_client_coordinates(target_hwnd, client_x, client_y)
            logger.info(f"[后台点击] 客户区坐标: ({client_x}, {client_y}) -> ({corrected_x}, {corrected_y})")

            return _send_click_messages(target_hwnd, corrected_x, corrected_y, button, clicks, interval)
        except ImportError:
            logger.debug("后台坐标修复器不可用，使用原始坐标")
            return _send_click_messages(target_hwnd, client_x, client_y, button, clicks, interval)

    except Exception as e:
        logger.error(f"后台点击时发生错误: {e}", exc_info=True)
        return False

def _get_window_to_activate(hwnd: int) -> int:
    """获取需要激活的窗口句柄（如果是渲染窗口则返回主窗口）"""
    try:
        # 检测是否是MuMu渲染窗口
        from utils.emulator_detector import detect_emulator_type
        is_emulator, emulator_type, description = detect_emulator_type(hwnd)

        if is_emulator and emulator_type == "mumu":
            # 如果是MuMu渲染窗口，查找对应的主窗口
            from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
            emulator_window = EmulatorWindowInputSimulator(hwnd, "mumu", "background")
            main_hwnd = emulator_window._get_mumu_parent_window()
            if main_hwnd:
                logger.debug(f"从渲染窗口 {hwnd} 找到主窗口 {main_hwnd} 用于激活")
                return main_hwnd

        # 如果不是渲染窗口或找不到主窗口，返回原窗口
        return hwnd

    except Exception as e:
        logger.debug(f"获取激活窗口失败: {e}")
        return hwnd

def _click_foreground(target_hwnd: Optional[int], x: int, y: int, coordinate_mode: str,
                     button: str, clicks: int, interval: float) -> bool:
    """前台模式点击 - 仅使用Interception驱动"""
    if not INTERCEPTION_AVAILABLE:
        logger.error("前台点击需要 Interception 驱动")
        return False
    
    try:
        # 坐标转换
        if coordinate_mode == '客户区坐标':
            # 客户区坐标转换为屏幕坐标
            if target_hwnd and PYWIN32_AVAILABLE and win32gui.IsWindow(target_hwnd):
                point = wintypes.POINT(x, y)
                if ctypes.windll.user32.ClientToScreen(target_hwnd, ctypes.byref(point)):
                    screen_x, screen_y = point.x, point.y
                    logger.debug(f"客户区坐标转换: ({x}, {y}) -> 屏幕坐标: ({screen_x}, {screen_y})")
                else:
                    logger.error("客户区坐标转换为屏幕坐标失败")
                    return False
            else:
                logger.error(f"前台点击需要有效的窗口句柄进行坐标转换: target_hwnd={target_hwnd}, pywin32={PYWIN32_AVAILABLE}")
                return False
        else:
            # 直接使用屏幕坐标
            screen_x, screen_y = x, y
            logger.debug(f"使用屏幕坐标: ({screen_x}, {screen_y})")
        
        # 工具 修复：简化窗口激活逻辑
        import os
        is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'

        # 窗口激活逻辑：
        # 1. 前台模式 + 非多窗口模式 = 激活窗口
        # 2. 后台模式 = 不激活窗口
        # 3. 多窗口模式 = 不激活窗口（避免冲突）

        should_activate = (not is_multi_window_mode)  # 前台模式默认激活窗口，除非是多窗口模式

        if target_hwnd and PYWIN32_AVAILABLE and should_activate:
            try:
                if win32gui.IsWindow(target_hwnd):
                    # 获取需要激活的窗口句柄（如果是渲染窗口则激活主窗口）
                    window_to_activate = _get_window_to_activate(target_hwnd)

                    logger.info(f"靶心 前台模式：激活目标窗口 {window_to_activate}")
                    if window_to_activate != target_hwnd:
                        logger.info(f"检测到渲染窗口，激活主窗口: {target_hwnd} -> {window_to_activate}")

                    win32gui.SetForegroundWindow(window_to_activate)
                    time.sleep(0.1)
                    logger.info(f"成功 窗口激活成功: {window_to_activate}")
                else:
                    logger.warning(f"警告 窗口句柄无效: {target_hwnd}")
            except Exception as e:
                logger.error(f"错误 激活窗口失败: {e}")
        else:
            reason = []
            if not target_hwnd:
                reason.append("无窗口句柄")
            if not PYWIN32_AVAILABLE:
                reason.append("pywin32不可用")
            if is_multi_window_mode:
                reason.append("多窗口模式")

            logger.debug(f"靶心 跳过窗口激活: {', '.join(reason)} (HWND: {target_hwnd})")
        
        logger.info(f"[前台点击] 屏幕坐标: ({screen_x}, {screen_y}), 按钮={button}, 次数={clicks}")

        # 工具 关键修复：确保点击前目标窗口在前台
        if target_hwnd and PYWIN32_AVAILABLE:
            try:
                current_fg = win32gui.GetForegroundWindow()
                if current_fg != target_hwnd:
                    logger.warning(f"警告 目标窗口不在前台! 当前前台: {current_fg}, 目标: {target_hwnd}")
                    logger.info("刷新 重新激活目标窗口...")
                    win32gui.SetForegroundWindow(target_hwnd)
                    time.sleep(0.1)  # 等待窗口激活

                    # 验证激活结果
                    new_fg = win32gui.GetForegroundWindow()
                    if new_fg == target_hwnd:
                        logger.info("成功 目标窗口重新激活成功")
                    else:
                        logger.error(f"错误 目标窗口激活失败! 当前前台: {new_fg}, 目标: {target_hwnd}")
                        return False
                else:
                    logger.debug("成功 目标窗口已在前台")
            except Exception as e:
                logger.error(f"错误 验证/激活目标窗口时出错: {e}")
                return False

        # 执行点击
        button_map = {'左键': 'left', '右键': 'right', '中键': 'middle'}
        driver_button = button_map.get(button, 'left')

        driver.click_mouse(x=screen_x, y=screen_y, clicks=clicks, interval=interval, button=driver_button)
        return True
        
    except Exception as e:
        logger.error(f"前台点击时发生错误: {e}", exc_info=True)
        return False

def _send_click_messages(hwnd: int, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
    """发送点击消息到窗口"""
    try:
        # 按钮消息映射
        button_messages = {
            '左键': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
            '右键': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
            '中键': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
        }
        
        if button not in button_messages:
            logger.error(f"不支持的按钮类型: {button}")
            return False
        
        down_msg, up_msg = button_messages[button]
        lParam = win32api.MAKELONG(x, y)
        
        for i in range(clicks):
            # 发送按下消息
            win32gui.PostMessage(hwnd, down_msg, 0, lParam)
            time.sleep(0.01)  # 短暂延迟
            
            # 发送释放消息
            win32gui.PostMessage(hwnd, up_msg, 0, lParam)
            
            # 多次点击间的间隔
            if i < clicks - 1 and interval > 0:
                time.sleep(interval)
        
        return True
        
    except Exception as e:
        logger.error(f"发送点击消息时发生错误: {e}", exc_info=True)
        return False

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

# 旧的DPI处理函数已移除，现在使用统一DPI处理器

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """获取参数定义"""
    from .task_utils import get_standard_next_step_delay_params, merge_params_definitions

    # 原有的点击坐标参数
    click_params = {
        "---coordinate_settings---": {"type": "separator", "label": "坐标设置"},
        "coordinate_x": {
            "label": "X坐标",
            "type": "int",
            "default": 0,
            "min": 0,
            "tooltip": "点击位置的X坐标"
        },
        "coordinate_y": {
            "label": "Y坐标",
            "type": "int",
            "default": 0,
            "min": 0,
            "tooltip": "点击位置的Y坐标"
        },
        "coordinate_selector_tool": {
            "label": "坐标获取工具",
            "type": "button",
            "button_text": "点击获取坐标",
            "tooltip": "点击后可以在目标窗口中选择坐标位置",
            "widget_hint": "coordinate_selector"
        },
        "coordinate_mode": {
            "label": "坐标模式",
            "type": "select",
            "options": ["客户区坐标", "屏幕坐标"],
            "default": "客户区坐标",
            "tooltip": "客户区坐标相对于窗口内容区域，屏幕坐标相对于整个屏幕"
        },
        "disable_random_offset": {
            "label": "禁止随机偏移",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后使用绝对坐标，不使用±5随机偏移"
        },

        "---click_settings---": {"type": "separator", "label": "点击设置"},
        "button": {
            "label": "鼠标按钮",
            "type": "select",
            "options": ["左键", "右键", "中键"],
            "default": "左键",
            "tooltip": "选择要点击的鼠标按钮"
        },
        "clicks": {
            "label": "点击次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "max": 10,
            "tooltip": "连续点击的次数"
        },
        "interval": {
            "label": "点击间隔(秒)",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 5.0,
            "decimals": 2,
            "tooltip": "多次点击之间的时间间隔"
        },

        "---post_execute---": {"type": "separator", "label": "执行后操作"},
        "on_success": {
            "type": "select",
            "label": "执行成功时",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步"
        },
        "success_jump_target_id": {
            "type": "int",
            "label": "成功跳转目标 ID",
            "required": False,
            "widget_hint": "card_selector",
            "condition": {"param": "on_success", "value": "跳转到步骤"}
        },
        "on_failure": {
            "type": "select", 
            "label": "执行失败时",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步"
        },
        "failure_jump_target_id": {
            "type": "int",
            "label": "失败跳转目标 ID",
            "required": False,
            "widget_hint": "card_selector",
            "condition": {"param": "on_failure", "value": "跳转到步骤"}
        }
    }

    # 合并延迟参数
    return merge_params_definitions(click_params, get_standard_next_step_delay_params())

def _click_with_new_simulator(hwnd: int, x: int, y: int, button: str = 'left',
                             clicks: int = 1, interval: float = 0.1, execution_mode: str = 'background',
                             forced_emulator_type: Optional[str] = None) -> Optional[bool]:
    """
    使用新的输入模拟模块执行点击

    Args:
        hwnd: 窗口句柄
        x, y: 坐标
        button: 按钮类型
        clicks: 点击次数
        interval: 间隔
        execution_mode: 执行模式
        forced_emulator_type: 强制模拟器类型 ('mumu', 'ldplayer', None)

    Returns:
        bool: 点击是否成功
        None: 新模拟器不可用，需要回退到传统方法
    """
    try:
        # 标准化执行模式
        normalized_mode = execution_mode
        if execution_mode.startswith('foreground'):
            normalized_mode = 'foreground'
        elif execution_mode.startswith('background'):
            normalized_mode = 'background'
        elif execution_mode.startswith('emulator_'):
            normalized_mode = 'emulator'

        # 前台模式使用前台输入管理器（自动处理 Interception/Win32 回退）
        if normalized_mode == 'foreground':
            logger.info("[前台模式] 使用前台输入管理器（自动选择最佳驱动）")

            if not FOREGROUND_INPUT_AVAILABLE:
                logger.error("[前台模式] 前台输入管理器不可用，回退到传统方法")
                return None

            # 转换按钮类型
            button_map = {
                '左键': 'left',
                '右键': 'right',
                '中键': 'middle'
            }
            button_type = button_map.get(button, 'left')

            logger.info(f"[前台模式] 执行点击: 坐标({x}, {y}), 按钮={button_type}, 次数={clicks}")

            # 执行点击 - 前台输入管理器会自动选择最佳驱动
            success = foreground_input.click_mouse(x, y, button_type, clicks, interval)

            if success:
                logger.info(f"[前台模式] ✓ 点击成功")
            else:
                logger.warning(f"[前台模式] ❌ 点击失败")

            return success

        # 模拟器模式或后台模式使用输入模拟器
        from utils.input_simulation import global_input_simulator_manager
        from utils.emulator_detector import detect_emulator_type

        # 检测模拟器类型 - 如果强制了模拟器类型则使用强制类型
        if forced_emulator_type:
            is_emulator = True
            emulator_type = forced_emulator_type
            description = f"强制模拟器类型: {forced_emulator_type}"
            logger.info(f"[强制模拟器] 使用强制模拟器类型: {emulator_type}")
        else:
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

        if is_emulator:
            logger.info(f"[模拟器模式] 检测到模拟器类型: {emulator_type}")

            # 获取适合的输入模拟器
            simulator = global_input_simulator_manager.get_simulator(
                hwnd, "emulator_window", execution_mode
            )

            if simulator:
                # 转换按钮类型
                button_map = {
                    '左键': 'left',
                    '右键': 'right',
                    '中键': 'middle'
                }

                button_type = button_map.get(button, 'left')

                logger.info(f"[模拟器模式] 执行{emulator_type}专用点击: 坐标({x}, {y}), 按钮={button}, 次数={clicks}, 间隔={interval}")

                # 执行点击
                success = simulator.click(x, y, button_type, clicks, interval)

                if success:
                    logger.info(f"[模拟器模式] {emulator_type}专用点击成功")
                else:
                    logger.warning(f"[模拟器模式] {emulator_type}专用点击失败")

                return success
            else:
                logger.warning("[模拟器模式] 无法获取模拟器专用输入模拟器，回退到后台模式")

        # 后台模式（或模拟器模式失败后的回退）：根据execution_mode直接使用SendMessage或PostMessage
        if normalized_mode == 'background' or (normalized_mode == 'emulator' and not is_emulator):
            if not PYWIN32_AVAILABLE:
                logger.error("[后台模式] pywin32不可用")
                return False

            # 转换按钮类型
            button_map = {
                '左键': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
                '右键': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
                '中键': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
            }

            if button not in button_map:
                logger.error(f"不支持的按钮类型: {button}")
                return False

            down_msg, up_msg = button_map[button]
            lParam = win32api.MAKELONG(int(x), int(y))

            # 根据execution_mode选择SendMessage或PostMessage
            if execution_mode == 'background_sendmessage':
                message_func = win32gui.SendMessage
                logger.info(f"[后台模式一] 使用SendMessage点击: 坐标({x}, {y}), 按钮={button}, 次数={clicks}")
            elif execution_mode == 'background_postmessage':
                message_func = win32gui.PostMessage
                logger.info(f"[后台模式二] 使用PostMessage点击: 坐标({x}, {y}), 按钮={button}, 次数={clicks}")
            else:
                # 默认使用SendMessage（兼容旧代码，包括模拟器回退情况）
                message_func = win32gui.SendMessage
                logger.info(f"[后台模式] 使用SendMessage点击（默认）: 坐标({x}, {y}), 按钮={button}, 次数={clicks}")

            # 执行点击
            try:
                for i in range(clicks):
                    message_func(hwnd, down_msg, 0, lParam)
                    time.sleep(0.01)
                    message_func(hwnd, up_msg, 0, lParam)
                    if i < clicks - 1:
                        time.sleep(interval)

                logger.info(f"[后台点击] 成功完成 {clicks} 次点击")
                return True
            except Exception as e:
                logger.error(f"[后台点击] 发送消息失败: {e}")
                return False

        # 不应该到达这里
        logger.error(f"未知的执行模式: {execution_mode}, normalized: {normalized_mode}")
        return None

    except ImportError:
        logger.debug("无法导入输入模拟模块，回退到传统方法")
        return None
    except Exception as e:
        logger.error(f"输入模拟器执行点击时发生错误: {e}")
        return False

def _click_background_universal(hwnd: int, x: int, y: int, button: str = 'left',
                               clicks: int = 1, interval: float = 0.1) -> bool:
    """通用后台点击函数（使用处理后的坐标）"""
    try:
        if not PYWIN32_AVAILABLE:
            logger.error("pywin32 不可用，无法执行后台点击")
            return False

        if not hwnd or not win32gui.IsWindow(hwnd):
            logger.error(f"无效的窗口句柄: {hwnd}")
            return False

        # 转换按钮类型
        button_map = {
            '左键': ('left', win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
            '右键': ('right', win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
            '中键': ('middle', win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
        }

        if button not in button_map:
            logger.error(f"不支持的按钮类型: {button}")
            return False

        _, down_msg, up_msg = button_map[button]

        # 构造lParam
        lParam = win32api.MAKELONG(int(x), int(y))

        logger.info(f"[后台点击] 坐标: ({x}, {y}), 按钮: {button}, 次数: {clicks}")

        # 执行点击
        for i in range(clicks):
            try:
                # 发送按下消息
                win32gui.SendMessage(hwnd, down_msg, 0, lParam)
                time.sleep(0.01)  # 短暂延迟

                # 发送释放消息
                win32gui.SendMessage(hwnd, up_msg, 0, lParam)

                if i < clicks - 1:  # 不是最后一次点击
                    time.sleep(interval)

            except Exception as e:
                logger.error(f"发送点击消息失败 (第{i+1}次): {e}")
                return False

        logger.info(f"[后台点击] 成功完成 {clicks} 次点击")
        return True

    except Exception as e:
        logger.error(f"后台点击失败: {e}")
        return False

def _click_foreground_universal(hwnd: int, x: int, y: int, button: str = 'left',
                               clicks: int = 1, interval: float = 0.1) -> bool:
    """
    通用前台点击函数 - 使用前台输入管理器（自动处理 Interception/Win32 回退）
    注意：x, y 应该是屏幕坐标（已经通过通用坐标系统转换过的）
    """
    try:
        # 检查前台输入是否可用
        if not FOREGROUND_INPUT_AVAILABLE:
            logger.error("❌ 前台输入管理器不可用")
            logger.error("请确保已安装必要的依赖：Interception驱动 或 pywin32")
            return False

        # 转换按钮类型
        button_map = {
            '左键': 'left',
            '右键': 'right',
            '中键': 'middle'
        }

        if button not in button_map:
            logger.error(f"不支持的按钮类型: {button}")
            return False

        button_type = button_map[button]

        logger.info(f"[前台点击] 接收到屏幕坐标: ({x}, {y}), 按钮: {button}, 次数: {clicks}")

        # 🔧 窗口激活逻辑优化：根据输入方式决定是否激活窗口
        import os
        is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'

        # 检查当前使用的输入方式
        driver_type = foreground_input.get_driver_type()
        needs_activation = (driver_type == 'interception')

        # 决定是否激活窗口
        should_activate = (not is_multi_window_mode) and needs_activation

        if hwnd and PYWIN32_AVAILABLE and should_activate:
            import win32gui
            if win32gui.IsWindow(hwnd):
                try:
                    logger.info("[前台点击] 激活目标窗口...")
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.1)

                    fg_hwnd = win32gui.GetForegroundWindow()
                    if fg_hwnd == hwnd:
                        logger.info("[前台点击] 窗口激活成功")
                    else:
                        logger.warning(f"[前台点击] 窗口激活可能失败，当前前台窗口: {fg_hwnd}")
                except Exception as e:
                    logger.warning(f"[前台点击] 激活窗口时出错: {e}")
            else:
                logger.warning(f"[前台点击] 窗口句柄无效: {hwnd}")
        else:
            if is_multi_window_mode:
                reason = "多窗口模式"
            elif not needs_activation:
                reason = "当前输入方式不需要激活"
            else:
                reason = "无有效窗口句柄"
            logger.info(f"[前台点击] 跳过窗口激活: {reason}")

        # 使用前台输入管理器执行点击（自动选择最佳驱动）
        try:
            # 验证坐标是否在屏幕范围内
            screen_width, screen_height = foreground_input.get_screen_size()
            if x < 0 or y < 0 or x > screen_width or y > screen_height:
                logger.error(f"[前台点击] 坐标超出屏幕范围: ({x}, {y}), 屏幕大小: {screen_width}x{screen_height}")
                return False

            # 执行点击 - 前台输入管理器会自动选择最佳驱动
            success = foreground_input.click_mouse(x, y, button_type, clicks, interval)

            if success:
                logger.info(f"[前台点击] ✓ 点击成功，坐标({x}, {y})")
            else:
                logger.error(f"[前台点击] ❌ 点击失败")

            return success

        except Exception as click_error:
            logger.error(f"[前台点击] 点击执行失败: {click_error}")
            return False

    except Exception as e:
        logger.error(f"前台点击失败: {e}")
        return False

# DPI修正函数已移除，Interception驱动自动处理DPI

if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    test_params = {
        'coordinate_x': 200,
        'coordinate_y': 300,
        'coordinate_mode': '客户区坐标',
        'button': '左键',
        'clicks': 1,
        'interval': 0.1,
        'disable_random_offset': False,
        'random_offset': 5
    }
    
    result = execute_task(test_params, {}, 'foreground', None, None)
    print(f"测试结果: {result}")
