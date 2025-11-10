"""
CPU信息检测工具
跨平台检测CPU核心数、线程数等信息，为并行处理提供最优配置

支持平台：
- Windows: 使用wmic和环境变量
- Linux: 使用/proc/cpuinfo和nproc
- macOS: 使用sysctl
"""

import os
import platform
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CPUInfoDetector:
    """CPU信息检测器"""
    
    def __init__(self):
        self._cache = {}
        self._detected = False
    
    def detect_cpu_info(self) -> Dict[str, Any]:
        """
        检测CPU信息
        
        Returns:
            Dict[str, Any]: CPU信息字典
        """
        if self._detected:
            return self._cache.copy()
        
        info = {
            'system': platform.system(),
            'processor': platform.processor(),
            'machine': platform.machine(),
            'physical_cores': os.cpu_count() or 4,
            'logical_cores': os.cpu_count() or 4,
            'optimal_threads': 4,
            'detection_method': 'default'
        }
        
        try:
            # 检测逻辑核心数（包含超线程）
            logical_cores = self._detect_logical_cores()
            if logical_cores > info['physical_cores']:
                info['logical_cores'] = logical_cores
                info['detection_method'] = 'advanced'
            
            # 计算最优线程数
            info['optimal_threads'] = self._calculate_optimal_threads(info['logical_cores'])
            
        except Exception as e:
            logger.debug(f"高级CPU检测失败，使用默认值: {e}")
        
        self._cache = info
        self._detected = True
        return info.copy()
    
    def _detect_logical_cores(self) -> int:
        """检测逻辑核心数"""
        system = platform.system()
        logical_cores = os.cpu_count() or 4
        
        if system == "Windows":
            logical_cores = self._detect_windows_logical_cores()
        elif system == "Linux":
            logical_cores = self._detect_linux_logical_cores()
        elif system == "Darwin":  # macOS
            logical_cores = self._detect_macos_logical_cores()
        
        return logical_cores
    
    def _detect_windows_logical_cores(self) -> int:
        """Windows平台检测逻辑核心数"""
        logical_cores = os.cpu_count() or 4
        
        try:
            # 方法1: 使用wmic命令
            import subprocess
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'NumberOfLogicalProcessors', '/value'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'NumberOfLogicalProcessors=' in line:
                        value = line.split('=')[1].strip()
                        if value.isdigit():
                            logical_cores = int(value)
                            logger.debug(f"Windows wmic检测到逻辑核心数: {logical_cores}")
                            return logical_cores
        except Exception as e:
            logger.debug(f"Windows wmic检测失败: {e}")
        
        try:
            # 方法2: 使用环境变量
            processors = os.environ.get('NUMBER_OF_PROCESSORS')
            if processors and processors.isdigit():
                logical_cores = int(processors)
                logger.debug(f"Windows环境变量检测到逻辑核心数: {logical_cores}")
        except Exception as e:
            logger.debug(f"Windows环境变量检测失败: {e}")
        
        return logical_cores
    
    def _detect_linux_logical_cores(self) -> int:
        """Linux平台检测逻辑核心数"""
        logical_cores = os.cpu_count() or 4
        
        try:
            # 方法1: 读取/proc/cpuinfo
            with open('/proc/cpuinfo', 'r') as f:
                processors = len([line for line in f if line.startswith('processor')])
                if processors > 0:
                    logical_cores = processors
                    logger.debug(f"Linux /proc/cpuinfo检测到逻辑核心数: {logical_cores}")
                    return logical_cores
        except Exception as e:
            logger.debug(f"Linux /proc/cpuinfo检测失败: {e}")
        
        try:
            # 方法2: 使用nproc命令
            import subprocess
            result = subprocess.run(['nproc'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                nproc_count = int(result.stdout.strip())
                logical_cores = nproc_count
                logger.debug(f"Linux nproc检测到逻辑核心数: {logical_cores}")
        except Exception as e:
            logger.debug(f"Linux nproc检测失败: {e}")
        
        return logical_cores
    
    def _detect_macos_logical_cores(self) -> int:
        """macOS平台检测逻辑核心数"""
        logical_cores = os.cpu_count() or 4
        
        try:
            # 使用sysctl命令
            import subprocess
            result = subprocess.run(
                ['sysctl', '-n', 'hw.logicalcpu'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                sysctl_count = int(result.stdout.strip())
                logical_cores = sysctl_count
                logger.debug(f"macOS sysctl检测到逻辑核心数: {logical_cores}")
        except Exception as e:
            logger.debug(f"macOS sysctl检测失败: {e}")
        
        return logical_cores
    
    def _calculate_optimal_threads(self, logical_cores: int) -> int:
        """计算最优线程数"""
        # 图片识别是I/O和CPU混合任务
        # 使用逻辑核心数作为基础
        optimal = logical_cores
        
        # 设置合理范围
        optimal = max(2, min(optimal, 64))
        
        # 对于高核心数CPU，可以适当增加线程数
        if logical_cores >= 16:
            optimal = min(logical_cores + 4, 64)
        elif logical_cores >= 8:
            optimal = min(logical_cores + 2, 32)
        
        return optimal
    
    def get_optimal_thread_count(self) -> int:
        """获取推荐的线程数"""
        info = self.detect_cpu_info()
        return info['optimal_threads']
    
    def print_cpu_info(self):
        """打印CPU信息"""
        info = self.detect_cpu_info()
        
        print("=" * 50)
        print("CPU信息检测结果")
        print("=" * 50)
        print(f"系统: {info['system']}")
        print(f"处理器: {info['processor']}")
        print(f"架构: {info['machine']}")
        print(f"物理核心数: {info['physical_cores']}")
        print(f"逻辑核心数: {info['logical_cores']}")
        print(f"推荐线程数: {info['optimal_threads']}")
        print(f"检测方法: {info['detection_method']}")
        
        # 显示超线程信息
        if info['logical_cores'] > info['physical_cores']:
            ratio = info['logical_cores'] / info['physical_cores']
            print(f"超线程倍数: {ratio:.1f}x")
        else:
            print("超线程: 未检测到或不支持")
        
        print("=" * 50)

# 全局实例
_cpu_detector = None

def get_cpu_detector() -> CPUInfoDetector:
    """获取全局CPU检测器实例"""
    global _cpu_detector
    if _cpu_detector is None:
        _cpu_detector = CPUInfoDetector()
    return _cpu_detector

def detect_optimal_thread_count() -> int:
    """快速获取最优线程数"""
    detector = get_cpu_detector()
    return detector.get_optimal_thread_count()

def get_cpu_info() -> Dict[str, Any]:
    """快速获取CPU信息"""
    detector = get_cpu_detector()
    return detector.detect_cpu_info()

if __name__ == "__main__":
    # 命令行运行时显示CPU信息
    detector = CPUInfoDetector()
    detector.print_cpu_info()
    
    # 测试多次检测的一致性
    print("\n测试检测一致性:")
    for i in range(3):
        optimal = detector.get_optimal_thread_count()
        print(f"第{i+1}次检测推荐线程数: {optimal}")
