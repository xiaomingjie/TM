import math
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsLineItem, QGraphicsPolygonItem
from PySide6.QtCore import Qt, QPointF
# QPainter, QPolygonF, QBrush are no longer needed here
from PySide6.QtGui import QPen, QColor, QPainterPath
# Import port types from TaskCard to avoid string literals here
from .task_card import PORT_TYPE_SEQUENTIAL, PORT_TYPE_SUCCESS, PORT_TYPE_FAILURE
from typing import TYPE_CHECKING, Optional
# Import Enum
from enum import Enum

# 调试开关 - 设置为 False 可以禁用所有调试输出
DEBUG_ENABLED = False

def debug_print(*args, **kwargs):
    """条件调试打印函数"""
    if DEBUG_ENABLED:
        print(*args, **kwargs)

# Forward reference for type hinting
if TYPE_CHECKING:
    from .task_card import TaskCard

# Define ConnectionType Enum
class ConnectionType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    # Add other types if needed

class ConnectionLine(QGraphicsPathItem):
    """Represents a connection line with refined style."""
    def __init__(self, start_item: 'TaskCard', end_item: 'TaskCard', line_type: str, parent=None):
        super().__init__(parent)
        debug_print(f"  [CONN_DEBUG] ConnectionLine __init__: Start={start_item.card_id}, End={end_item.card_id}, Type='{line_type}'")
        self.start_item = start_item
        self.end_item = end_item
        self.line_type = line_type
        
        self.pen = QPen()
        self.pen.setWidthF(1.5) # Make line slightly thinner
        self.set_line_color()
        self.setPen(self.pen)
        self.setZValue(-1)
        self.setBrush(Qt.BrushStyle.NoBrush) # Ensure the path item itself has no fill
        
        self.update_path()

    def set_line_color(self):
        """Sets the pen color based on the line type (less saturated)."""
        # Define less saturated colors
        # You can fine-tune these RGB values
        debug_print(f"  [CONN_DEBUG] set_line_color called for type: '{self.line_type}'")
        color_sequential = QColor(60, 140, 210) # Softer blue
        color_success = QColor(60, 160, 60)    # Softer green
        color_failure = QColor(210, 80, 80)     # Softer red
        
        color = color_sequential # Default
        if self.line_type == ConnectionType.SUCCESS.value:
            debug_print(f"    [CONN_DEBUG] Matched SUCCESS type.")
            color = color_success
        elif self.line_type == ConnectionType.FAILURE.value:
            debug_print(f"    [CONN_DEBUG] Matched FAILURE type.")
            color = color_failure
        
        self.pen.setColor(color)
        self.setPen(self.pen) # Apply the updated pen to the item

    def get_start_pos(self) -> QPointF:
        """Gets the connection point from the start item's corresponding output port."""
        if self.start_item:
            return self.start_item.get_output_port_scene_pos(self.line_type)
        return QPointF(0,0)

    def get_end_pos(self) -> QPointF:
        """Gets the connection point from the end item's corresponding input port."""
        if self.end_item:
            return self.end_item.get_input_port_scene_pos(self.line_type)
        return QPointF(0,0)

    def update_path(self):
        """Recalculates and sets the path as a cubic Bezier curve (no arrowhead)."""
        if not self.start_item or not self.end_item or not self.start_item.scene() or not self.end_item.scene():
            self.setPath(QPainterPath())
            return



        start_pos = self.get_start_pos()
        end_pos = self.get_end_pos()

        # --- ADDED: Log calculated positions ---
        debug_print(f"    [UPDATE_PATH_DEBUG] Connection {self.start_item.card_id if self.start_item else 'N/A'}->{self.end_item.card_id if self.end_item else 'N/A'} ({self.line_type}):")
        debug_print(f"      Start Pos: {start_pos}")
        debug_print(f"      End Pos:   {end_pos}")
        debug_print(f"      Start Restricted: {getattr(self.start_item, 'restricted_outputs', False)}")
        debug_print(f"      Start Item Scene: {self.start_item.scene() is not None}")
        debug_print(f"      End Item Scene: {self.end_item.scene() is not None}")
        # ---------------------------------------

        if start_pos == end_pos:
            # --- ADDED: Log when positions are equal ---
            debug_print(f"      [UPDATE_PATH_WARN] Start and End positions are equal! Setting empty path.")
            # -------------------------------------------
            self.setPath(QPainterPath())
            return

        # --- Create Cubic Bezier Curve --- 
        path = QPainterPath(start_pos)
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()
        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())
        path.cubicTo(ctrl1, ctrl2, end_pos)

        # Update the item's path directly
        self.prepareGeometryChange() # Notify system bounding rect might change
        self.setPath(path)
        self.update() # Explicitly request an update for this item

    # --- ADDED: Override paint to log execution --- 
    def paint(self, painter, option, widget=None):
        # Call the base class paint method to actually draw the path
        super().paint(painter, option, widget) 
    # --------------------------------------------

    # Rely on default QGraphicsPathItem painting for the line itself 