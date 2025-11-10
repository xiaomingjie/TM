"""
多窗口任务执行器 - 确保每个任务在正确的窗口中执行
解决多窗口执行时只操作顶层窗口的问题
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple
import win32gui
import win32con

logger = logging.getLogger(__name__)

class MultiWindowTaskExecutor:
    """多窗口任务执行器 - 确保任务在指定窗口中执行"""
    
    def __init__(self, target_hwnd: int, window_title: str):
        self.target_hwnd = target_hwnd
        self.window_title = window_title
        self.last_activation_time = 0
        self.activation_cooldown = 0.5  # 激活冷却时间
        
    def execute_task_with_window_context(self, task_module, task_params: Dict[str, Any], 
                                       execution_mode: str, **kwargs) -> Tuple[bool, str, Optional[int]]:
        """
        在指定窗口上下文中执行任务
        
        Args:
            task_module: 任务模块
            task_params: 任务参数
            execution_mode: 执行模式
            **kwargs: 其他参数
            
        Returns:
            Tuple[bool, str, Optional[int]]: (成功状态, 动作, 下一个卡片ID)
        """
        try:
            # 1. 验证窗口句柄
            if not self._validate_window():
                logger.error(f"窗口验证失败: {self.window_title} (HWND: {self.target_hwnd})")
                return False, "窗口无效", None
            
            # 2. 确保窗口处于正确状态
            if not self._prepare_window_for_execution(execution_mode):
                logger.error(f"窗口准备失败: {self.window_title}")
                return False, "窗口准备失败", None
            
            # 3. 强制使用后台模式和指定窗口句柄
            modified_params = task_params.copy()
            
            # 确保任务参数中包含正确的窗口信息
            execution_kwargs = kwargs.copy()
            execution_kwargs.update({
                'target_hwnd': self.target_hwnd,
                'execution_mode': 'background',  # 强制后台模式
                'window_region': None
            })
            
            logger.debug(f"靶心 执行任务在窗口: {self.window_title} (HWND: {self.target_hwnd})")
            
            # 4. 执行任务 - 使用窗口隔离执行
            if hasattr(task_module, 'execute_task'):
                # 工具 关键修复：使用窗口隔离执行，防止任务模块激活其他窗口
                result = self._execute_task_with_window_isolation(
                    task_module, modified_params, execution_kwargs
                )
            else:
                logger.error(f"任务模块缺少 execute_task 方法")
                return False, "任务模块错误", None
            
            # 5. 验证执行结果
            if isinstance(result, tuple) and len(result) >= 2:
                success, action = result[0], result[1]
                next_card_id = result[2] if len(result) > 2 else None
                
                if success:
                    logger.debug(f"成功 任务执行成功: {self.window_title}")
                else:
                    logger.warning(f"错误 任务执行失败: {self.window_title}")
                
                return success, action, next_card_id
            else:
                logger.error(f"任务返回格式错误: {result}")
                return False, "返回格式错误", None
                
        except Exception as e:
            logger.error(f"执行任务时发生异常: {e}", exc_info=True)
            return False, f"执行异常: {str(e)}", None
    
    def _validate_window(self) -> bool:
        """验证窗口句柄是否有效"""
        try:
            if not self.target_hwnd:
                logger.error(f"窗口句柄为空: {self.window_title}")
                return False
            
            if not win32gui.IsWindow(self.target_hwnd):
                logger.error(f"窗口句柄无效: {self.target_hwnd}")
                return False
            
            # 获取窗口信息进行验证
            try:
                actual_title = win32gui.GetWindowText(self.target_hwnd)
                class_name = win32gui.GetClassName(self.target_hwnd)
                window_rect = win32gui.GetWindowRect(self.target_hwnd)
                
                logger.debug(f"窗口验证: 标题='{actual_title}', 类名='{class_name}', 位置={window_rect}")
                
                # 检查窗口是否可见
                if not win32gui.IsWindowVisible(self.target_hwnd):
                    logger.warning(f"窗口不可见: {self.target_hwnd}")
                    # 不可见的窗口仍然可以进行后台操作
                
                return True
                
            except Exception as e:
                logger.error(f"获取窗口信息失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"验证窗口时发生异常: {e}")
            return False
    
    def _prepare_window_for_execution(self, execution_mode: str) -> bool:
        """为执行准备窗口状态"""
        try:
            current_time = time.time()
            
            # 检查是否需要激活窗口（仅在前台模式下）
            if execution_mode == 'foreground':
                # 前台模式需要激活窗口
                if current_time - self.last_activation_time > self.activation_cooldown:
                    if self._activate_window():
                        self.last_activation_time = current_time
                        logger.debug(f"窗口已激活: {self.window_title}")
                    else:
                        logger.warning(f"窗口激活失败: {self.window_title}")
                        return False
            else:
                # 后台模式不需要激活窗口，但需要确保窗口状态正常
                if win32gui.IsIconic(self.target_hwnd):
                    # 如果窗口最小化，恢复它（但不激活）
                    logger.info(f"恢复最小化窗口: {self.window_title}")
                    win32gui.ShowWindow(self.target_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.1)
            
            return True
            
        except Exception as e:
            logger.error(f"准备窗口状态时发生异常: {e}")
            return False
    
    def _activate_window(self) -> bool:
        """激活窗口（仅在前台模式下使用）"""
        try:
            # 检查是否已经是前台窗口
            current_foreground = win32gui.GetForegroundWindow()
            if current_foreground == self.target_hwnd:
                logger.debug(f"窗口已是前台窗口: {self.target_hwnd}")
                return True
            
            # 检查窗口是否最小化
            if win32gui.IsIconic(self.target_hwnd):
                logger.debug(f"恢复最小化窗口: {self.target_hwnd}")
                win32gui.ShowWindow(self.target_hwnd, win32con.SW_RESTORE)
                time.sleep(0.15)
            
            # 激活窗口
            win32gui.SetForegroundWindow(self.target_hwnd)
            time.sleep(0.1)
            
            # 验证激活是否成功
            new_foreground = win32gui.GetForegroundWindow()
            if new_foreground == self.target_hwnd:
                logger.debug(f"窗口激活成功: {self.target_hwnd}")
                return True
            else:
                logger.warning(f"窗口激活失败: 期望={self.target_hwnd}, 实际={new_foreground}")
                return False
                
        except Exception as e:
            logger.error(f"激活窗口时发生异常: {e}")
            return False
    
    def get_window_info(self) -> Dict[str, Any]:
        """获取窗口信息"""
        try:
            if not self._validate_window():
                return {"valid": False, "error": "窗口无效"}
            
            title = win32gui.GetWindowText(self.target_hwnd)
            class_name = win32gui.GetClassName(self.target_hwnd)
            rect = win32gui.GetWindowRect(self.target_hwnd)
            is_visible = win32gui.IsWindowVisible(self.target_hwnd)
            is_minimized = win32gui.IsIconic(self.target_hwnd)
            is_foreground = win32gui.GetForegroundWindow() == self.target_hwnd
            
            return {
                "valid": True,
                "hwnd": self.target_hwnd,
                "title": title,
                "class_name": class_name,
                "rect": rect,
                "is_visible": is_visible,
                "is_minimized": is_minimized,
                "is_foreground": is_foreground
            }
            
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _execute_task_with_window_isolation(self, task_module, task_params: Dict[str, Any],
                                          execution_kwargs: Dict[str, Any]):
        """
        工具 关键修复：在窗口隔离环境中执行任务，防止窗口激活冲突
        """
        try:
            # 保存当前前台窗口
            original_foreground = None
            try:
                original_foreground = win32gui.GetForegroundWindow()
                logger.debug(f"保存原始前台窗口: {original_foreground}")
            except:
                pass

            # 临时禁用窗口激活（通过环境变量标记）
            import os
            old_env = os.environ.get('MULTI_WINDOW_MODE', None)
            os.environ['MULTI_WINDOW_MODE'] = 'true'

            try:
                # 执行任务
                result = task_module.execute_task(
                    params=task_params,
                    counters=execution_kwargs.get('counters', {}),
                    execution_mode='background',  # 强制后台模式
                    target_hwnd=self.target_hwnd,
                    window_region=execution_kwargs.get('window_region'),
                    card_id=execution_kwargs.get('card_id'),
                    get_image_data=execution_kwargs.get('get_image_data'),
                    stop_checker=execution_kwargs.get('stop_checker')  # 传递停止检查函数
                )

                # 验证窗口没有被意外激活
                try:
                    current_foreground = win32gui.GetForegroundWindow()
                    if current_foreground != original_foreground and current_foreground == self.target_hwnd:
                        logger.warning(f"警告 检测到窗口被意外激活: {self.target_hwnd}")
                        # 尝试恢复原始前台窗口
                        if original_foreground and win32gui.IsWindow(original_foreground):
                            try:
                                win32gui.SetForegroundWindow(original_foreground)
                                logger.debug(f"已恢复原始前台窗口: {original_foreground}")
                            except:
                                pass
                except:
                    pass

                return result

            finally:
                # 恢复环境变量
                if old_env is None:
                    os.environ.pop('MULTI_WINDOW_MODE', None)
                else:
                    os.environ['MULTI_WINDOW_MODE'] = old_env

        except Exception as e:
            logger.error(f"窗口隔离执行失败: {e}")
            raise e


def create_multi_window_task_executor(target_hwnd: int, window_title: str) -> MultiWindowTaskExecutor:
    """创建多窗口任务执行器"""
    return MultiWindowTaskExecutor(target_hwnd, window_title)


def execute_task_in_window(task_module, task_params: Dict[str, Any], 
                          target_hwnd: int, window_title: str,
                          execution_mode: str = 'background',
                          **kwargs) -> Tuple[bool, str, Optional[int]]:
    """
    在指定窗口中执行任务的便捷函数
    
    Args:
        task_module: 任务模块
        task_params: 任务参数
        target_hwnd: 目标窗口句柄
        window_title: 窗口标题
        execution_mode: 执行模式
        **kwargs: 其他参数
        
    Returns:
        Tuple[bool, str, Optional[int]]: (成功状态, 动作, 下一个卡片ID)
    """
    executor = create_multi_window_task_executor(target_hwnd, window_title)
    return executor.execute_task_with_window_context(
        task_module, task_params, execution_mode, **kwargs
    )


def validate_multi_window_setup(windows: list) -> Dict[str, Any]:
    """
    验证多窗口设置
    
    Args:
        windows: 窗口列表，每个元素包含 {'title': str, 'hwnd': int}
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    results = {
        "total_windows": len(windows),
        "valid_windows": 0,
        "invalid_windows": 0,
        "window_details": [],
        "issues": []
    }
    
    for i, window in enumerate(windows):
        title = window.get('title', f'窗口{i+1}')
        hwnd = window.get('hwnd', 0)
        
        executor = create_multi_window_task_executor(hwnd, title)
        window_info = executor.get_window_info()
        
        if window_info.get("valid", False):
            results["valid_windows"] += 1
        else:
            results["invalid_windows"] += 1
            results["issues"].append(f"窗口 '{title}' (HWND: {hwnd}) 无效: {window_info.get('error', '未知错误')}")
        
        results["window_details"].append({
            "title": title,
            "hwnd": hwnd,
            "info": window_info
        })
    
    return results
