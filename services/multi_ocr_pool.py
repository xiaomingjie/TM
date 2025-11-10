
"""
多OCR服务池 - 根据窗口数量动态创建OCR服务实例
实现一个窗口对应一个OCR服务的模式，避免OCR资源竞争
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
import queue
logger = logging.getLogger(__name__)

# 尝试导入psutil，如果失败则使用替代方案
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil不可用，将使用简化的内存监控")
import os

# 导入OCR服务
try:
    from services.fastdeploy_ocr_service import get_fastdeploy_ocr_service, FastDeployOCRService
    FASTDEPLOY_AVAILABLE = True
except ImportError:
    FASTDEPLOY_AVAILABLE = False


@dataclass
class OCRServiceInstance:
    """OCR服务实例 - 支持多窗口共享"""
    service_id: str
    ocr_service: object
    is_active: bool = True
    last_used: float = 0.0
    total_requests: int = 0
    total_processing_time: float = 0.0
    # 新增：窗口管理
    assigned_windows: Dict[int, str] = field(default_factory=dict)  # hwnd -> window_title
    max_windows: int = 3  # 每个服务最多支持3个窗口

    def can_accept_window(self) -> bool:
        """检查是否可以接受新窗口"""
        return len(self.assigned_windows) < self.max_windows

    def add_window(self, window_hwnd: int, window_title: str) -> bool:
        """添加窗口到服务"""
        if self.can_accept_window():
            self.assigned_windows[window_hwnd] = window_title
            return True
        return False

    def remove_window(self, window_hwnd: int) -> bool:
        """从服务中移除窗口"""
        if window_hwnd in self.assigned_windows:
            del self.assigned_windows[window_hwnd]
            return True
        return False

    def get_window_count(self) -> int:
        """获取当前窗口数量"""
        return len(self.assigned_windows)

    def is_empty(self) -> bool:
        """检查服务是否为空（无窗口）"""
        return len(self.assigned_windows) == 0


@dataclass
class OCRRequest:
    """OCR请求"""
    request_id: str
    window_title: str
    window_hwnd: int
    image: object  # numpy array
    confidence: float
    timestamp: float


@dataclass
class OCRResponse:
    """OCR响应"""
    request_id: str
    service_id: str
    results: List[Dict]
    success: bool
    processing_time: float = 0.0
    error_message: str = ""


class MultiOCRPool:
    """多OCR服务池管理器"""
    
    def __init__(self, max_services: int = 10, max_windows_per_service: int = 3):
        """
        初始化多OCR服务池 - 优化分配策略

        Args:
            max_services: 最大OCR服务数量 (固定为10)
            max_windows_per_service: 每个服务最多支持的窗口数 (固定为3)
        """
        self.max_services = min(max_services, 10)  # 硬限制为10个服务
        self.max_windows_per_service = max_windows_per_service
        self.ocr_services: Dict[str, OCRServiceInstance] = {}
        self.window_service_mapping: Dict[int, str] = {}  # hwnd -> service_id
        
        # 线程安全
        self._pool_lock = threading.RLock()
        self._request_counter = 0
        self._counter_lock = threading.Lock()
        
        # 性能监控
        self._performance_stats = {
            "total_services": 0,
            "active_services": 0,
            "total_requests": 0,
            "average_processing_time": 0.0,
            "memory_usage_mb": 0.0
        }
        
        # 清理线程
        self._cleanup_thread = None
        self._cleanup_interval = 30   # 30秒清理一次（更频繁地检查窗口状态）
        self._service_timeout = 600   # 10分钟未使用则清理
        self._running = True
        
        logger.info(f"多OCR服务池已初始化，最大服务数: {max_services}")
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while self._running:
                try:
                    time.sleep(self._cleanup_interval)
                    if self._running:
                        # 检查并清理已关闭窗口的服务
                        self.check_and_cleanup_closed_windows()

                        # 清理不活跃的服务
                        self._cleanup_inactive_services()

                        # 更新性能统计
                        self._update_performance_stats()
                except Exception as e:
                    logger.error(f"清理线程异常: {e}")
                    time.sleep(60)  # 出错时等待1分钟再继续
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.debug("OCR服务池清理线程已启动")
    
    def _generate_service_id(self) -> str:
        """生成服务ID"""
        return f"ocr_service_{len(self.ocr_services)}_{int(time.time())}"

    def _find_best_service_for_window(self, window_hwnd: int, window_title: str) -> Optional[str]:
        """找到最适合分配给窗口的服务"""
        with self._pool_lock:
            # 1. 检查窗口是否已经分配给某个服务
            if window_hwnd in self.window_service_mapping:
                service_id = self.window_service_mapping[window_hwnd]
                if service_id in self.ocr_services and self.ocr_services[service_id].is_active:
                    return service_id

            # 2. 寻找负载最轻的可用服务
            best_service_id = None
            min_window_count = float('inf')

            for service_id, service_instance in self.ocr_services.items():
                if service_instance.is_active and service_instance.can_accept_window():
                    window_count = service_instance.get_window_count()
                    if window_count < min_window_count:
                        min_window_count = window_count
                        best_service_id = service_id

            # 3. 如果找到合适的服务，分配窗口
            if best_service_id:
                service_instance = self.ocr_services[best_service_id]
                if service_instance.add_window(window_hwnd, window_title):
                    self.window_service_mapping[window_hwnd] = best_service_id
                    logger.info(f"窗口分配到现有服务: {window_title} (HWND: {window_hwnd}) -> {best_service_id} "
                               f"(当前窗口数: {service_instance.get_window_count()}/{service_instance.max_windows})")
                    return best_service_id

            # 4. 如果没有可用服务且未达到服务上限，创建新服务
            if len(self.ocr_services) < self.max_services:
                new_service_id = self._generate_service_id()
                new_service = self._create_ocr_service(new_service_id)

                if new_service and new_service.add_window(window_hwnd, window_title):
                    self.ocr_services[new_service_id] = new_service
                    self.window_service_mapping[window_hwnd] = new_service_id
                    logger.info(f"创建新服务并分配窗口: {window_title} (HWND: {window_hwnd}) -> {new_service_id} "
                               f"(服务数: {len(self.ocr_services)}/{self.max_services})")
                    return new_service_id

            # 5. 服务池已满，无法分配
            logger.warning(f"无法为窗口分配OCR服务: {window_title} (HWND: {window_hwnd}) - "
                          f"服务池已满 ({len(self.ocr_services)}/{self.max_services})")
            return None
    
    def _generate_request_id(self) -> str:
        """生成请求ID"""
        with self._counter_lock:
            self._request_counter += 1
            return f"ocr_req_{self._request_counter}_{int(time.time() * 1000)}"
    
    def _create_ocr_service(self, service_id: str) -> Optional[OCRServiceInstance]:
        """创建新的OCR服务实例 - 支持多窗口共享"""
        try:
            logger.info(f"创建OCR服务实例: {service_id}")

            if not FASTDEPLOY_AVAILABLE:
                logger.error("FastDeploy不可用，无法创建OCR服务")
                return None

            # 创建独立的OCR服务实例
            ocr_service = FastDeployOCRService()

            # 初始化OCR服务
            if not ocr_service.initialize():
                logger.error(f"OCR服务初始化失败: {service_id}")
                return None

            # 创建服务实例 - 不绑定特定窗口
            service_instance = OCRServiceInstance(
                service_id=service_id,
                ocr_service=ocr_service,
                is_active=True,
                last_used=time.time(),
                max_windows=self.max_windows_per_service
            )

            logger.info(f"成功 OCR服务实例创建成功: {service_id} (最大窗口数: {self.max_windows_per_service})")
            return service_instance

        except Exception as e:
            logger.error(f"创建OCR服务实例失败: {service_id}, 错误: {e}")
            return None
    
    def preregister_window(self, window_title: str, window_hwnd: int) -> bool:
        """
        预注册窗口，使用智能分配策略

        Args:
            window_title: 窗口标题
            window_hwnd: 窗口句柄

        Returns:
            bool: 是否成功分配服务
        """
        # 使用智能分配逻辑
        service_id = self._find_best_service_for_window(window_hwnd, window_title)

        if service_id:
            logger.info(f"成功 为窗口分配OCR服务: {window_title} (HWND: {window_hwnd}) -> {service_id}")
            return True
        else:
            logger.error(f"错误 为窗口分配OCR服务失败: {window_title} (HWND: {window_hwnd})")
            return False



    def unregister_window(self, window_hwnd: int) -> bool:
        """
        注销窗口，清理对应的OCR服务

        Args:
            window_hwnd: 窗口句柄

        Returns:
            bool: 是否成功清理服务
        """
        with self._pool_lock:
            if window_hwnd in self.window_service_mapping:
                service_id = self.window_service_mapping[window_hwnd]

                # 移除服务
                if service_id in self.ocr_services:
                    window_title = self.ocr_services[service_id].window_title
                    self._remove_service(service_id)
                    logger.info(f"成功 窗口关闭，已清理OCR服务: {window_title} (HWND: {window_hwnd}) -> {service_id}")

                # 移除映射
                del self.window_service_mapping[window_hwnd]
                return True
            else:
                logger.debug(f"窗口无对应OCR服务: HWND {window_hwnd}")
                return False

    def check_and_cleanup_closed_windows(self):
        """检查并清理已关闭窗口的OCR服务"""
        try:
            import win32gui

            with self._pool_lock:
                closed_windows = []

                # 自动检测已禁用，因为雷电模拟器的窗口关闭机制特殊
                # 所有常规检测方法都无法准确判断窗口是否真正关闭
                logger.debug(f"跳过自动窗口检测，当前有 {len(self.window_service_mapping)} 个窗口绑定")

        except ImportError:
            logger.warning("win32gui不可用，无法检查窗口状态")
        except Exception as e:
            logger.error(f"检查窗口状态失败: {e}")





    def get_or_create_service(self, window_title: str, window_hwnd: int) -> Optional[str]:
        """
        获取或创建窗口对应的OCR服务 - 使用智能分配策略

        Args:
            window_title: 窗口标题
            window_hwnd: 窗口句柄

        Returns:
            str: 服务ID，失败返回None
        """
        # 使用智能分配逻辑
        service_id = self._find_best_service_for_window(window_hwnd, window_title)

        if service_id:
            # 更新服务使用时间
            with self._pool_lock:
                if service_id in self.ocr_services:
                    self.ocr_services[service_id].last_used = time.time()

            return service_id
        else:
            logger.error(f"无法为窗口分配OCR服务: {window_title} (HWND: {window_hwnd})")
            return None
    
    def recognize_text(self, window_title: str, window_hwnd: int, image, confidence: float = 0.5) -> List[Dict]:
        """
        执行OCR识别
        
        Args:
            window_title: 窗口标题
            window_hwnd: 窗口句柄
            image: 图像数据
            confidence: 置信度阈值
            
        Returns:
            List[Dict]: OCR结果
        """
        start_time = time.time()
        
        try:
            # 获取或创建OCR服务
            service_id = self.get_or_create_service(window_title, window_hwnd)
            if not service_id:
                logger.error(f"无法获取OCR服务: {window_title}")
                return []
            
            # 获取服务实例
            with self._pool_lock:
                if service_id not in self.ocr_services:
                    logger.error(f"OCR服务不存在: {service_id}")
                    return []
                
                service_instance = self.ocr_services[service_id]
                if not service_instance.is_active:
                    logger.error(f"OCR服务未激活: {service_id}")
                    return []
            
            # 执行OCR识别
            logger.debug(f"执行OCR识别: {service_id} (窗口: {window_title})")
            results = service_instance.ocr_service.recognize_text(image, confidence)
            
            # 更新统计信息
            processing_time = time.time() - start_time
            with self._pool_lock:
                service_instance.last_used = time.time()
                service_instance.total_requests += 1
                service_instance.total_processing_time += processing_time
            
            logger.debug(f"OCR识别完成: {service_id}, 耗时: {processing_time:.2f}s, 结果数: {len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"OCR识别异常: {window_title}, 错误: {e}")
            return []
    
    def _cleanup_inactive_services(self):
        """清理不活跃的OCR服务"""
        current_time = time.time()
        services_to_remove = []
        
        with self._pool_lock:
            for service_id, service_instance in self.ocr_services.items():
                # 检查服务是否超时未使用
                if current_time - service_instance.last_used > self._service_timeout:
                    services_to_remove.append(service_id)
                    logger.info(f"标记清理OCR服务: {service_id} (超时未使用)")
            
            # 移除超时服务
            for service_id in services_to_remove:
                self._remove_service(service_id)
        
        if services_to_remove:
            logger.info(f"已清理 {len(services_to_remove)} 个不活跃的OCR服务")
    
    def _remove_service(self, service_id: str):
        """移除OCR服务 - 支持多窗口清理"""
        try:
            if service_id in self.ocr_services:
                service_instance = self.ocr_services[service_id]

                # 清理所有相关的窗口映射
                hwnds_to_remove = []
                for hwnd, sid in self.window_service_mapping.items():
                    if sid == service_id:
                        hwnds_to_remove.append(hwnd)

                # 移除所有窗口映射
                for hwnd in hwnds_to_remove:
                    del self.window_service_mapping[hwnd]

                # 清理服务实例
                service_instance.is_active = False
                del self.ocr_services[service_id]

                logger.debug(f"OCR服务已移除: {service_id} (清理了 {len(hwnds_to_remove)} 个窗口映射)")

        except Exception as e:
            logger.error(f"移除OCR服务失败: {service_id}, 错误: {e}")
    
    def remove_window_service(self, window_hwnd: int):
        """移除指定窗口的OCR服务 - 支持多窗口共享"""
        with self._pool_lock:
            if window_hwnd in self.window_service_mapping:
                service_id = self.window_service_mapping[window_hwnd]

                # 从服务中移除窗口
                if service_id in self.ocr_services:
                    service_instance = self.ocr_services[service_id]
                    service_instance.remove_window(window_hwnd)

                    # 从映射中移除
                    del self.window_service_mapping[window_hwnd]

                    # 如果服务没有窗口了，移除整个服务
                    if service_instance.is_empty():
                        self._remove_service(service_id)
                        logger.info(f"已移除空OCR服务: {service_id} (窗口 HWND {window_hwnd} 已移除)")
                    else:
                        logger.info(f"已从OCR服务移除窗口: HWND {window_hwnd} -> {service_id} "
                                   f"(剩余窗口数: {service_instance.get_window_count()})")
                else:
                    # 清理无效映射
                    del self.window_service_mapping[window_hwnd]
                    logger.warning(f"清理无效窗口映射: HWND {window_hwnd}")
            else:
                logger.debug(f"窗口未找到对应的OCR服务: HWND {window_hwnd}")
    
    def _update_performance_stats(self):
        """更新性能统计"""
        try:
            with self._pool_lock:
                active_services = sum(1 for s in self.ocr_services.values() if s.is_active)
                total_requests = sum(s.total_requests for s in self.ocr_services.values())
                total_time = sum(s.total_processing_time for s in self.ocr_services.values())
                
                # 获取内存使用情况
                memory_mb = 0.0
                if PSUTIL_AVAILABLE:
                    try:
                        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                    except Exception as e:
                        logger.debug(f"获取内存信息失败: {e}")
                        memory_mb = 0.0

                self._performance_stats.update({
                    "total_services": len(self.ocr_services),
                    "active_services": active_services,
                    "total_requests": total_requests,
                    "average_processing_time": total_time / max(total_requests, 1),
                    "memory_usage_mb": memory_mb
                })
                
        except Exception as e:
            logger.error(f"更新性能统计失败: {e}")
    
    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        self._update_performance_stats()
        return self._performance_stats.copy()
    
    def get_service_info(self) -> List[Dict]:
        """获取所有服务信息 - 包含多窗口信息"""
        with self._pool_lock:
            services_info = []
            for service_id, service_instance in self.ocr_services.items():
                avg_time = (service_instance.total_processing_time /
                           max(service_instance.total_requests, 1))

                services_info.append({
                    "service_id": service_id,
                    "assigned_windows": service_instance.assigned_windows.copy(),
                    "window_count": service_instance.get_window_count(),
                    "max_windows": service_instance.max_windows,
                    "is_active": service_instance.is_active,
                    "total_requests": service_instance.total_requests,
                    "average_processing_time": avg_time,
                    "last_used": service_instance.last_used,
                    "can_accept_more": service_instance.can_accept_window()
                })

            return services_info
    


    def get_pool_status(self) -> Dict:
        """获取服务池状态信息"""
        with self._pool_lock:
            return {
                "pool_available": True,
                "fastdeploy_available": FASTDEPLOY_AVAILABLE,
                "max_services": self.max_services,
                "current_services": len(self.ocr_services),
                "active_services": sum(1 for s in self.ocr_services.values() if s.is_active),
                "cleanup_running": self._running,
                "cleanup_interval": self._cleanup_interval,
                "service_timeout": self._service_timeout
            }

    
    def integrate_with_stop_manager(self):
        """与停止管理器集成"""
        try:
            from services.enhanced_ocr_pool_stop_manager import get_ocr_stop_manager
            stop_manager = get_ocr_stop_manager()
            stop_manager.sync_with_ocr_pool(self)
            logger.info("已与OCR停止管理器集成")
            return True
        except Exception as e:
            logger.error(f"OCR停止管理器集成失败: {e}")
            return False

    def request_graceful_shutdown(self, timeout: float = 10.0):
        """请求优雅关闭OCR服务池"""
        logger.info("请求优雅关闭OCR服务池...")

        try:
            # 使用停止管理器进行优雅关闭
            from services.enhanced_ocr_pool_stop_manager import get_ocr_stop_manager
            stop_manager = get_ocr_stop_manager()
            stop_manager.sync_with_ocr_pool(self)

            # 停止所有服务
            success = stop_manager.request_stop_all_services(timeout=timeout)

            if success:
                logger.info("OCR服务池优雅关闭成功")
            else:
                logger.warning("OCR服务池优雅关闭部分失败，执行强制关闭")
                self.shutdown()

            return success

        except Exception as e:
            logger.error(f"OCR服务池优雅关闭失败: {e}")
            # 回退到强制关闭
            self.shutdown()
            return False

    def integrate_with_stop_manager(self):
        """与停止管理器集成"""
        try:
            from services.enhanced_ocr_pool_stop_manager import get_ocr_stop_manager
            stop_manager = get_ocr_stop_manager()
            stop_manager.sync_with_ocr_pool(self)
            logger.info("已与OCR停止管理器集成")
            return True
        except Exception as e:
            logger.error(f"OCR停止管理器集成失败: {e}")
            return False

    def request_graceful_shutdown(self, timeout: float = 10.0):
        """请求优雅关闭OCR服务池"""
        logger.info("请求优雅关闭OCR服务池...")

        try:
            # 使用停止管理器进行优雅关闭
            from services.enhanced_ocr_pool_stop_manager import get_ocr_stop_manager
            stop_manager = get_ocr_stop_manager()
            stop_manager.sync_with_ocr_pool(self)

            # 停止所有服务
            success = stop_manager.request_stop_all_services(timeout=timeout)

            if success:
                logger.info("OCR服务池优雅关闭成功")
            else:
                logger.warning("OCR服务池优雅关闭部分失败，执行强制关闭")
                self.shutdown()

            return success

        except Exception as e:
            logger.error(f"OCR服务池优雅关闭失败: {e}")
            # 回退到强制关闭
            self.shutdown()
            return False

    def shutdown(self):
        """关闭OCR服务池"""
        logger.info("正在关闭多OCR服务池...")

        self._running = False

        # 等待清理线程结束
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)

        # 清理所有服务
        with self._pool_lock:
            service_ids = list(self.ocr_services.keys())
            for service_id in service_ids:
                self._remove_service(service_id)

        logger.info("多OCR服务池已关闭")


# 全局实例
_multi_ocr_pool = None
_pool_lock = threading.Lock()

def get_multi_ocr_pool() -> MultiOCRPool:
    """获取全局多OCR服务池实例"""
    global _multi_ocr_pool
    if _multi_ocr_pool is None:
        with _pool_lock:
            if _multi_ocr_pool is None:
                # 根据CPU核心数和内存确定最大服务数
                if PSUTIL_AVAILABLE:
                    cpu_count = psutil.cpu_count()
                    memory_gb = psutil.virtual_memory().total / (1024**3)

                    # 基于CPU核心数的基础服务数
                    cpu_based_max = cpu_count

                    # 基于内存的服务数限制 (每个OCR服务约占用80MB)
                    memory_based_max = int(memory_gb * 1024 / 80)  # 保守估计每服务80MB

                    # 取两者较小值，但至少20个，最多50个
                    max_services = max(20, min(cpu_based_max, memory_based_max, 50))

                    logger.info(f"OCR服务池配置: CPU核心={cpu_count}, 内存={memory_gb:.1f}GB, 最大服务数={max_services}")
                else:
                    # 如果psutil不可用，使用默认值
                    import os
                    cpu_count = os.cpu_count() or 4
                    # 没有内存信息时，基于CPU核心数，但至少20个
                    max_services = max(20, min(cpu_count * 2, 30))
                _multi_ocr_pool = MultiOCRPool(max_services=max_services)
    return _multi_ocr_pool


def cleanup_ocr_services_on_stop():
    """停止时清理OCR服务"""
    try:
        ocr_pool = get_multi_ocr_pool()
        ocr_pool.request_graceful_shutdown(timeout=5.0)
        logger.info("已清理OCR服务池")
    except Exception as e:
        logger.error(f"清理OCR服务池失败: {e}")
