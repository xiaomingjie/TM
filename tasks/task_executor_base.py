# -*- coding: utf-8 -*-
"""
统一任务执行器基类 - 处理通用的延迟、跳转和结果处理逻辑
"""
import logging
import time
import random
from typing import Dict, Any, Tuple, Optional, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TaskExecutorBase(ABC):
    """任务执行器基类，提供统一的延迟和跳转处理"""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
    
    @abstractmethod
    def _execute_core_logic(self, params: Dict[str, Any], **kwargs) -> Tuple[bool, str]:
        """
        执行任务的核心逻辑（子类必须实现）
        
        Args:
            params: 任务参数
            **kwargs: 其他参数（如target_hwnd, stop_checker等）
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息或成功信息)
        """
        pass
    
    def execute_task(self, params: Dict[str, Any], **kwargs) -> Tuple[bool, str, Optional[int]]:
        """
        执行任务的统一入口，处理延迟和跳转逻辑
        
        Args:
            params: 任务参数
            **kwargs: 其他参数
            
        Returns:
            Tuple[bool, str, Optional[int]]: (是否成功, 动作, 跳转目标ID)
        """
        try:
            # 获取通用参数
            card_id = kwargs.get('card_id')
            stop_checker = kwargs.get('stop_checker')
            
            # 获取跳转参数
            on_success = params.get('on_success', '执行下一步')
            success_jump_id = params.get('success_jump_target_id')
            on_failure = params.get('on_failure', '执行下一步')
            failure_jump_id = params.get('failure_jump_target_id')
            
            logger.info(f"开始执行{self.task_name}任务")
            
            # 执行核心逻辑
            success, message = self._execute_core_logic(params, **kwargs)
            
            if success:
                logger.info(f"{self.task_name}任务执行成功: {message}")
                
                # 处理下一步延迟
                if params.get('enable_next_step_delay', False):
                    self._handle_next_step_delay(params, stop_checker)
                
                # 处理成功跳转
                return self._handle_success_action(on_success, success_jump_id, card_id)
            else:
                logger.error(f"{self.task_name}任务执行失败: {message}")
                
                # 处理失败跳转
                return self._handle_failure_action(on_failure, failure_jump_id, card_id)
                
        except Exception as e:
            logger.error(f"执行{self.task_name}任务时发生异常: {e}", exc_info=True)
            return self._handle_failure_action(
                params.get('on_failure', '执行下一步'),
                params.get('failure_jump_target_id'),
                kwargs.get('card_id')
            )
    
    def _handle_next_step_delay(self, params: Dict[str, Any], stop_checker=None):
        """处理下一步延迟执行"""
        try:
            delay_mode = params.get('delay_mode', '固定延迟')
            
            if delay_mode == '固定延迟':
                delay_time = params.get('fixed_delay', 1.0)
                logger.info(f"执行固定延迟: {delay_time} 秒")
                self._interruptible_sleep(delay_time, stop_checker)
            elif delay_mode == '随机延迟':
                min_delay = params.get('min_delay', 0.5)
                max_delay = params.get('max_delay', 2.0)
                delay_time = random.uniform(min_delay, max_delay)
                logger.info(f"执行随机延迟: {delay_time:.2f} 秒 (范围: {min_delay}-{max_delay})")
                self._interruptible_sleep(delay_time, stop_checker)
            else:
                logger.warning(f"未知的延迟模式: {delay_mode}")
        except Exception as e:
            logger.error(f"执行下一步延迟时发生错误: {e}")
    
    def _interruptible_sleep(self, duration: float, stop_checker=None):
        """可中断的睡眠函数"""
        if duration <= 0:
            return
        
        start_time = time.time()
        while time.time() - start_time < duration:
            if stop_checker and stop_checker():
                logger.info("延迟被中断")
                break
            time.sleep(0.1)
    
    def _handle_success_action(self, action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
        """处理成功动作"""
        if action == '跳转到步骤':
            return True, '跳转到步骤', jump_id
        elif action == '停止工作流':
            return True, '停止工作流', None
        elif action == '继续执行本步骤' or action == '继续本步骤':
            return True, '继续执行本步骤', card_id
        else:  # 执行下一步
            return True, '执行下一步', None
    
    def _handle_failure_action(self, action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
        """处理失败动作"""
        if action == '跳转到步骤':
            return False, '跳转到步骤', jump_id
        elif action == '停止工作流':
            return False, '停止工作流', None
        elif action == '继续执行本步骤' or action == '继续本步骤':
            return False, '继续执行本步骤', card_id
        else:  # 执行下一步
            return False, '执行下一步', None


def get_standard_next_step_delay_params() -> Dict[str, Dict[str, Any]]:
    """获取标准的下一步延迟参数定义"""
    return {
        "---next_step_delay---": {"type": "separator", "label": "下一步延迟执行"},
        "enable_next_step_delay": {
            "label": "启用下一步延迟执行",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，执行完当前操作会等待指定时间再执行下一步"
        },
        "delay_mode": {
            "label": "延迟模式",
            "type": "select",
            "options": ["固定延迟", "随机延迟"],
            "default": "固定延迟",
            "tooltip": "选择固定延迟时间还是随机延迟时间",
            "condition": {"param": "enable_next_step_delay", "value": True}
        },
        "fixed_delay": {
            "label": "固定延迟 (秒)",
            "type": "float",
            "default": 1.0,
            "min": 0.1,
            "max": 60.0,
            "decimals": 2,
            "tooltip": "固定延迟的时间（秒）",
            "condition": {"param": "delay_mode", "value": "固定延迟"}
        },
        "min_delay": {
            "label": "最小延迟 (秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.1,
            "max": 60.0,
            "decimals": 2,
            "tooltip": "随机延迟的最小时间（秒）",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },
        "max_delay": {
            "label": "最大延迟 (秒)",
            "type": "float",
            "default": 2.0,
            "min": 0.1,
            "max": 60.0,
            "decimals": 2,
            "tooltip": "随机延迟的最大时间（秒）",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        }
    }


def get_standard_action_params() -> Dict[str, Dict[str, Any]]:
    """获取标准的成功/失败动作参数定义"""
    return {
        "---post_execution---": {"type": "separator", "label": "执行后操作"},
        "on_success": {
            "type": "select",
            "label": "成功时",
            "options": ["执行下一步", "继续执行本步骤", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "当任务执行成功时的操作"
        },
        "success_jump_target_id": {
            "type": "int",
            "label": "成功跳转目标ID",
            "required": False,
            "condition": {"param": "on_success", "value": "跳转到步骤"},
            "tooltip": "任务成功时要跳转到的卡片ID"
        },
        "on_failure": {
            "type": "select",
            "label": "失败时",
            "options": ["执行下一步", "继续执行本步骤", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "当任务执行失败时的操作"
        },
        "failure_jump_target_id": {
            "type": "int",
            "label": "失败跳转目标ID",
            "required": False,
            "condition": {"param": "on_failure", "value": "跳转到步骤"},
            "tooltip": "任务失败时要跳转到的卡片ID"
        }
    }


def merge_params_definitions(*param_defs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """合并多个参数定义字典"""
    merged = {}
    for param_def in param_defs:
        merged.update(param_def)
    return merged
