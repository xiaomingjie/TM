"""
增强的鼠标拖拽工具 - 基于开源最佳实践优化
支持平滑拖拽、实时图片识别、多种缓动函数等高级功能
"""

import time
import math
import threading
import logging
from typing import Tuple, Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor, Future
import pyautogui
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class EasingFunctions:
    """缓动函数集合 - 基于开源动画库最佳实践"""
    
    @staticmethod
    def linear(t: float) -> float:
        """线性缓动"""
        return t
    
    @staticmethod
    def ease_in_quad(t: float) -> float:
        """二次缓入"""
        return t * t
    
    @staticmethod
    def ease_out_quad(t: float) -> float:
        """二次缓出"""
        return 1 - (1 - t) * (1 - t)
    
    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        """二次缓入缓出"""
        if t < 0.5:
            return 2 * t * t
        else:
            return -1 + (4 - 2 * t) * t
    
    @staticmethod
    def ease_in_cubic(t: float) -> float:
        """三次缓入"""
        return t * t * t
    
    @staticmethod
    def ease_out_cubic(t: float) -> float:
        """三次缓出"""
        return 1 - pow(1 - t, 3)
    
    @staticmethod
    def ease_in_out_cubic(t: float) -> float:
        """三次缓入缓出"""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2


class EnhancedMouseDrag:
    """增强的鼠标拖拽类 - 基于PyAutoGUI和OpenCV最佳实践"""
    
    def __init__(self):
        self.logger = logger
        self._stop_flag = threading.Event()
        self._drag_active = False
        
        # 保存原始PyAutoGUI设置
        self._original_pause = pyautogui.PAUSE
        self._original_failsafe = pyautogui.FAILSAFE
    
    def drag_with_recognition(self, 
                            start_x: int, start_y: int, 
                            end_x: int, end_y: int,
                            duration: float = 1.0,
                            button: str = 'left',
                            easing_func: str = 'ease_in_out_quad',
                            template_image: Optional[np.ndarray] = None,
                            confidence: float = 0.8,
                            recognition_interval: float = 0.1) -> Tuple[bool, bool]:
        """
        执行带实时图片识别的拖拽操作
        
        Args:
            start_x, start_y: 起始坐标
            end_x, end_y: 结束坐标
            duration: 拖拽持续时间
            button: 鼠标按钮 ('left', 'right', 'middle')
            easing_func: 缓动函数名称
            template_image: 要识别的模板图片
            confidence: 图片识别置信度
            recognition_interval: 图片识别间隔
            
        Returns:
            (拖拽是否成功, 是否找到图片)
        """
        self.logger.info(f"开始增强拖拽: ({start_x},{start_y}) -> ({end_x},{end_y}), 时长={duration}s")
        
        # 重置停止标志
        self._stop_flag.clear()
        self._drag_active = True
        
        # 优化PyAutoGUI设置
        self._optimize_pyautogui_settings()
        
        drag_success = False
        image_found = False
        
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 线程1: 执行平滑拖拽
                drag_future = executor.submit(
                    self._perform_smooth_drag,
                    start_x, start_y, end_x, end_y, duration, button, easing_func
                )
                
                # 线程2: 实时图片识别
                recognition_future = None
                if template_image is not None:
                    recognition_future = executor.submit(
                        self._real_time_recognition,
                        template_image, confidence, duration, recognition_interval
                    )
                
                # 等待拖拽完成
                drag_success = drag_future.result()
                
                # 获取识别结果
                if recognition_future:
                    image_found = recognition_future.result()
                
        except Exception as e:
            self.logger.error(f"增强拖拽执行异常: {e}")
            self._emergency_mouse_release(button)
        finally:
            self._drag_active = False
            self._restore_pyautogui_settings()
            
        self.logger.info(f"增强拖拽完成: 成功={drag_success}, 找到图片={image_found}")
        return drag_success, image_found
    
    def _optimize_pyautogui_settings(self):
        """优化PyAutoGUI设置以提高性能"""
        pyautogui.PAUSE = 0.01  # 减少延迟
        pyautogui.FAILSAFE = True  # 保持安全机制
    
    def _restore_pyautogui_settings(self):
        """恢复PyAutoGUI原始设置"""
        pyautogui.PAUSE = self._original_pause
        pyautogui.FAILSAFE = self._original_failsafe
    
    def _perform_smooth_drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                           duration: float, button: str, easing_func: str) -> bool:
        """执行平滑拖拽"""
        try:
            # 获取缓动函数
            easing = getattr(EasingFunctions, easing_func, EasingFunctions.ease_in_out_quad)
            
            # 移动到起始位置
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.05)
            
            # 按下鼠标
            pyautogui.mouseDown(button=button)
            time.sleep(0.05)
            
            # 计算拖拽参数
            total_distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
            steps = max(20, int(total_distance / 3))  # 更细腻的步数
            step_duration = duration / steps
            
            self.logger.debug(f"拖拽参数: 距离={total_distance:.1f}px, 步数={steps}, 缓动={easing_func}")
            
            # 执行平滑移动
            for i in range(steps + 1):
                if self._stop_flag.is_set():
                    self.logger.info("拖拽被停止标志中断")
                    break
                    
                progress = i / steps
                eased_progress = easing(progress)
                
                current_x = start_x + (end_x - start_x) * eased_progress
                current_y = start_y + (end_y - start_y) * eased_progress
                
                # 使用修复的鼠标移动
                try:
                    from main import mouse_move_fixer
                    success = mouse_move_fixer.safe_move_to(int(current_x), int(current_y), duration=0)
                    if not success:
                        pyautogui.moveTo(int(current_x), int(current_y))
                except ImportError:
                    pyautogui.moveTo(int(current_x), int(current_y))
                
                if i < steps:
                    time.sleep(step_duration)
            
            # 松开鼠标
            pyautogui.mouseUp(button=button)
            
            self.logger.debug("平滑拖拽执行完成")
            return True
            
        except Exception as e:
            self.logger.error(f"平滑拖拽失败: {e}")
            self._emergency_mouse_release(button)
            return False
    
    def _real_time_recognition(self, template_image: np.ndarray, confidence: float,
                             max_duration: float, check_interval: float) -> bool:
        """实时图片识别"""
        start_time = time.time()
        recognition_count = 0
        
        try:
            while time.time() - start_time < max_duration and not self._stop_flag.is_set():
                recognition_count += 1
                
                # 截取屏幕
                screenshot = pyautogui.screenshot()
                screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                
                # 模板匹配
                result = cv2.matchTemplate(screenshot_cv, template_image, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val >= confidence:
                    self.logger.info(f"实时识别成功! 置信度={max_val:.3f} (第{recognition_count}次)")
                    self._stop_flag.set()  # 通知拖拽停止
                    return True
                
                time.sleep(check_interval)
                
            self.logger.debug(f"实时识别完成: 共{recognition_count}次检查")
            return False
            
        except Exception as e:
            self.logger.error(f"实时识别异常: {e}")
            return False
    
    def _emergency_mouse_release(self, button: str):
        """紧急释放鼠标按键"""
        try:
            pyautogui.mouseUp(button=button)
            self.logger.info(f"紧急释放鼠标{button}键")
        except Exception as e:
            self.logger.error(f"紧急释放鼠标失败: {e}")
    
    def stop_drag(self):
        """停止当前拖拽操作"""
        self._stop_flag.set()
        self.logger.info("请求停止拖拽操作")


# 全局实例
_enhanced_drag_instance = None

def get_enhanced_drag() -> EnhancedMouseDrag:
    """获取增强拖拽实例（单例模式）"""
    global _enhanced_drag_instance
    if _enhanced_drag_instance is None:
        _enhanced_drag_instance = EnhancedMouseDrag()
    return _enhanced_drag_instance
