# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os

def bootstrap_sgtk():
    """
    Bootstraps SGTK to Nuke Studio, or Hiero, depending on which
    mode it's currently running in.
    """
    import nuke

    if nuke.env.get("hiero"):
        _bootstrap_hiero()
    elif nuke.env.get("studio"):
        _bootstrap_nuke_studio()

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

def _bootstrap_hiero():
    """
    Bootstrapping routine for the Hiero mode of Nuke.
    """
    import hiero.core
    _setup_sgtk(hiero.core.log.error)

    # Check if we should open a file.
    file_to_open = os.environ.get("TANK_FILE_TO_OPEN")
    if file_to_open:
        hiero.core.openProject(file_to_open.replace(os.path.sep, "/"))

    # Clean up temp env vars.
    _clean_env()

def _bootstrap_nuke_studio():
    """
    Bootstrapping routine for the Nuke Studio mode of Nuke.
    """
    _bootstrap_hiero()

bootstrap_sgtk()

