# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Panel support for Nuke
"""

import os
import sys
import nuke
import sgtk
import nukescripts

from sgtk.platform.qt import QtCore, QtGui
from .ui.panel_not_found_dialog import Ui_PanelNotFoundDialog


class NukePanelWidget(nukescripts.panels.PythonPanel):
    """
    Wrapper class that sets up a panel widget in Nuke.
    This panel widget wraps around a QT widget.
    """
    def __init__(self, dialog_name, panel_id, widget_class):
        """
        Constructor.
        
        :param dialog_name: Name to be displayed on the panel tab
        :param panel_id: Unique id for this panel
        :param widget_class: The class to be instantiated. Its constructor 
                             should not take any parameters.
        """
        
        # first, store the widget class on the sgtk object
        # and key it by id. This is because we then pass the class
        # name as a string into Nuke, and we need a way to uniquely refer
        # back to the class object.
        #
        # Once this attribute is set, it means that you can access the
        # class from sgtk.panel_id_name 
        setattr(tank, panel_id, widget_class)

        # Run parent constructor
        nukescripts.panels.PythonPanel.__init__(self, dialog_name, panel_id)
        
        # now crate a one liner command that can safely refer to the widget class
        cmd = "__import__('nukescripts').panels.WidgetKnob(__import__('sgtk')." + panel_id + ")"
        
        # and lastly tell nuke about our panel object 
        self.customKnob = nuke.PyCustom_Knob(dialog_name, "", cmd)
        self.addKnob(self.customKnob)






class PanelNotFoundDialog(QtGui.QWidget):
    """
    Panel not found widget
    """
    
    def __init__(self):
        """
        Constructor
        """
        # first, call the base class and let it do its thing.
        QtGui.QWidget.__init__(self)
        
        # now load in the UI that was created in the UI designer
        self.ui = Ui_PanelNotFoundDialog() 
        self.ui.setupUi(self)
        



class NukeNotFoundPanelWidget(nukescripts.panels.PythonPanel):
    """
    Panel that displays a "not found" message
    """
    def __init__(self, panel_id):
        """
        Constructor.
        
        :param dialog_name: Name to be displayed on the panel tab
        """
        
        # first, store the widget class on the sgtk object
        # and key it by id. This is because we then pass the class
        # name as a string into Nuke, and we need a way to uniquely refer
        # back to the class object.
        #
        # Once this attribute is set, it means that you can access the
        # class from sgtk.panel_id_name 
        setattr(tank, "sgtk_not_found_dialog", PanelNotFoundDialog)

        # Run parent constructor
        nukescripts.panels.PythonPanel.__init__(self, "Shotgun", panel_id)
        
        # now crate a one liner command that can safely refer to the widget class
        cmd = "__import__('nukescripts').panels.WidgetKnob(__import__('sgtk').sgtk_not_found_dialog)"
        
        # and lastly tell nuke about our panel object 
        self.customKnob = nuke.PyCustom_Knob("Shotgun", "", cmd)
        self.addKnob(self.customKnob)



