"""
输入模拟器工厂类
根据配置和窗口类型创建合适的输入模拟器
"""

import win32gui
import logging
from typing import Optional
from .base import BaseInputSimulator, InputSimulatorType
from .standard_window import StandardWindowInputSimulator
from .emulator_window import EmulatorWindowInputSimulator

logger = logging.getLogger(__name__)


class InputSimulatorFactory:
    """输入模拟器工厂类"""
    
    @staticmethod
    def create_simulator(hwnd: int, operation_mode: str = "auto", 
                        execution_mode: str = "background") -> Optional[BaseInputSimulator]:
        """
        创建输入模拟器

        Args:
            hwnd: 窗口句柄
            operation_mode: 操作模式 ("standard_window", "emulator_window", "auto")
            execution_mode: 执行模式 (支持: "foreground", "foreground_*", "background", "background_*", "emulator_*")

        Returns:
            BaseInputSimulator: 输入模拟器实例
        """
        try:
            # 自动检测模式
            if operation_mode == "auto":
                operation_mode = InputSimulatorFactory._detect_window_type(hwnd)
            
            # 根据操作模式创建对应的模拟器
            if operation_mode == InputSimulatorType.STANDARD_WINDOW:
                use_foreground = execution_mode.startswith('foreground') if execution_mode else False
                return StandardWindowInputSimulator(hwnd, use_foreground=use_foreground)
            elif operation_mode == InputSimulatorType.EMULATOR_WINDOW:
                emulator_type = InputSimulatorFactory._detect_emulator_type(hwnd)
                # 模拟器也需要传递execution_mode参数
                return EmulatorWindowInputSimulator(hwnd, emulator_type=emulator_type, execution_mode=execution_mode)
            else:
                logger.warning(f"未知的操作模式: {operation_mode}，使用默认普通窗口模式")
                use_foreground = execution_mode.startswith('foreground') if execution_mode else False
                return StandardWindowInputSimulator(hwnd, use_foreground=use_foreground)
                
        except Exception as e:
            logger.error(f"创建输入模拟器失败: {e}")
            return None
    
    @staticmethod
    def _detect_window_type(hwnd: int) -> str:
        """
        自动检测窗口类型
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            str: 窗口类型
        """
        try:
            window_text = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            
            # 检测模拟器窗口
            emulator_indicators = [
                "雷电", "LDPlayer", "TheRender",
                "MuMu", "NemuPlayer", "nemudisplay", "nemuwin",
                "逍遥", "MEmu",
                "腾讯手游助手", "AndroidEmulator"
            ]
            
            for indicator in emulator_indicators:
                if indicator in window_text or indicator in class_name:
                    logger.debug(f"检测到模拟器窗口: {window_text} ({class_name})")
                    return InputSimulatorType.EMULATOR_WINDOW
            
            # 默认为普通窗口
            logger.debug(f"检测为普通窗口: {window_text} ({class_name})")
            return InputSimulatorType.STANDARD_WINDOW
            
        except Exception as e:
            logger.error(f"检测窗口类型失败: {e}")
            return InputSimulatorType.STANDARD_WINDOW
    
    @staticmethod
    def _detect_emulator_type(hwnd: int) -> str:
        """
        检测具体的模拟器类型

        Args:
            hwnd: 窗口句柄

        Returns:
            str: 模拟器类型
        """
        try:
            # 优先使用统一的模拟器检测器
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            if is_emulator and emulator_type:
                return emulator_type

            # 回退到原有逻辑
            window_text = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)

            # 雷电模拟器
            if any(indicator in window_text or indicator in class_name
                   for indicator in ["雷电", "LDPlayer", "TheRender"]):
                return "ldplayer"

            # MuMu模拟器
            elif any(indicator in window_text or indicator in class_name
                     for indicator in ["MuMu", "NemuPlayer", "MuMu模拟器"]):
                return "mumu"

            # 逍遥模拟器
            elif any(indicator in window_text or indicator in class_name
                     for indicator in ["逍遥", "MEmu"]):
                return "memu"

            # 腾讯手游助手
            elif any(indicator in window_text or indicator in class_name
                     for indicator in ["腾讯手游助手", "AndroidEmulator"]):
                return "tencent"

            else:
                return "unknown"
                
        except Exception as e:
            logger.error(f"检测模拟器类型失败: {e}")
            return "unknown"


class GlobalInputSimulatorManager:
    """全局输入模拟器管理器"""
    
    def __init__(self):
        self._default_operation_mode = "auto"
        self._default_execution_mode = "background"
        self._simulators = {}  # 缓存已创建的模拟器
    
    def set_default_operation_mode(self, mode: str):
        """设置默认操作模式"""
        if mode in [InputSimulatorType.STANDARD_WINDOW, InputSimulatorType.EMULATOR_WINDOW, "auto"]:
            self._default_operation_mode = mode
            # 清除缓存，强制重新创建模拟器
            self._simulators.clear()
            logger.info(f"默认操作模式已设置为: {mode}")
        else:
            logger.warning(f"无效的操作模式: {mode}")
    
    def set_default_execution_mode(self, mode: str):
        """设置默认执行模式"""
        if mode in ["foreground", "background"]:
            self._default_execution_mode = mode
            # 清除缓存，强制重新创建模拟器
            self._simulators.clear()
            logger.info(f"默认执行模式已设置为: {mode}")
        else:
            logger.warning(f"无效的执行模式: {mode}")
    
    def get_simulator(self, hwnd: int, operation_mode: Optional[str] = None, 
                     execution_mode: Optional[str] = None) -> Optional[BaseInputSimulator]:
        """
        获取输入模拟器（带缓存）
        
        Args:
            hwnd: 窗口句柄
            operation_mode: 操作模式，None使用默认值
            execution_mode: 执行模式，None使用默认值
            
        Returns:
            BaseInputSimulator: 输入模拟器实例
        """
        # 使用默认值
        if operation_mode is None:
            operation_mode = self._default_operation_mode
        if execution_mode is None:
            execution_mode = self._default_execution_mode
        
        # 生成缓存键
        cache_key = (hwnd, operation_mode, execution_mode)
        
        # 检查缓存
        if cache_key in self._simulators:
            simulator = self._simulators[cache_key]
            # 验证窗口是否仍然有效
            try:
                if win32gui.IsWindow(hwnd):
                    return simulator
                else:
                    # 窗口已关闭，移除缓存
                    del self._simulators[cache_key]
            except Exception:
                # 窗口验证失败，移除缓存
                del self._simulators[cache_key]
        
        # 创建新的模拟器
        simulator = InputSimulatorFactory.create_simulator(hwnd, operation_mode, execution_mode)
        if simulator:
            self._simulators[cache_key] = simulator
        
        return simulator
    
    def clear_cache(self):
        """清除模拟器缓存"""
        self._simulators.clear()
        logger.info("输入模拟器缓存已清除")
    
    def get_default_operation_mode(self) -> str:
        """获取默认操作模式"""
        return self._default_operation_mode
    
    def get_default_execution_mode(self) -> str:
        """获取默认执行模式"""
        return self._default_execution_mode


# 全局管理器实例
global_input_simulator_manager = GlobalInputSimulatorManager()
