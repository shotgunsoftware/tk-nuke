"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Callbacks to manage the engine when a new file is loaded in tank.

"""
import os
import textwrap
import nuke
import tank
import pickle
import sys
import traceback


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
    cmd = lambda m=message: nuke.message(m)    
    sg_menu.addCommand("[Tank Error - Click for details]", cmd)

    
def __engine_refresh(new_context):
    """
    Checks the the tank engine should be 
    """
    
    engine_name = os.environ.get("TANK_NUKE_ENGINE_INIT_NAME")
    
    curr_engine = tank.engine()
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
        tank.platform.start_engine(engine_name, new_context)
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
        new_ctx = tank.platform.Context.from_path(file_name)
    except:
        new_ctx = tank.platform.Context.create_empty()
    
    # now restart the engine with the new context
    try:
        __engine_refresh(new_ctx)
    except Exception, e:
        __create_tank_error_menu()


def __tank_startup_node_callback():    
    """
    Callback that fires every time a node gets created.
    
    Carefully manage exceptions here so that a bug in Tank never
    interrupts the normal workflows in Nuke.    
    """    
    tn = nuke.thisNode()

    # look for the root node - this is created only when a new or existing file is opened.
    if tn == nuke.root():
                
        if nuke.root().name() == "Root":
            # file->new
            # base it on the context we 'inherited' from the prev session
            # get the context from the previous session - this is helpful if user does file->new
            ctx_pickled = os.environ.get("TANK_NUKE_ENGINE_INIT_CONTEXT")
            if ctx_pickled:
                try:
                    new_ctx = pickle.loads(ctx_pickled)
                except:
                    new_ctx = tank.platform.Context.create_empty()
            else:
                new_ctx = tank.platform.Context.create_empty()
        
        else:
            # file->open
            try:
                new_ctx = tank.platform.Context.from_path(nuke.root().name())
            except:
                new_ctx = tank.platform.Context.create_empty()
        
        # now restart the engine with the new context
        try:
            __engine_refresh(new_ctx)
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

