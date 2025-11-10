"""
窗口句柄管理器
处理模拟器重启后的窗口句柄变化问题
"""

import logging
import time
import threading
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class WindowInfo:
    """窗口信息"""
    hwnd: int
    title: str
    vm_index: Optional[int] = None
    emulator_type: Optional[str] = None
    last_update: float = 0.0

class WindowHandleManager:
    """窗口句柄管理器"""
    
    def __init__(self):
        self._window_registry: Dict[str, WindowInfo] = {}
        self._update_callbacks: Dict[str, Callable[[int, int], None]] = {}
        self._user_notification_callbacks = []  # 用户通知回调列表
        self._invalid_windows = {}  # 失效窗口记录
        self._lock = threading.RLock()
        self._monitoring = False
        self._monitor_thread = None
        
        logger.info("窗口句柄管理器初始化完成")
    
    def register_window(self, key: str, hwnd: int, title: str, vm_index: Optional[int] = None, 
                       emulator_type: Optional[str] = None) -> bool:
        """注册窗口"""
        try:
            with self._lock:
                window_info = WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    vm_index=vm_index,
                    emulator_type=emulator_type,
                    last_update=time.time()
                )
                
                self._window_registry[key] = window_info
                logger.info(f"注册窗口: {key} -> HWND:{hwnd}, 标题:{title}, VM:{vm_index}")
                return True
                
        except Exception as e:
            logger.error(f"注册窗口失败: {e}")
            return False
    
    def get_window_hwnd(self, key: str) -> Optional[int]:
        """获取窗口句柄"""
        with self._lock:
            window_info = self._window_registry.get(key)
            if window_info:
                # 检查窗口是否仍然有效
                if self._is_window_valid(window_info.hwnd):
                    return window_info.hwnd
                else:
                    logger.warning(f"窗口句柄已失效: {key} -> HWND:{window_info.hwnd}")
                    # 尝试重新查找
                    new_hwnd = self._find_window_by_info(window_info)
                    if new_hwnd:
                        self._update_window_hwnd(key, new_hwnd)
                        return new_hwnd
            return None
    
    def add_update_callback(self, key: str, callback: Callable[[int, int], None]):
        """添加窗口句柄更新回调"""
        with self._lock:
            self._update_callbacks[key] = callback
            logger.debug(f"添加窗口句柄更新回调: {key}")

    def add_user_notification_callback(self, callback: Callable[[str, any], None]):
        """添加用户通知回调，当窗口句柄失效时调用"""
        with self._lock:
            if callback not in self._user_notification_callbacks:
                self._user_notification_callbacks.append(callback)
                logger.debug(f"添加用户通知回调: {callback}")

    def remove_user_notification_callback(self, callback: Callable[[str, any], None]):
        """移除用户通知回调"""
        with self._lock:
            if callback in self._user_notification_callbacks:
                self._user_notification_callbacks.remove(callback)
                logger.debug(f"移除用户通知回调: {callback}")

    def get_invalid_windows(self) -> dict:
        """获取失效的窗口列表"""
        with self._lock:
            return self._invalid_windows.copy()

    def clear_invalid_window(self, key: str):
        """清除失效窗口记录（用户重新绑定后调用）"""
        with self._lock:
            if key in self._invalid_windows:
                del self._invalid_windows[key]
                logger.debug(f"清除失效窗口记录: {key}")
    
    def remove_update_callback(self, key: str):
        """移除窗口句柄更新回调"""
        with self._lock:
            if key in self._update_callbacks:
                del self._update_callbacks[key]
                logger.debug(f"移除窗口句柄更新回调: {key}")
    
    def start_monitoring(self, interval: float = 5.0):
        """开始监控窗口句柄变化"""
        if self._monitoring:
            return
        
        self._monitoring = True
        
        def monitor_loop():
            while self._monitoring:
                try:
                    self._check_all_windows()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"窗口监控异常: {e}")
                    time.sleep(interval)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"开始窗口句柄监控，间隔: {interval}秒")
    
    def stop_monitoring(self):
        """停止监控窗口句柄变化"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        logger.info("停止窗口句柄监控")
    
    def _check_all_windows(self):
        """检查所有注册的窗口"""
        with self._lock:
            for key, window_info in list(self._window_registry.items()):
                if not self._is_window_valid(window_info.hwnd):
                    logger.warning(f"检测到窗口句柄失效: {key} -> HWND:{window_info.hwnd}，窗口可能已关闭或重启，请手动重新绑定")
                    # 不再自动重新绑定，仅提示用户手动重新绑定
                    self._notify_user_rebind_needed(key, window_info)
    
    def _notify_user_rebind_needed(self, key: str, window_info):
        """通知用户需要手动重新绑定窗口"""
        try:
            window_title = window_info.title if hasattr(window_info, 'title') else '未知窗口'
            logger.warning(f"⚠️ 窗口句柄失效通知: '{window_title}' (绑定键: {key})")

            # 触发UI通知回调
            if hasattr(self, '_user_notification_callbacks') and self._user_notification_callbacks:
                for callback in self._user_notification_callbacks:
                    try:
                        callback(key, window_info)
                    except Exception as e:
                        logger.error(f"执行用户通知回调失败: {e}")

            # 记录失效的窗口，供UI查询
            if not hasattr(self, '_invalid_windows'):
                self._invalid_windows = {}
            self._invalid_windows[key] = {
                'window_info': window_info,
                'invalid_time': time.time(),
                'notified': True
            }

        except Exception as e:
            logger.error(f"通知用户重新绑定失败: {e}")

    def _is_window_valid(self, hwnd: int) -> bool:
        """检查窗口句柄是否有效"""
        try:
            import win32gui
            return win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd)
        except:
            return False
    
    def _find_window_by_info(self, window_info: WindowInfo) -> Optional[int]:
        """根据窗口信息重新查找窗口句柄"""
        try:
            import win32gui

            # 如果是MuMu模拟器，使用多种方法查找
            if window_info.emulator_type == "mumu":
                # 方法1：使用VM索引查找
                if window_info.vm_index is not None:
                    hwnd = self._find_mumu_window_by_vm_index(window_info.vm_index)
                    if hwnd:
                        logger.info(f"通过VM索引找到MuMu窗口: VM{window_info.vm_index} -> HWND:{hwnd}")
                        return hwnd

                # 方法2：使用模拟器检测器查找
                hwnd = self._find_mumu_window_by_detector(window_info.title)
                if hwnd:
                    logger.info(f"通过模拟器检测器找到MuMu窗口: {window_info.title} -> HWND:{hwnd}")
                    return hwnd

                # 方法3：使用标题模糊匹配
                hwnd = self._find_mumu_window_by_title_pattern(window_info.title)
                if hwnd:
                    logger.info(f"通过标题模式找到MuMu窗口: {window_info.title} -> HWND:{hwnd}")
                    return hwnd

            # 通用方法：根据标题精确查找
            found_hwnd = None

            def enum_windows_proc(hwnd, lParam):
                nonlocal found_hwnd
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title == window_info.title:
                            found_hwnd = hwnd
                            return False  # 停止枚举
                except:
                    pass
                return True

            win32gui.EnumWindows(enum_windows_proc, None)

            if found_hwnd:
                logger.info(f"通过标题精确匹配找到窗口: {window_info.title} -> HWND:{found_hwnd}")

            return found_hwnd

        except Exception as e:
            logger.error(f"重新查找窗口失败: {e}")
            return None
    
    def _find_mumu_window_by_vm_index(self, vm_index: int) -> Optional[int]:
        """根据VM索引查找MuMu窗口"""
        try:
            from .mumu_resolution_manager import get_mumu_resolution_manager
            manager = get_mumu_resolution_manager()
            hwnd = manager._find_window_by_vm_index(vm_index)
            if hwnd:
                logger.debug(f"VM索引查找成功: VM{vm_index} -> HWND:{hwnd}")
            else:
                logger.debug(f"VM索引查找失败: VM{vm_index}")
            return hwnd
        except Exception as e:
            logger.error(f"根据VM索引查找MuMu窗口失败: {e}")
            return None

    def _find_mumu_window_by_detector(self, original_title: str) -> Optional[int]:
        """使用模拟器检测器查找MuMu窗口"""
        try:
            import win32gui
            from .emulator_detector import EmulatorDetector

            detector = EmulatorDetector()
            found_hwnd = None

            def enum_windows_proc(hwnd, lParam):
                nonlocal found_hwnd
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        is_emulator, emulator_type, _ = detector.detect_emulator_type(hwnd)
                        if is_emulator and emulator_type == "mumu":
                            title = win32gui.GetWindowText(hwnd)
                            # 检查是否是设备窗口
                            if "设备" in title or "MuMu" in title:
                                found_hwnd = hwnd
                                logger.debug(f"检测器找到MuMu窗口: {title} -> HWND:{hwnd}")
                                return False  # 停止枚举
                except:
                    pass
                return True

            win32gui.EnumWindows(enum_windows_proc, None)
            return found_hwnd

        except Exception as e:
            logger.error(f"使用检测器查找MuMu窗口失败: {e}")
            return None

    def _find_mumu_window_by_title_pattern(self, original_title: str) -> Optional[int]:
        """使用标题模式查找MuMu窗口"""
        try:
            import win32gui
            import re

            # 提取原标题中的关键信息
            # 例如："MuMu模拟器12-设备1" -> 提取"设备1"
            device_match = re.search(r'设备(\d+)', original_title)
            device_num = device_match.group(1) if device_match else None

            found_hwnd = None

            def enum_windows_proc(hwnd, lParam):
                nonlocal found_hwnd
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)

                        # 检查是否是MuMu窗口
                        if "MuMu" in title and "设备" in title:
                            # 如果有设备号，优先匹配设备号
                            if device_num:
                                if f"设备{device_num}" in title:
                                    found_hwnd = hwnd
                                    logger.debug(f"标题模式匹配成功: {title} -> HWND:{hwnd}")
                                    return False
                            else:
                                # 没有设备号，匹配第一个找到的MuMu设备窗口
                                found_hwnd = hwnd
                                logger.debug(f"标题模式匹配成功: {title} -> HWND:{hwnd}")
                                return False
                except:
                    pass
                return True

            win32gui.EnumWindows(enum_windows_proc, None)
            return found_hwnd

        except Exception as e:
            logger.error(f"使用标题模式查找MuMu窗口失败: {e}")
            return None
    
    def _update_window_hwnd(self, key: str, new_hwnd: int):
        """更新窗口句柄"""
        with self._lock:
            if key in self._window_registry:
                old_hwnd = self._window_registry[key].hwnd

                # 防抖：如果句柄没有真正改变，跳过更新
                if old_hwnd == new_hwnd:
                    return

                # 防抖：检查是否在短时间内重复更新
                current_time = time.time()
                last_update = self._window_registry[key].last_update
                if current_time - last_update < 2.0:  # 2秒内不重复更新
                    logger.debug(f"跳过重复更新窗口句柄: {key} (距离上次更新 {current_time - last_update:.1f}秒)")
                    return

                self._window_registry[key].hwnd = new_hwnd
                self._window_registry[key].last_update = current_time

                logger.info(f"更新窗口句柄: {key} -> {old_hwnd} => {new_hwnd}")

                # 通知回调 - 使用线程安全的方式
                if key in self._update_callbacks:
                    try:
                        # 在新线程中执行回调，避免阻塞监控线程
                        callback = self._update_callbacks[key]

                        def safe_callback():
                            try:
                                callback(old_hwnd, new_hwnd)
                            except Exception as e:
                                logger.error(f"窗口句柄更新回调执行失败: {e}")

                        # 使用线程池执行回调，避免阻塞
                        import threading
                        callback_thread = threading.Thread(target=safe_callback, daemon=True)
                        callback_thread.start()

                    except Exception as e:
                        logger.error(f"启动窗口句柄更新回调线程失败: {e}")
    
    def unregister_window(self, key: str):
        """注销窗口"""
        with self._lock:
            if key in self._window_registry:
                del self._window_registry[key]
                logger.info(f"注销窗口: {key}")
            
            if key in self._update_callbacks:
                del self._update_callbacks[key]
    
    def get_all_registered_windows(self) -> Dict[str, WindowInfo]:
        """获取所有注册的窗口"""
        with self._lock:
            return self._window_registry.copy()

    def get_vm_index_by_hwnd(self, hwnd: int) -> Optional[int]:
        """通过窗口句柄获取VM索引"""
        try:
            with self._lock:
                for window_info in self._window_registry.values():
                    if window_info.hwnd == hwnd and window_info.vm_index is not None:
                        return window_info.vm_index

                # 如果注册表中没有找到，尝试通过MuMu管理器查找
                try:
                    from utils.mumu_manager import get_mumu_manager
                    mumu_manager = get_mumu_manager()

                    if mumu_manager.is_available():
                        vm_info_data = mumu_manager.get_all_vm_info()  # 获取所有VM信息
                        logger.debug(f"WindowHandleManager获取VM信息: {type(vm_info_data)} - {vm_info_data}")
                        if vm_info_data and isinstance(vm_info_data, dict):
                            logger.info(f"WindowHandleManager获取到VM信息: {vm_info_data}")
                            # MuMu管理器已经处理了格式转换，这里应该总是字典格式
                            for vm_index, vm_info in vm_info_data.items():
                                if vm_info and isinstance(vm_info, dict) and 'main_wnd' in vm_info:
                                    try:
                                        vm_hwnd = int(vm_info['main_wnd'], 16)
                                        logger.info(f"比较窗口句柄: VM{vm_index} hwnd={vm_hwnd} vs 目标={hwnd}")
                                        if vm_hwnd == hwnd:
                                            logger.info(f"找到匹配的VM索引: {vm_index}")
                                            return int(vm_index)
                                    except Exception as e:
                                        logger.debug(f"解析VM{vm_index}窗口句柄失败: {e}")
                                        continue
                        else:
                            logger.warning(f"VM信息数据无效: {type(vm_info_data)} - {vm_info_data}")
                except Exception as e:
                    logger.debug(f"通过MuMu管理器查找VM索引失败: {e}")

                logger.warning(f"无法找到窗口句柄 {hwnd} 对应的VM索引")
                return None

        except Exception as e:
            logger.error(f"获取VM索引异常: {e}")
            return None

    def get_window_handle_by_vm_index(self, vm_index: int) -> Optional[int]:
        """通过VM索引获取窗口句柄"""
        try:
            with self._lock:
                for window_info in self._window_registry.values():
                    if window_info.vm_index == vm_index:
                        return window_info.hwnd

                # 如果注册表中没有找到，尝试通过MuMu管理器查找
                try:
                    from utils.mumu_manager import get_mumu_manager
                    mumu_manager = get_mumu_manager()

                    if mumu_manager.is_available():
                        vm_info = mumu_manager.get_simulator_info(vm_index)  # 获取指定VM信息
                        if vm_info and 'main_wnd' in vm_info:
                            try:
                                vm_hwnd = int(vm_info['main_wnd'], 16)
                                return vm_hwnd
                            except:
                                pass
                except Exception as e:
                    logger.debug(f"通过MuMu管理器查找窗口句柄失败: {e}")

                logger.warning(f"无法找到VM索引 {vm_index} 对应的窗口句柄")
                return None

        except Exception as e:
            logger.error(f"获取窗口句柄异常: {e}")
            return None

# 全局实例
_window_handle_manager = None

def get_window_handle_manager() -> WindowHandleManager:
    """获取窗口句柄管理器实例"""
    global _window_handle_manager
    if _window_handle_manager is None:
        _window_handle_manager = WindowHandleManager()
    return _window_handle_manager
