# Copyright (c) 2016 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sys

def bootstrap_sgtk():
    """
    Bootstrapping routine for the Nuke mode of Nuke.
    """
    import nuke

    _setup_sgtk(nuke.warning)

    # Clean up temp env vars.
    _clean_env()

def _clean_env():
    """
    Cleans up SGTK related environment variables.
    """
    for var in ["TANK_ENGINE", "TANK_CONTEXT", "TANK_FILE_TO_OPEN"]:
        if var in os.environ:
            del os.environ[var]

def _setup_sgtk(output_handle):
    """
    Extracts the necessary information from the environment and starts
    the tk-nuke engine.
    """
    try:
        import tank
    except Exception, e:
        output_handle("Shotgun: Could not import sgtk! Disabling: %s" % str(e))
        return

    if not "TANK_ENGINE" in os.environ:
        output_handle("Shotgun: Unable to determine engine to start!")
        return

    engine_name = os.environ.get("TANK_ENGINE")
    try:
        context = tank.context.deserialize(os.environ.get("TANK_CONTEXT"))
    except Exception, e:
        output_handle(
            "Shotgun: Could not create context! "
            "Shotgun Toolkit will be disabled. Details: %s" % str(e)
        )
        return

    try:
        engine = tank.platform.start_engine(engine_name, context.tank, context)
    except Exception, e:
        output_handle("Shotgun: Could not start engine: %s" % str(e))
        return

    path = os.environ.get("TANK_NUKE_ENGINE_MOD_PATH")
    if path:
        sys.path.append(path)
        import tk_nuke
        tk_nuke.tank_ensure_callbacks_registered()
    else:
        output_handle("Shotgun could not find the environment variable TANK_NUKE_ENGINE_MOD_PATH!")

bootstrap_sgtk()
