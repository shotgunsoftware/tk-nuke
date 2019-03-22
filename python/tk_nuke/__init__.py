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

logger = tank.LogManager.get_logger(__name__)


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
        msg = "The Shotgun Pipeline Toolkit is disabled: %s" % details
        logger.error(msg)
        nuke.error(msg)


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
        msg = "The Shotgun Pipeline Toolkit caught an error: %s" % message
        logger.error(msg)
        nuke.error(msg)

def __engine_refresh(tk, new_context):
    """
    Checks if the tank engine should be refreshed.
    """

    engine_name = os.environ.get("TANK_NUKE_ENGINE_INIT_NAME")
    logger.debug("Refreshing engine '%s'" % engine_name)

    curr_engine = tank.platform.current_engine()
    if curr_engine:
        # an old engine is running.
        if new_context == curr_engine.context:
            # no need to restart the engine!
            logger.debug("Same engine, same context. No restart needed.")
            return
        else:
            # shut down the engine
            curr_engine.destroy()

    # try to create new engine
    try:
        logger.debug("Starting new engine: %s, %s, %s" % (engine_name, tk, new_context))
        e = tank.platform.start_engine(engine_name, tk, new_context)
        logger.debug("Successfully loaded %s" % e)
    except tank.TankEngineInitError, e:
        # context was not sufficient! - disable tank!
        logger.exception("Engine could not be started.")
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
        logger.debug("SGTK Callback: addOnScriptSave('%s')" % file_name)
        # this file could be in another project altogether, so create a new Tank
        # API instance.
        try:
            tk = tank.tank_from_path(file_name)
            logger.debug("Tk instance '%r' associated with path '%s'" % (tk, file_name))
        except tank.TankError, e:
            logger.exception("Could not execute tank_from_path('%s')" % file_name)
            __create_tank_disabled_menu(e)
            return

        # try to get current ctx and inherit its values if possible
        curr_ctx = None
        if tank.platform.current_engine():
            curr_ctx = tank.platform.current_engine().context

        # and now extract a new context based on the file
        new_ctx = tk.context_from_path(file_name, curr_ctx)
        logger.debug("New context computed to be: %r" % new_ctx)

        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        logger.exception("An exception was raised during addOnScriptSave callback.")
        __create_tank_error_menu()


def tank_startup_node_callback():
    """
    Callback that fires every time a script is loaded.

    Carefully manage exceptions here so that a bug in Tank never
    interrupts the normal workflows in Nuke.
    """
    try:
        logger.debug("SGTK Callback: addOnScriptLoad")
        if nuke.root().name() == "Root":

            # file->new
            # base it on the context we 'inherited' from the prev session
            # get the context from the previous session - this is helpful if user does file->new
            logger.debug("File->New detected.")
            project_root = os.environ.get("TANK_NUKE_ENGINE_INIT_PROJECT_ROOT")
            logger.debug("Will spin up a new tk session based on "
                         "previous session's config from '%s'" % project_root)
            tk = tank.Tank(project_root)

            ctx_str = os.environ.get("TANK_NUKE_ENGINE_INIT_CONTEXT")
            if ctx_str:
                try:
                    new_ctx = tank.context.deserialize(ctx_str)
                    logger.debug("Will use previous context '%r'" % new_ctx)
                except:
                    logger.debug("Could not extract previous context "
                                 "from env var TANK_NUKE_ENGINE_INIT_CONTEXT. "
                                 "New session will use empty context.")
                    new_ctx = tk.context_empty()
            else:
                new_ctx = tk.context_empty()
                logger.debug("No previous context found in TANK_NUKE_ENGINE_INIT_CONTEXT. "
                             "New session will use empty context.")

        else:
            # file->open
            file_name = nuke.root().name()
            logger.debug("File->Open detected with file name '%s'" % file_name)

            try:
                tk = tank.tank_from_path(file_name)
                logger.debug("Tk instance '%r' associated with path '%s'" % (tk, file_name))
            except tank.TankError, e:
                logger.exception("Could not execute tank_from_path('%s')" % file_name)
                __create_tank_disabled_menu(e)
                return

            # try to get current ctx and inherit its values if possible
            curr_ctx = None
            if tank.platform.current_engine():
                engine = tank.platform.current_engine()
                logger.debug("Engine currently running: %s" % engine)
                curr_ctx = engine.context

            new_ctx = tk.context_from_path(file_name, curr_ctx)
            logger.debug("New context computed to be: %r" % new_ctx)

        # now restart the engine with the new context
        __engine_refresh(tk, new_ctx)
    except Exception, e:
        logger.exception("An exception was raised during addOnScriptLoad callback.")
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
