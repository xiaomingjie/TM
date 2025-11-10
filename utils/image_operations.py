# -*- coding: utf-8 -*-
"""
统一图像操作模块 - 整合所有图像处理相关的通用操作
"""
import logging
import numpy as np
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV 不可用，图像处理功能受限")


class ImageOperations:
    """统一的图像操作类"""
    
    @staticmethod
    def load_image_from_memory(image_data: bytes) -> Optional[np.ndarray]:
        """
        从内存数据加载图像
        
        Args:
            image_data: 图像二进制数据
            
        Returns:
            Optional[np.ndarray]: 加载的图像数组，失败返回None
        """
        if not CV2_AVAILABLE:
            logger.error("无法加载图像：缺少 OpenCV 库")
            return None
            
        try:
            image_array = np.frombuffer(image_data, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_UNCHANGED)
            if image is not None:
                logger.debug("从内存加载图像成功")
            else:
                logger.error("从内存加载图像失败：解码失败")
            return image
        except Exception as e:
            logger.error(f"从内存加载图像失败: {e}")
            return None
    
    @staticmethod
    def load_image_from_file(file_path: str) -> Optional[np.ndarray]:
        """
        从文件加载图像
        
        Args:
            file_path: 图像文件路径
            
        Returns:
            Optional[np.ndarray]: 加载的图像数组，失败返回None
        """
        if not CV2_AVAILABLE:
            logger.error("无法加载图像：缺少 OpenCV 库")
            return None
            
        try:
            image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if image is not None:
                logger.debug(f"从文件加载图像成功: {file_path}")
            else:
                logger.error(f"从文件加载图像失败：解码失败: {file_path}")
            return image
        except Exception as e:
            logger.error(f"从文件加载图像失败: {file_path}, 错误: {e}")
            return None
    
    @staticmethod
    def load_image_universal(image_source: Union[str, bytes], get_image_data_func=None) -> Optional[np.ndarray]:
        """
        通用图像加载方法，支持内存和文件两种模式
        
        Args:
            image_source: 图像源（文件路径或内存标识符）
            get_image_data_func: 获取内存图像数据的函数
            
        Returns:
            Optional[np.ndarray]: 加载的图像数组，失败返回None
        """
        if isinstance(image_source, str) and image_source.startswith('memory://'):
            # 内存模式
            if get_image_data_func is None:
                logger.error("内存模式缺少 get_image_data 函数")
                return None
            
            image_data = get_image_data_func(image_source)
            if image_data:
                return ImageOperations.load_image_from_memory(image_data)
            else:
                logger.error("无法从内存获取图像数据")
                return None
        else:
            # 文件模式
            return ImageOperations.load_image_from_file(image_source)
    
    @staticmethod
    def preprocess_image(image: np.ndarray, params: dict) -> Optional[np.ndarray]:
        """
        预处理图像（统一的预处理接口）
        
        Args:
            image: 输入图像
            params: 预处理参数
            
        Returns:
            Optional[np.ndarray]: 预处理后的图像，失败返回None
        """
        if image is None:
            return None
            
        try:
            # 尝试使用统一的预处理模块（动态导入避免静态分析警告）
            import importlib
            preprocessing_module = importlib.import_module('utils.image_preprocessing')
            apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
            processed_image = apply_preprocessing(image, params)
            if processed_image is not None:
                return processed_image
        except (ImportError, ModuleNotFoundError):
            logger.debug("统一预处理模块不可用，使用回退方法")
        except Exception as e:
            logger.warning(f"统一预处理失败: {e}，使用回退方法")
        
        # 回退到基本预处理
        return ImageOperations._basic_preprocess(image)
    
    @staticmethod
    def _basic_preprocess(image: np.ndarray) -> np.ndarray:
        """
        基本图像预处理（回退方法）
        
        Args:
            image: 输入图像
            
        Returns:
            np.ndarray: 预处理后的图像
        """
        if not CV2_AVAILABLE:
            return image
            
        try:
            # 处理BGRA格式
            if len(image.shape) == 3 and image.shape[2] == 4:
                return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            return image
        except Exception as e:
            logger.warning(f"基本预处理失败: {e}")
            return image
    
    @staticmethod
    def match_template(haystack: np.ndarray, needle: np.ndarray, confidence: float = 0.8) -> Tuple[bool, Optional[Tuple[int, int, int, int]], float]:
        """
        模板匹配
        
        Args:
            haystack: 搜索图像
            needle: 模板图像
            confidence: 置信度阈值
            
        Returns:
            Tuple[bool, Optional[Tuple[int, int, int, int]], float]: (是否找到, 位置(x,y,w,h), 匹配分数)
        """
        if not CV2_AVAILABLE:
            logger.error("无法进行模板匹配：缺少 OpenCV 库")
            return False, None, 0.0
            
        if haystack is None or needle is None:
            logger.error("模板匹配失败：图像数据为空")
            return False, None, 0.0
            
        try:
            # 检查尺寸
            template_h, template_w = needle.shape[:2]
            haystack_h, haystack_w = haystack.shape[:2]
            
            if haystack_h < template_h or haystack_w < template_w:
                logger.debug("模板匹配失败：搜索图像小于模板图像")
                return False, None, 0.0
            
            # 执行模板匹配
            match_method = cv2.TM_CCOEFF_NORMED
            result_matrix = cv2.matchTemplate(haystack, needle, match_method)
            _, max_val, _, max_loc = cv2.minMaxLoc(result_matrix)
            
            if max_val >= confidence:
                # 找到匹配
                top_left_x, top_left_y = max_loc
                location = (top_left_x, top_left_y, template_w, template_h)
                logger.debug(f"模板匹配成功，匹配分数: {max_val:.4f}")
                return True, location, max_val
            else:
                logger.debug(f"模板匹配失败，匹配分数: {max_val:.4f} < {confidence}")
                return False, None, max_val
                
        except Exception as e:
            logger.error(f"模板匹配时发生异常: {e}")
            return False, None, 0.0
    
    @staticmethod
    def get_image_name(image_path: str) -> str:
        """
        获取图像名称（用于日志显示）
        
        Args:
            image_path: 图像路径
            
        Returns:
            str: 图像名称
        """
        if image_path.startswith('memory://'):
            return image_path.replace('memory://', '')
        else:
            import os
            return os.path.basename(image_path)
    
    @staticmethod
    def validate_image_size(image: np.ndarray, min_width: int = 1, min_height: int = 1) -> bool:
        """
        验证图像尺寸
        
        Args:
            image: 图像数组
            min_width: 最小宽度
            min_height: 最小高度
            
        Returns:
            bool: 尺寸是否有效
        """
        if image is None:
            return False
            
        try:
            height, width = image.shape[:2]
            return height >= min_height and width >= min_width
        except Exception:
            return False


# 兼容性函数，保持与现有代码的兼容
def load_image_from_memory(image_data: bytes) -> Optional[np.ndarray]:
    """兼容性函数 - 从内存加载图像"""
    return ImageOperations.load_image_from_memory(image_data)


def load_image_from_file(file_path: str) -> Optional[np.ndarray]:
    """兼容性函数 - 从文件加载图像"""
    return ImageOperations.load_image_from_file(file_path)


def preprocess_image_unified(image: np.ndarray, params: dict) -> Optional[np.ndarray]:
    """兼容性函数 - 统一图像预处理"""
    return ImageOperations.preprocess_image(image, params)


def match_template_unified(haystack: np.ndarray, needle: np.ndarray, confidence: float = 0.8) -> Tuple[bool, Optional[Tuple[int, int, int, int]], float]:
    """兼容性函数 - 模板匹配"""
    return ImageOperations.match_template(haystack, needle, confidence)
