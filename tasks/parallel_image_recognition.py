"""
并行图片识别模块 - 多图识别性能优化
支持多线程并行处理，显著提升多图识别速度

主要特性：
1. 并行图片识别：多张图片同时处理
2. 智能截图复用：避免重复截图开销
3. 线程池管理：动态调整线程数量
4. 结果聚合：统一处理识别结果
5. 错误隔离：单张图片失败不影响其他
"""

import time
import threading
import concurrent.futures
from typing import Dict, Any, Optional, Tuple, List, NamedTuple
import cv2
import numpy as np
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

def detect_optimal_thread_count() -> int:
    """
    智能检测最优线程数

    Returns:
        int: 推荐的线程数
    """
    try:
        # 使用专门的CPU检测工具
        from utils.cpu_info_detector import detect_optimal_thread_count as cpu_detect
        return cpu_detect()
    except ImportError:
        # 回退到简单检测
        import os
        cpu_count = os.cpu_count() or 4
        optimal_threads = max(2, min(cpu_count, 32))
        logger.debug(f"使用简单CPU检测: 核心数={cpu_count}, 推荐线程数={optimal_threads}")
        return optimal_threads

class RecognitionMode(Enum):
    """识别模式"""
    FIRST_MATCH = "first_match"      # 找到第一张就停止
    ALL_MATCHES = "all_matches"      # 识别所有图片
    BEST_MATCH = "best_match"        # 找到置信度最高的

@dataclass
class ImageTask:
    """图片识别任务"""
    image_path: str
    image_name: str
    index: int
    params: Dict[str, Any]

@dataclass
class RecognitionResult:
    """识别结果"""
    image_path: str
    image_name: str
    index: int
    success: bool
    confidence: float
    location: Optional[Tuple[int, int, int, int]]
    center_x: Optional[int]
    center_y: Optional[int]
    error_message: Optional[str]
    processing_time: float

