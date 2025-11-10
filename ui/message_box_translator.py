# -*- coding: utf-8 -*-
"""消息框翻译模块 - 确保所有对话框按钮都显示中文"""

from PySide6.QtWidgets import QApplication, QMessageBox, QDialogButtonBox
from PySide6.QtCore import QObject, QEvent

class MessageBoxTranslator(QObject):
    """消息框翻译器，自动将英文按钮翻译为中文"""

    def __init__(self):
        super().__init__()
        self.button_translations = {
            # QMessageBox 标准按钮翻译
            "OK": "确定",
            "Ok": "确定",
            "Cancel": "取消",
            "Yes": "是",
            "No": "否",
            "Close": "关闭",
            "Apply": "应用",
            "Reset": "重置",
            "Help": "帮助",
            "Save": "保存",
            "Discard": "丢弃",
            "Don't Save": "不保存",
            "Retry": "重试",
            "Ignore": "忽略",
            "Abort": "中止",
            "Open": "打开",
            "Save All": "全部保存",
            "Yes to All": "全部是",
            "No to All": "全部否",
            "Restore Defaults": "恢复默认",

            # 常见对话框按钮翻译
            "Browse": "浏览",
            "Select": "选择",
            "Accept": "接受",
            "Reject": "拒绝",
            "Continue": "继续",
            "Stop": "停止",
            "Start": "开始",
            "Finish": "完成",
            "Next": "下一步",
            "Previous": "上一步",
            "Back": "返回",
            "Forward": "前进",
            "Details": "详情",
            "Show Details": "显示详情",
            "Hide Details": "隐藏详情",
        }

    def eventFilter(self, obj, event):
        """事件过滤器，拦截并翻译按钮文本"""
        if event.type() == QEvent.Type.Show:
            self.translate_widget_buttons(obj)
        return super().eventFilter(obj, event)

    def translate_widget_buttons(self, widget):
        """翻译小部件中的所有按钮"""
        try:
            # 处理 QMessageBox
            if isinstance(widget, QMessageBox):
                self.translate_message_box(widget)

            # 处理包含 QDialogButtonBox 的对话框
            button_boxes = widget.findChildren(QDialogButtonBox)
            for button_box in button_boxes:
                self.translate_button_box(button_box)

            # 处理所有 QPushButton
            from PySide6.QtWidgets import QPushButton
            buttons = widget.findChildren(QPushButton)
            for button in buttons:
                self.translate_button(button)

        except Exception as e:
            # 静默处理翻译错误，避免影响正常功能
            pass

    def translate_message_box(self, message_box):
        """翻译 QMessageBox 的按钮"""
        try:
            # 获取所有标准按钮
            standard_buttons = message_box.standardButtons()

            # 翻译每个标准按钮
            button_map = {
                QMessageBox.StandardButton.Ok: "确定",
                QMessageBox.StandardButton.Cancel: "取消",
                QMessageBox.StandardButton.Yes: "是",
                QMessageBox.StandardButton.No: "否",
                QMessageBox.StandardButton.Close: "关闭",
                QMessageBox.StandardButton.Apply: "应用",
                QMessageBox.StandardButton.Reset: "重置",
                QMessageBox.StandardButton.Help: "帮助",
                QMessageBox.StandardButton.Save: "保存",
                QMessageBox.StandardButton.Discard: "丢弃",
                QMessageBox.StandardButton.Retry: "重试",
                QMessageBox.StandardButton.Ignore: "忽略",
                QMessageBox.StandardButton.Abort: "中止",
                QMessageBox.StandardButton.Open: "打开",
                QMessageBox.StandardButton.SaveAll: "全部保存",
                QMessageBox.StandardButton.YesToAll: "全部是",
                QMessageBox.StandardButton.NoToAll: "全部否",
                QMessageBox.StandardButton.RestoreDefaults: "恢复默认",
            }

            for std_button, chinese_text in button_map.items():
                if standard_buttons & std_button:
                    button = message_box.button(std_button)
                    if button:
                        button.setText(chinese_text)

        except Exception as e:
            pass

    def translate_button_box(self, button_box):
        """翻译 QDialogButtonBox 的按钮"""
        try:
            button_map = {
                QDialogButtonBox.StandardButton.Ok: "确定",
                QDialogButtonBox.StandardButton.Cancel: "取消",
                QDialogButtonBox.StandardButton.Yes: "是",
                QDialogButtonBox.StandardButton.No: "否",
                QDialogButtonBox.StandardButton.Close: "关闭",
                QDialogButtonBox.StandardButton.Apply: "应用",
                QDialogButtonBox.StandardButton.Reset: "重置",
                QDialogButtonBox.StandardButton.Help: "帮助",
                QDialogButtonBox.StandardButton.Save: "保存",
                QDialogButtonBox.StandardButton.Discard: "丢弃",
                QDialogButtonBox.StandardButton.Retry: "重试",
                QDialogButtonBox.StandardButton.Ignore: "忽略",
                QDialogButtonBox.StandardButton.Abort: "中止",
                QDialogButtonBox.StandardButton.Open: "打开",
                QDialogButtonBox.StandardButton.SaveAll: "全部保存",
                QDialogButtonBox.StandardButton.YesToAll: "全部是",
                QDialogButtonBox.StandardButton.NoToAll: "全部否",
                QDialogButtonBox.StandardButton.RestoreDefaults: "恢复默认",
            }

            for std_button, chinese_text in button_map.items():
                button = button_box.button(std_button)
                if button:
                    button.setText(chinese_text)

        except Exception as e:
            pass

    def translate_button(self, button):
        """翻译单个按钮"""
        try:
            current_text = button.text().strip()
            if current_text in self.button_translations:
                button.setText(self.button_translations[current_text])
        except Exception as e:
            pass

