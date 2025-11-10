"""
统一坐标处理器 - 基于图片识别点击的最佳实践
整合所有坐标相关的DPI处理、转换和验证功能
"""

import time
import logging
import ctypes
from typing import Dict, Tuple, Any, Optional, Union
from ctypes import wintypes
import threading

try:
    import win32gui
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)

class CoordinateType:
    """坐标类型枚举"""
    LOGICAL = "logical"      # 逻辑坐标（UI框选返回的坐标）
    PHYSICAL = "physical"    # 物理坐标（实际像素坐标）
    CLIENT = "client"        # 客户区坐标
    SCREEN = "screen"        # 屏幕坐标

class CoordinateInfo:
    """坐标信息类"""
    def __init__(self, x: int, y: int, width: int = 0, height: int = 0, 
                 coord_type: str = CoordinateType.LOGICAL, source: str = "unknown"):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.coord_type = coord_type
        self.source = source  # 坐标来源：ocr_selector, coordinate_selector, image_click等

class UnifiedCoordinateProcessor:
    """统一坐标处理器 - 基于图片识别点击的最佳实践"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self.user32 = ctypes.windll.user32
        
        # 导入统一DPI处理器
        from utils.unified_dpi_handler import get_unified_dpi_handler
        self.dpi_handler = get_unified_dpi_handler()
        
        logger.info("统一坐标处理器初始化完成")
    
    def process_coordinates_for_click(self, coord_info: CoordinateInfo, target_hwnd: int, 
                                    execution_mode: str = 'background') -> Tuple[int, int]:
        """
        处理坐标用于点击操作（基于图片识别点击的最佳实践）
        
        Args:
            coord_info: 坐标信息
            target_hwnd: 目标窗口句柄
            execution_mode: 执行模式 ('foreground' 或 'background')
            
        Returns:
            Tuple[int, int]: 处理后的坐标
        """
        try:
            with self._lock:
                logger.info(f"工具 [统一坐标处理] 开始处理坐标: ({coord_info.x}, {coord_info.y})")
                logger.info(f"   坐标类型: {coord_info.coord_type}, 来源: {coord_info.source}")
                logger.info(f"   目标窗口: {target_hwnd}, 执行模式: {execution_mode}")
                
                # 1. 根据坐标来源确定正确的处理方式
                processed_x, processed_y = self._determine_coordinate_processing(coord_info, target_hwnd)
                
                # 2. 应用DPI调整（统一使用physical类型，确保一致性）
                dpi_adjusted_x, dpi_adjusted_y = self.dpi_handler.adjust_coordinates(
                    target_hwnd, processed_x, processed_y, "physical"
                )
                
                logger.info(f"工具 [DPI调整] 坐标调整: ({processed_x}, {processed_y}) -> ({dpi_adjusted_x}, {dpi_adjusted_y})")
                
                # 3. 前台模式需要额外的坐标转换
                if execution_mode == 'foreground':
                    final_x, final_y = self._convert_to_screen_coordinates(
                        dpi_adjusted_x, dpi_adjusted_y, target_hwnd
                    )
                    logger.info(f" [前台转换] 客户区到屏幕: ({dpi_adjusted_x}, {dpi_adjusted_y}) -> ({final_x}, {final_y})")
                else:
                    final_x, final_y = dpi_adjusted_x, dpi_adjusted_y
                
                # 4. 执行坐标验证和诊断
                self._diagnose_coordinates(coord_info, final_x, final_y, target_hwnd, execution_mode)
                
                return final_x, final_y
                
        except Exception as e:
            logger.error(f"坐标处理失败: {e}")
            return coord_info.x, coord_info.y
    
    def process_region_for_ocr(self, coord_info: CoordinateInfo, target_hwnd: int) -> Tuple[int, int, int, int]:
        """
        处理区域坐标用于OCR操作
        
        Args:
            coord_info: 坐标信息
            target_hwnd: 目标窗口句柄
            
        Returns:
            Tuple[int, int, int, int]: 处理后的区域坐标 (x, y, width, height)
        """
        try:
            with self._lock:
                logger.info(f"工具 [OCR区域处理] 开始处理区域: ({coord_info.x}, {coord_info.y}, {coord_info.width}, {coord_info.height})")
                logger.info(f"   坐标类型: {coord_info.coord_type}, 来源: {coord_info.source}")
                
                # 根据坐标来源确定处理方式
                if coord_info.source == "ocr_selector":
                    # OCR选择器现在返回的已经是物理坐标，无需额外转换
                    region_type = "logical"  # 保持物理坐标不变
                else:
                    # 其他来源，保持逻辑坐标
                    region_type = "logical"
                
                # 应用DPI调整
                final_x, final_y, final_width, final_height = self.dpi_handler.adjust_region(
                    target_hwnd, coord_info.x, coord_info.y, coord_info.width, coord_info.height, region_type
                )
                
                logger.info(f"工具 [OCR区域调整] 区域调整: ({coord_info.x}, {coord_info.y}, {coord_info.width}, {coord_info.height}) -> "
                          f"({final_x}, {final_y}, {final_width}, {final_height})")
                
                return final_x, final_y, final_width, final_height
                
        except Exception as e:
            logger.error(f"OCR区域处理失败: {e}")
            return coord_info.x, coord_info.y, coord_info.width, coord_info.height
    
    def _determine_coordinate_processing(self, coord_info: CoordinateInfo, target_hwnd: int) -> Tuple[int, int]:
        """根据坐标来源确定正确的处理方式"""
        
        if coord_info.source == "ocr_selector":
            # OCR选择器现在返回的已经是物理坐标，直接使用
            logger.debug(f"OCR选择器坐标: 物理({coord_info.x}, {coord_info.y})")
            return coord_info.x, coord_info.y
            
        elif coord_info.source == "coordinate_selector":
            # 坐标选择器返回物理坐标，直接使用
            logger.debug(f"坐标选择器坐标: 物理({coord_info.x}, {coord_info.y})")
            return coord_info.x, coord_info.y
            
        elif coord_info.source == "image_click":
            # 图片识别返回物理坐标，直接使用
            logger.debug(f"图片识别坐标: 物理({coord_info.x}, {coord_info.y})")
            return coord_info.x, coord_info.y
            
        else:
            # 未知来源，根据坐标类型处理
            if coord_info.coord_type == CoordinateType.LOGICAL:
                scale_factor = self.dpi_handler.get_scale_factor(target_hwnd)
                physical_x = int(coord_info.x * scale_factor)
                physical_y = int(coord_info.y * scale_factor)
                logger.debug(f"未知来源逻辑坐标转换: ({coord_info.x}, {coord_info.y}) -> ({physical_x}, {physical_y})")
                return physical_x, physical_y
            else:
                logger.debug(f"未知来源物理坐标: ({coord_info.x}, {coord_info.y})")
                return coord_info.x, coord_info.y
    
    def _convert_to_screen_coordinates(self, client_x: int, client_y: int, target_hwnd: int) -> Tuple[int, int]:
        """将客户区坐标转换为屏幕坐标（基于图片识别点击的实现）"""
        try:
            # 使用Windows API进行精确坐标转换
            point = wintypes.POINT(int(client_x), int(client_y))
            result = self.user32.ClientToScreen(target_hwnd, ctypes.byref(point))
            
            if result:
                screen_x, screen_y = point.x, point.y
                logger.debug(f"API坐标转换成功: 客户区({client_x}, {client_y}) -> 屏幕({screen_x}, {screen_y})")
                return screen_x, screen_y
            else:
                # API失败时的备用计算方法
                logger.warning("ClientToScreen API失败，使用备用方法")
                return self._fallback_coordinate_conversion(client_x, client_y, target_hwnd)
                
        except Exception as e:
            logger.error(f"坐标转换失败: {e}")
            return client_x, client_y
    
    def _fallback_coordinate_conversion(self, client_x: int, client_y: int, target_hwnd: int) -> Tuple[int, int]:
        """备用坐标转换方法"""
        try:
            if not PYWIN32_AVAILABLE:
                return client_x, client_y
                
            window_rect = win32gui.GetWindowRect(target_hwnd)
            client_rect = win32gui.GetClientRect(target_hwnd)
            
            window_width = window_rect[2] - window_rect[0]
            window_height = window_rect[3] - window_rect[1]
            client_width = client_rect[2] - client_rect[0]
            client_height = client_rect[3] - client_rect[1]
            
            border_x = (window_width - client_width) // 2
            title_height = window_height - client_height - border_x
            
            screen_x = window_rect[0] + border_x + client_x
            screen_y = window_rect[1] + title_height + client_y
            
            logger.debug(f"备用坐标转换: 客户区({client_x}, {client_y}) -> 屏幕({screen_x}, {screen_y})")
            return screen_x, screen_y
            
        except Exception as e:
            logger.error(f"备用坐标转换失败: {e}")
            return client_x, client_y
    
    def _diagnose_coordinates(self, coord_info: CoordinateInfo, final_x: int, final_y: int, 
                            target_hwnd: int, execution_mode: str):
        """坐标诊断和验证（基于图片识别点击的诊断功能）"""
        try:
            logger.info("搜索 ===== 坐标诊断开始 =====")
            
            # 1. 基本信息
            logger.info(f"列表 原始坐标: ({coord_info.x}, {coord_info.y}), 类型: {coord_info.coord_type}, 来源: {coord_info.source}")
            logger.info(f"列表 最终坐标: ({final_x}, {final_y}), 执行模式: {execution_mode}")
            
            if not PYWIN32_AVAILABLE or not target_hwnd:
                logger.warning("警告 缺少pywin32或窗口句柄，跳过详细诊断")
                return
            
            # 2. 窗口信息
            try:
                window_title = win32gui.GetWindowText(target_hwnd)
                window_rect = win32gui.GetWindowRect(target_hwnd)
                client_rect = win32gui.GetClientRect(target_hwnd)
                
                logger.info(f"窗户 窗口信息: '{window_title}' (HWND: {target_hwnd})")
                logger.info(f"   窗口矩形: {window_rect}")
                logger.info(f"   客户区矩形: {client_rect}")
                
            except Exception as e:
                logger.warning(f"获取窗口信息失败: {e}")
            
            # 3. DPI信息
            dpi_info = self.dpi_handler.get_window_dpi_info(target_hwnd)
            logger.info(f"搜索 DPI信息: {dpi_info['dpi']} (缩放: {dpi_info['scale_factor']:.2f}x)")
            
            logger.info("搜索 ===== 坐标诊断结束 =====")
            
        except Exception as e:
            logger.error(f"坐标诊断失败: {e}")


# 全局实例
_unified_coordinate_processor = None
_processor_lock = threading.Lock()

def get_unified_coordinate_processor() -> UnifiedCoordinateProcessor:
    """获取统一坐标处理器的全局实例"""
    global _unified_coordinate_processor
    
    with _processor_lock:
        if _unified_coordinate_processor is None:
            _unified_coordinate_processor = UnifiedCoordinateProcessor()
        return _unified_coordinate_processor

def cleanup_unified_coordinate_processor():
    """清理统一坐标处理器"""
    global _unified_coordinate_processor

    with _processor_lock:
        if _unified_coordinate_processor is not None:
            _unified_coordinate_processor = None
            logger.info("统一坐标处理器已清理")


# ===== 使用示例和便捷函数 =====

def create_coordinate_info_from_ocr_selector(x: int, y: int, width: int = 0, height: int = 0) -> CoordinateInfo:
    """从OCR选择器创建坐标信息"""
    return CoordinateInfo(x, y, width, height, CoordinateType.LOGICAL, "ocr_selector")

def create_coordinate_info_from_coordinate_selector(x: int, y: int) -> CoordinateInfo:
    """从坐标选择器创建坐标信息"""
    return CoordinateInfo(x, y, 0, 0, CoordinateType.PHYSICAL, "coordinate_selector")

def create_coordinate_info_from_image_click(x: int, y: int) -> CoordinateInfo:
    """从图片识别创建坐标信息"""
    return CoordinateInfo(x, y, 0, 0, CoordinateType.PHYSICAL, "image_click")

def create_coordinate_info_from_user_input(x: int, y: int, coord_mode: str = "客户区坐标") -> CoordinateInfo:
    """从用户输入创建坐标信息"""
    # 根据坐标模式确定类型
    if coord_mode == "客户区坐标":
        # 用户输入的客户区坐标通常是物理坐标
        return CoordinateInfo(x, y, 0, 0, CoordinateType.PHYSICAL, "user_input_client")
    else:
        # 屏幕坐标
        return CoordinateInfo(x, y, 0, 0, CoordinateType.PHYSICAL, "user_input_screen")


# ===== 任务集成示例 =====

def example_ocr_task_integration():
    """OCR任务集成示例"""
    # 模拟OCR选择器返回的坐标
    ocr_x, ocr_y, ocr_width, ocr_height = 100, 100, 200, 50
    target_hwnd = 12345

    # 创建坐标信息
    coord_info = create_coordinate_info_from_ocr_selector(ocr_x, ocr_y, ocr_width, ocr_height)

    # 获取处理器
    processor = get_unified_coordinate_processor()

    # 处理OCR区域
    final_x, final_y, final_width, final_height = processor.process_region_for_ocr(coord_info, target_hwnd)

    logger.info(f"OCR任务: 原始({ocr_x}, {ocr_y}, {ocr_width}, {ocr_height}) -> "
               f"最终({final_x}, {final_y}, {final_width}, {final_height})")

def example_coordinate_click_integration():
    """坐标点击任务集成示例"""
    # 模拟坐标选择器返回的坐标
    click_x, click_y = 150, 200
    target_hwnd = 12345
    execution_mode = 'background'

    # 创建坐标信息
    coord_info = create_coordinate_info_from_coordinate_selector(click_x, click_y)

    # 获取处理器
    processor = get_unified_coordinate_processor()

    # 处理点击坐标
    final_x, final_y = processor.process_coordinates_for_click(coord_info, target_hwnd, execution_mode)

    logger.info(f"坐标点击任务: 原始({click_x}, {click_y}) -> 最终({final_x}, {final_y})")

def example_image_click_integration():
    """图片识别点击任务集成示例"""
    # 模拟图片识别返回的坐标
    image_x, image_y = 300, 400
    target_hwnd = 12345
    execution_mode = 'foreground'

    # 创建坐标信息
    coord_info = create_coordinate_info_from_image_click(image_x, image_y)

    # 获取处理器
    processor = get_unified_coordinate_processor()

    # 处理点击坐标
    final_x, final_y = processor.process_coordinates_for_click(coord_info, target_hwnd, execution_mode)

    logger.info(f"图片点击任务: 原始({image_x}, {image_y}) -> 最终({final_x}, {final_y})")
