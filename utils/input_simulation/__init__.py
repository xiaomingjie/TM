"""
输入模拟模块
提供统一的键盘鼠标模拟接口，支持普通窗口和模拟器窗口
"""

from .base import BaseInputSimulator, InputSimulatorType
from .standard_window import StandardWindowInputSimulator
from .emulator_window import EmulatorWindowInputSimulator
from .factory import InputSimulatorFactory, GlobalInputSimulatorManager, global_input_simulator_manager

__all__ = [
    'BaseInputSimulator',
    'InputSimulatorType',
    'StandardWindowInputSimulator',
    'EmulatorWindowInputSimulator',
    'InputSimulatorFactory',
    'GlobalInputSimulatorManager',
    'global_input_simulator_manager'
]
