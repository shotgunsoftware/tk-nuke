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
import sgtk
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


def __engine_refresh(new_context):
    """
    Checks if the nuke engine should be created or just have the context changed.
    If an engine is already started then we just need to change context, else we need to start the engine.
    """
    
    engine_name = os.environ.get("TANK_NUKE_ENGINE_INIT_NAME")
    
    curr_engine = sgtk.platform.current_engine()
    if curr_engine:
        # If we already have an engine, we can just tell it to change contexts
        curr_engine.change_context(new_context)
    else:
        # try to create new engine
        try:
            sgtk.platform.start_engine(engine_name, new_context.sgtk, new_context)
        except sgtk.TankEngineInitError as e:
            # context was not sufficient! - disable tank!
            __create_tank_disabled_menu(e)
         
    
def __sgtk_on_save_callback():
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
            tk = sgtk.sgtk_from_path(file_name)
        except sgtk.TankError as e:
            __create_tank_disabled_menu(e)
            return

        # try to get current ctx and inherit its values if possible
        curr_ctx = None
        curr_engine = sgtk.platform.current_engine()
        if curr_engine:
            curr_ctx = curr_engine.context

        # and now extract a new context based on the file
        new_ctx = tk.context_from_path(file_name, curr_ctx)
        
        # now restart the engine with the new context
        __engine_refresh(new_ctx)

    except Exception:
        __create_tank_error_menu()


def sgtk_on_load_callback():
    try:
        # If we have opened a file then we should check if automatic context switching is enabled and change if possible
        engine = sgtk.platform.current_engine()
        file_name = nuke.root().name()

        if file_name != "Root" and engine is not None and engine.get_setting("automatic_context_switch"):
            # We have a current script, and we have an engine and the current environment is set to
            # automatic context switch, so we should attempt to change the context to suit the file that is open.
            try:
                # todo: do we need to create a new tk object, instead should we just check the context gets created correctly?
                tk = sgtk.sgtk_from_path(file_name)
            except sgtk.TankError as e:
                __create_tank_disabled_menu(e)
                return

            # try to get current ctx and inherit its values if possible
            curr_ctx = None
            if sgtk.platform.current_engine():
                curr_ctx = sgtk.platform.current_engine().context

            new_ctx = tk.context_from_path(file_name, curr_ctx)
            # Now switch to the context appropriate for the file
            __engine_refresh(new_ctx)

        elif file_name != "Root" and engine is None:
            # we have no engine, this maybe because the integration disabled itself, due to a non Toolkit file being
            # opened, prior to this new file. We must create a sgtk instance from the script path.
            try:
                tk = sgtk.sgtk_from_path(file_name)
            except sgtk.TankError as e:
                __create_tank_disabled_menu(e)
                return

            new_ctx = tk.context_from_path(file_name)
            # Now switch to the context appropriate for the file
            __engine_refresh(new_ctx)

    except Exception:
        __create_tank_error_menu()

g_tank_callbacks_registered = False


def tank_ensure_callbacks_registered(engine=None):
    """
    Make sure that we have callbacks tracking context state changes.
    The OnScriptLoad callback really only come into play when your opening a file or creating a new script, when there is
    no current script open in your Nuke session. If there is a script currently open then this will spawn a new Nuke
    instance and the callback won't be called.
    """

    # Register only if we're missing an engine (to allow going from disabled to something else)
    # or if the engine specifically requests for it.
    if not engine or engine.get_setting("automatic_context_switch"):
        global g_tank_callbacks_registered
        if not g_tank_callbacks_registered:
            nuke.addOnScriptLoad(sgtk_on_load_callback)
            nuke.addOnScriptSave(__sgtk_on_save_callback)
            g_tank_callbacks_registered = True
    elif engine and not engine.get_setting("automatic_context_switch"):
        # we have an engine but the automatic context switching has been disabled, we should ensure the callbacks
        # are removed.
        global g_tank_callbacks_registered
        if g_tank_callbacks_registered:
            nuke.removeOnScriptLoad(sgtk_on_load_callback)
            nuke.removeOnScriptSave(__sgtk_on_save_callback)
            g_tank_callbacks_registered = False

