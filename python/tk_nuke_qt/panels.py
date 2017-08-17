# Copyright (c) 2015 Shotgun Software Inc.
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
        
        :param bundle: The app/engine/framework that the dialog belongs to
        :param dialog_name: Name to be displayed on the panel tab
        :param panel_id: Unique id for this panel
        :param widget_class: The class to be instantiated. Its constructor 
                             should not take any parameters.
        """
        self.toolkit_widget = None

        # create a reference to the ToolkitWidgetWrapper class so that 
        # we can refer to it safely using a single line of fully qualified
        # python to return it:
        # 
        # __import__('sgtk')._panel_wrapper_class
        #
        # This necessary for the panel creation in Nuke
        setattr(sgtk, "_panel_wrapper_class", ToolkitWidgetWrapper)
                
        # we cannot pass parameters to the constructor of our wrapper class
        # directly, so instead pass them via a special class method
        ToolkitWidgetWrapper.set_init_parameters(
            widget_class,
            panel_id,
            bundle,
            self,
            args,
            kwargs,
        )
        
        # Run parent constructor
        nukescripts.panels.PythonPanel.__init__(self, dialog_name, panel_id)
        
        # now crate a one liner command that can safely refer to the widget class
        cmd = "__import__('nukescripts').panels.WidgetKnob(__import__('sgtk')._panel_wrapper_class)"
        
        # and lastly tell nuke about our panel object 
        self.customKnob = nuke.PyCustom_Knob(dialog_name, "", cmd)
        self.addKnob(self.customKnob)

    def __getattr__(self, name):
        """
        Custom attribute lookup that will attempt to find the given attribute
        on the wrapped Toolkit panel widget.

        :param str name: The name of the attribute to get.
        """
        if self.toolkit_widget:
            return getattr(self.toolkit_widget, name)
        else:
            raise AttributeError("NukePanelWidget has no attribute %s!" % name)

    def __eq__(self, other):
        """
        Custom equality check. This will make the Nuke panel wrapper evaluate
        as equal (== operator) to the panel widget that it is wrapping. This will
        help panel apps quickly know whether this is the panel they're expecting,
        like during Qt close events.

        :param other: The object being compared to.
        """
        if self.toolkit_widget and self.toolkit_widget is other:
            return True
        else:
            return False


class ToolkitWidgetWrapper(QtGui.QWidget):
    """
    Wrapper widget which wraps around a tk app widget
    """
    _init_widget_class = None
    _init_panel_id = None
    _init_kwargs = None
    _init_bundle = None
    _init_args = None
    _nuke_panel = None
    
    @classmethod
    def set_init_parameters(cls, widget_class, panel_id, bundle, nuke_panel, args, kwargs):
        """
        Specify construction arguments. Because we don't have direct access to 
        the arg list of the constructor, initialization happens though this mechanism
        instead. See the code in the NukePanelWidget above for an example of how this
        is being used and why.
        
        :param widget_class: Class to wrap
        :param panel_id: Unique panel id
        :param bundle: Bundle that the class belongs to
        :param args: Args to pass to class constructor
        :param kwargs: Args to pass to class constructor
        """
        cls._init_widget_class = widget_class
        cls._init_panel_id = panel_id
        cls._init_bundle = bundle
        cls._init_args = args
        cls._init_kwargs = kwargs
        cls._nuke_panel = nuke_panel
    
    
    def __init__(self):
        """
        Constructor
        """
        
        # first, call the base class and let it do its thing.
        QtGui.QWidget.__init__(self)

        # On Linux, in Nuke 11, we have a crash on close problem. This
        # should be safe across the board, though, so no need to limit
        # it to a specific version of Nuke. We just want to make sure
        # that panel apps, specifically shotgunpanel, have the opportunity
        # to shut down gracefully prior to application close.
        QtGui.QApplication.instance().aboutToQuit.connect(self._on_parent_closed)
        
        # pick up the rest of the construction parameters
        # these are set via the class emthod set_init_parameters() 
        # because we cannot control the constructor args
        PanelClass = self._init_widget_class
        
        panel_id = self._init_panel_id
        args = self._init_args
        kwargs = self._init_kwargs
        bundle = self._init_bundle
        self.nuke_panel = self._nuke_panel
        
        # and now clear the init parameters
        self.set_init_parameters(None, None, None, None, None, None)
        
        bundle.logger.debug("Creating panel '%s' to host %s", panel_id, PanelClass)
        
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
        
        widget_name = "%s.widget" % panel_id
        
        for widget in QtGui.QApplication.allWidgets():
            
            # if the widget has got the unique widget name,
            # it's our previously created object!
            if widget.objectName() == widget_name:
                
                # found an existing panel widget!
                self.toolkit_widget = widget
                
                bundle.logger.debug("Found existing panel widget: %s", self.toolkit_widget)
                
                # now find the tab widget by going up the hierarchy
                tab_widget = self._find_panel_tab(self.toolkit_widget)
                if tab_widget:
                    # find the stacked widget that the tab is parented to
                    stacked_widget = tab_widget.parent()
                    if stacked_widget:
                        # and remove the tab widget completely!
                        # our widget will now be hidden
                        stacked_widget.removeWidget(tab_widget)
                        bundle.logger.debug("Removed previous panel tab %s", tab_widget)
                break

        # now check if a widget was found. If not, 
        # we need to create one. 
        if self.toolkit_widget is None:
            # create a new dialog
            # keep a python side reference
            # and also parent it to this widget
            self.toolkit_widget = PanelClass(*args, **kwargs)
            
            # give our main widget a name so that we can identify it later
            self.toolkit_widget.setObjectName(widget_name)
            
            bundle.logger.debug("Created new toolkit panel widget %s", self.toolkit_widget)
            
            # now let the core apply any external stylesheets
            bundle.engine._apply_external_styleshet(bundle, self.toolkit_widget)
            
        else:
            # there is already a dialog. Re-parent it to this
            # object and move it across into this layout
            self.toolkit_widget.setParent(self)
            bundle.logger.debug("Reparented existing toolkit widget.")
        
        # Add the widget to our current layout
        self.layout.addWidget(self.toolkit_widget)
        bundle.logger.debug("Added toolkit widget to panel hierarchy")
        
        # now, the close widget logic does not propagate correctly
        # down to the child widgets. When someone closes a tab or pane,
        # QStackedWidget::removeWidget is being called, which merely takes
        # our widget out of the layout and hides it. So it will stay resident
        # in memory which is not what we want. Instead, it should close properly
        # if someone decides to close its tab. 
        #
        # We can accomplish this by installing a close event listener on the 
        # tab itself and have that call our widget so that we can close ourselves.
        # note that we search for the tab widget by unique id rather than going
        # up in the widget hierarchy, because the hierarchy has not been properly
        # established at this point yet. 
        for widget in QtGui.QApplication.allWidgets():
            if widget.objectName() == panel_id:
                filter = CloseEventFilter(widget)
                filter.parent_closed.connect(self._on_parent_closed)
                widget.installEventFilter(filter)
                bundle.logger.debug("Installed close-event filter watcher on tab %s", widget)
                break

        # We should have a parent panel object. If we do, we can alert it to the
        # concrete sgtk panel widget we're wrapping. This will allow is to provide
        # the wrapped widget's interface to higher-level callers.
        if self.nuke_panel:
            self.nuke_panel.toolkit_widget = self.toolkit_widget
        
    def _find_panel_tab(self, widget):
        """
        Helper method.
        Given a tk panel widget, traverse upwards in the hierarchy and
        attempt to locate the tab widget. In the case for some reason
        the object hiearchy is not as we expect it to be (caused by an
        incomplete or inconsistent state restore in Nuke), None is returned.
        
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
        if nuke.env.get("NukeVersionMajor") >= 11:
            # We don't seem to be able to deleteLater safely in Nuke 11, which
            # is a PySide2/Qt5 app. My guess is that deleteLater is more "efficient"
            # than it was in Qt4, and as a result, the deleteLater actually seems
            # to delete RIGHT NOW. That plays havoc with the shutdown routines in
            # some of our lower-level objects from the qtwidgets and shotgunutils
            # frameworks. The result was that we ended up with dangling Python objects
            # that have had their C++ object deleted by Qt before we're done with
            # them in Python.
            #
            # However, we do need to get this widget out of the way, because there's
            # logic that looks up existing stuff by object name and activates, which
            # prevents us from opening up multiple, concurrent panel apps. We can
            # just rename the widget, and let Qt/Python decide when to delete it.
            self.toolkit_widget.setObjectName("%s.CLOSED" % self.objectName())
        else:
            # This was safe in Nuke versions previous to 11.x, so
            # we can let Qt delete the widget hierarchy as soon as
            # it has a free cycle.
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
    Event filter which emits a parent_closed signal whenever
    the monitored widget closes.
    """
    parent_closed = QtCore.Signal()
     
    def eventFilter(self,  obj,  event):
        """
        QT Event filter callback
        
        :param obj: The object where the event originated from
        :param event: The actual event object
        :returns: True if event was consumed, False if not
        """        
        # peek at the message
        if event.type() == QtCore.QEvent.Close:
            # re-broadcast any close events
            self.parent_closed.emit()
        # pass it on!
        return False