class ParallelImageRecognizer:
    """并行图片识别器"""
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化并行识别器

        Args:
            max_workers: 最大工作线程数，None表示自动检测
        """
        # 自动检测最优线程数
        if max_workers is None:
            max_workers = detect_optimal_thread_count()

        self.max_workers = max_workers
        self.thread_pool = None
        self._screenshot_cache = {}
        self._cache_lock = threading.Lock()

        logger.info(f"并行图片识别器初始化: 最大线程数={max_workers} (CPU线程数自动检测)")
    
    def recognize_images_parallel(self, 
                                image_paths: List[str],
                                params: Dict[str, Any],
                                execution_mode: str,
                                target_hwnd: Optional[int],
                                mode: RecognitionMode = RecognitionMode.FIRST_MATCH) -> List[RecognitionResult]:
        """
        并行识别多张图片
        
        Args:
            image_paths: 图片路径列表
            params: 识别参数
            execution_mode: 执行模式
            target_hwnd: 目标窗口句柄
            mode: 识别模式
            
        Returns:
            List[RecognitionResult]: 识别结果列表
        """
        if not image_paths:
            return []
        
        start_time = time.time()
        logger.info(f"[并行识别] 开始处理{len(image_paths)}张图片，模式={mode.value}")
        
        # 预先获取截图（避免重复截图）
        screenshot = self._get_screenshot_cached(execution_mode, target_hwnd, params)
        if screenshot is None:
            logger.error("获取截图失败，无法进行图片识别")
            return []
        
        # 创建识别任务
        tasks = []
        for i, image_path in enumerate(image_paths):
            image_name = self._get_image_name(image_path)
            task = ImageTask(
                image_path=image_path,
                image_name=image_name,
                index=i,
                params=params.copy()
            )
            tasks.append(task)
        
        # 执行并行识别
        results = self._execute_parallel_recognition(tasks, screenshot, mode)
        
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r.success)
        logger.info(f"[并行识别] 完成: {success_count}/{len(image_paths)}张成功, 总耗时={total_time:.2f}s")
        
        return results
    
    def _get_screenshot_cached(self, execution_mode: str, target_hwnd: Optional[int], params: Dict[str, Any]) -> Optional[np.ndarray]:
        """获取缓存的截图"""
        cache_key = f"{execution_mode}_{target_hwnd}_{time.time()//1}"  # 1秒缓存
        
        with self._cache_lock:
            if cache_key in self._screenshot_cache:
                logger.debug("使用缓存截图")
                return self._screenshot_cache[cache_key]
        
        # 获取新截图
        screenshot = self._capture_screenshot(execution_mode, target_hwnd, params)
        
        if screenshot is not None:
            with self._cache_lock:
                # 清理旧缓存
                self._screenshot_cache.clear()
                self._screenshot_cache[cache_key] = screenshot
        
        return screenshot
    
    def _capture_screenshot(self, execution_mode: str, target_hwnd: Optional[int], params: Dict[str, Any]) -> Optional[np.ndarray]:
        """捕获截图"""
        try:
            if execution_mode == 'background' and target_hwnd:
                # 后台模式：窗口截图
                from utils.win32_utils import capture_window_background
                screenshot = capture_window_background(target_hwnd)
            else:
                # 前台模式：全屏截图
                from utils.screenshot_helper import take_screenshot_opencv
                screenshot = take_screenshot_opencv()
            
            if screenshot is None:
                return None
            
            # 应用预处理
            try:
                import importlib
                preprocessing_module = importlib.import_module('utils.image_preprocessing')
                apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                processed_screenshot = apply_preprocessing(screenshot, params)
                return processed_screenshot if processed_screenshot is not None else screenshot
            except (ImportError, ModuleNotFoundError, AttributeError):
                # 基本预处理
                if len(screenshot.shape) == 3 and screenshot.shape[2] == 4:
                    return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                return screenshot
                
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None
    
    def _execute_parallel_recognition(self, tasks: List[ImageTask], screenshot: np.ndarray, mode: RecognitionMode) -> List[RecognitionResult]:
        """执行并行识别"""
        results = []
        stop_event = threading.Event()
        
        # 创建线程池
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {}
            for task in tasks:
                future = executor.submit(self._recognize_single_image, task, screenshot, stop_event)
                future_to_task[future] = task
            
            # 收集结果
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    # 根据模式决定是否提前停止
                    if mode == RecognitionMode.FIRST_MATCH and result.success:
                        logger.info(f"[并行识别] 找到第一张匹配图片: {result.image_name}")
                        stop_event.set()  # 通知其他线程停止
                        break
                        
                except Exception as e:
                    logger.error(f"任务执行异常: {task.image_name}, 错误: {e}")
                    # 创建失败结果
                    error_result = RecognitionResult(
                        image_path=task.image_path,
                        image_name=task.image_name,
                        index=task.index,
                        success=False,
                        confidence=0.0,
                        location=None,
                        center_x=None,
                        center_y=None,
                        error_message=str(e),
                        processing_time=0.0
                    )
                    results.append(error_result)
        
        # 按原始顺序排序
        results.sort(key=lambda r: r.index)
        return results
    
    def _recognize_single_image(self, task: ImageTask, screenshot: np.ndarray, stop_event: threading.Event) -> RecognitionResult:
        """识别单张图片"""
        start_time = time.time()
        
        try:
            # 检查是否需要停止
            if stop_event.is_set():
                return RecognitionResult(
                    image_path=task.image_path,
                    image_name=task.image_name,
                    index=task.index,
                    success=False,
                    confidence=0.0,
                    location=None,
                    center_x=None,
                    center_y=None,
                    error_message="任务被取消",
                    processing_time=time.time() - start_time
                )
            
            # 加载模板图片
            template_image = self._load_template_image(task.image_path)
            if template_image is None:
                raise Exception(f"无法加载模板图片: {task.image_path}")
            
            # 应用预处理
            processed_template = self._preprocess_template(template_image, task.params)
            
            # 执行模板匹配
            confidence_threshold = task.params.get('confidence', 0.6)
            success, confidence, location = self._match_template(screenshot, processed_template, confidence_threshold)
            
            # 计算中心点
            center_x, center_y = None, None
            if success and location:
                center_x = location[0] + location[2] // 2
                center_y = location[1] + location[3] // 2
            
            processing_time = time.time() - start_time
            
            return RecognitionResult(
                image_path=task.image_path,
                image_name=task.image_name,
                index=task.index,
                success=success,
                confidence=confidence,
                location=location,
                center_x=center_x,
                center_y=center_y,
                error_message=None,
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            return RecognitionResult(
                image_path=task.image_path,
                image_name=task.image_name,
                index=task.index,
                success=False,
                confidence=0.0,
                location=None,
                center_x=None,
                center_y=None,
                error_message=str(e),
                processing_time=processing_time
            )
    
    def _load_template_image(self, image_path: str) -> Optional[np.ndarray]:
        """加载模板图片"""
        try:
            if image_path.startswith('memory://'):
                # 从内存加载
                from ui.main_window import get_main_window
                main_window = get_main_window()
                if main_window and hasattr(main_window, 'get_image_data'):
                    image_data = main_window.get_image_data(image_path)
                    if image_data:
                        return cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
                return None
            else:
                # 从文件加载
                return cv2.imread(image_path, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.error(f"加载模板图片失败: {image_path}, 错误: {e}")
            return None
    
    def _preprocess_template(self, template: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
        """预处理模板图片"""
        try:
            import importlib
            preprocessing_module = importlib.import_module('utils.image_preprocessing')
            apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
            processed = apply_preprocessing(template, params)
            return processed if processed is not None else template
        except (ImportError, ModuleNotFoundError, AttributeError):
            return template
    
    def _match_template(self, screenshot: np.ndarray, template: np.ndarray, confidence_threshold: float) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]]]:
        """执行模板匹配"""
        try:
            template_h, template_w = template.shape[:2]
            screenshot_h, screenshot_w = screenshot.shape[:2]
            
            if screenshot_h < template_h or screenshot_w < template_w:
                return False, 0.0, None
            
            # OpenCV模板匹配
            result_matrix = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result_matrix)
            
            if max_val >= confidence_threshold:
                location = (max_loc[0], max_loc[1], template_w, template_h)
                return True, float(max_val), location
            else:
                return False, float(max_val), None
                
        except Exception as e:
            logger.error(f"模板匹配失败: {e}")
            return False, 0.0, None
    
    def _get_image_name(self, image_path: str) -> str:
        """获取图片名称"""
        if image_path.startswith('memory://'):
            return image_path.replace('memory://', '')
        else:
            import os
            return os.path.basename(image_path)
    
    def cleanup(self):
        """清理资源"""
        with self._cache_lock:
            self._screenshot_cache.clear()

# 全局实例
_parallel_recognizer = None
_recognizer_lock = threading.Lock()

def get_parallel_recognizer() -> ParallelImageRecognizer:
    """获取全局并行识别器实例"""
    global _parallel_recognizer
    if _parallel_recognizer is None:
        with _recognizer_lock:
            if _parallel_recognizer is None:
                _parallel_recognizer = ParallelImageRecognizer()
    return _parallel_recognizer
