#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动清理失效窗口
"""

import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def manual_cleanup():
    """手动清理失效窗口"""
    try:
        import win32gui
        
        print("🔍 开始手动清理失效窗口...")
        
        # 读取当前配置
        config_file = "config.json"
        if not os.path.exists(config_file):
            print("❌ 配置文件不存在")
            return
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        bound_windows = config.get('bound_windows', [])
        print(f"配置文件中有 {len(bound_windows)} 个绑定窗口")
        
        # 清理失效窗口
        valid_windows = []
        removed_count = 0
        
        for window_info in bound_windows:
            title = window_info.get('title', '')
            hwnd = window_info.get('hwnd', 0)
            
            print(f"\n检查窗口: {title} (HWND: {hwnd})")
            
            is_valid = False
            try:
                if hwnd and hwnd != 0:
                    window_exists = win32gui.IsWindow(hwnd)
                    window_visible = win32gui.IsWindowVisible(hwnd) if window_exists else False
                    
                    current_title = ""
                    if window_exists:
                        try:
                            current_title = win32gui.GetWindowText(hwnd)
                        except:
                            pass
                    
                    if window_exists and window_visible and current_title:
                        # 检查窗口类型：现在我们只保留渲染窗口
                        window_class = ""
                        try:
                            window_class = win32gui.GetClassName(hwnd)
                        except:
                            pass

                        if "nemudisplay" in current_title.lower() and window_class == "nemuwin":
                            is_valid = True
                            print(f"  ✅ 窗口有效(渲染窗口) (当前标题: {current_title}, 类名: {window_class})")
                        elif ("安卓设备" in current_title or "Android" in current_title):
                            is_valid = False
                            print(f"  ❌ 清理主窗口 - 现在使用渲染窗口 (当前标题: {current_title}, 类名: {window_class})")
                        else:
                            is_valid = True
                            print(f"  ✅ 窗口有效(其他类型) (当前标题: {current_title})")
                    else:
                        print(f"  ❌ 窗口失效 - 存在:{window_exists}, 可见:{window_visible}, 标题:'{current_title}'")
                else:
                    print(f"  ❌ 窗口失效 - 无有效句柄")
            except Exception as e:
                print(f"  ❌ 检查失败: {e}")
            
            if is_valid:
                valid_windows.append(window_info)
            else:
                removed_count += 1
                print(f"  🗑️ 将移除此窗口")
        
        print(f"\n📊 清理结果:")
        print(f"  有效窗口: {len(valid_windows)} 个")
        print(f"  移除窗口: {removed_count} 个")
        
        if removed_count > 0:
            # 更新配置文件
            config['bound_windows'] = valid_windows
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            print(f"\n✅ 已更新配置文件，移除了 {removed_count} 个失效窗口")
        else:
            print(f"\n✅ 没有发现失效窗口，无需清理")
        
        return valid_windows
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        return []

def main():
    """主函数"""
    print("🚀 开始手动清理失效窗口")
    print("=" * 50)
    
    valid_windows = manual_cleanup()
    
    print("\n" + "=" * 50)
    print("✅ 清理完成")
    
    if valid_windows:
        print(f"\n📋 剩余有效窗口:")
        for i, window in enumerate(valid_windows):
            title = window.get('title', '')
            hwnd = window.get('hwnd', 0)
            print(f"  {i+1}. {title} (HWND: {hwnd})")

if __name__ == "__main__":
    main()
