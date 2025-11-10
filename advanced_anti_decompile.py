#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级Python反编译保护模块
专门针对Python反编译工具的深度防护
"""

import os
import sys
import time
import hashlib
import base64
import marshal
import types
import inspect
import gc
import threading
import random
from typing import Optional, List, Dict, Any

class AdvancedAntiDecompile:
    """高级反编译保护器"""
    
    def __init__(self):
        self._protection_active = True
        self._check_interval = 30.0  # 30秒检查间隔，减少误报
        self._monitor_thread = None
        self._original_bytecode_hashes = {}

        # 精确的反编译工具特征检测（避免误报）
        self._decompile_signatures = [
            b'uncompyle6', b'decompyle3', b'pycdc', b'unpyc',
            b'pyinstxtractor', b'pyinstaller-extractor'
        ]

        # 初始化保护
        self._init_protection()

    
    def _init_protection(self):
        """初始化保护机制"""
        try:
            # 记录关键函数的原始字节码哈希
            self._record_original_bytecode()
            
            # 启动监控线程
            self._start_monitoring()
            
            # 设置异常钩子
            self._setup_exception_hooks()
            
        except Exception:
            pass  # 静默失败，不暴露保护机制
    
    def _record_original_bytecode(self):
        """记录关键函数的原始字节码哈希"""
        try:
            # 获取当前模块的所有函数
            current_module = sys.modules[__name__]
            for name, obj in inspect.getmembers(current_module):
                if inspect.isfunction(obj) and hasattr(obj, '__code__'):
                    bytecode = obj.__code__.co_code
                    hash_value = hashlib.sha256(bytecode).hexdigest()
                    self._original_bytecode_hashes[name] = hash_value
        except Exception:
            pass
    
    def _start_monitoring(self):
        """启动后台监控线程"""
        try:
            if self._monitor_thread is None or not self._monitor_thread.is_alive():
                self._monitor_thread = threading.Thread(
                    target=self._continuous_monitoring,
                    daemon=True
                )
                self._monitor_thread.start()
        except Exception:
            pass
    
    def _continuous_monitoring(self):
        """持续监控威胁"""
        while self._protection_active:
            try:
                threats_detected = []

                # 检查反编译威胁
                decompile_threats = self._detect_decompilation_attempt()
                if decompile_threats:
                    threats_detected.extend(decompile_threats)

                # 检查字节码完整性
                bytecode_threats = self._check_bytecode_integrity()
                if bytecode_threats:
                    threats_detected.extend(bytecode_threats)

                # 检查内存中的可疑模块
                module_threats = self._check_suspicious_modules()
                if module_threats:
                    threats_detected.extend(module_threats)

                # 如果检测到威胁，触发保护并显示详细信息
                if threats_detected:
                    self._trigger_protection(threats_detected)

                time.sleep(self._check_interval)

            except Exception as e:
                # 监控过程中的异常不应该影响主程序
                import logging
                logging.debug(f"监控过程异常: {e}")
                time.sleep(self._check_interval)
    
    def _detect_decompilation_attempt(self) -> list:
        """检测反编译尝试"""
        threats_found = []

        try:
            # 1. 检查进程内存中的可疑字符串（更精确的检测）
            dangerous_signatures = [
                b'uncompyle6.main', b'decompyle3.main', b'pycdc.exe',
                b'pyinstxtractor.py', b'pyinstaller-extractor'
            ]

            # 只检查字符串长度较短的对象，避免检查大文件内容
            for obj in gc.get_objects():
                if isinstance(obj, (str, bytes)) and len(str(obj)) < 200:
                    obj_data = obj if isinstance(obj, bytes) else obj.encode('utf-8', errors='ignore')
                    for signature in dangerous_signatures:
                        if signature in obj_data:
                            threats_found.append(f"内存中发现反编译工具特征: {signature.decode()}")
                            break  # 避免重复检测同一对象
            
            # 2. 检查调用栈中的可疑操作（排除自身文件）
            frame = sys._getframe()
            while frame:
                try:
                    filename = frame.f_code.co_filename
                    # 排除自身的保护文件
                    if 'advanced_anti_decompile.py' not in filename:
                        if any(keyword in filename.lower() for keyword in
                               ['uncompyle6', 'decompyle3', 'pycdc', 'pyinstxtractor']):
                            threats_found.append(f"调用栈中发现可疑文件: {filename}")

                    frame = frame.f_back
                except Exception:
                    break
            
            # 3. 检查当前目录中的可疑文件（更精确的检测）
            try:
                current_dir = os.getcwd()
                # 只检查当前目录，不递归搜索整个文件系统
                for file in os.listdir(current_dir):
                    file_path = os.path.join(current_dir, file)
                    if os.path.isfile(file_path):
                        # 只检查明确的反编译工具文件
                        if any(pattern in file.lower() for pattern in
                               ['.extracted', '.decompiled', 'uncompyle6', 'decompyle3', 'pycdc']):
                            threats_found.append(f"发现可疑文件: {file}")
            except Exception:
                pass

            return threats_found
            
        except Exception:
            return False
    
    def _check_bytecode_integrity(self) -> list:
        """检查字节码完整性"""
        threats_found = []

        try:
            current_module = sys.modules[__name__]
            for name, obj in inspect.getmembers(current_module):
                if inspect.isfunction(obj) and hasattr(obj, '__code__'):
                    if name in self._original_bytecode_hashes:
                        current_bytecode = obj.__code__.co_code
                        current_hash = hashlib.sha256(current_bytecode).hexdigest()

                        if current_hash != self._original_bytecode_hashes[name]:
                            threats_found.append(f"函数字节码被修改: {name}")

            return threats_found

        except Exception as e:
            threats_found.append(f"字节码完整性检查异常: {e}")
            return threats_found
    
    def _check_suspicious_modules(self) -> list:
        """检查可疑模块"""
        threats_found = []

        try:
            # 只检查明确的反编译工具，不检查Python内置模块
            dangerous_modules = [
                'uncompyle6', 'decompyle3', 'pycdc', 'unpyc',
                'pyinstxtractor'
            ]

            for module_name in dangerous_modules:
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    # 进一步验证是否真的是反编译工具
                    if hasattr(module, '__file__') and module.__file__:
                        threats_found.append(f"检测到反编译模块: {module_name} ({module.__file__})")
                    else:
                        threats_found.append(f"检测到反编译模块: {module_name}")

            return threats_found

        except Exception as e:
            # 不记录正常的异常
            return threats_found
    
    def _setup_exception_hooks(self):
        """设置异常钩子来检测调试尝试"""
        try:
            original_excepthook = sys.excepthook
            
            def protected_excepthook(exc_type, exc_value, exc_traceback):
                # 检查异常是否来自反编译工具
                if exc_traceback:
                    frame = exc_traceback.tb_frame
                    while frame:
                        filename = frame.f_code.co_filename
                        if any(keyword in filename.lower() for keyword in 
                               ['decompile', 'extract', 'unpack', 'debug']):
                            self._trigger_protection()
                            return
                        frame = frame.f_back
                
                # 调用原始异常处理器
                original_excepthook(exc_type, exc_value, exc_traceback)
            
            sys.excepthook = protected_excepthook
            
        except Exception:
            pass
    
    def _trigger_protection(self, threats_detected=None):
        """触发保护机制（检测到威胁直接退出）"""
        try:
            if threats_detected:
                # 详细显示检测到的威胁
                threat_details = "; ".join(threats_detected)
                print(f"严重 高级反编译保护检测到威胁: {threat_details}")

                import logging
                logging.critical(f"高级反编译保护检测到威胁: {threat_details}")

                # 分别记录每个威胁
                for threat in threats_detected:
                    logging.critical(f"威胁详情: {threat}")
            else:
                print("严重 高级反编译保护检测到未知威胁")
                import logging
                logging.critical("高级反编译保护检测到未知威胁")

            # 清理敏感数据
            self._cleanup_sensitive_data()

            # 混淆内存
            self._obfuscate_memory()

            # 强制退出程序
            print("程序因安全威胁退出")
            os._exit(1)

        except Exception as e:
            print(f"严重 保护机制触发时发生异常: {e}")
            import logging
            logging.critical(f"保护机制触发异常: {e}")
            # 即使异常也要退出
            os._exit(1)
    
    def _cleanup_sensitive_data(self):
        """清理内存中的敏感数据"""
        try:
            # 清理包含敏感信息的对象
            for obj in gc.get_objects():
                if isinstance(obj, str):
                    if any(keyword in obj for keyword in 
                           ['ED-', 'license', 'key', 'token', 'password']):
                        try:
                            # 尝试清零字符串内容（Python中字符串不可变，但可以尝试）
                            obj = '0' * len(obj)
                        except:
                            pass
            
            # 强制垃圾回收
            gc.collect()
            
        except Exception:
            pass
    
    def _obfuscate_memory(self):
        """混淆内存内容"""
        try:
            # 创建大量随机数据来混淆内存
            dummy_data = []
            for _ in range(1000):
                dummy_data.append(''.join(chr(random.randint(32, 126)) for _ in range(100)))
            
            # 立即删除
            del dummy_data
            gc.collect()
            
        except Exception:
            pass
    
    def stop_protection(self):
        """停止保护（用于正常退出）"""
        self._protection_active = False

# 全局保护实例
_global_anti_decompile = AdvancedAntiDecompile()

def init_advanced_protection():
    """初始化高级反编译保护"""
    global _global_anti_decompile
    if _global_anti_decompile is None:
        _global_anti_decompile = AdvancedAntiDecompile()

def stop_advanced_protection():
    """停止高级保护"""
    global _global_anti_decompile
    if _global_anti_decompile:
        _global_anti_decompile.stop_protection()
