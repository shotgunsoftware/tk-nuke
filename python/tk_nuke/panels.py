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

class NukePanelWidget(nukescripts.panels.PythonPanel):
    """
    Wrapper class that sets up a panel widget in Nuke.
    This panel widget wraps around a QT widget.
    """
    def __init__(self, bundle, dialog_name, panel_id, widget_class, *args, **kwargs):
        """
        Constructor.
        
        :param bundle: The app/engine/fraemwork that the dialog belongs to
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
        setattr(sgtk, "_panel_wrapper_class", ToolkitWidgetWrapper)
        setattr(sgtk, "_current_panel_class", widget_class)
        setattr(sgtk, "_current_panel_id", panel_id)
        setattr(sgtk, "_current_panel_args", args)
        setattr(sgtk, "_current_panel_kwargs", kwargs)
        setattr(sgtk, "_current_panel_bundle", bundle)

        # Run parent constructor
        nukescripts.panels.PythonPanel.__init__(self, dialog_name, panel_id)
        
        # now crate a one liner command that can safely refer to the widget class
        cmd = "__import__('nukescripts').panels.WidgetKnob(__import__('sgtk')._panel_wrapper_class)"
        
        # and lastly tell nuke about our panel object 
        self.customKnob = nuke.PyCustom_Knob(dialog_name, "", cmd)
        self.addKnob(self.customKnob)


class ToolkitWidgetWrapper(QtGui.QWidget):
    """
    Wrapper widget which wraps around a tk app widget
    """
    
    def __init__(self):
        """
        Constructor
        """
        
        # first, call the base class and let it do its thing.
        QtGui.QWidget.__init__(self)
        
        # pick up members from the global sgtk namespace
        # where it was set by the NukePanelWidget code above
        panel_id = sgtk._current_panel_id
        args = sgtk._current_panel_args
        kwargs = sgtk._current_panel_kwargs
        bundle = sgtk._current_panel_bundle
        
        PanelClass = sgtk._current_panel_class
        
        bundle.log_debug("Creating panel '%s' to host %s" % (panel_id, PanelClass))
        
        # deallocate global tmp variables
        sgtk._current_panel_id = None
        sgtk._current_panel_args = None
        sgtk._current_panel_kwargs = None
        sgtk._current_panel_bundle = None
        sgtk._current_panel_class = None
        
        # set up this object and create a layout
        self.setObjectName("%s.wrapper" % panel_id)
        self.layout = QtGui.QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setObjectName("%s.wrapper.layout" % panel_id)
        
        # now loop over all widgets and look for our panel widget
        # if we find it, take it out of the layout and then
        # destroy the current container.
        # this will keep the widget around but destroy the nuke tab 
        # that it was sitting in.
        self.toolkit_widget = None
        for widget in QtGui.QApplication.allWidgets():
            if type(widget) == PanelClass:
                # found an existing panel widget!
                self.toolkit_widget = widget
                
                bundle.log_debug("Found existing panel widget: %s" % self.toolkit_widget)
                
                # now find the tab widget by going up the hierarchy
                tab_widget = self._find_panel_tab(self.toolkit_widget)
                if tab_widget:
                    # find the stacked widget that the tab is parented to
                    stacked_widget = tab_widget.parent()
                    if stacked_widget:
                        # and remove the tab widget completely!
                        # our widget will now be hidden
                        stacked_widget.removeWidget(tab_widget)
                        bundle.log_debug("Removed previous panel tab %s" % tab_widget)
                break

        # now check if a widget was found. If not, 
        # we need to create one. 
        if self.toolkit_widget is None:
            # create a new dialog
            # keep a python side reference
            # and also parent it to this widget
            self.toolkit_widget = PanelClass(*args, **kwargs)
            bundle.log_debug("Created new toolkit panel widget %s" % self.toolkit_widget)
            
            # now let the core apply any external stylesheets
            bundle.engine._apply_external_styleshet(bundle, self.toolkit_widget)
            
        else:
            # there is already a dialog. Re-parent it to this
            # object and move it across into this layout
            self.toolkit_widget.setParent(self)
            bundle.log_debug("Reparented existing toolkit widget.")
        
        # Add the widget to our current layout
        self.layout.addWidget(self.toolkit_widget)
        bundle.log_debug("Added toolkit widget to panel hierarchy")
        
        # now, the close widget logic does not propagate correctly
        # down to the child widgets. When someone closes a tab or pane,
        # QStackedWidget::removeWidget is being called, which merely takes
        # our widget out of the layout and hides it. So it will stay resindent
        # in memory which is not what we want. Instead, it should close properly
        # if someone decides to close its tab. 
        #
        # We can accomplish this by installing a close event listener on the 
        # tab itself and have that call our widget so that we can close ourselves.
        # note that we search for the tab widget by unique id rather than going
        # up in the widget hierarchy, because the hiearchy has not been properly
        # established at this point yet. 
        for widget in QtGui.QApplication.allWidgets():
            if widget.objectName() == panel_id:
                filter = CloseEventFilter(widget)
                filter.parent_closed.connect(self._on_parent_closed)
                widget.installEventFilter(filter)
                bundle.log_debug("Installed close-event filter watcher on tab %s" % widget)     
        
    def _find_panel_tab(self, widget):
        """
        Helper method.
        Given a tk panel widget, traverse upwards in the hierarchy and
        attempt to locate the tab widget. 
        
        :param widget: widget to start from
        :returns: QWidget instance or None if not found
        """
        p = widget
        
        while p:
            # traverse up until the stacked widget is found
            if p.parent() and isinstance(p.parent(), QtGui.QStackedWidget):
                return p
            else:
                p = p.parent()
            
        return None

    def closeEvent(self, event):
        """
        Overridden close event method
        """
        # close child widget
        self.toolkit_widget.close()
        # delete this widget and all children        
        self.deleteLater()
        # okay to close dialog
        event.accept()
        
    def _on_parent_closed(self):
        """
        Callback slot from the event filter
        """
        # close this widget
        self.close()
         

class CloseEventFilter(QtCore.QObject):
    """
    Event filter which emits a resized signal whenever
    the monitored widget closes.
    """
    parent_closed = QtCore.Signal()
     
    def eventFilter(self,  obj,  event):
        # peek at the message
        if event.type() == QtCore.QEvent.Close:
            # re-broadcast any resize events
            self.parent_closed.emit()
        # pass it on!
        return False

