"""
并行图片识别演示脚本
展示CPU检测和并行识别的效果

运行方式：
python examples/parallel_recognition_demo.py
"""

import sys
import os
import time
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def demo_cpu_detection():
    """演示CPU检测功能"""
    print("🔍 CPU信息检测演示")
    print("=" * 60)
    
    try:
        from utils.cpu_info_detector import CPUInfoDetector
        
        detector = CPUInfoDetector()
        detector.print_cpu_info()
        
        # 显示检测性能
        start_time = time.time()
        for i in range(10):
            optimal = detector.get_optimal_thread_count()
        detection_time = (time.time() - start_time) / 10
        
        print(f"\n检测性能: 平均耗时 {detection_time*1000:.2f}ms")
        
    except ImportError as e:
        print(f"❌ CPU检测模块导入失败: {e}")
    except Exception as e:
        print(f"❌ CPU检测演示失败: {e}")

def demo_parallel_recognition():
    """演示并行识别功能"""
    print("\n🚀 并行识别功能演示")
    print("=" * 60)
    
    try:
        from tasks.parallel_image_recognition import get_parallel_recognizer, RecognitionMode
        import numpy as np
        
        # 创建测试数据
        test_images = create_demo_images()
        if not test_images:
            print("❌ 无法创建测试图片")
            return
        
        # 创建测试截图
        screenshot = create_demo_screenshot()
        
        # 测试参数
        params = {
            'confidence': 0.6,
            'preprocessing_method': '无'
        }
        
        print(f"📊 测试配置:")
        print(f"  图片数量: {len(test_images)}")
        print(f"  截图尺寸: {screenshot.shape}")
        
        # 获取并行识别器
        recognizer = get_parallel_recognizer()
        print(f"  线程数: {recognizer.max_workers}")
        
        # 执行并行识别
        print(f"\n🔄 执行并行识别...")
        start_time = time.time()
        
        results = recognizer.recognize_images_parallel(
            image_paths=test_images,
            params=params,
            execution_mode='foreground',
            target_hwnd=None,
            mode=RecognitionMode.ALL_MATCHES
        )
        
        total_time = time.time() - start_time
        
        # 显示结果
        print(f"\n📈 识别结果:")
        print(f"  总耗时: {total_time:.2f}s")
        print(f"  平均耗时: {total_time/len(test_images):.2f}s/图片")
        print(f"  成功数量: {sum(1 for r in results if r.success)}/{len(results)}")
        
        # 显示详细结果
        for i, result in enumerate(results):
            status = "✅" if result.success else "❌"
            print(f"  图片{i+1}: {status} 置信度={result.confidence:.3f} 耗时={result.processing_time:.3f}s")
        
        # 清理测试文件
        cleanup_demo_images(test_images)
        
    except ImportError as e:
        print(f"❌ 并行识别模块导入失败: {e}")
    except Exception as e:
        print(f"❌ 并行识别演示失败: {e}")

def create_demo_images():
    """创建演示用的测试图片"""
    try:
        import cv2
        import numpy as np
        import tempfile
        
        test_images = []
        temp_dir = tempfile.mkdtemp(prefix='parallel_demo_')
        
        # 创建5张不同的测试图片
        colors = [
            (255, 0, 0),    # 红色
            (0, 255, 0),    # 绿色
            (0, 0, 255),    # 蓝色
            (255, 255, 0),  # 黄色
            (255, 0, 255),  # 紫色
        ]
        
        for i, color in enumerate(colors):
            # 创建图片
            img = np.zeros((80, 80, 3), dtype=np.uint8)
            cv2.rectangle(img, (10, 10), (70, 70), color, -1)
            cv2.putText(img, f'{i+1}', (35, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # 保存图片
            image_path = os.path.join(temp_dir, f'demo_{i+1}.png')
            cv2.imwrite(image_path, img)
            test_images.append(image_path)
        
        return test_images
        
    except Exception as e:
        logger.error(f"创建演示图片失败: {e}")
        return []

def create_demo_screenshot():
    """创建演示用的截图"""
    try:
        import cv2
        import numpy as np
        
        # 创建一个包含测试图片的截图
        screenshot = np.zeros((400, 600, 3), dtype=np.uint8)
        
        # 在截图中放置一些图案
        positions = [(50, 50), (200, 50), (350, 50), (125, 200), (275, 200)]
        colors = [
            (255, 0, 0),    # 红色
            (0, 255, 0),    # 绿色
            (0, 0, 255),    # 蓝色
            (255, 255, 0),  # 黄色
            (255, 0, 255),  # 紫色
        ]
        
        for i, ((x, y), color) in enumerate(zip(positions, colors)):
            cv2.rectangle(screenshot, (x, y), (x+80, y+80), color, -1)
            cv2.putText(screenshot, f'{i+1}', (x+35, y+45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return screenshot
        
    except Exception as e:
        logger.error(f"创建演示截图失败: {e}")
        return np.zeros((400, 600, 3), dtype=np.uint8)

def cleanup_demo_images(test_images):
    """清理演示图片"""
    try:
        import shutil
        
        if test_images:
            # 获取临时目录
            temp_dir = os.path.dirname(test_images[0])
            if 'parallel_demo_' in temp_dir:
                shutil.rmtree(temp_dir)
                logger.debug("演示图片清理完成")
                
    except Exception as e:
        logger.warning(f"清理演示图片失败: {e}")

def demo_performance_comparison():
    """演示性能对比"""
    print("\n⚡ 性能对比演示")
    print("=" * 60)
    
    try:
        # 模拟串行处理
        print("🐌 模拟串行处理...")
        start_time = time.time()
        
        # 模拟5张图片的串行处理
        for i in range(5):
            time.sleep(0.2)  # 模拟单张图片处理时间
            print(f"  处理图片{i+1}...")
        
        serial_time = time.time() - start_time
        print(f"  串行总耗时: {serial_time:.2f}s")
        
        # 模拟并行处理
        print("\n🚀 模拟并行处理...")
        start_time = time.time()
        
        # 模拟并行处理（所有图片同时处理）
        import threading
        import concurrent.futures
        
        def process_image(image_id):
            time.sleep(0.2)  # 模拟单张图片处理时间
            return f"图片{image_id}"
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_image, i+1) for i in range(5)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        parallel_time = time.time() - start_time
        print(f"  并行总耗时: {parallel_time:.2f}s")
        
        # 计算性能提升
        speedup = serial_time / parallel_time if parallel_time > 0 else 1
        print(f"\n📊 性能提升: {speedup:.1f}x")
        print(f"  时间节省: {((serial_time - parallel_time) / serial_time * 100):.1f}%")
        
    except Exception as e:
        print(f"❌ 性能对比演示失败: {e}")

def main():
    """主函数"""
    print("🎯 并行图片识别优化演示")
    print("=" * 80)
    
    # 1. CPU检测演示
    demo_cpu_detection()
    
    # 2. 性能对比演示
    demo_performance_comparison()
    
    # 3. 并行识别演示
    demo_parallel_recognition()
    
    print("\n✅ 演示完成！")
    print("=" * 80)
    print("💡 提示:")
    print("  - 实际性能提升取决于CPU核心数和图片复杂度")
    print("  - 建议在实际项目中启用并行识别以获得最佳性能")
    print("  - 可以通过参数 'enable_parallel_recognition' 控制是否启用")

if __name__ == "__main__":
    main()
