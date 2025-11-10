"""
优化后的异步多窗口执行器使用示例
展示现代异步编程模式的使用方法
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.unified_multi_window_executor import (
    UnifiedMultiWindowExecutor, 
    ExecutionMode, 
    WindowExecutionState,
    TaskStatus
)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AsyncExecutorDemo:
    """异步执行器演示类"""
    
    def __init__(self):
        self.executor = UnifiedMultiWindowExecutor()
        self.setup_executor()
    
    def setup_executor(self):
        """设置执行器"""
        # 启用异步模式
        self.executor.set_async_mode(True)
        
        # 设置完成策略
        self.executor.set_completion_strategy(auto_stop_on_first=False)
        
        # 添加示例窗口
        self.add_demo_windows()
    
    def add_demo_windows(self):
        """添加演示窗口"""
        demo_windows = [
            ("剑网3", 12345, True),
            ("剑网3_2", 12346, True),
            ("剑网3_3", 12347, True),
            ("剑网3_4", 12348, False),  # 禁用的窗口
            ("剑网3_5", 12349, True),
        ]
        
        for title, hwnd, enabled in demo_windows:
            self.executor.add_window(title, hwnd, enabled)
            logger.info(f"添加窗口: {title} (HWND: {hwnd}, 启用: {enabled})")

    async def demo_parallel_execution(self):
        """演示并行异步执行"""
        logger.info("=== 演示并行异步执行 ===")
        
        workflow_data = {
            'cards': self.create_demo_workflow(),
            'connections': [],
            'task_modules': {},
            'images_dir': None
        }
        
        try:
            # 异步并行执行
            success = await self.executor.start_execution_async(
                workflow_data=workflow_data,
                delay_ms=500,
                execution_mode=ExecutionMode.PARALLEL
            )
            
            logger.info(f"并行执行结果: {'成功' if success else '失败'}")
            
            # 获取性能统计
            stats = await self.executor.get_async_performance_stats()
            self.print_performance_stats(stats)
            
        except Exception as e:
            logger.error(f"并行执行失败: {e}")

    async def demo_streaming_execution(self):
        """演示流式异步执行"""
        logger.info("=== 演示流式异步执行 ===")
        
        workflow_data = {
            'cards': self.create_demo_workflow(),
            'connections': [],
            'task_modules': {},
            'images_dir': None
        }
        
        try:
            # 异步流式执行
            success = await self.executor.start_execution_async(
                workflow_data=workflow_data,
                delay_ms=200,
                execution_mode=ExecutionMode.STREAMING
            )
            
            logger.info(f"流式执行结果: {'成功' if success else '失败'}")
            
        except Exception as e:
            logger.error(f"流式执行失败: {e}")

    async def demo_batch_execution(self):
        """演示批处理异步执行"""
        logger.info("=== 演示批处理异步执行 ===")
        
        # 设置批处理大小
        self.executor.sync_config.batch_size = 2
        
        workflow_data = {
            'cards': self.create_demo_workflow(),
            'connections': [],
            'task_modules': {},
            'images_dir': None
        }
        
        try:
            # 异步批处理执行
            success = await self.executor.start_execution_async(
                workflow_data=workflow_data,
                delay_ms=300,
                execution_mode=ExecutionMode.BATCH
            )
            
            logger.info(f"批处理执行结果: {'成功' if success else '失败'}")
            
        except Exception as e:
            logger.error(f"批处理执行失败: {e}")

    async def demo_error_handling(self):
        """演示错误处理和重试机制"""
        logger.info("=== 演示错误处理和重试机制 ===")
        
        # 创建会失败的工作流
        workflow_data = {
            'cards': self.create_failing_workflow(),
            'connections': [],
            'task_modules': {},
            'images_dir': None
        }
        
        try:
            success = await self.executor.start_execution_async(
                workflow_data=workflow_data,
                delay_ms=100,
                execution_mode=ExecutionMode.PARALLEL
            )
            
            logger.info(f"错误处理测试结果: {'成功' if success else '失败'}")
            
            # 检查窗口状态
            for window in self.executor.windows.values():
                logger.info(f"窗口 {window.title}: 状态={window.status.value}, 错误={window.last_error}")
            
        except Exception as e:
            logger.error(f"错误处理测试失败: {e}")

    async def demo_graceful_cancellation(self):
        """演示优雅取消机制"""
        logger.info("=== 演示优雅取消机制 ===")
        
        workflow_data = {
            'cards': self.create_long_running_workflow(),
            'connections': [],
            'task_modules': {},
            'images_dir': None
        }
        
        try:
            # 启动长时间运行的任务
            execution_task = asyncio.create_task(
                self.executor.start_execution_async(
                    workflow_data=workflow_data,
                    delay_ms=100,
                    execution_mode=ExecutionMode.PARALLEL
                )
            )
            
            # 等待一段时间后取消
            await asyncio.sleep(2.0)
            logger.info("请求取消执行...")
            
            # 异步停止
            stop_success = await self.executor.stop_all_async(timeout=10.0)
            logger.info(f"停止结果: {'成功' if stop_success else '失败'}")
            
            # 等待执行任务完成
            try:
                await execution_task
            except asyncio.CancelledError:
                logger.info("执行任务已被取消")
            
        except Exception as e:
            logger.error(f"取消测试失败: {e}")

    def create_demo_workflow(self) -> List[Dict[str, Any]]:
        """创建演示工作流"""
        return [
            {
                'id': 1,
                'task_type': '起点',
                'params': {}
            },
            {
                'id': 2,
                'task_type': '延迟',
                'params': {
                    'delay_seconds': 1,
                    'random_delay': False
                }
            },
            {
                'id': 3,
                'task_type': '终点',
                'params': {}
            }
        ]

    def create_failing_workflow(self) -> List[Dict[str, Any]]:
        """创建会失败的工作流"""
        return [
            {
                'id': 1,
                'task_type': '起点',
                'params': {}
            },
            {
                'id': 2,
                'task_type': '模拟失败',
                'params': {
                    'failure_rate': 0.7  # 70% 失败率
                }
            }
        ]

    def create_long_running_workflow(self) -> List[Dict[str, Any]]:
        """创建长时间运行的工作流"""
        return [
            {
                'id': 1,
                'task_type': '起点',
                'params': {}
            },
            {
                'id': 2,
                'task_type': '延迟',
                'params': {
                    'delay_seconds': 10,  # 长时间延迟
                    'random_delay': False
                }
            }
        ]

    def print_performance_stats(self, stats: Dict[str, Any]):
        """打印性能统计"""
        logger.info("=== 性能统计 ===")
        
        if 'error' in stats:
            logger.error(f"获取统计失败: {stats['error']}")
            return
        
        perf = stats.get('performance', {})
        resources = stats.get('resources', {})
        tasks = stats.get('async_tasks', {})
        windows = stats.get('windows', {})
        
        logger.info(f"性能指标:")
        logger.info(f"  - 总窗口数: {perf.get('total_windows', 0)}")
        logger.info(f"  - 成功窗口: {perf.get('successful_windows', 0)}")
        logger.info(f"  - 失败窗口: {perf.get('failed_windows', 0)}")
        logger.info(f"  - 平均执行时间: {perf.get('average_execution_time', 0):.2f}秒")
        
        logger.info(f"资源使用:")
        logger.info(f"  - 活跃窗口资源: {resources.get('windows_active', 0)}")
        logger.info(f"  - 活跃OCR资源: {resources.get('ocr_active', 0)}")
        logger.info(f"  - 队列深度: {resources.get('queue_depth', 0)}")
        
        logger.info(f"异步任务:")
        logger.info(f"  - 总任务数: {tasks.get('total', 0)}")
        logger.info(f"  - 运行中: {tasks.get('running', 0)}")
        logger.info(f"  - 已完成: {tasks.get('completed', 0)}")
        logger.info(f"  - 已取消: {tasks.get('cancelled', 0)}")


async def main():
    """主函数"""
    logger.info("开始异步执行器演示")
    
    demo = AsyncExecutorDemo()
    
    try:
        # 演示各种执行模式
        await demo.demo_parallel_execution()
        await asyncio.sleep(1)
        
        await demo.demo_streaming_execution()
        await asyncio.sleep(1)
        
        await demo.demo_batch_execution()
        await asyncio.sleep(1)
        
        await demo.demo_error_handling()
        await asyncio.sleep(1)
        
        await demo.demo_graceful_cancellation()
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
    
    finally:
        # 清理资源
        demo.executor.cleanup()
        logger.info("演示完成，资源已清理")


if __name__ == "__main__":
    # 运行异步演示
    asyncio.run(main())
