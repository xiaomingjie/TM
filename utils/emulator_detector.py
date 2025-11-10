#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟器检测工具模块
用于检测窗口是否为模拟器窗口，并根据全局设置自动切换输入模式
"""

import logging
import win32gui
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class EmulatorDetector:
    """模拟器检测器"""
    
    def __init__(self):
        # 模拟器检测规则 - 支持雷电模拟器和MuMu模拟器，只检测渲染窗口
        self.emulator_rules = {
            "ldplayer": {
                "render_class_names": ["RenderWindow"],  # 雷电模拟器渲染窗口
                "main_class_names": ["LDPlayerMainFrame"],  # 雷电模拟器主窗口（用于识别但不绑定）
                "window_keywords": ["雷电", "LDPlayer"],
                "description": "雷电模拟器"
            },
            "therender": {
                "render_class_names": ["TheRender"],  # 通用渲染窗口（雷电模拟器的另一种渲染窗口）
                "main_class_names": [],  # 无主窗口
                "window_keywords": ["TheRender"],
                "description": "雷电模拟器"
            },
            "mumu": {
                "render_class_names": ["nemuwin"],  # MuMu模拟器真正的渲染窗口
                "main_class_names": ["Qt5156QWindowIcon", "Qt6QWindowIcon"],  # MuMu模拟器主窗口（用于识别但不绑定）
                "window_keywords": ["MuMu", "MuMu模拟器", "NemuPlayer", "nemudisplay"],
                "description": "MuMu模拟器"
            }
        }
    
    def detect_emulator_type(self, hwnd: int) -> Tuple[bool, Optional[str], str]:
        """
        检测窗口是否为模拟器窗口
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            Tuple[bool, Optional[str], str]: (是否为模拟器, 模拟器类型, 描述)
        """
        try:
            if not hwnd or not win32gui.IsWindow(hwnd):
                return False, None, "无效窗口"
            
            class_name = win32gui.GetClassName(hwnd)
            window_title = win32gui.GetWindowText(hwnd)
            
            logger.debug(f"检测窗口: 句柄={hwnd}, 类名='{class_name}', 标题='{window_title}'")
            
            # 遍历所有模拟器规则
            for emulator_type, rules in self.emulator_rules.items():
                # 特殊处理MuMu模拟器
                if emulator_type == "mumu":
                    # 检测渲染窗口：nemuwin类且标题包含nemudisplay
                    if (class_name == "nemuwin" and
                        "nemudisplay" in window_title.lower()):
                        logger.info(f"检测到MuMu渲染窗口: {class_name} '{window_title}'")
                        return True, emulator_type, rules["description"]

                    # 检测MuMu的TheRender窗口：通过父窗口判断
                    if (class_name == "RenderWindow" and window_title == "TheRender"):
                        # 检查是否有MuMu父窗口
                        if self._has_mumu_parent_window(hwnd):
                            logger.info(f"检测到MuMu的TheRender窗口: {class_name} '{window_title}'")
                            return True, emulator_type, rules["description"]

                    # 检测主窗口：Qt窗口且标题包含mumu关键词
                    if (class_name in rules["main_class_names"] and
                        any(keyword.lower() in window_title.lower() for keyword in ["mumu", "模拟器"])):
                        logger.info(f"检测到MuMu主窗口: {class_name} '{window_title}'")
                        return True, emulator_type, rules["description"]
                else:
                    # 其他模拟器的检测逻辑
                    # 1. 检查渲染窗口类名匹配
                    for class_pattern in rules["render_class_names"]:
                        if class_pattern.lower() in class_name.lower():
                            logger.info(f"通过渲染窗口类名检测到{rules['description']}: {class_name}")
                            return True, emulator_type, rules["description"]

                    # 2. 检查主窗口类名匹配
                    for main_class in rules["main_class_names"]:
                        if main_class.lower() in class_name.lower():
                            logger.info(f"通过主窗口类名检测到{rules['description']}: {class_name}")
                            return True, emulator_type, rules["description"]

                    # 3. 检查窗口标题关键词匹配
                    for keyword in rules["window_keywords"]:
                        if keyword.lower() in window_title.lower():
                            logger.info(f"通过标题检测到{rules['description']}: {window_title}")
                            return True, emulator_type, rules["description"]
            
            # 未检测到模拟器
            logger.debug(f"未检测到模拟器窗口: {window_title} ({class_name})")
            return False, None, "普通窗口"
            
        except Exception as e:
            logger.error(f"检测模拟器类型时发生异常: {e}")
            return False, None, "检测失败"

    def _has_mumu_parent_window(self, hwnd: int) -> bool:
        """检查窗口是否有MuMu父窗口"""
        try:
            current_hwnd = hwnd
            max_depth = 5  # 限制查找深度，避免无限循环

            for _ in range(max_depth):
                # 获取父窗口
                parent_hwnd = win32gui.GetParent(current_hwnd)
                if not parent_hwnd:
                    break

                try:
                    parent_title = win32gui.GetWindowText(parent_hwnd)
                    parent_class = win32gui.GetClassName(parent_hwnd)

                    # 检查是否是MuMu窗口
                    if (parent_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                        ("mumu" in parent_title.lower() or "安卓设备" in parent_title)):
                        logger.debug(f"找到MuMu父窗口: {parent_title} ({parent_class})")
                        return True

                    # 检查是否是MuMuNxDevice窗口
                    if "MuMuNxDevice" in parent_title:
                        logger.debug(f"找到MuMu设备窗口: {parent_title}")
                        return True

                except Exception:
                    pass

                current_hwnd = parent_hwnd

            return False

        except Exception as e:
            logger.debug(f"检查MuMu父窗口失败: {e}")
            return False
    
    def is_emulator_window(self, hwnd: int) -> bool:
        """
        简单检测是否为模拟器窗口
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            bool: 是否为模拟器窗口
        """
        is_emulator, _, _ = self.detect_emulator_type(hwnd)
        return is_emulator

    def is_main_window(self, hwnd: int) -> bool:
        """
        检测是否为模拟器主窗口（应该被过滤掉）

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 是否为主窗口
        """
        try:
            if not hwnd or not win32gui.IsWindow(hwnd):
                return False

            class_name = win32gui.GetClassName(hwnd)
            window_title = win32gui.GetWindowText(hwnd)

            # 检查是否为任何模拟器的主窗口
            for emulator_type, rules in self.emulator_rules.items():
                for main_class in rules["main_class_names"]:
                    if main_class.lower() in class_name.lower():
                        logger.debug(f"检测到模拟器主窗口: {window_title} ({class_name})")
                        return True

            return False

        except Exception as e:
            logger.error(f"检测主窗口时发生异常: {e}")
            return False

    def get_emulator_info(self, hwnd: int) -> Dict[str, Any]:
        """
        获取模拟器详细信息
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            Dict[str, Any]: 模拟器信息
        """
        is_emulator, emulator_type, description = self.detect_emulator_type(hwnd)
        
        try:
            class_name = win32gui.GetClassName(hwnd) if hwnd else ""
            window_title = win32gui.GetWindowText(hwnd) if hwnd else ""
        except:
            class_name = ""
            window_title = ""
        
        return {
            "is_emulator": is_emulator,
            "emulator_type": emulator_type,
            "description": description,
            "class_name": class_name,
            "window_title": window_title,
            "hwnd": hwnd
        }

def should_use_emulator_mode(hwnd: int, operation_mode: str = None) -> bool:
    """
    根据全局设置和窗口类型决定是否使用模拟器模式
    
    Args:
        hwnd: 窗口句柄
        operation_mode: 操作模式 ("auto", "standard_window", "emulator_window")
        
    Returns:
        bool: 是否应该使用模拟器模式
    """
    try:
        # 获取全局设置
        if operation_mode is None:
            try:
                from utils.universal_config_manager import get_config
                operation_mode = get_config("input_simulation.default_operation_mode", "auto")
            except:
                operation_mode = "auto"
        
        logger.debug(f"操作模式设置: {operation_mode}")
        
        # 根据操作模式决定
        if operation_mode == "emulator_window":
            # 强制使用模拟器模式
            logger.debug("强制使用模拟器模式")
            return True
        elif operation_mode == "standard_window":
            # 强制使用普通窗口模式
            logger.debug("强制使用普通窗口模式")
            return False
        elif operation_mode == "auto":
            # 自动检测
            detector = EmulatorDetector()
            is_emulator = detector.is_emulator_window(hwnd)
            logger.debug(f"自动检测结果: {'模拟器窗口' if is_emulator else '普通窗口'}")
            return is_emulator
        else:
            # 未知模式，默认自动检测
            logger.warning(f"未知操作模式: {operation_mode}，使用自动检测")
            detector = EmulatorDetector()
            return detector.is_emulator_window(hwnd)
            
    except Exception as e:
        logger.error(f"判断是否使用模拟器模式时发生异常: {e}")
        return False

def get_emulator_info(hwnd: int) -> Dict[str, Any]:
    """
    获取窗口的模拟器信息（便捷函数）
    
    Args:
        hwnd: 窗口句柄
        
    Returns:
        Dict[str, Any]: 模拟器信息
    """
    detector = EmulatorDetector()
    return detector.get_emulator_info(hwnd)

def log_window_detection_info(hwnd: int, operation_mode: str = None):
    """
    记录窗口检测信息（用于调试）
    
    Args:
        hwnd: 窗口句柄
        operation_mode: 操作模式
    """
    try:
        info = get_emulator_info(hwnd)
        should_use_emulator = should_use_emulator_mode(hwnd, operation_mode)
        
        logger.info("=== 窗口检测信息 ===")
        logger.info(f"窗口句柄: {hwnd}")
        logger.info(f"窗口标题: {info['window_title']}")
        logger.info(f"窗口类名: {info['class_name']}")
        logger.info(f"是否为模拟器: {info['is_emulator']}")
        logger.info(f"模拟器类型: {info['emulator_type']}")
        logger.info(f"模拟器描述: {info['description']}")
        logger.info(f"操作模式设置: {operation_mode}")
        logger.info(f"最终使用模拟器模式: {should_use_emulator}")
        logger.info("==================")
        
    except Exception as e:
        logger.error(f"记录窗口检测信息时发生异常: {e}")

# 全局实例
global_emulator_detector = EmulatorDetector()

# 便捷函数
def is_emulator_window(hwnd: int) -> bool:
    """检测是否为模拟器窗口的便捷函数"""
    return global_emulator_detector.is_emulator_window(hwnd)

def detect_emulator_type(hwnd: int) -> Tuple[bool, Optional[str], str]:
    """检测模拟器类型的便捷函数"""
    return global_emulator_detector.detect_emulator_type(hwnd)

if __name__ == "__main__":
    # 测试模块
    import sys
    
    print("模拟器检测工具测试")
    print("=" * 40)
    
    detector = EmulatorDetector()
    
    # 如果提供了窗口句柄参数
    if len(sys.argv) > 1:
        try:
            hwnd = int(sys.argv[1])
            info = detector.get_emulator_info(hwnd)
            
            print(f"窗口句柄: {hwnd}")
            print(f"窗口标题: {info['window_title']}")
            print(f"窗口类名: {info['class_name']}")
            print(f"是否为模拟器: {info['is_emulator']}")
            print(f"模拟器类型: {info['emulator_type']}")
            print(f"模拟器描述: {info['description']}")
            
            should_use = should_use_emulator_mode(hwnd)
            print(f"应该使用模拟器模式: {should_use}")
            
        except ValueError:
            print("错误: 请提供有效的窗口句柄（整数）")
        except Exception as e:
            print(f"测试时发生错误: {e}")
    else:
        print("用法: python emulator_detector.py <窗口句柄>")
        print("示例: python emulator_detector.py 525780")
