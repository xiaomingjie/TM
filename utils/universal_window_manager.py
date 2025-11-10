"""
通用窗口管理器 - 统一处理窗口分辨率调整和管理
基于通用分辨率适配器，提供标准化的窗口操作接口

功能：
1. 窗口分辨率调整
2. 多窗口批量调整
3. 窗口状态监控
4. DPI变化检测和处理
"""

import logging
import threading
import time
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass

try:
    from .universal_resolution_adapter import get_universal_adapter, REFERENCE_WIDTH, REFERENCE_HEIGHT
except ImportError:
    # 如果适配器不可用，使用默认值
    REFERENCE_WIDTH = 1280
    REFERENCE_HEIGHT = 720

    def get_universal_adapter():
        class MockAdapter:
            def get_window_state(self, hwnd):
                return None
            def adjust_window_resolution(self, hwnd, width, height):
                return False
        return MockAdapter()

try:
    from .mumu_resolution_manager import get_mumu_resolution_manager
    from .ldplayer_resolution_manager import get_ldplayer_resolution_manager
    from .emulator_detector import EmulatorDetector
except ImportError:
    # 如果分辨率管理器不可用，使用空实现
    def get_mumu_resolution_manager():
        return None

    def get_ldplayer_resolution_manager():
        return None

    class EmulatorDetector:
        def detect_emulator_type(self, hwnd):
            return False, None, ""

logger = logging.getLogger(__name__)

@dataclass
class WindowAdjustmentResult:
    """窗口调整结果"""
    hwnd: int
    title: str
    success: bool
    message: str
    before_size: Tuple[int, int] = (0, 0)
    after_size: Tuple[int, int] = (0, 0)
    adjustment_time: float = 0.0

