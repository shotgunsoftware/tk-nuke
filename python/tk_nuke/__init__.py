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
Callbacks to manage the engine when a new file is loaded in tank.

Please note that this module is imported  during Nuke's setup 
phase to handle automatic context switching. At this point, QT is 
not necessarily fully initialized. Therefore, any modules that require
QT to be imported should be placed in the tk_nuke_qt module instead
in order to avoid import errors at startup and context switch.
"""
import os
import textwrap
import nuke
import tank
import sys
import traceback

from .menu_generation import (
    NukeMenuGenerator,
    HieroMenuGenerator,
    NukeStudioMenuGenerator,
)

from .context import ClassicStudioContextSwitcher, PluginStudioContextSwitcher # noqa


def __show_tank_disabled_message(details):
    """
    Message when user clicks the tank is disabled menu
    """
    msg = ("Shotgun integration is currently disabled because the file you " 
           "have opened is not recognized. Shotgun cannot "
           "determine which Context the currently open file belongs to. "
           "In order to enable the Shotgun functionality, try opening another "
           "file. <br><br><i>Details:</i> %s" % details)
    nuke.message(msg)
    
def __create_tank_disabled_menu(details):    
    """
    Creates a std "disabled" shotgun menu
    """
    if nuke.env.get("gui"):
        nuke_menu = nuke.menu("Nuke")
        sg_menu = nuke_menu.addMenu("Shotgun")
        sg_menu.clearMenu()
        cmd = lambda d=details: __show_tank_disabled_message(d)    
        sg_menu.addCommand("Toolkit is disabled.", cmd)
    else:
        nuke.error("The Shotgun Pipeline Toolkit is disabled: %s" % details)
        
    
def __create_tank_error_menu():    
    """
    Creates a std "error" tank menu and grabs the current context.
    Make sure that this is called from inside an except clause.
    """
    (exc_type, exc_value, exc_traceback) = sys.exc_info()
    message = ""
    message += "Message: Shotgun encountered a problem starting the Engine.\n"
    message += "Please contact support@shotgunsoftware.com\n\n"
    message += "Exception: %s - %s\n" % (exc_type, exc_value)
    message += "Traceback (most recent call last):\n"
    message += "\n".join( traceback.format_tb(exc_traceback))
    
    if nuke.env.get("gui"):
        nuke_menu = nuke.menu("Nuke")
        sg_menu = nuke_menu.addMenu("Shotgun")
        sg_menu.clearMenu()
        cmd = lambda m=message: nuke.message(m)    
        sg_menu.addCommand("[Shotgun Error - Click for details]", cmd)
    else:
        nuke.error("The Shotgun Pipeline Toolkit caught an error: %s" % message)
    
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
        
        # try to get current ctx and inherit its values if possible
        curr_ctx = None
        if tank.platform.current_engine():
            curr_ctx = tank.platform.current_engine().context
        
        # and now extract a new context based on the file
        new_ctx = tk.context_from_path(file_name, curr_ctx)
        
        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        __create_tank_error_menu()


def tank_startup_node_callback():    
    """
    Callback that fires every time a node gets created.
    
    Carefully manage exceptions here so that a bug in Tank never
    interrupts the normal workflows in Nuke.    
    """    
    try:    
        if nuke.root().name() == "Root":
            # file->new
            # base it on the context we 'inherited' from the prev session
            # get the context from the previous session - this is helpful if user does file->new
            project_root = os.environ.get("TANK_NUKE_ENGINE_INIT_PROJECT_ROOT")
            tk = tank.Tank(project_root)
            
            ctx_str = os.environ.get("TANK_NUKE_ENGINE_INIT_CONTEXT")
            if ctx_str:
                try:
                    new_ctx = tank.context.deserialize(ctx_str)
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
                
            # try to get current ctx and inherit its values if possible
            curr_ctx = None
            if tank.platform.current_engine():
                curr_ctx = tank.platform.current_engine().context                
                
            new_ctx = tk.context_from_path(file_name, curr_ctx)
    
        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        __create_tank_error_menu()
        
g_tank_callbacks_registered = False

def tank_ensure_callbacks_registered():   
    """
    Make sure that we have callbacks tracking context state changes.
    """

    import sgtk
    engine = sgtk.platform.current_engine()

    # Register only if we're missing an engine (to allow going from disabled to something else)
    # or if the engine specifically requests for it.
    if not engine or engine.get_setting("automatic_context_switch"):
        global g_tank_callbacks_registered
        if not g_tank_callbacks_registered:
            nuke.addOnScriptLoad(tank_startup_node_callback)
            nuke.addOnScriptSave(__tank_on_save_callback)
            g_tank_callbacks_registered = True