# 全局翻译器实例
_message_box_translator = None

def setup_message_box_translations():
    """设置消息框翻译"""
    global _message_box_translator

    try:
        app = QApplication.instance()
        if app and not _message_box_translator:
            _message_box_translator = MessageBoxTranslator()
            app.installEventFilter(_message_box_translator)

            # 设置应用程序级别的按钮文本翻译
            app.setProperty("chinese_buttons", True)

    except Exception as e:
        # 静默处理设置错误
        pass

def get_message_box_translator():
    """获取消息框翻译器实例"""
    return _message_box_translator

def show_question_box(parent, title, text, buttons=None, default_button=None):
    """显示中文问题对话框"""
    from PySide6.QtWidgets import QMessageBox

    if buttons is None:
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No

    if default_button is None:
        default_button = QMessageBox.StandardButton.No

    # 创建消息框
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setStandardButtons(buttons)
    msg_box.setDefaultButton(default_button)

    # 设置中文按钮文本
    button_map = {
        QMessageBox.StandardButton.Yes: "是",
        QMessageBox.StandardButton.No: "否",
        QMessageBox.StandardButton.Ok: "确定",
        QMessageBox.StandardButton.Cancel: "取消",
        QMessageBox.StandardButton.Close: "关闭",
        QMessageBox.StandardButton.Retry: "重试",
        QMessageBox.StandardButton.Ignore: "忽略",
        QMessageBox.StandardButton.Abort: "中止",
    }

    for std_button, chinese_text in button_map.items():
        if buttons & std_button:
            button = msg_box.button(std_button)
            if button:
                button.setText(chinese_text)

    return msg_box.exec()

def show_warning_box(parent, title, text):
    """显示中文警告对话框"""
    from PySide6.QtWidgets import QMessageBox

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    # 设置确定按钮为中文
    ok_button = msg_box.button(QMessageBox.StandardButton.Ok)
    if ok_button:
        ok_button.setText("确定")

    return msg_box.exec()

def show_information_box(parent, title, text):
    """显示中文信息对话框"""
    from PySide6.QtWidgets import QMessageBox

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    # 设置确定按钮为中文
    ok_button = msg_box.button(QMessageBox.StandardButton.Ok)
    if ok_button:
        ok_button.setText("确定")

    return msg_box.exec()

def show_critical_box(parent, title, text):
    """显示中文错误对话框"""
    from PySide6.QtWidgets import QMessageBox

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    # 设置确定按钮为中文
    ok_button = msg_box.button(QMessageBox.StandardButton.Ok)
    if ok_button:
        ok_button.setText("确定")

    return msg_box.exec()
