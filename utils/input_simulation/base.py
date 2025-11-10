"""
输入模拟基础接口模块
定义键盘鼠标模拟的统一接口
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BaseInputSimulator(ABC):
    """输入模拟器基础接口"""
    
    def __init__(self, hwnd: int):
        """
        初始化输入模拟器
        
        Args:
            hwnd: 目标窗口句柄
        """
        self.hwnd = hwnd
        self.logger = logger
    
    @abstractmethod
    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """
        鼠标点击
        
        Args:
            x: X坐标
            y: Y坐标
            button: 鼠标按钮 ('left', 'right', 'middle')
            clicks: 点击次数
            interval: 点击间隔
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def double_click(self, x: int, y: int, button: str = 'left') -> bool:
        """
        鼠标双击
        
        Args:
            x: X坐标
            y: Y坐标
            button: 鼠标按钮
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
             duration: float = 1.0, button: str = 'left') -> bool:
        """
        鼠标拖拽
        
        Args:
            start_x: 起始X坐标
            start_y: 起始Y坐标
            end_x: 结束X坐标
            end_y: 结束Y坐标
            duration: 拖拽持续时间
            button: 鼠标按钮
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def scroll(self, x: int, y: int, delta: int) -> bool:
        """
        鼠标滚轮
        
        Args:
            x: X坐标
            y: Y坐标
            delta: 滚动量
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """
        发送按键
        
        Args:
            vk_code: 虚拟键码
            scan_code: 扫描码
            extended: 是否为扩展键
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """
        发送按键按下
        
        Args:
            vk_code: 虚拟键码
            scan_code: 扫描码
            extended: 是否为扩展键
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """
        发送按键释放
        
        Args:
            vk_code: 虚拟键码
            scan_code: 扫描码
            extended: 是否为扩展键
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def send_text(self, text: str) -> bool:
        """
        发送文本
        
        Args:
            text: 要发送的文本
            
        Returns:
            bool: 操作是否成功
        """
        pass
    
    @abstractmethod
    def send_key_combination(self, keys: list, hold_duration: float = 0.1) -> bool:
        """
        发送组合键
        
        Args:
            keys: 按键列表
            hold_duration: 按键保持时间
            
        Returns:
            bool: 操作是否成功
        """
        pass


class InputSimulatorType:
    """输入模拟器类型枚举"""
    STANDARD_WINDOW = "standard_window"  # 普通窗口
    EMULATOR_WINDOW = "emulator_window"  # 模拟器窗口