class UniversalWindowManager:
    """通用窗口管理器"""

    def __init__(self):
        self.adapter = get_universal_adapter()
        self.mumu_resolution_manager = get_mumu_resolution_manager()
        # 获取底层的MuMu管理器用于VM索引查找
        from utils.mumu_manager import get_mumu_manager
        self.mumu_manager = get_mumu_manager()
        self.ldplayer_manager = get_ldplayer_resolution_manager()
        self.detector = EmulatorDetector()
        self._lock = threading.RLock()
        self._adjustment_callbacks: List[Callable] = []
        self._monitoring_enabled = True

        logger.info("通用窗口管理器初始化完成")
    
    def add_adjustment_callback(self, callback: Callable[[WindowAdjustmentResult], None]):
        """添加窗口调整回调函数"""
        with self._lock:
            if callback not in self._adjustment_callbacks:
                self._adjustment_callbacks.append(callback)
    
    def remove_adjustment_callback(self, callback: Callable):
        """移除窗口调整回调函数"""
        with self._lock:
            if callback in self._adjustment_callbacks:
                self._adjustment_callbacks.remove(callback)
    
    def _notify_adjustment_callbacks(self, result: WindowAdjustmentResult):
        """通知窗口调整回调"""
        with self._lock:
            for callback in self._adjustment_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"窗口调整回调执行失败: {e}")
    
    def adjust_single_window(self, hwnd: int, target_width: int = REFERENCE_WIDTH,
                           target_height: int = REFERENCE_HEIGHT, async_mode: bool = False) -> WindowAdjustmentResult:
        """调整单个窗口分辨率"""
        start_time = time.time()

        # 如果没有指定目标分辨率，尝试从全局设置获取
        if target_width == REFERENCE_WIDTH and target_height == REFERENCE_HEIGHT:
            try:
                # 尝试获取全局设置的分辨率
                global_width, global_height = self._get_global_resolution_settings()
                if global_width > 0 and global_height > 0:
                    target_width = global_width
                    target_height = global_height
                    logger.info(f"使用全局设置的分辨率: {target_width}x{target_height}")
            except Exception as e:
                logger.debug(f"获取全局分辨率设置失败，使用默认值: {e}")

        # 检测是否为模拟器窗口
        is_emulator, emulator_type, _ = self.detector.detect_emulator_type(hwnd)

        if is_emulator and emulator_type == "mumu" and self.mumu_manager:
            logger.info(f"检测到MuMu模拟器窗口，使用专门的分辨率调整方法")
            if async_mode:
                return self._adjust_mumu_window_async(hwnd, target_width, target_height, start_time)
            else:
                return self._adjust_mumu_window(hwnd, target_width, target_height, start_time)

        elif is_emulator and emulator_type == "ldplayer":
            logger.info(f"检测到雷电模拟器窗口，使用专门的分辨率调整方法")
            if async_mode:
                return self._adjust_ldplayer_window_async(hwnd, target_width, target_height, start_time)
            else:
                return self._adjust_ldplayer_window(hwnd, target_width, target_height, start_time)

        # 使用通用方法调整其他窗口
        return self._adjust_standard_window(hwnd, target_width, target_height, start_time)

    def _adjust_mumu_window(self, hwnd: int, target_width: int, target_height: int, start_time: float) -> WindowAdjustmentResult:
        """调整MuMu模拟器窗口分辨率"""
        try:
            import win32gui
            window_title = win32gui.GetWindowText(hwnd)

            # 首先需要通过hwnd获取vm_index
            vm_index = self._get_vm_index_by_hwnd(hwnd)
            if vm_index is None:
                from utils.mumu_resolution_manager import ResolutionResult
                mumu_result = ResolutionResult(
                    success=False,
                    message="无法获取VM索引",
                    vm_index=-1,
                    target_resolution=(target_width, target_height),
                    before_size=(0, 0),
                    after_size=(0, 0)
                )
            else:
                # 使用MuMu专门的分辨率管理器（内置分辨率检查）
                mumu_result = self.mumu_resolution_manager.adjust_resolution(vm_index, target_width, target_height)

            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title=window_title,
                success=mumu_result.success,
                message=mumu_result.message,
                before_size=mumu_result.before_size,
                after_size=mumu_result.after_size,
                adjustment_time=time.time() - start_time
            )

            self._notify_adjustment_callbacks(result)
            return result

        except Exception as e:
            logger.error(f"调整MuMu模拟器窗口失败: {e}")
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title="MuMu模拟器",
                success=False,
                message=f"调整失败: {str(e)}",
                adjustment_time=time.time() - start_time
            )
            self._notify_adjustment_callbacks(result)
            return result

    def _adjust_mumu_window_async(self, hwnd: int, target_width: int, target_height: int, start_time: float) -> WindowAdjustmentResult:
        """异步调整MuMu模拟器窗口分辨率"""
        try:
            import win32gui
            import time  # 在方法开始就导入time模块
            window_title = win32gui.GetWindowText(hwnd)

            # 立即返回一个"进行中"的结果
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title=window_title,
                success=True,
                message="MuMu模拟器分辨率调整已启动，请等待重启完成...",
                before_size=(0, 0),
                after_size=(target_width, target_height),
                adjustment_time=time.time() - start_time
            )

            # 启动异步调整任务
            import threading
            import time  # 在函数开始就导入time模块
            def async_adjust():
                try:
                    logger.info(f"开始异步调整MuMu模拟器分辨率: {target_width}x{target_height}")
                    # 获取VM索引
                    vm_index = self._get_vm_index_by_hwnd(hwnd)
                    if vm_index is None:
                        from utils.mumu_resolution_manager import ResolutionResult
                        mumu_result = ResolutionResult(
                            success=False,
                            message="无法获取VM索引",
                            vm_index=-1,
                            target_resolution=(target_width, target_height),
                            before_size=(0, 0),
                            after_size=(0, 0)
                        )
                    else:
                        # 添加随机延迟避免并发冲突
                        import random
                        delay = random.uniform(0.5, 2.0)  # 0.5-2秒随机延迟
                        logger.info(f"VM {vm_index} 随机延迟 {delay:.1f} 秒避免并发冲突")
                        time.sleep(delay)

                        # 使用MuMu专门的分辨率管理器（内置分辨率检查）
                        mumu_result = self.mumu_resolution_manager.adjust_resolution(vm_index, target_width, target_height)

                    # 调整完成后的回调
                    final_result = WindowAdjustmentResult(
                        hwnd=hwnd,
                        title=window_title,
                        success=mumu_result.success,
                        message=f"MuMu模拟器分辨率调整完成: {mumu_result.message}",
                        before_size=mumu_result.before_size,
                        after_size=mumu_result.after_size,
                        adjustment_time=time.time() - start_time
                    )

                    # 通知回调
                    self._notify_adjustment_callbacks(final_result)
                    logger.info(f"MuMu模拟器异步分辨率调整完成")

                except Exception as e:
                    logger.error(f"MuMu模拟器异步分辨率调整失败: {e}")
                    error_result = WindowAdjustmentResult(
                        hwnd=hwnd,
                        title=window_title,
                        success=False,
                        message=f"异步调整失败: {str(e)}",
                        adjustment_time=time.time() - start_time
                    )
                    self._notify_adjustment_callbacks(error_result)

            # 启动异步线程
            thread = threading.Thread(target=async_adjust, daemon=True)
            thread.start()

            # 立即返回进行中的结果
            self._notify_adjustment_callbacks(result)
            return result

        except Exception as e:
            logger.error(f"启动MuMu模拟器异步分辨率调整失败: {e}")
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title="MuMu模拟器",
                success=False,
                message=f"启动异步调整失败: {str(e)}",
                adjustment_time=time.time() - start_time
            )
            self._notify_adjustment_callbacks(result)
            return result

    def _adjust_standard_window(self, hwnd: int, target_width: int, target_height: int, start_time: float) -> WindowAdjustmentResult:
        """调整标准窗口分辨率"""
        # 获取窗口状态
        window_state = self.adapter.get_window_state(hwnd, force_refresh=True)
        if not window_state:
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title="未知窗口",
                success=False,
                message="无法获取窗口状态",
                adjustment_time=time.time() - start_time
            )
            self._notify_adjustment_callbacks(result)
            return result

        before_size = (window_state.width, window_state.height)

        # 检查当前分辨率是否已经符合要求
        if window_state.width == target_width and window_state.height == target_height:
            logger.info(f"窗口 {window_state.title} 当前分辨率 {window_state.width}x{window_state.height} 已符合目标分辨率，跳过调整")
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title=window_state.title,
                success=True,
                message="分辨率已符合要求，无需调整",
                before_size=before_size,
                after_size=before_size,
                adjustment_time=time.time() - start_time
            )
            self._notify_adjustment_callbacks(result)
            return result

        # 检查是否需要调整
        if window_state.width == target_width and window_state.height == target_height:
            result = WindowAdjustmentResult(
                hwnd=hwnd,
                title=window_state.title,
                success=True,
                message="窗口已经是目标尺寸",
                before_size=before_size,
                after_size=before_size,
                adjustment_time=time.time() - start_time
            )
            self._notify_adjustment_callbacks(result)
            return result
        
        # 执行调整
        logger.info(f"调整窗口分辨率: {window_state.title} ({before_size[0]}x{before_size[1]} -> {target_width}x{target_height})")
        
        success = self.adapter.adjust_window_resolution(hwnd, target_width, target_height)
        
        # 获取调整后的状态
        after_state = self.adapter.get_window_state(hwnd, force_refresh=True)
        after_size = (after_state.width, after_state.height) if after_state else before_size
        
        result = WindowAdjustmentResult(
            hwnd=hwnd,
            title=window_state.title,
            success=success,
            message="调整成功" if success else "调整失败",
            before_size=before_size,
            after_size=after_size,
            adjustment_time=time.time() - start_time
        )
        
        self._notify_adjustment_callbacks(result)
        return result
    
    def adjust_multiple_windows(self, window_list: List[Dict[str, Any]],
                              target_width: int = REFERENCE_WIDTH,
                              target_height: int = REFERENCE_HEIGHT) -> List[WindowAdjustmentResult]:
        """批量调整多个窗口分辨率"""
        results = []

        logger.info(f"开始批量调整 {len(window_list)} 个窗口到 {target_width}x{target_height}")

        # 首先验证所有窗口句柄的唯一性
        hwnd_count = {}
        for i, window_info in enumerate(window_list):
            hwnd = window_info.get('hwnd')
            title = window_info.get('title', '未知窗口')
            logger.info(f"窗口 {i+1}: {title} (HWND: {hwnd})")

            if hwnd:
                hwnd_count[hwnd] = hwnd_count.get(hwnd, 0) + 1

        # 检查重复的句柄
        duplicate_hwnds = [hwnd for hwnd, count in hwnd_count.items() if count > 1]
        if duplicate_hwnds:
            logger.warning(f"发现重复的窗口句柄: {duplicate_hwnds}")

        for i, window_info in enumerate(window_list):
            hwnd = window_info.get('hwnd')
            title = window_info.get('title', '未知窗口')

            if not hwnd:
                # 尝试通过标题查找窗口
                if title:
                    hwnd = self._find_window_by_title(title)
                    if hwnd:
                        window_info['hwnd'] = hwnd
                        logger.info(f"通过标题找到窗口句柄: {title} -> {hwnd}")

            if hwnd:
                # 验证窗口句柄是否有效
                try:
                    import win32gui
                    if not win32gui.IsWindow(hwnd):
                        logger.error(f"窗口句柄无效: {title} (HWND: {hwnd})")
                        result = WindowAdjustmentResult(
                            hwnd=hwnd,
                            title=title,
                            success=False,
                            message="窗口句柄无效"
                        )
                        results.append(result)
                        continue
                except Exception as e:
                    logger.error(f"验证窗口句柄时出错: {e}")

                logger.info(f"[批量调整] 调整窗口 {i+1}/{len(window_list)}: {title} (HWND: {hwnd})")
                result = self.adjust_single_window(hwnd, target_width, target_height)
                logger.info(f"[批量调整] 窗口 {i+1} 调整结果: 成功={result.success}, "
                           f"调整前={result.before_size}, 调整后={result.after_size}")
                results.append(result)
            else:
                logger.error(f"无法找到窗口句柄: {title}")
                result = WindowAdjustmentResult(
                    hwnd=0,
                    title=title,
                    success=False,
                    message="无法找到窗口句柄"
                )
                results.append(result)
                self._notify_adjustment_callbacks(result)

        # 统计结果
        success_count = sum(1 for r in results if r.success)
        logger.info(f"批量调整完成: 成功 {success_count}/{len(results)} 个窗口")

        # 为所有成功调整的MuMu窗口统一设置DPI
        self._unify_mumu_dpi(results)

        return results

    def _unify_mumu_dpi(self, results: List[WindowAdjustmentResult], target_dpi: int = 180):
        """统一设置所有MuMu模拟器的DPI"""
        if not self.mumu_manager:
            return

        logger.info(f"开始统一设置MuMu模拟器DPI为 {target_dpi}")

        # 收集所有成功调整的MuMu窗口
        mumu_hwnds = []
        for result in results:
            if result.success and result.hwnd:
                # 检测是否为MuMu窗口
                is_emulator, emulator_type, _ = self.detector.detect_emulator_type(result.hwnd)
                if is_emulator and emulator_type == "mumu":
                    mumu_hwnds.append(result.hwnd)

        if not mumu_hwnds:
            logger.info("没有找到需要设置DPI的MuMu窗口")
            return

        logger.info(f"找到 {len(mumu_hwnds)} 个MuMu窗口需要设置DPI")

        # 获取所有VM信息
        try:
            all_vm_info = self.mumu_manager.get_all_vm_info()
            if not all_vm_info:
                logger.warning("无法获取VM信息，跳过DPI设置")
                return

            # 为每个VM设置DPI
            for vm_index_str, vm_info in all_vm_info.items():
                try:
                    vm_index = int(vm_index_str)
                    vm_name = vm_info.get('name', f'VM{vm_index}')

                    logger.info(f"设置 {vm_name} (VM{vm_index}) DPI为 {target_dpi}")

                    # 使用简单的ADB命令设置DPI
                    manager_path = self.mumu_manager.manager_path
                    dpi_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", f"wm density {target_dpi}"]

                    import subprocess
                    result = subprocess.run(dpi_cmd, capture_output=True, text=True, timeout=30)

                    if result.returncode == 0:
                        logger.info(f"✅ {vm_name} DPI设置成功")
                    else:
                        logger.warning(f"❌ {vm_name} DPI设置失败: {result.stderr}")

                except Exception as e:
                    logger.warning(f"设置VM{vm_index} DPI时出错: {e}")

        except Exception as e:
            logger.error(f"统一设置DPI时出错: {e}")

    def _find_window_by_title(self, title: str) -> Optional[int]:
        """通过标题查找窗口句柄"""
        try:
            import win32gui
            
            def enum_windows_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    window_title = win32gui.GetWindowText(hwnd)
                    if title in window_title:
                        windows.append(hwnd)
                return True
            
            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            
            return windows[0] if windows else None
            
        except Exception as e:
            logger.error(f"查找窗口失败: {e}")
            return None
    
    def get_window_adjustment_status(self, hwnd: int, target_width: int = REFERENCE_WIDTH,
                                   target_height: int = REFERENCE_HEIGHT) -> Dict[str, Any]:
        """获取窗口调整状态"""
        window_state = self.adapter.get_window_state(hwnd)
        if not window_state:
            return {"error": "无法获取窗口状态"}
        
        needs_adjustment = (window_state.width != target_width or 
                          window_state.height != target_height)
        
        return {
            "hwnd": hwnd,
            "title": window_state.title,
            "current_size": f"{window_state.width}x{window_state.height}",
            "target_size": f"{target_width}x{target_height}",
            "needs_adjustment": needs_adjustment,
            "dpi_info": {
                "dpi": window_state.dpi,
                "scale_factor": window_state.scale_factor
            },
            "size_difference": {
                "width_diff": window_state.width - target_width,
                "height_diff": window_state.height - target_height
            }
        }
    
    def monitor_window_changes(self, window_list: List[Dict[str, Any]], 
                             check_interval: float = 5.0,
                             auto_adjust: bool = False) -> None:
        """监控窗口变化（在后台线程中运行）"""
        def monitor_thread():
            logger.info(f"开始监控 {len(window_list)} 个窗口的变化")
            
            while self._monitoring_enabled:
                try:
                    for window_info in window_list:
                        hwnd = window_info.get('hwnd')
                        if not hwnd:
                            continue
                        
                        # 检查窗口状态
                        current_state = self.adapter.get_window_state(hwnd, force_refresh=True)
                        if not current_state:
                            continue
                        
                        # 检查是否需要调整
                        target_width = window_info.get('target_width', REFERENCE_WIDTH)
                        target_height = window_info.get('target_height', REFERENCE_HEIGHT)
                        
                        if (current_state.width != target_width or 
                            current_state.height != target_height):
                            
                            logger.info(f"检测到窗口尺寸变化: {current_state.title} "
                                      f"({current_state.width}x{current_state.height})")
                            
                            if auto_adjust:
                                self.adjust_single_window(hwnd, target_width, target_height)
                    
                    time.sleep(check_interval)
                    
                except Exception as e:
                    logger.error(f"窗口监控过程中发生错误: {e}")
                    time.sleep(check_interval)
        
        # 在后台线程中启动监控
        monitor_thread_obj = threading.Thread(target=monitor_thread, daemon=True)
        monitor_thread_obj.start()
    
    def stop_monitoring(self):
        """停止窗口监控"""
        self._monitoring_enabled = False
        logger.info("窗口监控已停止")
    
    def get_all_adjustable_windows(self) -> List[Dict[str, Any]]:
        """获取所有可调整的窗口列表"""
        try:
            import win32gui
            
            windows = []
            
            def enum_windows_callback(hwnd, windows_list):
                if win32gui.IsWindowVisible(hwnd):
                    try:
                        title = win32gui.GetWindowText(hwnd)
                        if title and len(title.strip()) > 0:
                            window_state = self.adapter.get_window_state(hwnd)
                            if window_state and window_state.width > 100 and window_state.height > 100:
                                windows_list.append({
                                    'hwnd': hwnd,
                                    'title': title,
                                    'size': f"{window_state.width}x{window_state.height}",
                                    'dpi': window_state.dpi,
                                    'needs_adjustment': (window_state.width != REFERENCE_WIDTH or 
                                                       window_state.height != REFERENCE_HEIGHT)
                                })
                    except Exception:
                        pass
                return True
            
            win32gui.EnumWindows(enum_windows_callback, windows)
            return windows
            
        except Exception as e:
            logger.error(f"获取窗口列表失败: {e}")
            return []

    def _get_global_resolution_settings(self) -> Tuple[int, int]:
        """获取全局设置的分辨率"""
        try:
            # 尝试从主窗口获取分辨率设置
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                for widget in app.topLevelWidgets():
                    if hasattr(widget, 'custom_width') and hasattr(widget, 'custom_height'):
                        width = getattr(widget, 'custom_width', 0)
                        height = getattr(widget, 'custom_height', 0)
                        if width > 0 and height > 0:
                            logger.debug(f"从主窗口获取全局分辨率设置: {width}x{height}")
                            return (width, height)

            # 如果无法从主窗口获取，尝试从配置文件读取
            import json
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    width = config.get('custom_width', 0)
                    height = config.get('custom_height', 0)
                    if width > 0 and height > 0:
                        logger.debug(f"从配置文件获取全局分辨率设置: {width}x{height}")
                        return (width, height)

            return (0, 0)

        except Exception as e:
            logger.debug(f"获取全局分辨率设置失败: {e}")
            return (0, 0)
    
    def create_adjustment_report(self, results: List[WindowAdjustmentResult]) -> Dict[str, Any]:
        """创建调整报告"""
        if not results:
            return {"error": "没有调整结果"}
        
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        total_time = sum(r.adjustment_time for r in results)
        
        successful_windows = [r for r in results if r.success]
        failed_windows = [r for r in results if not r.success]
        
        return {
            "summary": {
                "total_windows": len(results),
                "successful": success_count,
                "failed": failed_count,
                "success_rate": f"{success_count/len(results)*100:.1f}%",
                "total_time": f"{total_time:.2f}s",
                "average_time": f"{total_time/len(results):.2f}s"
            },
            "successful_windows": [
                {
                    "title": r.title,
                    "before": f"{r.before_size[0]}x{r.before_size[1]}",
                    "after": f"{r.after_size[0]}x{r.after_size[1]}",
                    "time": f"{r.adjustment_time:.2f}s"
                }
                for r in successful_windows
            ],
            "failed_windows": [
                {
                    "title": r.title,
                    "reason": r.message,
                    "time": f"{r.adjustment_time:.2f}s"
                }
                for r in failed_windows
            ]
        }

    def _get_vm_index_by_hwnd(self, hwnd) -> Optional[int]:
        """通过窗口句柄获取VM索引（支持渲染窗口和主窗口）"""
        try:
            # 首先尝试使用MuMu输入模拟器获取VM索引（支持渲染窗口）
            try:
                from utils.mumu_input_simulator import get_mumu_input_simulator
                mumu_simulator = get_mumu_input_simulator()
                vm_index = mumu_simulator.get_vm_index_from_hwnd(hwnd)
                if vm_index is not None:
                    logger.debug(f"通过MuMu输入模拟器获取VM索引: {hwnd} -> {vm_index}")
                    return vm_index
            except Exception as e:
                logger.debug(f"MuMu输入模拟器获取VM索引失败: {e}")

            # 如果是渲染窗口，尝试找到对应的主窗口
            main_hwnd = self._get_main_window_from_render_window(hwnd)
            if main_hwnd and main_hwnd != hwnd:
                logger.debug(f"从渲染窗口 {hwnd} 找到主窗口 {main_hwnd}")
                # 递归调用，使用主窗口句柄
                return self._get_vm_index_by_hwnd(main_hwnd)

            # 尝试通过窗口句柄管理器获取
            from utils.window_handle_manager import get_window_handle_manager
            window_manager = get_window_handle_manager()
            vm_index = window_manager.get_vm_index_by_hwnd(hwnd)
            if vm_index is not None:
                return vm_index

            # 如果直接获取失败，尝试通过MuMu管理器获取
            if self.mumu_manager and hasattr(self.mumu_manager, 'get_all_vm_info'):
                vm_info_data = self.mumu_manager.get_all_vm_info()
                if vm_info_data and isinstance(vm_info_data, dict):
                    # MuMu管理器已经处理了格式转换，这里应该总是字典格式
                    for vm_index, vm_info in vm_info_data.items():
                        if vm_info and isinstance(vm_info, dict) and 'main_wnd' in vm_info:
                            try:
                                vm_hwnd = int(vm_info['main_wnd'], 16)
                                if vm_hwnd == hwnd:
                                    return int(vm_index)
                            except:
                                continue

            logger.warning(f"无法获取窗口句柄 {hwnd} 对应的VM索引")
            return None

        except Exception as e:
            logger.error(f"获取VM索引异常: {e}")
            return None

    def _get_main_window_from_render_window(self, render_hwnd: int) -> Optional[int]:
        """从渲染窗口获取对应的主窗口句柄"""
        try:
            # 检测是否是MuMu渲染窗口
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(render_hwnd)

            if is_emulator and emulator_type == "mumu":
                # 使用EmulatorWindow的父窗口查找逻辑
                from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                emulator_window = EmulatorWindowInputSimulator(render_hwnd, "mumu", "background")
                main_hwnd = emulator_window._get_mumu_parent_window()
                if main_hwnd:
                    logger.debug(f"找到MuMu主窗口: 渲染窗口({render_hwnd}) -> 主窗口({main_hwnd})")
                    return main_hwnd

            return None
        except Exception as e:
            logger.debug(f"获取主窗口失败: {e}")
            return None

    def _should_auto_restart_ldplayer(self) -> bool:
        """检查是否应该自动重启雷电模拟器"""
        try:
            # 尝试从配置文件读取设置
            import json
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 检查是否有自动重启设置
                    auto_restart = config.get('ldplayer_auto_restart', True)  # 默认为True
                    logger.debug(f"配置文件中的雷电模拟器自动重启设置: {auto_restart}")
                    return auto_restart
        except Exception as e:
            logger.debug(f"读取自动重启配置失败: {e}")

        # 默认自动重启
        return True

    def _get_optimal_dpi_for_resolution(self, width: int, height: int) -> int:
        """根据分辨率获取最佳DPI设置"""
        try:
            # 尝试从配置文件读取自定义DPI
            import json
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    custom_dpi = config.get('ldplayer_dpi')
                    if custom_dpi and isinstance(custom_dpi, int):
                        logger.info(f"使用配置文件中的自定义DPI: {custom_dpi}")
                        return custom_dpi
        except Exception as e:
            logger.debug(f"读取自定义DPI配置失败: {e}")

        # 根据分辨率自动选择DPI
        resolution_area = width * height

        if resolution_area <= 1280 * 720:  # 720p及以下
            return 180  # 适中的DPI，界面清晰且不会太大
        elif resolution_area <= 1920 * 1080:  # 1080p
            return 160  # 标准DPI
        elif resolution_area <= 2560 * 1440:  # 1440p
            return 240  # 高DPI，保持界面元素合适大小
        else:  # 4K及以上
            return 320  # 超高DPI

    def _adjust_ldplayer_window(self, hwnd: int, target_width: int, target_height: int, start_time: float) -> WindowAdjustmentResult:
        """调整雷电模拟器窗口分辨率"""
        try:
            import win32gui
            window_title = win32gui.GetWindowText(hwnd)

            if not self.ldplayer_manager:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=False,
                    message="雷电模拟器分辨率管理器不可用",
                    adjustment_time=time.time() - start_time
                )

            # 获取实例信息
            instance = self.ldplayer_manager.get_instance_by_hwnd(hwnd)
            if not instance:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=False,
                    message="无法找到对应的雷电模拟器实例",
                    adjustment_time=time.time() - start_time
                )

            instance_index = instance['index']
            logger.info(f"找到雷电模拟器实例: 索引={instance_index}, 标题={instance['title']}")

            # 获取当前窗口状态
            current_state = self.adapter.get_window_state(hwnd, force_refresh=True)
            before_size = (current_state.width, current_state.height) if current_state else (0, 0)

            # 检查是否已经是目标分辨率
            if current_state and current_state.width == target_width and current_state.height == target_height:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=True,
                    message="分辨率已符合要求，无需调整",
                    before_size=before_size,
                    after_size=before_size,
                    adjustment_time=time.time() - start_time
                )

            # 使用雷电模拟器专用方法调整分辨率和DPI
            # 设置DPI为180，提供适中的显示效果
            target_dpi = 180
            result = self.ldplayer_manager.modify_resolution_and_dpi(
                instance_index, target_width, target_height, target_dpi
            )

            if result.success:
                logger.info(f"雷电模拟器分辨率调整成功: {result.message}")

                # 检查是否自动重启（可以通过配置控制）
                auto_restart = self._should_auto_restart_ldplayer()

                if auto_restart:
                    logger.info(f"自动重启雷电模拟器实例 {instance_index}")
                    restart_success = self.ldplayer_manager.restart_instance(instance_index)
                    if restart_success:
                        result.message += "，模拟器已自动重启"
                    else:
                        result.message += "，模拟器自动重启失败，请手动重启"
                else:
                    # 询问用户是否重启模拟器
                    try:
                        from PySide6.QtWidgets import QMessageBox, QApplication
                        app = QApplication.instance()
                        if app:
                            reply = QMessageBox.question(
                                None,
                                "雷电模拟器分辨率调整",
                                f"雷电模拟器实例 {instance_index} 的分辨率和DPI已修改为 {target_width}x{target_height} (DPI: {target_dpi})。\n\n"
                                f"需要重启模拟器使设置生效。是否现在重启？",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes
                            )

                            if reply == QMessageBox.StandardButton.Yes:
                                logger.info(f"用户选择重启雷电模拟器实例 {instance_index}")
                                restart_success = self.ldplayer_manager.restart_instance(instance_index)
                                if restart_success:
                                    result.message += "，模拟器已重启"
                                else:
                                    result.message += "，模拟器重启失败，请手动重启"
                            else:
                                result.message += "，请手动重启模拟器使设置生效"
                        else:
                            # 没有GUI环境，自动重启
                            logger.info(f"无GUI环境，自动重启雷电模拟器实例 {instance_index}")
                            restart_success = self.ldplayer_manager.restart_instance(instance_index)
                            if restart_success:
                                result.message += "，模拟器已自动重启"
                            else:
                                result.message += "，模拟器自动重启失败，请手动重启"
                    except Exception as e:
                        logger.debug(f"显示重启对话框失败: {e}")
                        # 对话框失败时自动重启
                        logger.info(f"对话框失败，自动重启雷电模拟器实例 {instance_index}")
                        restart_success = self.ldplayer_manager.restart_instance(instance_index)
                        if restart_success:
                            result.message += "，模拟器已自动重启"
                        else:
                            result.message += "，模拟器自动重启失败，请手动重启"

                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=True,
                    message=result.message,
                    before_size=before_size,
                    after_size=(target_width, target_height),
                    adjustment_time=time.time() - start_time
                )
            else:
                logger.error(f"雷电模拟器分辨率调整失败: {result.message}")
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=False,
                    message=result.message,
                    before_size=before_size,
                    after_size=before_size,
                    adjustment_time=time.time() - start_time
                )

        except Exception as e:
            logger.error(f"调整雷电模拟器窗口失败: {e}")
            return WindowAdjustmentResult(
                hwnd=hwnd,
                title="雷电模拟器",
                success=False,
                message=f"调整失败: {str(e)}",
                adjustment_time=time.time() - start_time
            )

    def _adjust_ldplayer_window_async(self, hwnd: int, target_width: int, target_height: int, start_time: float) -> WindowAdjustmentResult:
        """异步调整雷电模拟器窗口分辨率"""
        try:
            import win32gui
            window_title = win32gui.GetWindowText(hwnd)

            if not self.ldplayer_manager:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=False,
                    message="雷电模拟器分辨率管理器不可用",
                    adjustment_time=time.time() - start_time
                )

            # 获取实例信息
            instance = self.ldplayer_manager.get_instance_by_hwnd(hwnd)
            if not instance:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=False,
                    message="无法找到对应的雷电模拟器实例",
                    adjustment_time=time.time() - start_time
                )

            instance_index = instance['index']
            logger.info(f"异步调整雷电模拟器实例: 索引={instance_index}, 标题={instance['title']}")

            # 获取当前窗口状态
            current_state = self.adapter.get_window_state(hwnd, force_refresh=True)
            before_size = (current_state.width, current_state.height) if current_state else (0, 0)

            # 检查是否已经是目标分辨率
            if current_state and current_state.width == target_width and current_state.height == target_height:
                return WindowAdjustmentResult(
                    hwnd=hwnd,
                    title=window_title,
                    success=True,
                    message="分辨率已符合要求，无需调整",
                    before_size=before_size,
                    after_size=before_size,
                    adjustment_time=time.time() - start_time
                )

            # 使用异步方法调整分辨率和DPI
            target_dpi = 180

            def on_adjustment_complete(result):
                """调整完成回调"""
                try:
                    if result.success:
                        logger.info(f"雷电模拟器异步调整成功: {result.message}")

                        # 检查是否自动重启
                        auto_restart = self._should_auto_restart_ldplayer()
                        if auto_restart:
                            logger.info(f"异步自动重启雷电模拟器实例 {instance_index}")

                            def on_restart_complete(restart_success):
                                if restart_success:
                                    logger.info(f"雷电模拟器实例 {instance_index} 异步重启成功")
                                else:
                                    logger.warning(f"雷电模拟器实例 {instance_index} 异步重启失败")

                            # 异步重启
                            self.ldplayer_manager.restart_instance_async(instance_index, on_restart_complete)
                    else:
                        logger.error(f"雷电模拟器异步调整失败: {result.message}")
                except Exception as e:
                    logger.error(f"调整完成回调异常: {e}")

            # 启动异步调整
            future = self.ldplayer_manager.modify_resolution_and_dpi_async(
                instance_index, target_width, target_height, target_dpi, on_adjustment_complete
            )

            # 立即返回成功结果，实际调整在后台进行
            return WindowAdjustmentResult(
                hwnd=hwnd,
                title=window_title,
                success=True,
                message="雷电模拟器分辨率调整已在后台进行，请稍候...",
                before_size=before_size,
                after_size=(target_width, target_height),
                adjustment_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"异步调整雷电模拟器窗口失败: {e}")
            return WindowAdjustmentResult(
                hwnd=hwnd,
                title="雷电模拟器",
                success=False,
                message=f"异步调整失败: {str(e)}",
                adjustment_time=time.time() - start_time
            )

# 全局实例
_window_manager = None

def get_universal_window_manager() -> UniversalWindowManager:
    """获取全局通用窗口管理器实例"""
    global _window_manager
    if _window_manager is None:
        _window_manager = UniversalWindowManager()
    return _window_manager
