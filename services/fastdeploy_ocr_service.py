#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FastDeploy OCR服务管理器 - 使用FastDeploy替换PaddleOCR
支持PPOCRv3 CPU版本，提供更好的性能和部署体验
"""

import logging
import threading
import time
import os
import sys
from typing import Optional, Dict, List, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# 打包环境支持
def setup_packaged_fastdeploy():
    """设置打包环境的FastDeploy支持"""
    try:
        if getattr(sys, 'frozen', False):
            # 获取打包后的路径
            if hasattr(sys, '_MEIPASS'):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(sys.executable)

            # FastDeploy所有可能的库路径
            possible_paths = [
                # 主要库路径
                os.path.join(base_path, 'fastdeploy', 'libs'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs'),

                # ONNX Runtime
                os.path.join(base_path, 'fastdeploy', 'libs', 'third_libs', 'onnxruntime', 'lib'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs', 'third_libs', 'onnxruntime', 'lib'),

                # OpenCV
                os.path.join(base_path, 'fastdeploy', 'libs', 'third_libs', 'opencv', 'build', 'x64', 'vc14', 'bin'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs', 'third_libs', 'opencv', 'build', 'x64', 'vc14', 'bin'),
                os.path.join(base_path, 'fastdeploy', 'libs', 'third_libs', 'opencv', 'build', 'x64', 'vc15', 'bin'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs', 'third_libs', 'opencv', 'build', 'x64', 'vc15', 'bin'),

                # OpenVINO (如果存在)
                os.path.join(base_path, 'fastdeploy', 'libs', 'third_libs', 'openvino', 'runtime', 'bin'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs', 'third_libs', 'openvino', 'runtime', 'bin'),

                # TBB (Threading Building Blocks)
                os.path.join(base_path, 'fastdeploy', 'libs', 'third_libs', 'openvino', 'runtime', '3rdparty', 'tbb', 'bin'),
                os.path.join(base_path, '_internal', 'fastdeploy', 'libs', 'third_libs', 'openvino', 'runtime', '3rdparty', 'tbb', 'bin'),

                # 其他可能的路径
                os.path.join(base_path, '_internal'),
                os.path.join(base_path, '_internal', 'cv2'),
                os.path.join(base_path, '_internal', 'numpy', '.libs')
            ]

            # 添加所有存在的路径
            for lib_path in possible_paths:
                if os.path.exists(lib_path):
                    try:
                        if hasattr(os, 'add_dll_directory'):
                            os.add_dll_directory(lib_path)

                        current_path = os.environ.get('PATH', '')
                        if lib_path not in current_path:
                            os.environ['PATH'] = lib_path + os.pathsep + current_path

                        # 简化日志输出，不显示临时路径细节
                        if 'fastdeploy' in lib_path:
                            logger.info(f"成功 添加FastDeploy库路径")
                        else:
                            logger.debug(f"成功 添加库路径: {lib_path}")
                    except Exception as e:
                        logger.warning(f"警告 无法添加路径 {lib_path}: {e}")

    except Exception as e:
        logger.error(f"错误 设置打包环境失败: {e}")

# 延迟导入标志 - 避免在模块导入时立即加载重型库
_fastdeploy_setup_done = False
_fastdeploy_import_attempted = False
FASTDEPLOY_AVAILABLE = False
fd = None
cv2 = None

def _ensure_fastdeploy_setup():
    """确保FastDeploy环境已设置（延迟执行）"""
    global _fastdeploy_setup_done
    if not _fastdeploy_setup_done:
        setup_packaged_fastdeploy()
        _fastdeploy_setup_done = True

def _ensure_fastdeploy_imported():
    """确保FastDeploy已导入（延迟执行）"""
    global _fastdeploy_import_attempted, FASTDEPLOY_AVAILABLE, fd, cv2

    if _fastdeploy_import_attempted:
        return FASTDEPLOY_AVAILABLE

    _fastdeploy_import_attempted = True

    # 先设置环境
    _ensure_fastdeploy_setup()

    # 然后尝试导入
    try:
        import fastdeploy as fd_module
        import cv2 as cv2_module
        fd = fd_module
        cv2 = cv2_module
        FASTDEPLOY_AVAILABLE = True
        logger.debug("FastDeploy 延迟导入成功")
        return True
    except ImportError as e:
        FASTDEPLOY_AVAILABLE = False
        logger.warning(f"FastDeploy 未安装: {e}")
        logger.warning("请运行: pip install fastdeploy-python")
        return False
    except Exception as e:
        FASTDEPLOY_AVAILABLE = False
        logger.error(f"FastDeploy 运行时错误: {e}")
        logger.warning("OCR功能将不可用，可能是打包环境问题")
        return False

class FastDeployOCRService:
    """FastDeploy OCR服务管理器 - 单例模式，常驻OCR引擎"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(FastDeployOCRService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._ocr_pipeline = None
        self._det_model = None
        self._cls_model = None
        self._rec_model = None
        self._init_lock = threading.Lock()
        self._recognition_lock = threading.Lock()
        self._is_initializing = False
        self._init_error = None
        
        # 简单状态管理
        self._service_active = False
        
        # 错误容忍机制
        self._error_count = 0
        self._max_error_count = 5
        self._last_success_time = time.time()
        
        # 模型路径配置
        self._model_paths = self._get_default_model_paths()
        
        logger.debug("FastDeploy OCR服务管理器已创建")

    def _get_default_model_paths(self) -> Dict[str, str]:
        """获取默认的PPOCRv3模型路径"""
        # 检查是否为打包环境
        if getattr(sys, 'frozen', False):
            # 打包环境 - 优先使用打包内的模型
            possible_paths = [
                os.path.join(sys._MEIPASS, 'models', 'ppocrv3'),  # PyInstaller临时路径（打包内模型，优先）
                os.path.join(os.path.dirname(sys.executable), 'models', 'ppocrv3'),  # exe同目录
                os.path.join(os.path.expanduser('~'), '.fastdeploy', 'models', 'ppocrv3'),  # 用户目录（备用）
            ]

            # 选择第一个存在的路径
            models_path = None
            for i, path in enumerate(possible_paths):
                if os.path.exists(path):
                    models_path = path
                    source_type = ["打包内模型", "exe同目录", "用户目录"][i]
                    logger.info(f"找到模型路径: {models_path} ({source_type})")
                    break

            if models_path is None:
                # 如果都不存在，使用用户目录并尝试下载
                models_path = os.path.join(os.path.expanduser('~'), '.fastdeploy', 'models', 'ppocrv3')
                logger.info(f"使用用户目录模型路径: {models_path}")
                logger.info("将尝试下载模型到用户目录")
        else:
            # 开发环境
            models_path = os.path.join(os.getcwd(), 'models', 'ppocrv3')

        return {
            'det_model': os.path.join(models_path, 'ch_PP-OCRv3_det_infer'),
            'cls_model': os.path.join(models_path, 'ch_ppocr_mobile_v2.0_cls_infer'),
            'rec_model': os.path.join(models_path, 'ch_PP-OCRv3_rec_infer')
        }

    def set_model_paths(self, det_model: str = None, cls_model: str = None, rec_model: str = None):
        """设置自定义模型路径"""
        if det_model:
            self._model_paths['det_model'] = det_model
        if cls_model:
            self._model_paths['cls_model'] = cls_model
        if rec_model:
            self._model_paths['rec_model'] = rec_model
        
        logger.info(f"已更新模型路径: {self._model_paths}")

    def _download_models_if_needed(self) -> bool:
        """如果需要，下载PPOCRv3模型"""
        try:
            # 检查模型是否存在
            for model_name, model_path in self._model_paths.items():
                if not os.path.exists(model_path):
                    logger.info(f"模型 {model_name} 不存在于 {model_path}")
                    return self._download_ppocrv3_models()
            return True
        except Exception as e:
            logger.error(f"检查模型时出错: {e}")
            return False

    def _download_ppocrv3_models(self) -> bool:
        """下载PPOCRv3模型文件"""
        logger.info("开始下载PPOCRv3模型...")

        try:
            # 创建模型目录
            models_dir = os.path.dirname(self._model_paths['det_model'])
            os.makedirs(models_dir, exist_ok=True)

            # PPOCRv3模型下载链接（多个镜像源）
            model_urls = {
                'det_model': [
                    'https://paddleocr.bj.bcebos.com/PP-OCRv3/chinese/ch_PP-OCRv3_det_infer.tar',  # 百度云（主要，已验证可用）
                    'https://github.com/PaddlePaddle/PaddleOCR/releases/download/v2.6.0/ch_PP-OCRv3_det_infer.tar',  # GitHub
                    'https://gitee.com/paddlepaddle/PaddleOCR/releases/download/v2.6.0/ch_PP-OCRv3_det_infer.tar'  # Gitee
                ],
                'cls_model': [
                    'https://paddleocr.oss-cn-beijing.aliyuncs.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar',
                    'https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar',
                    'https://github.com/PaddlePaddle/PaddleOCR/releases/download/v2.6.0/ch_ppocr_mobile_v2.0_cls_infer.tar',
                    'https://gitee.com/paddlepaddle/PaddleOCR/releases/download/v2.6.0/ch_ppocr_mobile_v2.0_cls_infer.tar'
                ],
                'rec_model': [
                    'https://paddleocr.oss-cn-beijing.aliyuncs.com/PP-OCRv3/chinese/ch_PP-OCRv3_rec_infer.tar',
                    'https://paddleocr.bj.bcebos.com/PP-OCRv3/chinese/ch_PP-OCRv3_rec_infer.tar',
                    'https://github.com/PaddlePaddle/PaddleOCR/releases/download/v2.6.0/ch_PP-OCRv3_rec_infer.tar',
                    'https://gitee.com/paddlepaddle/PaddleOCR/releases/download/v2.6.0/ch_PP-OCRv3_rec_infer.tar'
                ]
            }

            import urllib.request
            import tarfile

            for model_name, urls in model_urls.items():
                model_path = self._model_paths[model_name]
                tar_path = f"{model_path}.tar"

                # 尝试多个下载源
                download_success = False
                for i, url in enumerate(urls):
                    source_name = ['阿里云OSS', '百度云', 'GitHub', 'Gitee'][i] if i < 4 else f'镜像{i+1}'
                    logger.info(f"尝试从 {source_name} 下载 {model_name}: {url}")

                    try:
                        urllib.request.urlretrieve(url, tar_path)
                        logger.info(f"成功 从 {source_name} 下载 {model_name} 成功")
                        download_success = True
                        break
                    except Exception as e:
                        logger.warning(f"错误 从 {source_name} 下载失败: {e}")
                        if i < len(urls) - 1:
                            logger.info(f"尝试下一个下载源...")
                        continue

                if not download_success:
                    logger.error(f"错误 所有下载源都失败，无法下载 {model_name}")
                    raise Exception(f"无法下载模型 {model_name}")

                # 解压
                with tarfile.open(tar_path, 'r') as tar:
                    tar.extractall(os.path.dirname(model_path))

                # 删除tar文件
                os.remove(tar_path)

                logger.info(f"成功 {model_name} 下载并解压完成")

            # 下载字典文件（多个镜像源）
            dict_urls = [
                'https://paddleocr.oss-cn-beijing.aliyuncs.com/ppocr/utils/ppocr_keys_v1.txt',
                'https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/release/2.6/ppocr/utils/ppocr_keys_v1.txt',
                'https://gitee.com/paddlepaddle/PaddleOCR/raw/release/2.6/ppocr/utils/ppocr_keys_v1.txt',
                'https://raw.fastgit.org/PaddlePaddle/PaddleOCR/release/2.6/ppocr/utils/ppocr_keys_v1.txt',
                'https://cdn.jsdelivr.net/gh/PaddlePaddle/PaddleOCR@release/2.6/ppocr/utils/ppocr_keys_v1.txt'
            ]
            dict_path = os.path.join(models_dir, 'ppocr_keys_v1.txt')

            if not os.path.exists(dict_path):
                dict_downloaded = False
                for i, dict_url in enumerate(dict_urls):
                    source_names = ['阿里云OSS', 'GitHub', 'Gitee', 'FastGit', 'jsDelivr']
                    source_name = source_names[i] if i < len(source_names) else f'镜像{i+1}'

                    try:
                        logger.info(f"尝试从 {source_name} 下载字典文件: {dict_url}")
                        urllib.request.urlretrieve(dict_url, dict_path)
                        logger.info(f"成功 从 {source_name} 下载字典文件成功")
                        dict_downloaded = True
                        break
                    except Exception as e:
                        logger.warning(f"错误 从 {source_name} 下载字典文件失败: {e}")
                        continue

                if not dict_downloaded:
                    # 如果所有链接都失败，创建一个基本的字典文件
                    logger.info("所有字典文件下载源都失败，创建基本字典文件...")
                    self._create_basic_dict(dict_path)

            return True

        except Exception as e:
            logger.error(f"下载模型失败: {e}")
            return False

    def _create_basic_dict(self, dict_path: str):
        """创建基本的字典文件"""
        try:
            # 基本的中文字符集
            basic_chars = [
                '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
                'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
                '的', '一', '是', '在', '不', '了', '有', '和', '人', '这', '中', '大', '为', '上', '个',
                '国', '我', '以', '要', '他', '时', '来', '用', '们', '生', '到', '作', '地', '于', '出',
                '就', '分', '对', '成', '会', '可', '主', '发', '年', '动', '同', '工', '也', '能', '下',
                '过', '子', '说', '产', '种', '面', '而', '方', '后', '多', '定', '行', '学', '法', '所',
                '民', '得', '经', '十', '三', '之', '进', '着', '等', '部', '度', '家', '电', '力', '里',
                '如', '水', '化', '高', '自', '二', '理', '起', '小', '物', '现', '实', '加', '量', '都',
                '两', '体', '制', '机', '当', '使', '点', '从', '业', '本', '去', '把', '性', '好', '应',
                '开', '它', '合', '还', '因', '由', '其', '些', '然', '前', '外', '天', '政', '四', '日',
                '那', '社', '义', '事', '平', '形', '相', '全', '表', '间', '样', '与', '关', '各', '重',
                '新', '线', '内', '数', '正', '心', '反', '你', '明', '看', '原', '又', '么', '利', '比',
                '或', '但', '质', '气', '第', '向', '道', '命', '此', '变', '条', '只', '没', '结', '解',
                '问', '意', '建', '月', '公', '无', '系', '军', '很', '情', '者', '最', '立', '代', '想',
                '已', '通', '并', '提', '直', '题', '党', '程', '展', '五', '果', '料', '象', '员', '革',
                '位', '入', '常', '文', '总', '次', '品', '式', '活', '设', '及', '管', '特', '件', '长',
                '求', '老', '头', '基', '资', '边', '流', '路', '级', '少', '图', '山', '统', '接', '知',
                '较', '将', '组', '见', '计', '别', '她', '手', '角', '期', '根', '论', '运', '农', '指',
                '！', '？', '。', '，', '、', '；', '：', '"', '"', ''', ''', '（', '）', '【', '】', '《', '》',
                '—', '…', '·', '～', '￥', '%', '@', '#', '$', '&', '*', '+', '-', '=', '/', '\\', '|',
                '<', '>', '[', ']', '{', '}', '^', '_', '`', '~'
            ]

            with open(dict_path, 'w', encoding='utf-8') as f:
                for char in basic_chars:
                    f.write(char + '\n')

            logger.info("成功 基本字典文件创建完成")

        except Exception as e:
            logger.error(f"创建字典文件失败: {e}")

    def initialize(self, force_reinit: bool = False) -> bool:
        """初始化FastDeploy OCR引擎"""
        # 延迟导入FastDeploy
        if not _ensure_fastdeploy_imported():
            logger.error("FastDeploy不可用，无法初始化OCR服务")
            return False
        
        if self._service_active and not force_reinit:
            return True
        
        if self._is_initializing:
            logger.debug("OCR引擎正在初始化中，请稍候...")
            return False
        
        with self._init_lock:
            if self._service_active and not force_reinit:
                return True
            
            self._is_initializing = True
            self._init_error = None
            
            try:
                logger.debug("开始初始化FastDeploy OCR引擎...")
                
                # 下载模型（如果需要）
                if not self._download_models_if_needed():
                    logger.error("模型下载失败，无法初始化OCR服务")
                    logger.error("请检查网络连接或手动下载模型文件")
                    raise Exception("模型文件不可用，无法初始化OCR服务")
                
                # 创建运行时选项（CPU模式）
                det_option = fd.RuntimeOption()
                det_option.use_cpu()
                
                cls_option = fd.RuntimeOption()
                cls_option.use_cpu()
                
                rec_option = fd.RuntimeOption()
                rec_option.use_cpu()
                
                # 初始化各个模型
                try:
                    det_model_file = os.path.join(self._model_paths['det_model'], 'inference.pdmodel')
                    det_params_file = os.path.join(self._model_paths['det_model'], 'inference.pdiparams')
                    self._det_model = fd.vision.ocr.DBDetector(
                        det_model_file, det_params_file,
                        runtime_option=det_option
                    )
                    logger.debug("检测模型初始化成功")
                except Exception as e:
                    logger.error(f"检测模型初始化失败: {e}")
                    raise

                try:
                    cls_model_file = os.path.join(self._model_paths['cls_model'], 'inference.pdmodel')
                    cls_params_file = os.path.join(self._model_paths['cls_model'], 'inference.pdiparams')
                    self._cls_model = fd.vision.ocr.Classifier(
                        cls_model_file, cls_params_file,
                        runtime_option=cls_option
                    )
                    logger.debug("分类模型初始化成功")
                except Exception as e:
                    logger.error(f"分类模型初始化失败: {e}")
                    raise

                try:
                    rec_model_file = os.path.join(self._model_paths['rec_model'], 'inference.pdmodel')
                    rec_params_file = os.path.join(self._model_paths['rec_model'], 'inference.pdiparams')

                    # 查找字典文件
                    models_dir = os.path.dirname(self._model_paths['det_model'])
                    dict_path = os.path.join(models_dir, 'ppocr_keys_v1.txt')

                    if os.path.exists(dict_path):
                        self._rec_model = fd.vision.ocr.Recognizer(
                            rec_model_file, rec_params_file, dict_path,
                            runtime_option=rec_option
                        )
                    else:
                        # 如果字典文件不存在，不使用字典
                        self._rec_model = fd.vision.ocr.Recognizer(
                            rec_model_file, rec_params_file,
                            runtime_option=rec_option
                        )
                    logger.debug("识别模型初始化成功")
                except Exception as e:
                    logger.error(f"识别模型初始化失败: {e}")
                    raise
                
                # 创建PPOCRv3管道
                self._ocr_pipeline = fd.vision.ocr.PPOCRv3(
                    det_model=self._det_model,
                    cls_model=self._cls_model,
                    rec_model=self._rec_model
                )
                
                self._service_active = True
                self._error_count = 0

                logger.info("成功 OCR引擎初始化成功，服务已激活")
                return True
                
            except Exception as e:
                self._init_error = str(e)
                logger.error(f"错误 FastDeploy OCR引擎初始化失败: {e}")
                return False
            
            finally:
                self._is_initializing = False

    def is_ready(self) -> bool:
        """检查OCR服务是否就绪"""
        return self._service_active and self._ocr_pipeline is not None

    def recognize_text(self, image: np.ndarray, confidence: float = 0.5) -> List[Dict[str, Any]]:
        """
        使用FastDeploy识别文字
        
        Args:
            image: 输入图像 (numpy数组)
            confidence: 置信度阈值
            
        Returns:
            识别结果列表，每个元素包含 {'text': str, 'confidence': float, 'bbox': list}
        """
        if not self.is_ready():
            logger.warning("OCR服务未就绪")
            return []
        
        with self._recognition_lock:
            try:
                # 确保图像格式正确
                if len(image.shape) == 3 and image.shape[2] == 4:
                    # RGBA转RGB
                    image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
                elif len(image.shape) == 3 and image.shape[2] == 3:
                    # BGR转RGB (OpenCV默认是BGR)
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                # 执行OCR识别
                result = self._ocr_pipeline.predict(image)
                
                # 转换结果格式以兼容原有接口
                formatted_results = []
                
                if result and hasattr(result, 'boxes') and hasattr(result, 'text'):
                    for i, (box, text, conf) in enumerate(zip(result.boxes, result.text, result.rec_scores)):
                        if conf >= confidence:
                            formatted_results.append({
                                'text': text,
                                'confidence': float(conf),
                                'bbox': box.tolist() if hasattr(box, 'tolist') else list(box)
                            })
                
                self._last_success_time = time.time()
                self._error_count = 0
                
                logger.debug(f"OCR识别完成，找到 {len(formatted_results)} 个文本区域")
                return formatted_results
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"OCR识别失败: {e}")
                
                # 如果错误次数过多，尝试重新初始化
                if self._error_count >= self._max_error_count:
                    logger.warning("OCR错误次数过多，尝试重新初始化...")
                    self._service_active = False
                    threading.Thread(target=self.initialize, args=(True,), daemon=True).start()
                
                return []

    def shutdown(self):
        """关闭OCR服务"""
        logger.info("正在关闭FastDeploy OCR服务...")
        self._service_active = False
        self._ocr_pipeline = None
        self._det_model = None
        self._cls_model = None
        self._rec_model = None
        logger.info("FastDeploy OCR服务已关闭")

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        return {
            'engine_type': 'fastdeploy',
            'model_type': 'PPOCRv3',
            'backend': 'CPU',
            'service_active': self._service_active,
            'error_count': self._error_count,
            'last_success_time': self._last_success_time,
            'model_paths': self._model_paths,
            'init_error': self._init_error
        }


