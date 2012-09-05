"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Callbacks to manage the engine when a new file is loaded in tank.

"""
import os
import textwrap
import sys
import traceback

import nuke
import nukescripts

import tank
from tank_vendor import yaml

from .menu_generation import MenuGenerator

def __show_tank_disabled_message(details):
    """
    Message when user clicks the tank is disabled menu
    """
    msg = ("Tank is currently disabled because the file you " 
           "have opened is not recognized by Tank. Tank cannot "
           "determine which Context the currently open file belongs to. "
           "In order to enable the Tank functionality, try opening another "
           "file. <br><br><i>Details:</i> %s" % details)
    nuke.message(msg)
    
def __create_tank_disabled_menu(details):    
    """
    Creates a std "disabled" tank menu
    """
    nuke_menu = nuke.menu("Nuke")
    sg_menu = nuke_menu.addMenu("Tank")
    sg_menu.clearMenu()
    cmd = lambda d=details: __show_tank_disabled_message(d)    
    sg_menu.addCommand("Tank is disabled.", cmd)

    
def __create_tank_error_menu():    
    """
    Creates a std "error" tank menu and grabs the current context.
    Make sure that this is called from inside an except clause.
    """
    (exc_type, exc_value, exc_traceback) = sys.exc_info()
    message = ""
    message += "Message: There was a problem starting the Tank Engine.\n"
    message += "Please contact tanksupport@shotgunsoftware.com\n\n"
    message += "Exception: %s - %s\n" % (exc_type, exc_value)
    message += "Traceback (most recent call last):\n"
    message += "\n".join( traceback.format_tb(exc_traceback))
    
    nuke_menu = nuke.menu("Nuke")
    sg_menu = nuke_menu.addMenu("Tank")
    sg_menu.clearMenu()
    cmd = lambda m=message: nuke.message(m)    
    sg_menu.addCommand("[Tank Error - Click for details]", cmd)

    
def __engine_refresh(tk, new_context):
    """
    Checks the the tank engine should be 
    """
    
    engine_name = os.environ.get("TANK_NUKE_ENGINE_INIT_NAME")
    
    curr_engine = tank.platform.current_engine()
    if curr_engine:
        # an old engine is running. 
        if new_context == curr_engine.context:
            # no need to restart the engine!
            return         
        else:
            # shut down the engine
            curr_engine.destroy()
        
    # try to create new engine
    try:
        tank.platform.start_engine(engine_name, tk, new_context)
    except tank.TankEngineInitError, e:
        # context was not sufficient! - disable tank!
        __create_tank_disabled_menu(e)
         
    
def __tank_on_save_callback():
    """
    Callback that fires every time a file is saved.
    
    Carefully manage exceptions here so that a bug in Tank never
    interrupts the normal workflows in Nuke.
    """
    # get the new file name
    file_name = nuke.root().name()
    
    try:
        # this file could be in another project altogether, so create a new Tank
        # API instance.
        try:
            tk = tank.tank_from_path(file_name)
        except tank.TankError, e:
            __create_tank_disabled_menu(e)
            return
        
        new_ctx = tk.context_from_path(file_name)
        
        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        __create_tank_error_menu()


def __tank_startup_node_callback():    
    """
    Callback that fires every time a node gets created.
    
    Carefully manage exceptions here so that a bug in Tank never
    interrupts the normal workflows in Nuke.    
    """    
    try:
        # look for the root node - this is created only when a new or existing file is opened.
        tn = nuke.thisNode()
        if tn != nuke.root():
            return
            
        if nuke.root().name() == "Root":
            # file->new
            # base it on the context we 'inherited' from the prev session
            # get the context from the previous session - this is helpful if user does file->new
            project_root = os.environ.get("TANK_NUKE_ENGINE_INIT_PROJECT_ROOT")
            tk = tank.Tank(project_root)
            
            ctx_yaml = os.environ.get("TANK_NUKE_ENGINE_INIT_CONTEXT")
            if ctx_yaml:
                try:
                    new_ctx = yaml.load(ctx_yaml)
                except:
                    new_ctx = tk.context_empty()
            else:
                new_ctx = tk.context_empty()
    
        else:
            # file->open
            file_name = nuke.root().name()
            
            try:
                tk = tank.tank_from_path(file_name)
            except tank.TankError, e:
                __create_tank_disabled_menu(e)
                return
                
            new_ctx = tk.context_from_path(file_name)
    
        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        __create_tank_error_menu()
        
g_tank_callbacks_registered = False

def tank_ensure_callbacks_registered():   
    """
    Make sure that we have callbacks tracking context state changes.
    """
    global g_tank_callbacks_registered
    if not g_tank_callbacks_registered:
        nuke.addOnCreate(__tank_startup_node_callback)
        nuke.addOnScriptSave(__tank_on_save_callback)
        g_tank_callbacks_registered = True


##########################################################################################
# pyside/qt specific stuff.  could be expanded for PyQt

_registered_nuke_panels = {} # tracks nuke panel instances
_qt_widget_instances = {} # tracks qt widget instances.
_widget_wrapper_classes = {} # tracks custom widget wrapper classes.

_widget_callbacks = {}


def _register_qt_widget_instance(widget_id, instance):
    '''
    Adds a qt widget instance to the tracking
    dict.
    '''
    _qt_widget_instances[widget_id] = instance

def _remove_qt_widget_instance(widget_id):
    '''
    Removes a widget instance from the tracking
    dict.
    '''
    if widget_id in _qt_widget_instances:
        _qt_widget_instances.pop(widget_id)

def get_qt_widget_instance(widget_id):
    return _qt_widget_instances.get(widget_id)

def _register_nuke_panel(id, panel):
    '''
    Adds a tank nuke panel instance.
    '''
    _registered_nuke_panels[id] = panel

def _get_nuke_panel(id):
    '''
    Returns the custom nuke panel instance
    for the passed in id.
    '''
    return _registered_nuke_panels.get(id, None)

def _remove_panel_custom_knob(widget_id):
    '''
    Removes the custom knob from the panel and
    removes the widget instance from the tracking
    dict.
    '''
    panel = _get_nuke_panel(widget_id)
    if panel:
        panel.removeCustomKnob()
    _remove_qt_widget_instance(widget_id)

def _register_widget_wrapper_cls(widget_id, cls):
    '''
    Registers a wrapper class for widget with passed
    in id.
    '''
    _widget_wrapper_classes[widget_id] = cls

def _get_widget_wrapper_cls(widget_id):
    '''
    Returns the custom wrapper class created for the widget
    with the passed in id.
    '''
    return _widget_wrapper_classes.get(widget_id)

class TankNukeWidgetKnob(object):
    '''
    Class used by TankNukePanelWrapper to
    wrap a custom QtWidget.
    '''
    def __init__(self, widget_id, widget):
        self.widgetClass = widget
        self.widget_id = widget_id
    
    def makeUI(self):    
        self.widget = self.widgetClass()
        _register_qt_widget_instance(self.widget_id, self.widget)
        return self.widget

class TankNukePanelWrapper(nukescripts.PythonPanel):
    '''
    Wraps the nukescripts.PythonPanel to allow customization.
    '''
    def __init__(self, name, id):
        nukescripts.PythonPanel.__init__(self, name, id)
        self.customKnob = None
        self.addCustomKnob(name)
        _register_nuke_panel(name, self)
        
    def addCustomKnob(self, name):
        '''
        Adds our QtWidget as a custom knob to this
        nuke panel.
        '''
        # If a customKnob already exists
        # return nothing.
        # 
        if self.customKnob:
            return
        # Have to set this as a string.  Nuke handles creating the
        # Widget knob when it decides it wants to....
        #
        import_str = "__import__('tk_nuke')._get_widget_wrapper_cls('%s')" % name
        import_str = "__import__('tk_nuke').TankNukeWidgetKnob('%s', %s)" % (name, import_str)

        self.customKnob = nuke.PyCustom_Knob(name, "", import_str)
        self.addKnob(self.customKnob)

    def removeCustomKnob(self):
        '''
        Removes our custom knob.
        '''
        self.removeKnob(self.customKnob)
        self.customKnob = None

def _add_nuke_panel(widget_wrapped_cls, name, panel_id, addToMenu=None, create=True):
    '''
    Adds a nuke panel if a panel for the given name doesn't exist.
    '''
    # If a panel is already created for
    # this widget return it.
    #
    panel = _get_nuke_panel(name)
    if panel:
        panel.addCustomKnob(name)
        return panel

    if addToMenu:
        # Creates the method to use when adding to a
        # menu.
        #
        def addPanel():
            if _get_nuke_panel(name):
                return _get_nuke_panel(name).addToPane()
            return TankNukePanelWrapper( name, panel_id ).addToPane()

        menu = nuke.menu('Pane')
        menu.addCommand( name, addPanel )
    
    # If create is set create the panel instance
    #
    if create:
        panel = TankNukePanelWrapper( name, panel_id )

    return panel

def _wrap_qt_widget(widget_cls, widget_id):
    '''
    Wraps the passed in widget in a custom class so
    we can add extra things we need.
    '''
    # Define the close method we'll use in
    # the Qt TankWrapper class we'll create
    # below.  This allows us to ensure our
    # parent wrapper widget we've created
    # is closed when it need's to be.
    #

    def close(self):
        _remove_panel_custom_knob(widget_id)
        widget_cls.close(self)
        try:
            self.parentWidget().close()
            # This is needed for dock widgets.
            #
            self.parentWidget().deleteLater()
        except:
            pass

    extra_attributes = {'close':close}

    # Needed to become a custom knob.  Nuke will
    # Automatically try to call this function
    # when a value changes.  We only add this one
    # if the class we are wrapping doesn't have
    # this method.
    #
    def updateValue(self, *args, **kwargs):
        pass

    if not hasattr(widget_cls, 'updateValue'):
        extra_attributes['updateValue'] = updateValue
    
    # Create a TankWrapper class that is a subclass of
    # the widget_class that came in.  This lets us
    # override the close method but still call the 
    # original widget_cls close method.  We pass in
    # the close method and our widget tracking dict.
    # The new class is instantiated and added to
    # our parent_widget's layout.
    #
    if _get_widget_wrapper_cls(widget_id):
        return _get_widget_wrapper_cls(widget_id)
    
    wrapper_name = '%sTankWrapper' % widget_id    
    widget_wrapper_class = type(wrapper_name, (widget_cls, ), extra_attributes)
    _register_widget_wrapper_cls(widget_id, widget_wrapper_class)
    
    return widget_wrapper_class

WIDGET_ID_STR = 'tv.psyop.%s' # Used to create unique panel id.

def new_qt_widget(widget_cls, widget_id, app_settings={}, **kwargs):
    '''
    Accepts a Qt Widget class and a unique widget_id.  app_settings is
    used to define host application specific settings.

    asPane (bool): sets the QWidget to appear as a nuke panel.
    asPane options:
        addToPane (str): adds the nuke panel to the specified pane.
        addToMenu (str): adds a command to the pane menu.
        create (bool): creates the nuke panel when called.

    QDialog options:
        modal (bool): sets a QDialog window as modal.

    '''
    from PySide import QtCore, QtGui
    
    app_settings = app_settings.pop('nuke', {})

    nuke_main_qwidget = QtGui.QMainWindow(QtGui.QApplication.activeWindow())
    parent_widget = None
    widget = None
    
    # If the instance is already a QMainWindow
    # just parent it to the main window and
    # move on with life.
    #
    if QtGui.QMainWindow in widget_cls.__bases__:
        widget = widget_cls(nuke_main_qwidget)
        parent_widget = widget
    else:
        # Default layout used for both the dock
        # and dialog wrapper methods.
        #
        widget_wrapped_cls = _wrap_qt_widget(widget_cls, widget_id)
        if app_settings.pop('asPane', False):
            parent_widget = _add_nuke_panel( widget_wrapped_cls, 
                                             widget_id, 
                                             WIDGET_ID_STR % widget_id,
                                             addToMenu=app_settings.pop('addToMenu', None),
                                             create=app_settings.pop('create', True))

            addToPane = app_settings.pop('addToPane', None)
            if addToPane:
                pane = nuke.getPaneFor(addToPane)
                if pane:
                    parent_widget.addToPane(pane)

            # Bail out early, we don't need
            # to do any widget registration
            # because the panel functions called
            # earlier are already doing it for us.
            #
            return parent_widget
        else:
            # Dock wasn't requested so we create a QDialog
            # to wrap the passed in widget with.
            #
            widget = widget_wrapped_cls()
            parent_widget = QtGui.QDialog(nuke_main_qwidget)
            parent_widget.setModal(app_settings.pop('modal', False))

            layout = QtGui.QVBoxLayout()
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(widget)
            parent_widget.setLayout(layout)
        
            # Set the new parent widget's size and title to match
            # the passed in widget.
            #
            parent_widget.resize(widget.width(), widget.height())
            parent_widget.setWindowTitle(widget.windowTitle())
            widget.setParent(parent_widget)

    # Add the widget to our dict of widgets.
    #
    # If we have already created a widget with the
    # same window title as this widget, close
    # the old one before creating a new one.
    #
    if get_qt_widget_instance(widget_id):
        get_qt_widget_instance(widget_id).close()
    _register_qt_widget_instance(widget_id, widget)
    
    return parent_widget