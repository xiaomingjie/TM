"""
MuMu模拟器专用输入模拟器
基于MuMuManager命令行工具实现鼠标和键盘模拟
支持通过官方命令行接口进行精确的输入控制
"""

import logging
import subprocess
import time
import win32gui
from typing import Optional, Tuple, Dict, Any, List, List
from dataclasses import dataclass

from .mumu_manager import get_mumu_manager
from .emulator_detector import EmulatorDetector

logger = logging.getLogger(__name__)

@dataclass
class MuMuInputResult:
    """MuMu输入操作结果"""
    success: bool
    message: str
    vm_index: int
    operation_type: str
    details: Dict[str, Any] = None

class MuMuInputSimulator:
    """MuMu模拟器专用输入模拟器"""

    def __init__(self):
        self.mumu_manager = get_mumu_manager()
        self.detector = EmulatorDetector()
        # 添加缓存以提高性能
        self._vm_index_cache = {}  # hwnd -> vm_index
        self._vm_info_cache = None  # 缓存模拟器信息
        self._vm_info_cache_time = 0  # 缓存时间戳
        self._cache_timeout = 5.0  # 缓存超时时间（秒）

        # 从simple版本合并：窗口句柄变化检测和绑定会话管理
        self._last_hwnd_for_vm = {}  # vm_index -> hwnd
        self._binding_session_id = None  # 当前绑定会话ID
        self._vm_binding_sessions = {}  # vm_index -> session_id

        # ADBKeyboard状态缓存
        self._adb_keyboard_active_cache = {}  # vm_index -> (is_active, timestamp)
        self._adb_keyboard_cache_timeout = 300.0  # 缓存超时时间（秒）

        # 高效模式配置
        self._efficient_mode = True  # 启用高效模式，减少不必要的检测
        self._skip_verification = True  # 跳过ADBKeyboard验证步骤

        logger.info("MuMu输入模拟器初始化完成（高效模式已启用）")
    
    def is_mumu_window(self, hwnd: int) -> bool:
        """检查是否为MuMu模拟器窗口（包括主窗口和渲染窗口）"""
        try:
            # 首先使用模拟器检测器检查渲染窗口
            is_emulator, emulator_type, _ = self.detector.detect_emulator_type(hwnd)
            if is_emulator and emulator_type == "mumu":
                return True

            # 如果不是渲染窗口，检查是否是MuMu主窗口
            import win32gui
            window_title = win32gui.GetWindowText(hwnd)
            window_class = win32gui.GetClassName(hwnd)

            # 检查是否是MuMu主窗口（Qt窗口且标题包含mumu）
            if (window_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                "mumu" in window_title.lower()):
                return True

            return False
        except Exception as e:
            logger.error(f"检测MuMu窗口失败: {e}")
            return False
    
    def get_vm_index_from_hwnd(self, hwnd: int) -> Optional[int]:
        """根据窗口句柄获取MuMu模拟器索引（带缓存优化）"""
        if not hwnd or not self.is_mumu_window(hwnd):
            logger.debug(f"窗口 {hwnd} 不是MuMu窗口或无效")
            return None

        # 检查缓存
        if hwnd in self._vm_index_cache:
            cached_vm_index = self._vm_index_cache[hwnd]
            logger.debug(f"从缓存获取VM索引: HWND {hwnd} -> VM {cached_vm_index}")
            return cached_vm_index

        try:
            logger.info(f"开始为窗口句柄 {hwnd} 获取VM索引")

            # 获取模拟器信息（带缓存）
            vm_info = self._get_cached_vm_info()
            if not vm_info:
                logger.warning("无法获取VM信息")
                return None

            # 将hwnd转换为十六进制字符串进行比较
            hwnd_hex = f"{hwnd:08X}".upper()
            logger.debug(f"目标窗口句柄十六进制: {hwnd_hex}")

            # 处理返回的模拟器信息
            if isinstance(vm_info, dict):
                vm_list = []
                for key, value in vm_info.items():
                    if isinstance(value, dict) and 'index' in value:
                        vm_list.append(value)
                        logger.debug(f"找到VM信息: VM{value.get('index')} - main_wnd:{value.get('main_wnd', 'N/A')} render_wnd:{value.get('render_wnd', 'N/A')}")
                if not vm_list and 'index' in vm_info:
                    vm_list = [vm_info]
                    logger.debug(f"单个VM信息: VM{vm_info.get('index')} - main_wnd:{vm_info.get('main_wnd', 'N/A')} render_wnd:{vm_info.get('render_wnd', 'N/A')}")
            elif isinstance(vm_info, list):
                vm_list = vm_info
                for vm_data in vm_list:
                    if isinstance(vm_data, dict):
                        logger.debug(f"列表VM信息: VM{vm_data.get('index')} - main_wnd:{vm_data.get('main_wnd', 'N/A')} render_wnd:{vm_data.get('render_wnd', 'N/A')}")
            else:
                vm_list = []
                logger.warning(f"VM信息格式不支持: {type(vm_info)}")

            logger.info(f"共找到 {len(vm_list)} 个VM信息")

            # 遍历所有模拟器，查找匹配的窗口句柄
            for vm_data in vm_list:
                if isinstance(vm_data, dict):
                    main_wnd = vm_data.get('main_wnd', '')
                    render_wnd = vm_data.get('render_wnd', '')
                    vm_index = int(vm_data.get('index', 0))

                    logger.debug(f"比较VM{vm_index}: main_wnd={main_wnd} render_wnd={render_wnd} vs 目标={hwnd_hex}")

                    if main_wnd and main_wnd.upper() == hwnd_hex:
                        logger.info(f"通过主窗口匹配找到VM索引: HWND {hwnd} -> VM {vm_index}")
                        self._vm_index_cache[hwnd] = vm_index  # 缓存结果
                        return vm_index
                    if render_wnd and render_wnd.upper() == hwnd_hex:
                        logger.info(f"通过渲染窗口匹配找到VM索引: HWND {hwnd} -> VM {vm_index}")
                        self._vm_index_cache[hwnd] = vm_index  # 缓存结果
                        return vm_index

            logger.warning(f"未找到窗口句柄 {hwnd} 对应的VM索引")
            return None

        except Exception as e:
            logger.error(f"获取VM索引失败: {e}")
            return None

    def _get_cached_vm_info(self):
        """获取缓存的模拟器信息"""
        import time
        current_time = time.time()

        # 如果缓存过期或不存在，重新获取
        if (self._vm_info_cache is None or
            current_time - self._vm_info_cache_time > self._cache_timeout):

            logger.debug("VM信息缓存过期，重新获取...")

            # 使用get_all_vm_info获取所有VM信息，这样可以处理多个VM的情况
            self._vm_info_cache = self.mumu_manager.get_all_vm_info()
            self._vm_info_cache_time = current_time

            # 清理过期的VM索引缓存
            self._vm_index_cache.clear()

            logger.info(f"更新VM信息缓存: {self._vm_info_cache}")

        return self._vm_info_cache

    def clear_cache(self):
        """清理所有缓存（用于多VM绑定时强制刷新）"""
        logger.info("清理MuMu输入模拟器缓存")
        self._vm_info_cache = None
        self._vm_info_cache_time = 0
        self._vm_index_cache.clear()


    # ==================== 键盘输入模拟 ====================
    
    def input_text(self, hwnd: int, text: str) -> MuMuInputResult:
        """输入文本"""
        import os
        is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'
        logger.info(f"🎯 MuMu文本输入开始: HWND={hwnd}, 文本='{text}', 多窗口模式={is_multi_window_mode}")

        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            logger.error(f"❌ 无法获取窗口 {hwnd} 的VM索引，文本输入失败")
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="input_text"
            )

        logger.info(f"✅ 获取到VM索引: HWND {hwnd} -> VM {vm_index}")
        return self.input_text_by_vm_index(vm_index, text, hwnd)
    
    def input_text_by_vm_index(self, vm_index: int, text: str, hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引输入文本（高效版，减少不必要的检测）"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 输入文本: {text}")

            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="input_text"
                )

            # 高效模式：直接尝试输入，失败时才进行检测和激活
            success = self._execute_adb_text_command(vm_index, text)

            # 如果失败，可能需要激活ADBKeyboard
            if not success:
                logger.info(f"VM{vm_index} 首次输入失败，检查并激活ADBKeyboard")

                # 只在失败时才进行重启检测
                if self._should_activate_adb_keyboard_aggressive(vm_index, hwnd):
                    logger.info(f"VM{vm_index} 检测到需要激活ADBKeyboard（可能重启过或窗口变化）")

                # 快速激活ADBKeyboard
                if self._quick_ensure_adb_keyboard_active(vm_index):
                    # 重试输入
                    success = self._execute_adb_text_command(vm_index, text)
                    if not success:
                        logger.warning(f"VM{vm_index} 重试后仍然失败，可能需要手动检查ADBKeyboard配置")

            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"文本输入成功: {text}",
                    vm_index=vm_index,
                    operation_type="input_text",
                    details={"text": text}
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="文本输入失败，请检查ADBKeyboard配置",
                    vm_index=vm_index,
                    operation_type="input_text"
                )
                
        except Exception as e:
            logger.error(f"MuMu模拟器文本输入失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"文本输入异常: {str(e)}",
                vm_index=vm_index,
                operation_type="input_text"
            )
    
    def send_key(self, hwnd: int, key_command: str) -> MuMuInputResult:
        """发送按键命令"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="send_key"
            )
        
        return self.send_key_by_vm_index(vm_index, key_command, hwnd)

    def send_vk_key(self, hwnd: int, vk_code: int) -> MuMuInputResult:
        """发送VK码按键"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="send_vk_key"
            )

        return self.send_vk_key_by_vm_index(vm_index, vk_code, hwnd)

    def send_vk_key_by_vm_index(self, vm_index: int, vk_code: int, hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引发送VK码按键"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 发送VK码按键: {vk_code}")

            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="send_vk_key"
                )

            # 将VK码映射到Android KeyEvent码
            keyevent_code = self._map_vk_to_keyevent(vk_code)
            if keyevent_code is None:
                return MuMuInputResult(
                    success=False,
                    message=f"不支持的VK码: {vk_code}",
                    vm_index=vm_index,
                    operation_type="send_vk_key"
                )

            # 使用shell命令发送keyevent
            shell_command = f"input keyevent {keyevent_code}"
            success = self._execute_adb_shell_command(vm_index, shell_command)

            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"VK码按键发送成功: {vk_code} -> keyevent {keyevent_code}",
                    vm_index=vm_index,
                    operation_type="send_vk_key",
                    details={"vk_code": vk_code, "keyevent_code": keyevent_code}
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="VK码按键发送失败",
                    vm_index=vm_index,
                    operation_type="send_vk_key"
                )

        except Exception as e:
            logger.error(f"MuMu模拟器VK码按键发送失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"VK码按键发送异常: {str(e)}",
                vm_index=vm_index,
                operation_type="send_vk_key"
            )
    
    def send_key_by_vm_index(self, vm_index: int, key_command: str, hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引发送按键命令"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 发送按键: {key_command}")
            
            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="send_key"
                )
            
            # 优先尝试MuMu快捷命令
            adb_command = self._map_key_to_adb_command(key_command)
            if adb_command:
                # 使用MuMu快捷命令
                success = self._execute_adb_command(vm_index, adb_command)
            else:
                # 不支持的按键命令
                return MuMuInputResult(
                    success=False,
                    message=f"不支持的按键命令: {key_command}",
                    vm_index=vm_index,
                    operation_type="send_key"
                )
            
            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"按键发送成功: {key_command}",
                    vm_index=vm_index,
                    operation_type="send_key",
                    details={"key_command": key_command, "adb_command": adb_command}
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="按键发送失败",
                    vm_index=vm_index,
                    operation_type="send_key"
                )
                
        except Exception as e:
            logger.error(f"MuMu模拟器按键发送失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"按键发送异常: {str(e)}",
                vm_index=vm_index,
                operation_type="send_key"
            )

    def send_key_combination(self, hwnd: int, vk_codes: List[int]) -> MuMuInputResult:
        """发送组合键"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="send_key_combination"
            )

        return self.send_key_combination_by_vm_index(vm_index, vk_codes, hwnd)

    def send_key_combination_by_vm_index(self, vm_index: int, vk_codes: List[int], hwnd: Optional[int] = None, hold_duration: float = 0.1) -> MuMuInputResult:
        """根据VM索引发送组合键"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 发送组合键: {vk_codes}")

            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="send_key_combination"
                )

            # 将所有VK码映射到keyevent码
            keyevent_codes = []
            for vk_code in vk_codes:
                keyevent_code = self._map_vk_to_keyevent(vk_code)
                if keyevent_code is None:
                    return MuMuInputResult(
                        success=False,
                        message=f"不支持的VK码: {vk_code}",
                        vm_index=vm_index,
                        operation_type="send_key_combination"
                    )
                keyevent_codes.append(keyevent_code)

            # 构建组合键命令：模拟真实的组合键按下和释放
            success = True

            logger.info(f"MuMu ADB组合键: 按下所有键 {keyevent_codes}，持续时间: {hold_duration}秒")

            # 第一阶段：按下所有键（不释放）
            for keyevent_code in keyevent_codes:
                # 使用 sendevent 模拟按键按下（不释放）
                shell_command = f"input keyevent {keyevent_code}"
                if not self._execute_adb_shell_command(vm_index, shell_command):
                    success = False
                    break
                # 短暂延迟避免按键冲突
                time.sleep(0.02)

            if success and hold_duration > 0:
                # 第二阶段：保持按键状态
                logger.debug(f"保持组合键状态 {hold_duration} 秒")
                time.sleep(hold_duration)

            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"组合键发送成功: {vk_codes} -> {keyevent_codes}",
                    vm_index=vm_index,
                    operation_type="send_key_combination",
                    details={"vk_codes": vk_codes, "keyevent_codes": keyevent_codes}
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="组合键发送失败",
                    vm_index=vm_index,
                    operation_type="send_key_combination"
                )

        except Exception as e:
            logger.error(f"MuMu模拟器组合键发送失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"组合键发送异常: {str(e)}",
                vm_index=vm_index,
                operation_type="send_key_combination"
            )

    # ==================== 鼠标输入模拟 ====================
    
    def mouse_click(self, hwnd: int, x: int, y: int, button: str = "left") -> MuMuInputResult:
        """鼠标点击"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="mouse_click"
            )
        
        return self.mouse_click_by_vm_index(vm_index, x, y, button, hwnd)
    
    def mouse_click_by_vm_index(self, vm_index: int, x: int, y: int, button: str = "left", 
                               hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引执行鼠标点击"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 鼠标点击: ({x}, {y}), 按钮: {button}")
            
            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="mouse_click"
                )
            
            # 使用ADB shell input tap命令
            success = self._execute_adb_shell_command(vm_index, f"input tap {x} {y}")
            
            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"鼠标点击成功: ({x}, {y})",
                    vm_index=vm_index,
                    operation_type="mouse_click",
                    details={"x": x, "y": y, "button": button}
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="鼠标点击失败",
                    vm_index=vm_index,
                    operation_type="mouse_click"
                )
                
        except Exception as e:
            logger.error(f"MuMu模拟器鼠标点击失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"鼠标点击异常: {str(e)}",
                vm_index=vm_index,
                operation_type="mouse_click"
            )
    
    def mouse_swipe(self, hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int, 
                   duration: int = 1000) -> MuMuInputResult:
        """鼠标滑动/拖拽"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="mouse_swipe"
            )
        
        return self.mouse_swipe_by_vm_index(vm_index, start_x, start_y, end_x, end_y, duration, hwnd)
    
    def mouse_swipe_by_vm_index(self, vm_index: int, start_x: int, start_y: int, end_x: int, end_y: int,
                               duration: int = 1000, hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引执行鼠标滑动"""
        try:
            logger.info(f"MuMu模拟器 {vm_index} 鼠标滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y}), 时长: {duration}ms")

            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="mouse_swipe"
                )

            # 使用ADB shell input swipe命令
            success = self._execute_adb_shell_command(vm_index, f"input swipe {start_x} {start_y} {end_x} {end_y} {duration}")

            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"鼠标滑动成功: ({start_x}, {start_y}) -> ({end_x}, {end_y})",
                    vm_index=vm_index,
                    operation_type="mouse_swipe",
                    details={
                        "start_x": start_x, "start_y": start_y,
                        "end_x": end_x, "end_y": end_y,
                        "duration": duration
                    }
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="鼠标滑动失败",
                    vm_index=vm_index,
                    operation_type="mouse_swipe"
                )

        except Exception as e:
            logger.error(f"MuMu模拟器鼠标滑动失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"鼠标滑动异常: {str(e)}",
                vm_index=vm_index,
                operation_type="mouse_swipe"
            )

    def mouse_swipe_path(self, hwnd: int, path_points: list, duration: int = 1000) -> MuMuInputResult:
        """多点路径拖拽 - 通过多个坐标点进行连续拖拽"""
        vm_index = self.get_vm_index_from_hwnd(hwnd)
        if vm_index is None:
            return MuMuInputResult(
                success=False,
                message="无法确定模拟器索引",
                vm_index=-1,
                operation_type="mouse_swipe_path"
            )

        return self.mouse_swipe_path_by_vm_index(vm_index, path_points, duration, hwnd)

    def mouse_swipe_path_by_vm_index(self, vm_index: int, path_points: list, duration: int = 1000,
                                    hwnd: Optional[int] = None) -> MuMuInputResult:
        """根据VM索引执行多点路径拖拽

        Args:
            vm_index: MuMu虚拟机索引
            path_points: 路径点列表，格式: [(x1, y1), (x2, y2), (x3, y3), ...]
            duration: 总持续时间（毫秒）
            hwnd: 窗口句柄（可选）

        Returns:
            MuMuInputResult: 执行结果
        """
        try:
            if not path_points or len(path_points) < 2:
                return MuMuInputResult(
                    success=False,
                    message="路径点数量不足，至少需要2个点",
                    vm_index=vm_index,
                    operation_type="mouse_swipe_path"
                )

            logger.info(f"MuMu模拟器 {vm_index} 多点路径拖拽: {len(path_points)}个点, 总时长: {duration}ms")

            if not self.mumu_manager.is_available():
                return MuMuInputResult(
                    success=False,
                    message="MuMuManager不可用",
                    vm_index=vm_index,
                    operation_type="mouse_swipe_path"
                )

            # 使用motionevent命令实现连续拖拽
            success = self._execute_continuous_swipe(vm_index, path_points, duration)

            if success:
                return MuMuInputResult(
                    success=True,
                    message=f"多点路径拖拽成功: {len(path_points)}个点",
                    vm_index=vm_index,
                    operation_type="mouse_swipe_path",
                    details={
                        "path_points": path_points,
                        "total_duration": duration,
                        "point_count": len(path_points)
                    }
                )
            else:
                return MuMuInputResult(
                    success=False,
                    message="多点路径拖拽失败",
                    vm_index=vm_index,
                    operation_type="mouse_swipe_path"
                )

        except Exception as e:
            logger.error(f"MuMu模拟器多点路径拖拽失败: {e}")
            return MuMuInputResult(
                success=False,
                message=f"多点路径拖拽异常: {str(e)}",
                vm_index=vm_index,
                operation_type="mouse_swipe_path"
            )
    
    def _execute_continuous_swipe(self, vm_index: int, path_points: list, total_duration: int) -> bool:
        """执行连续拖拽 - 优化版本，减少ADB命令调用次数

        Args:
            vm_index: MuMu虚拟机索引
            path_points: 路径点列表 [(x1, y1), (x2, y2), ...]
            total_duration: 总持续时间（毫秒）

        Returns:
            bool: 是否执行成功
        """
        try:
            if len(path_points) < 2:
                return False

            # 优先尝试管道命令方式（最简单高效）
            if self._execute_pipe_swipe(vm_index, path_points, total_duration):
                return True

            # 次选脚本文件方式
            if self._execute_script_swipe(vm_index, path_points, total_duration):
                return True

            # 再次选批量命令方式
            if self._execute_batch_swipe(vm_index, path_points, total_duration):
                return True

            # 回退到逐个执行方式
            logger.warning("批量执行失败，回退到逐个执行模式")
            return self._execute_sequential_swipe(vm_index, path_points, total_duration)

        except Exception as e:
            logger.error(f"执行连续拖拽失败: {e}")
            # 尝试发送UP事件以确保触摸状态正确结束
            try:
                if path_points:
                    end_x, end_y = path_points[-1]
                    self._execute_adb_shell_command(vm_index, f"input motionevent UP {end_x} {end_y}")
            except:
                pass
            return False

    def _execute_pipe_swipe(self, vm_index: int, path_points: list, total_duration: int) -> bool:
        """管道命令执行拖拽 - 使用echo管道一次性发送所有命令"""
        try:
            if len(path_points) < 2:
                return False

            # 计算每个点之间的时间间隔（毫秒）
            segment_count = len(path_points) - 1
            segment_duration_ms = total_duration // segment_count

            # 构建命令序列
            commands = []

            # DOWN事件
            start_x, start_y = path_points[0]
            commands.append(f"input motionevent DOWN {start_x} {start_y}")

            # MOVE事件（包含延迟）
            for i in range(1, len(path_points) - 1):
                x, y = path_points[i]
                if segment_duration_ms > 0:
                    # 添加延迟命令（使用sleep，单位为秒）
                    delay_seconds = segment_duration_ms / 1000.0
                    commands.append(f"sleep {delay_seconds:.3f}")
                commands.append(f"input motionevent MOVE {x} {y}")

            # 最后一个点的延迟和UP事件
            if segment_duration_ms > 0:
                delay_seconds = segment_duration_ms / 1000.0
                commands.append(f"sleep {delay_seconds:.3f}")

            end_x, end_y = path_points[-1]
            commands.append(f"input motionevent UP {end_x} {end_y}")

            # 使用echo和管道一次性执行所有命令
            command_script = "; ".join(commands)
            pipe_command = f'echo "{command_script}" | sh'

            logger.debug(f"管道执行拖拽: {len(commands)}个命令")
            logger.debug(f"管道命令: {pipe_command[:200]}...")  # 只显示前200个字符

            # 执行管道命令
            success = self._execute_adb_shell_command(vm_index, pipe_command)

            if success:
                logger.info(f"管道拖拽完成: {len(path_points)}个点, 总时长: {total_duration}ms")
                return True
            else:
                logger.warning("管道拖拽执行失败")
                return False

        except Exception as e:
            logger.error(f"管道执行拖拽失败: {e}")
            return False

    def _execute_script_swipe(self, vm_index: int, path_points: list, total_duration: int) -> bool:
        """脚本文件执行拖拽 - 最高效的方式，创建临时脚本文件执行"""
        try:
            if len(path_points) < 2:
                return False

            import tempfile
            import os

            # 计算每个点之间的时间间隔（毫秒）
            segment_count = len(path_points) - 1
            segment_duration_ms = total_duration // segment_count

            # 创建临时脚本文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as script_file:
                script_path = script_file.name

                # 写入脚本内容
                script_file.write("#!/system/bin/sh\n")

                # DOWN事件
                start_x, start_y = path_points[0]
                script_file.write(f"input motionevent DOWN {start_x} {start_y}\n")

                # MOVE事件（包含延迟）
                for i in range(1, len(path_points) - 1):
                    x, y = path_points[i]
                    if segment_duration_ms > 0:
                        # 添加延迟（使用usleep，单位为微秒）
                        delay_microseconds = segment_duration_ms * 1000
                        script_file.write(f"usleep {delay_microseconds}\n")
                    script_file.write(f"input motionevent MOVE {x} {y}\n")

                # 最后一个点的延迟和UP事件
                if segment_duration_ms > 0:
                    delay_microseconds = segment_duration_ms * 1000
                    script_file.write(f"usleep {delay_microseconds}\n")

                end_x, end_y = path_points[-1]
                script_file.write(f"input motionevent UP {end_x} {end_y}\n")

            try:
                # 将脚本文件推送到设备
                device_script_path = f"/data/local/tmp/swipe_script_{vm_index}.sh"

                # 推送文件到设备
                push_success = self._push_script_to_device(vm_index, script_path, device_script_path)
                if not push_success:
                    logger.warning("推送脚本文件到设备失败")
                    return False

                # 给脚本文件执行权限并执行
                chmod_success = self._execute_adb_shell_command(vm_index, f"chmod +x {device_script_path}")
                if not chmod_success:
                    logger.warning("设置脚本执行权限失败")
                    return False

                # 执行脚本
                exec_success = self._execute_adb_shell_command(vm_index, f"sh {device_script_path}")

                # 清理设备上的脚本文件
                self._execute_adb_shell_command(vm_index, f"rm {device_script_path}")

                if exec_success:
                    logger.info(f"脚本拖拽完成: {len(path_points)}个点, 总时长: {total_duration}ms")
                    return True
                else:
                    logger.warning("脚本执行失败")
                    return False

            finally:
                # 清理本地临时文件
                try:
                    os.unlink(script_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"脚本执行拖拽失败: {e}")
            return False

    def _push_script_to_device(self, vm_index: int, local_path: str, device_path: str) -> bool:
        """推送脚本文件到设备"""
        try:
            if not self.mumu_manager.is_available():
                return False

            manager_path = self.mumu_manager.get_manager_path()
            if not manager_path:
                return False

            # 构建push命令
            cmd_args = [manager_path, "adb", "-v", str(vm_index), "-c", f"push {local_path} {device_path}"]

            import subprocess
            result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                logger.debug(f"成功推送脚本文件: {local_path} -> {device_path}")
                return True
            else:
                logger.warning(f"推送脚本文件失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"推送脚本文件异常: {e}")
            return False

    def _execute_batch_swipe(self, vm_index: int, path_points: list, total_duration: int) -> bool:
        """批量执行拖拽 - 使用shell脚本一次性执行所有命令"""
        try:
            if len(path_points) < 2:
                return False

            # 计算每个点之间的时间间隔（毫秒）
            segment_count = len(path_points) - 1
            segment_duration_ms = total_duration // segment_count

            # 构建批量命令脚本
            commands = []

            # DOWN事件
            start_x, start_y = path_points[0]
            commands.append(f"input motionevent DOWN {start_x} {start_y}")

            # MOVE事件（包含延迟）
            for i in range(1, len(path_points) - 1):
                x, y = path_points[i]
                if segment_duration_ms > 0:
                    # 添加延迟命令（使用sleep，单位为秒）
                    delay_seconds = segment_duration_ms / 1000.0
                    commands.append(f"sleep {delay_seconds:.3f}")
                commands.append(f"input motionevent MOVE {x} {y}")

            # 最后一个点的延迟和UP事件
            if segment_duration_ms > 0:
                delay_seconds = segment_duration_ms / 1000.0
                commands.append(f"sleep {delay_seconds:.3f}")

            end_x, end_y = path_points[-1]
            commands.append(f"input motionevent UP {end_x} {end_y}")

            # 将所有命令合并为一个shell脚本
            batch_script = " && ".join(commands)

            logger.debug(f"批量执行拖拽脚本: {len(commands)}个命令")
            logger.debug(f"脚本内容: {batch_script[:200]}...")  # 只显示前200个字符

            # 执行批量命令
            success = self._execute_adb_shell_command(vm_index, batch_script)

            if success:
                logger.info(f"批量拖拽完成: {len(path_points)}个点, 总时长: {total_duration}ms")
                return True
            else:
                logger.warning("批量拖拽执行失败")
                return False

        except Exception as e:
            logger.error(f"批量执行拖拽失败: {e}")
            return False

    def _execute_sequential_swipe(self, vm_index: int, path_points: list, total_duration: int) -> bool:
        """逐个执行拖拽 - 原有的逐个命令方式（作为回退方案）"""
        try:
            if len(path_points) < 2:
                return False

            # 计算每个点之间的时间间隔
            segment_count = len(path_points) - 1
            segment_duration = total_duration / segment_count / 1000.0  # 转换为秒

            # 开始触摸 - DOWN事件
            start_x, start_y = path_points[0]
            down_success = self._execute_adb_shell_command(vm_index, f"input motionevent DOWN {start_x} {start_y}")
            if not down_success:
                logger.error("发送DOWN事件失败")
                return False

            logger.debug(f"发送DOWN事件: ({start_x}, {start_y})")

            # 移动到中间点 - MOVE事件
            import time
            for i in range(1, len(path_points) - 1):
                x, y = path_points[i]
                move_success = self._execute_adb_shell_command(vm_index, f"input motionevent MOVE {x} {y}")
                if not move_success:
                    logger.warning(f"发送MOVE事件失败: ({x}, {y})")
                    # 继续执行，不中断整个流程
                else:
                    logger.debug(f"发送MOVE事件: ({x}, {y})")

                # 等待指定时间
                time.sleep(segment_duration)

            # 结束触摸 - UP事件
            end_x, end_y = path_points[-1]
            up_success = self._execute_adb_shell_command(vm_index, f"input motionevent UP {end_x} {end_y}")
            if not up_success:
                logger.error("发送UP事件失败")
                return False

            logger.debug(f"发送UP事件: ({end_x}, {end_y})")

            logger.info(f"逐个拖拽完成: {len(path_points)}个点, 总时长: {total_duration}ms")
            return True

        except Exception as e:
            logger.error(f"逐个执行拖拽失败: {e}")
            return False

    # ==================== 辅助方法 ====================
    
    def _execute_adb_command(self, vm_index: int, command: str, *args) -> bool:
        """执行MuMu ADB快捷命令"""
        try:
            manager_path = self.mumu_manager.mumu_manager_path
            if not manager_path:
                return False

            # 构建命令参数 - MuMu快捷命令格式
            cmd_args = [manager_path, "adb", "-v", str(vm_index), "-c", command]
            if args:
                cmd_args.extend(args)

            logger.debug(f"执行MuMu ADB快捷命令: {' '.join(cmd_args)}")

            # 使用更强力的方法隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = (
                subprocess.CREATE_NO_WINDOW |
                subprocess.DETACHED_PROCESS |
                subprocess.CREATE_NEW_PROCESS_GROUP
            )

            result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=3,
                                   creationflags=creation_flags, startupinfo=startupinfo)

            if result.returncode == 0:
                logger.debug(f"MuMu ADB快捷命令执行成功: {command}")
                return True
            else:
                logger.error(f"MuMu ADB快捷命令执行失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"执行MuMu ADB快捷命令异常: {e}")
            return False
    
    def _execute_adb_shell_command(self, vm_index: int, shell_command: str) -> bool:
        """执行MuMu ADB shell命令"""
        try:
            manager_path = self.mumu_manager.mumu_manager_path
            if not manager_path:
                return False

            # 构建shell命令 - MuMu格式：用引号包围整个shell命令
            full_command = f"shell {shell_command}"
            cmd_args = [manager_path, "adb", "-v", str(vm_index), "-c", full_command]

            logger.debug(f"执行MuMu ADB shell命令: {' '.join(cmd_args)}")

            # 使用更强力的方法隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = (
                subprocess.CREATE_NO_WINDOW |
                subprocess.DETACHED_PROCESS |
                subprocess.CREATE_NEW_PROCESS_GROUP
            )

            result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=3,
                                   creationflags=creation_flags, startupinfo=startupinfo)

            if result.returncode == 0:
                logger.debug(f"MuMu ADB shell命令执行成功: {shell_command}")
                return True
            else:
                logger.error(f"MuMu ADB shell命令执行失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"执行MuMu ADB shell命令异常: {e}")
            return False

    def _execute_adb_text_command(self, vm_index: int, text: str) -> bool:
        """执行MuMu ADB文本输入命令 - 只使用ADBKeyboard方法"""
        try:
            manager_path = self.mumu_manager.mumu_manager_path
            if not manager_path:
                return False

            logger.info(f"MuMu模拟器 {vm_index} 使用ADBKeyboard输入文本: {text}")

            # 只使用ADBKeyboard方法（已验证有效）
            success = self._execute_adb_keyboard_input(vm_index, text)
            if success:
                logger.info(f"ADBKeyboard输入成功: {text}")
                return True
            else:
                logger.error(f"ADBKeyboard输入失败: {text}")
                return False

        except Exception as e:
            logger.error(f"执行ADBKeyboard文本输入异常: {e}")
            return False

    def _execute_adb_keyboard_input(self, vm_index: int, text: str) -> bool:
        """使用ADBKeyboard输入法发送文本（高效简化版）"""
        try:
            manager_path = self.mumu_manager.mumu_manager_path
            if not manager_path:
                return False

            # 直接发送文本，不做过多检查
            escaped_text = text.replace("'", "\\'").replace('"', '\\"')
            shell_command = f"am broadcast -a ADB_INPUT_TEXT --es msg '{escaped_text}'"

            # 直接执行命令
            success = self._execute_adb_shell_command(vm_index, shell_command)

            if success:
                logger.info(f"VM{vm_index} ADBKeyboard输入成功: '{text}'")
                return True
            else:
                logger.error(f"VM{vm_index} ADBKeyboard输入失败: '{text}'")
                return False

        except Exception as e:
            logger.error(f"VM{vm_index} ADBKeyboard输入异常: {e}")
            return False

    def _ensure_adb_keyboard_active(self, vm_index: int) -> bool:
        """确保ADBKeyboard输入法已激活并可用（带缓存优化和深度验证）"""
        try:
            current_time = time.time()

            # 检查缓存
            if vm_index in self._adb_keyboard_active_cache:
                is_active, cache_time = self._adb_keyboard_active_cache[vm_index]
                if current_time - cache_time < self._adb_keyboard_cache_timeout and is_active:
                    logger.debug(f"VM{vm_index} ADBKeyboard状态从缓存获取: 已激活")
                    return True

            logger.debug(f"VM{vm_index} 检查并激活ADBKeyboard输入法")

            # 1. 检查ADBKeyboard是否已安装
            check_cmd = f"pm list packages com.android.adbkeyboard"
            if not self._execute_adb_shell_command(vm_index, check_cmd):
                logger.warning(f"VM{vm_index} ADBKeyboard未安装")
                self._adb_keyboard_active_cache[vm_index] = (False, current_time)
                return False

            # 2. 启用ADBKeyboard输入法
            enable_cmd = "ime enable com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, enable_cmd):
                logger.warning(f"VM{vm_index} 启用ADBKeyboard失败")

            # 3. 设置ADBKeyboard为当前输入法
            set_cmd = "ime set com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, set_cmd):
                logger.warning(f"VM{vm_index} 设置ADBKeyboard为当前输入法失败")
                self._adb_keyboard_active_cache[vm_index] = (False, current_time)
                return False

            # 4. 工具 修复：深度验证ADBKeyboard是否真正激活
            if not self._verify_adb_keyboard_really_active(vm_index):
                logger.warning(f"VM{vm_index} ADBKeyboard深度验证失败，尝试强制激活")
                # 尝试强制激活
                if not self._force_activate_adb_keyboard(vm_index):
                    logger.error(f"VM{vm_index} 强制激活ADBKeyboard失败")
                    self._adb_keyboard_active_cache[vm_index] = (False, current_time)
                    return False

            logger.debug(f"VM{vm_index} ADBKeyboard输入法激活完成")
            # 缓存成功状态
            self._adb_keyboard_active_cache[vm_index] = (True, current_time)
            return True

        except Exception as e:
            logger.warning(f"VM{vm_index} 激活ADBKeyboard输入法异常: {e}")
            # 缓存失败状态（较短时间）
            self._adb_keyboard_active_cache[vm_index] = (False, time.time())
            return False

    def _verify_adb_keyboard_really_active(self, vm_index: int) -> bool:
        """简化验证ADBKeyboard是否激活"""
        try:
            logger.debug(f"VM{vm_index} 验证ADBKeyboard状态")

            # 发送测试广播验证是否能接收
            test_cmd = "am broadcast -a ADB_INPUT_TEXT --es msg ''"
            success = self._execute_adb_shell_command(vm_index, test_cmd)

            if success:
                logger.debug(f"VM{vm_index} ADBKeyboard验证通过")
                return True
            else:
                logger.debug(f"VM{vm_index} ADBKeyboard验证失败")
                return False

        except Exception as e:
            logger.debug(f"VM{vm_index} ADBKeyboard验证异常: {e}")
            return False

    def _quick_ensure_adb_keyboard_active(self, vm_index: int) -> bool:
        """快速确保ADBKeyboard激活（可配置是否跳过验证）"""
        try:
            if self._skip_verification:
                logger.debug(f"VM{vm_index} 快速激活ADBKeyboard（跳过验证）")
            else:
                logger.debug(f"VM{vm_index} 快速激活ADBKeyboard（包含验证）")

            # 1. 启用ADBKeyboard输入法
            enable_cmd = "ime enable com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, enable_cmd):
                logger.warning(f"VM{vm_index} 启用ADBKeyboard失败")
                return False

            # 2. 设置ADBKeyboard为当前输入法
            set_cmd = "ime set com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, set_cmd):
                logger.warning(f"VM{vm_index} 设置ADBKeyboard为当前输入法失败")
                return False

            # 3. 根据配置决定是否验证
            if not self._skip_verification:
                # 验证ADBKeyboard是否真正激活
                if not self._verify_adb_keyboard_really_active(vm_index):
                    logger.warning(f"VM{vm_index} ADBKeyboard验证失败")
                    return False

            # 4. 短暂等待生效（减少等待时间）
            time.sleep(0.1 if self._skip_verification else 0.2)

            # 5. 更新缓存
            current_time = time.time()
            self._adb_keyboard_active_cache[vm_index] = (True, current_time)

            mode_desc = "（跳过验证）" if self._skip_verification else "（包含验证）"
            logger.info(f"VM{vm_index} ADBKeyboard快速激活完成{mode_desc}")
            return True

        except Exception as e:
            logger.error(f"VM{vm_index} 快速激活ADBKeyboard异常: {e}")
            return False

    def _should_activate_adb_keyboard_aggressive(self, vm_index: int, hwnd: int = None) -> bool:
        """激进的ADBKeyboard检测（适用于父窗口句柄频繁变化的情况）"""
        try:
            import time
            current_time = time.time()

            # 检查绑定会话是否变化（重新绑定检测）
            if self._check_binding_session_change(vm_index):
                logger.info(f"VM{vm_index} 检测到重新绑定，强制重新激活ADBKeyboard")
                # 清除相关缓存
                if vm_index in self._adb_keyboard_active_cache:
                    del self._adb_keyboard_active_cache[vm_index]
                if hwnd is not None:
                    self._last_hwnd_for_vm[vm_index] = hwnd
                return True  # 强制激活

            # 检查窗口句柄是否变化（更严格的检测）
            if hwnd is not None:
                if vm_index in self._last_hwnd_for_vm:
                    last_hwnd = self._last_hwnd_for_vm[vm_index]
                    if last_hwnd != hwnd:
                        logger.info(f"VM{vm_index} 检测到父窗口句柄变化: {last_hwnd} -> {hwnd}，强制重新激活")
                        # 窗口变化，清除缓存强制重新检测
                        if vm_index in self._adb_keyboard_active_cache:
                            del self._adb_keyboard_active_cache[vm_index]
                        self._last_hwnd_for_vm[vm_index] = hwnd
                        return True  # 强制激活
                else:
                    # 首次记录窗口句柄
                    self._last_hwnd_for_vm[vm_index] = hwnd

            # 缩短缓存时间，更频繁地检测
            short_cache_timeout = 10.0  # 只缓存10秒

            # 检查缓存
            if vm_index in self._adb_keyboard_active_cache:
                is_active, cache_time = self._adb_keyboard_active_cache[vm_index]
                if current_time - cache_time < short_cache_timeout and is_active:
                    logger.debug(f"VM{vm_index} ADBKeyboard状态缓存有效（激进模式），跳过检测")
                    return False

            # 快速检测：发送空广播测试ADBKeyboard是否响应
            test_cmd = "am broadcast -a ADB_INPUT_TEXT --es msg ''"
            success = self._execute_adb_shell_command(vm_index, test_cmd)

            if success:
                # 检测成功，更新缓存
                self._adb_keyboard_active_cache[vm_index] = (True, current_time)
                logger.debug(f"VM{vm_index} ADBKeyboard状态正常（激进模式），已缓存")
                return False
            else:
                # 检测失败，清除缓存
                if vm_index in self._adb_keyboard_active_cache:
                    del self._adb_keyboard_active_cache[vm_index]
                logger.debug(f"VM{vm_index} ADBKeyboard测试失败（激进模式），需要激活")
                return True

        except Exception as e:
            logger.debug(f"VM{vm_index} 激进检测ADBKeyboard状态异常: {e}，需要激活")
            return True

    def _check_binding_session_change(self, vm_index: int) -> bool:
        """检查绑定会话是否变化"""
        if self._binding_session_id is None:
            return False

        if vm_index not in self._vm_binding_sessions:
            # 首次记录
            self._vm_binding_sessions[vm_index] = self._binding_session_id
            logger.debug(f"VM{vm_index} 首次记录绑定会话: {self._binding_session_id}")
            return True  # 首次绑定，需要激活

        last_session = self._vm_binding_sessions[vm_index]
        if last_session != self._binding_session_id:
            logger.info(f"VM{vm_index} 检测到绑定会话变化: {last_session} -> {self._binding_session_id}，需要重新激活")
            self._vm_binding_sessions[vm_index] = self._binding_session_id
            return True  # 会话变化，需要重新激活

        return False  # 会话未变化

    def set_binding_session(self, session_id: str = None):
        """设置绑定会话ID（用于检测重新绑定）"""
        import time
        if session_id is None:
            session_id = f"session_{int(time.time())}"

        old_session = self._binding_session_id
        self._binding_session_id = session_id

        if old_session != session_id:
            logger.info(f"检测到绑定会话变化: {old_session} -> {session_id}，清除所有缓存")
            # 绑定会话变化，清除所有缓存
            self.clear_cache()

        return session_id

    def force_reactivate_adb_keyboard(self, vm_index: int = None):
        """强制重新激活ADBKeyboard（清除缓存并激活）"""
        if vm_index is not None:
            # 清除特定VM的缓存
            if vm_index in self._adb_keyboard_active_cache:
                del self._adb_keyboard_active_cache[vm_index]
            if vm_index in self._last_hwnd_for_vm:
                del self._last_hwnd_for_vm[vm_index]
            logger.info(f"已清除VM{vm_index}的ADBKeyboard缓存和窗口句柄，下次输入时将重新激活")
        else:
            # 清除所有缓存
            self._adb_keyboard_active_cache.clear()
            self._last_hwnd_for_vm.clear()
            self._vm_binding_sessions.clear()
            logger.info("已清除所有ADBKeyboard缓存和窗口句柄，下次输入时将重新激活")

    def clear_cache(self):
        """清理所有缓存"""
        self._vm_index_cache.clear()
        self._adb_keyboard_active_cache.clear()
        self._last_hwnd_for_vm.clear()
        self._vm_binding_sessions.clear()
        self._vm_info_cache = None
        self._vm_info_cache_time = 0
        logger.info("已清理所有缓存（VM索引、ADBKeyboard状态、窗口句柄和绑定会话）")

    def set_efficient_mode(self, enabled: bool = True, skip_verification: bool = True):
        """设置高效模式

        Args:
            enabled: 是否启用高效模式（直接尝试输入，失败时才检测）
            skip_verification: 是否跳过ADBKeyboard验证步骤
        """
        self._efficient_mode = enabled
        self._skip_verification = skip_verification

        mode_desc = "高效模式" if enabled else "完整检测模式"
        verify_desc = "跳过验证" if skip_verification else "包含验证"
        logger.info(f"MuMu输入模拟器模式设置: {mode_desc} ({verify_desc})")

    def get_efficient_mode_status(self) -> dict:
        """获取当前高效模式状态"""
        return {
            "efficient_mode": self._efficient_mode,
            "skip_verification": self._skip_verification,
            "description": "高效模式" if self._efficient_mode else "完整检测模式"
        }

    def _force_activate_adb_keyboard(self, vm_index: int) -> bool:
        """强制激活ADBKeyboard输入法（简化版）"""
        try:
            logger.info(f"VM{vm_index} 强制激活ADBKeyboard")

            # 1. 启用ADBKeyboard输入法
            enable_cmd = "ime enable com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, enable_cmd):
                logger.error(f"VM{vm_index} 启用ADBKeyboard失败")
                return False

            # 2. 设置为当前输入法
            set_cmd = "ime set com.android.adbkeyboard/.AdbIME"
            if not self._execute_adb_shell_command(vm_index, set_cmd):
                logger.error(f"VM{vm_index} 设置ADBKeyboard失败")
                return False

            # 3. 等待输入法生效
            time.sleep(0.5)

            logger.info(f"VM{vm_index} ADBKeyboard激活完成")
            return True

        except Exception as e:
            logger.error(f"VM{vm_index} 激活ADBKeyboard异常: {e}")
            return False



    def _ensure_input_focus(self, vm_index: int) -> bool:
        """确保有输入焦点（简化版 - 只点击屏幕中央）"""
        try:
            logger.debug(f"VM{vm_index} 尝试激活输入焦点")

            # 点击屏幕中央激活焦点
            tap_cmd = "input tap 400 600"
            success = self._execute_adb_shell_command(vm_index, tap_cmd)

            if success:
                time.sleep(0.3)  # 等待焦点切换
                logger.debug(f"VM{vm_index} 焦点激活完成")
            else:
                logger.debug(f"VM{vm_index} 焦点激活失败")

            return True  # 总是返回True，不阻止后续输入

        except Exception as e:
            logger.debug(f"VM{vm_index} 激活焦点异常: {e}")
            return True

    def force_refresh_adb_keyboard_status(self, vm_index: int = None):
        """强制刷新ADBKeyboard状态缓存"""
        if vm_index is not None:
            # 清除特定VM的缓存
            if vm_index in self._adb_keyboard_active_cache:
                del self._adb_keyboard_active_cache[vm_index]
                logger.debug(f"已清除VM{vm_index}的ADBKeyboard状态缓存")
        else:
            # 清除所有缓存
            self._adb_keyboard_active_cache.clear()
            logger.debug("已清除所有VM的ADBKeyboard状态缓存")

    def _map_key_to_adb_command(self, key_command: str) -> Optional[str]:
        """将按键命令映射到MuMu支持的ADB命令"""
        # MuMu官方支持的快捷按键命令映射
        key_mapping = {
            # 系统按键
            "back": "go_back",
            "home": "go_home",
            "menu": "go_task",
            "task": "go_task",

            # 音量按键
            "volume_up": "volume_up",
            "volume_down": "volume_down",
            "volume_mute": "volume_mute",

            # 别名支持
            "返回": "go_back",
            "主页": "go_home",
            "首页": "go_home",
            "任务": "go_task",
            "音量加": "volume_up",
            "音量减": "volume_down",
            "静音": "volume_mute",
        }

        return key_mapping.get(key_command.lower())

    def _map_vk_to_keyevent(self, vk_code: int) -> Optional[int]:
        """将VK码映射到Android KeyEvent码"""
        # VK码到Android KeyEvent的映射表
        vk_to_keyevent = {
            # 数字键 0-9
            0x30: 7,   # VK_0 -> KEYCODE_0
            0x31: 8,   # VK_1 -> KEYCODE_1
            0x32: 9,   # VK_2 -> KEYCODE_2
            0x33: 10,  # VK_3 -> KEYCODE_3
            0x34: 11,  # VK_4 -> KEYCODE_4
            0x35: 12,  # VK_5 -> KEYCODE_5
            0x36: 13,  # VK_6 -> KEYCODE_6
            0x37: 14,  # VK_7 -> KEYCODE_7
            0x38: 15,  # VK_8 -> KEYCODE_8
            0x39: 16,  # VK_9 -> KEYCODE_9

            # 字母键 A-Z
            0x41: 29,  # VK_A -> KEYCODE_A
            0x42: 30,  # VK_B -> KEYCODE_B
            0x43: 31,  # VK_C -> KEYCODE_C
            0x44: 32,  # VK_D -> KEYCODE_D
            0x45: 33,  # VK_E -> KEYCODE_E
            0x46: 34,  # VK_F -> KEYCODE_F
            0x47: 35,  # VK_G -> KEYCODE_G
            0x48: 36,  # VK_H -> KEYCODE_H
            0x49: 37,  # VK_I -> KEYCODE_I
            0x4A: 38,  # VK_J -> KEYCODE_J
            0x4B: 39,  # VK_K -> KEYCODE_K
            0x4C: 40,  # VK_L -> KEYCODE_L
            0x4D: 41,  # VK_M -> KEYCODE_M
            0x4E: 42,  # VK_N -> KEYCODE_N
            0x4F: 43,  # VK_O -> KEYCODE_O
            0x50: 44,  # VK_P -> KEYCODE_P
            0x51: 45,  # VK_Q -> KEYCODE_Q
            0x52: 46,  # VK_R -> KEYCODE_R
            0x53: 47,  # VK_S -> KEYCODE_S
            0x54: 48,  # VK_T -> KEYCODE_T
            0x55: 49,  # VK_U -> KEYCODE_U
            0x56: 50,  # VK_V -> KEYCODE_V
            0x57: 51,  # VK_W -> KEYCODE_W
            0x58: 52,  # VK_X -> KEYCODE_X
            0x59: 53,  # VK_Y -> KEYCODE_Y
            0x5A: 54,  # VK_Z -> KEYCODE_Z

            # 功能键
            0x0D: 66,  # VK_RETURN -> KEYCODE_ENTER
            0x20: 62,  # VK_SPACE -> KEYCODE_SPACE
            0x08: 67,  # VK_BACK -> KEYCODE_DEL
            0x09: 61,  # VK_TAB -> KEYCODE_TAB
            0x1B: 4,   # VK_ESCAPE -> KEYCODE_BACK

            # 方向键
            0x25: 21,  # VK_LEFT -> KEYCODE_DPAD_LEFT
            0x26: 19,  # VK_UP -> KEYCODE_DPAD_UP
            0x27: 22,  # VK_RIGHT -> KEYCODE_DPAD_RIGHT
            0x28: 20,  # VK_DOWN -> KEYCODE_DPAD_DOWN

            # 系统键
            0x24: 3,   # VK_HOME -> KEYCODE_HOME
            0x23: 6,   # VK_END -> KEYCODE_ENDCALL
            0x2D: 124, # VK_INSERT -> KEYCODE_INSERT
            0x2E: 112, # VK_DELETE -> KEYCODE_FORWARD_DEL

            # 修饰键
            0x10: 59,  # VK_SHIFT -> KEYCODE_SHIFT_LEFT
            0x11: 113, # VK_CONTROL -> KEYCODE_CTRL_LEFT
            0x12: 57,  # VK_MENU -> KEYCODE_ALT_LEFT

            # 音量键
            0xAF: 24,  # VK_VOLUME_UP -> KEYCODE_VOLUME_UP
            0xAE: 25,  # VK_VOLUME_DOWN -> KEYCODE_VOLUME_DOWN
            0xAD: 164, # VK_VOLUME_MUTE -> KEYCODE_VOLUME_MUTE
        }

        return vk_to_keyevent.get(vk_code)

# 全局实例
_mumu_input_simulator = None

def get_mumu_input_simulator() -> MuMuInputSimulator:
    """获取MuMu输入模拟器实例"""
    global _mumu_input_simulator
    if _mumu_input_simulator is None:
        _mumu_input_simulator = MuMuInputSimulator()
    return _mumu_input_simulator

def get_simple_mumu_input_simulator() -> MuMuInputSimulator:
    """获取简化MuMu输入模拟器实例（兼容接口，实际返回完整版）"""
    return get_mumu_input_simulator()