# 全局服务实例
_fastdeploy_ocr_service = None

def get_fastdeploy_ocr_service() -> FastDeployOCRService:
    """获取FastDeploy OCR服务实例（单例）"""
    global _fastdeploy_ocr_service
    if _fastdeploy_ocr_service is None:
        _fastdeploy_ocr_service = FastDeployOCRService()
    return _fastdeploy_ocr_service

def initialize_fastdeploy_ocr_service() -> bool:
    """初始化FastDeploy OCR服务"""
    service = get_fastdeploy_ocr_service()
    return service.initialize()

def is_fastdeploy_ocr_service_ready() -> bool:
    """检查FastDeploy OCR服务是否就绪"""
    service = get_fastdeploy_ocr_service()
    return service.is_ready()

def recognize_text_with_fastdeploy(image: np.ndarray, confidence: float = 0.5) -> List[Dict[str, Any]]:
    """使用FastDeploy OCR服务识别文字（容错版本）"""
    try:
        service = get_fastdeploy_ocr_service()
        if service and service.is_ready():
            return service.recognize_text(image, confidence)
        else:
            logger.warning("FastDeploy OCR服务不可用，返回空结果")
            return []
    except Exception as e:
        logger.error(f"FastDeploy OCR识别异常: {e}")
        return []

def shutdown_fastdeploy_ocr_service():
    """关闭FastDeploy OCR服务"""
    global _fastdeploy_ocr_service
    if _fastdeploy_ocr_service is not None:
        _fastdeploy_ocr_service.shutdown()
        _fastdeploy_ocr_service = None
