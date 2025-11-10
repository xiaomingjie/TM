"""
统一DPI处理器 - 简化所有DPI相关操作
提供统一的DPI检测、坐标转换和区域调整功能
"""

import time
import logging
import ctypes
from typing import Dict, Tuple, Any, Optional, Callable
from ctypes import wintypes
import threading

logger = logging.getLogger(__name__)

class UnifiedDPIHandler:
    """统一DPI处理器 - 简化所有DPI相关操作"""
    
    def __init__(self):
        self._dpi_cache = {}  # 缓存窗口DPI信息
        self._last_check_time = {}  # 最后检查时间
        self._cache_timeout = 0.1  # 缓存超时时间（秒）- 极短以便立即检测DPI变化
        self._lock = threading.RLock()

        # DPI变化检测
        self._dpi_history = {}  # 窗口DPI历史记录
        self._change_callbacks = []  # DPI变化回调函数
        self._monitoring_enabled = True

        # Windows API
        self.user32 = ctypes.windll.user32
        self.shcore = None

        # 尝试加载shcore.dll（Windows 8.1+）
        try:
            self.shcore = ctypes.windll.shcore
            logger.debug("成功加载shcore.dll，支持高级DPI功能")
        except Exception:
            logger.debug("未能加载shcore.dll，使用基础DPI功能")

        logger.info("统一DPI处理器初始化完成")
    
    def get_window_dpi_info(self, hwnd: int, check_changes: bool = True) -> Dict[str, Any]:
        """获取窗口DPI信息（带缓存和变化检测）"""
        if not hwnd:
            logger.warning("窗口句柄为空，返回默认DPI信息")
            return self._get_default_dpi_info()

        current_time = time.time()

        with self._lock:
            # 检查缓存（5秒内有效）
            if (hwnd in self._dpi_cache and
                current_time - self._last_check_time.get(hwnd, 0) < self._cache_timeout):
                return self._dpi_cache[hwnd]

            # 获取新的DPI信息
            dpi_info = self._get_dpi_info_direct(hwnd)

            # 检查DPI变化
            if check_changes and self._monitoring_enabled:
                self._check_dpi_change(hwnd, dpi_info)

            # 更新缓存
            self._dpi_cache[hwnd] = dpi_info
            self._last_check_time[hwnd] = current_time

            return dpi_info
    
    def _get_dpi_info_direct(self, hwnd: int) -> Dict[str, Any]:
        """直接获取窗口DPI信息，优先使用Qt检测"""
        try:
            # 方法1：优先使用Qt设备像素比（最准确）
            try:
                qt_dpi_info = self._get_qt_dpi_info()
                logger.info(f"Qt DPI检测: {qt_dpi_info['dpi']} DPI (缩放: {qt_dpi_info['scale_factor']:.2f})")
                return qt_dpi_info
            except Exception as e:
                logger.debug(f"Qt DPI检测失败: {e}")

            # 方法2：使用系统DPI（屏幕级别）
            try:
                hdc = self.user32.GetDC(0)  # 获取屏幕DC而不是窗口DC
                if hdc:
                    gdi32 = ctypes.windll.gdi32
                    dpi_x = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                    self.user32.ReleaseDC(0, hdc)

                    if dpi_x > 0:
                        scale_factor = dpi_x / 96.0
                        logger.info(f"系统DPI检测: {dpi_x} DPI (缩放: {scale_factor:.2f})")
                        return {
                            'dpi': dpi_x,
                            'scale_factor': scale_factor,
                            'method': 'SystemDPI',
                            'is_high_dpi': scale_factor > 1.0
                        }
            except Exception as e:
                logger.debug(f"系统DPI检测失败: {e}")

            # 方法3：使用GetDpiForWindow（可能不准确）
            if hasattr(self.user32, 'GetDpiForWindow'):
                try:
                    dpi = self.user32.GetDpiForWindow(hwnd)
                    if dpi > 0:
                        scale_factor = dpi / 96.0
                        logger.warning(f"窗口DPI检测（可能不准确）: {dpi} DPI (缩放: {scale_factor:.2f})")
                        return {
                            'dpi': dpi,
                            'scale_factor': scale_factor,
                            'method': 'GetDpiForWindow',
                            'is_high_dpi': scale_factor > 1.0
                        }
                except Exception as e:
                    logger.debug(f"GetDpiForWindow失败: {e}")

            # 方法4：使用窗口GetDeviceCaps（备用）
            try:
                hdc = self.user32.GetDC(hwnd)
                if hdc:
                    gdi32 = ctypes.windll.gdi32
                    dpi_x = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                    self.user32.ReleaseDC(hwnd, hdc)

                    if dpi_x > 0:
                        scale_factor = dpi_x / 96.0
                        logger.debug(f"窗口 {hwnd} DPI (GetDeviceCaps): {dpi_x} (缩放: {scale_factor:.2f})")
                        return {
                            'dpi': dpi_x,
                            'scale_factor': scale_factor,
                            'method': 'GetDeviceCaps',
                            'is_high_dpi': scale_factor > 1.0
                        }
            except Exception as e:
                logger.debug(f"GetDeviceCaps失败: {e}")

            # 方法5：系统默认DPI
            logger.debug(f"窗口 {hwnd} 使用系统默认DPI")
            return self._get_system_dpi_info()

        except Exception as e:
            logger.error(f"获取窗口 {hwnd} DPI信息失败: {e}")
            return self._get_default_dpi_info()
    
    def _get_system_dpi_info(self) -> Dict[str, Any]:
        """获取系统DPI信息"""
        try:
            # 获取系统DPI
            hdc = self.user32.GetDC(0)  # 桌面DC
            if hdc:
                gdi32 = ctypes.windll.gdi32
                dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                self.user32.ReleaseDC(0, hdc)
                
                if dpi > 0:
                    scale_factor = dpi / 96.0
                    return {
                        'dpi': dpi,
                        'scale_factor': scale_factor,
                        'method': 'SystemDPI',
                        'is_high_dpi': scale_factor > 1.0
                    }
        except Exception as e:
            logger.debug(f"获取系统DPI失败: {e}")
        
        return self._get_default_dpi_info()
    
    def _get_qt_dpi_info(self) -> Dict[str, Any]:
        """获取Qt设备像素比信息"""
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                # 如果没有QApplication实例，尝试创建一个临时的
                logger.debug("创建临时QApplication实例用于DPI检测")
                app = QApplication([])

            screen = app.primaryScreen()
            if screen:
                device_pixel_ratio = screen.devicePixelRatio()
                logical_dpi = screen.logicalDotsPerInch()

                # 计算实际DPI
                actual_dpi = int(logical_dpi * device_pixel_ratio)

                logger.debug(f"Qt DPI检测: 设备像素比={device_pixel_ratio}, 逻辑DPI={logical_dpi}, 实际DPI={actual_dpi}")

                return {
                    'dpi': actual_dpi,
                    'scale_factor': device_pixel_ratio,
                    'method': 'QtDevicePixelRatio',
                    'is_high_dpi': device_pixel_ratio > 1.0
                }
            else:
                logger.warning("无法获取Qt屏幕信息")
                return self._get_default_dpi_info()

        except Exception as e:
            logger.debug(f"Qt DPI检测失败: {e}")
            return self._get_default_dpi_info()

    def _get_default_dpi_info(self) -> Dict[str, Any]:
        """获取默认DPI信息"""
        return {
            'dpi': 96,
            'scale_factor': 1.0,
            'method': 'Default',
            'is_high_dpi': False
        }
    
    def adjust_coordinates(self, hwnd: int, x: int, y: int, 
                          coord_type: str = "client") -> Tuple[int, int]:
        """统一的坐标调整方法"""
        try:
            dpi_info = self.get_window_dpi_info(hwnd)
            scale_factor = dpi_info.get('scale_factor', 1.0)
            
            # 如果缩放因子接近1.0，无需调整
            if abs(scale_factor - 1.0) < 0.01:
                return x, y
            
            if coord_type == "client":
                # 客户区坐标：通常保持逻辑坐标
                # 在高DPI环境下，客户区坐标通常已经是逻辑坐标
                return x, y
            elif coord_type == "screen":
                # 屏幕坐标：可能需要转换为逻辑坐标
                # 这取决于具体的使用场景和API
                adjusted_x = int(x / scale_factor)
                adjusted_y = int(y / scale_factor)
                logger.debug(f"屏幕坐标调整: ({x}, {y}) -> ({adjusted_x}, {adjusted_y}), 缩放: {scale_factor:.2f}")
                return adjusted_x, adjusted_y
            elif coord_type == "physical":
                # 物理坐标：转换为逻辑坐标
                adjusted_x = int(x / scale_factor)
                adjusted_y = int(y / scale_factor)
                logger.debug(f"物理坐标调整: ({x}, {y}) -> ({adjusted_x}, {adjusted_y}), 缩放: {scale_factor:.2f}")
                return adjusted_x, adjusted_y
            else:
                logger.warning(f"未知的坐标类型: {coord_type}，不进行调整")
                return x, y
                
        except Exception as e:
            logger.error(f"坐标调整失败: {e}")
            return x, y
    
    def adjust_region(self, hwnd: int, x: int, y: int, width: int, height: int,
                     region_type: str = "ocr") -> Tuple[int, int, int, int]:
        """统一的区域调整方法"""
        try:
            dpi_info = self.get_window_dpi_info(hwnd)
            scale_factor = dpi_info.get('scale_factor', 1.0)
            
            # 如果缩放因子接近1.0，无需调整
            if abs(scale_factor - 1.0) < 0.01:
                return x, y, width, height
            
            if region_type == "ocr":
                # OCR区域：通常需要物理像素
                adjusted_x = int(x * scale_factor)
                adjusted_y = int(y * scale_factor)
                adjusted_width = int(width * scale_factor)
                adjusted_height = int(height * scale_factor)
                
                logger.debug(f"OCR区域调整: ({x}, {y}, {width}, {height}) -> "
                           f"({adjusted_x}, {adjusted_y}, {adjusted_width}, {adjusted_height}), "
                           f"缩放: {scale_factor:.2f}")
                
                return adjusted_x, adjusted_y, adjusted_width, adjusted_height
            
            elif region_type == "logical":
                # 逻辑区域：保持逻辑像素
                return x, y, width, height
            
            elif region_type == "capture":
                # 截图区域：可能需要物理像素
                adjusted_x = int(x * scale_factor)
                adjusted_y = int(y * scale_factor)
                adjusted_width = int(width * scale_factor)
                adjusted_height = int(height * scale_factor)
                
                return adjusted_x, adjusted_y, adjusted_width, adjusted_height
            
            else:
                logger.warning(f"未知的区域类型: {region_type}，不进行调整")
                return x, y, width, height
                
        except Exception as e:
            logger.error(f"区域调整失败: {e}")
            return x, y, width, height
    
    def is_high_dpi_window(self, hwnd: int) -> bool:
        """检查窗口是否为高DPI"""
        try:
            dpi_info = self.get_window_dpi_info(hwnd)
            return dpi_info.get('is_high_dpi', False)
        except Exception:
            return False
    
    def get_scale_factor(self, hwnd: int) -> float:
        """获取窗口缩放因子"""
        try:
            dpi_info = self.get_window_dpi_info(hwnd)
            return dpi_info.get('scale_factor', 1.0)
        except Exception:
            return 1.0
    
    def clear_cache(self, hwnd: Optional[int] = None):
        """清理DPI缓存"""
        with self._lock:
            if hwnd is None:
                # 清理所有缓存
                self._dpi_cache.clear()
                self._last_check_time.clear()
                logger.debug("已清理所有DPI缓存")
            else:
                # 清理特定窗口缓存
                self._dpi_cache.pop(hwnd, None)
                self._last_check_time.pop(hwnd, None)
                logger.debug(f"已清理窗口 {hwnd} 的DPI缓存")
    
    def enable_monitoring(self, enabled: bool = True):
        """启用或禁用DPI监控"""
        with self._lock:
            self._monitoring_enabled = enabled
            if enabled:
                logger.info("DPI监控已启用")
            else:
                logger.info("DPI监控已禁用")

    def disable_monitoring(self):
        """禁用DPI监控"""
        self.enable_monitoring(False)

    def add_dpi_change_callback(self, callback: Callable):
        """添加DPI变化回调函数"""
        with self._lock:
            if callback not in self._change_callbacks:
                self._change_callbacks.append(callback)
                logger.debug(f"添加DPI变化回调函数: {callback.__name__}")

    def remove_dpi_change_callback(self, callback: Callable):
        """移除DPI变化回调函数"""
        with self._lock:
            if callback in self._change_callbacks:
                self._change_callbacks.remove(callback)
                logger.debug(f"移除DPI变化回调函数: {callback.__name__}")

    def force_check_all_windows(self, windows_list=None):
        """强制检查所有缓存窗口的DPI变化

        Args:
            windows_list: 可选的窗口列表，格式为 [{'hwnd': int, 'title': str}, ...]
                         如果为None，则检查所有缓存的窗口
        """
        try:
            with self._lock:
                if not self._monitoring_enabled:
                    logger.debug("DPI监控未启用，跳过强制检查")
                    return {}

                # 确定要检查的窗口句柄列表
                if windows_list is not None:
                    # 使用提供的窗口列表
                    check_hwnds = []
                    for window in windows_list:
                        if isinstance(window, dict) and 'hwnd' in window:
                            check_hwnds.append(window['hwnd'])
                        elif isinstance(window, int):
                            check_hwnds.append(window)
                    logger.debug(f"使用提供的窗口列表，共 {len(check_hwnds)} 个窗口")
                else:
                    # 使用缓存的窗口句柄
                    check_hwnds = list(self._dpi_cache.keys())
                    logger.debug(f"使用缓存的窗口列表，共 {len(check_hwnds)} 个窗口")

                if not check_hwnds:
                    logger.debug("没有窗口需要检查，跳过DPI检查")
                    return {}

                logger.debug(f"强制检查 {len(check_hwnds)} 个窗口的DPI变化")

                results = {}
                for hwnd in check_hwnds:
                    try:
                        # 强制重新检测DPI（不使用缓存）
                        old_dpi_info = self._dpi_cache.get(hwnd)
                        new_dpi_info = self._get_dpi_info_direct(hwnd)

                        # 检查是否有变化
                        if old_dpi_info and new_dpi_info:
                            old_dpi = old_dpi_info.get('dpi', 96)
                            new_dpi = new_dpi_info.get('dpi', 96)

                            if abs(old_dpi - new_dpi) > 1:
                                logger.info(f"检测到窗口 {hwnd} DPI变化: {old_dpi} -> {new_dpi}")

                                # 更新缓存
                                self._dpi_cache[hwnd] = new_dpi_info
                                self._last_check_time[hwnd] = time.time()

                                # 触发变化检测
                                self._check_dpi_change(hwnd, new_dpi_info)
                                results[hwnd] = True
                            else:
                                # 更新检查时间但保持DPI信息不变
                                self._last_check_time[hwnd] = time.time()
                                results[hwnd] = False
                        else:
                            # 新窗口或检测失败
                            if new_dpi_info:
                                self._dpi_cache[hwnd] = new_dpi_info
                                self._last_check_time[hwnd] = time.time()
                            results[hwnd] = False

                    except Exception as e:
                        logger.debug(f"检查窗口 {hwnd} DPI失败: {e}")
                        results[hwnd] = False

                return results

        except Exception as e:
            logger.error(f"强制检查所有窗口DPI失败: {e}")
            return {}

    def cleanup(self):
        """清理资源"""
        with self._lock:
            self._dpi_cache.clear()
            self._last_check_time.clear()
            self._dpi_history.clear()
            self._change_callbacks.clear()
            self._monitoring_enabled = False
        logger.info("统一DPI处理器资源清理完成")

    def _check_dpi_change(self, hwnd: int, new_dpi_info: Dict[str, Any]):
        """检查DPI变化并触发回调"""
        try:
            if hwnd not in self._dpi_history:
                # 首次记录
                self._dpi_history[hwnd] = new_dpi_info
                logger.debug(f"首次记录窗口 {hwnd} DPI: {new_dpi_info['dpi']}")
                return

            old_dpi_info = self._dpi_history[hwnd]
            old_dpi = old_dpi_info.get('dpi', 96)
            new_dpi = new_dpi_info.get('dpi', 96)

            # 检查DPI是否发生显著变化
            if abs(old_dpi - new_dpi) > 1:
                logger.info(f"搜索 [DPI变化] 检测到窗口 {hwnd} DPI变化: {old_dpi} -> {new_dpi}")

                # 更新历史记录
                self._dpi_history[hwnd] = new_dpi_info

                # 清除所有DPI缓存，强制重新检测
                self.clear_all_cache()
                logger.info(f"已清除所有DPI缓存，强制重新检测")

                # 触发所有回调函数
                for callback in self._change_callbacks:
                    try:
                        callback(hwnd, old_dpi_info, new_dpi_info)
                    except Exception as e:
                        logger.error(f"DPI变化回调函数执行失败: {e}")

        except Exception as e:
            logger.error(f"检查DPI变化失败: {e}")

    def clear_all_cache(self):
        """清除所有DPI缓存"""
        with self._lock:
            self._dpi_cache.clear()
            self._last_check_time.clear()
            logger.debug("已清除所有DPI缓存")

    def force_refresh_dpi(self, hwnd: int = None):
        """强制刷新指定窗口或所有窗口的DPI信息"""
        with self._lock:
            if hwnd:
                # 刷新指定窗口
                if hwnd in self._dpi_cache:
                    del self._dpi_cache[hwnd]
                if hwnd in self._last_check_time:
                    del self._last_check_time[hwnd]
                logger.debug(f"已强制刷新窗口 {hwnd} 的DPI缓存")
            else:
                # 刷新所有窗口
                self.clear_all_cache()
                logger.debug("已强制刷新所有窗口的DPI缓存")


# 全局实例
_unified_dpi_handler = None
_handler_lock = threading.Lock()

def get_unified_dpi_handler() -> UnifiedDPIHandler:
    """获取统一DPI处理器的全局实例"""
    global _unified_dpi_handler
    
    with _handler_lock:
        if _unified_dpi_handler is None:
            _unified_dpi_handler = UnifiedDPIHandler()
        return _unified_dpi_handler

def cleanup_unified_dpi_handler():
    """清理统一DPI处理器"""
    global _unified_dpi_handler
    
    with _handler_lock:
        if _unified_dpi_handler is not None:
            _unified_dpi_handler.cleanup()
            _unified_dpi_handler = None
