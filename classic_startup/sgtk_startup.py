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
    Cleans up PTR related environment variables.
    """
    # We don't clean up the TANK_CONTEXT or TANK_ENGINE a these get reset with the current context
    # and used if a new Nuke session is spawned from this one.
    if "TANK_FILE_TO_OPEN" in os.environ:
        del os.environ["TANK_FILE_TO_OPEN"]


def _setup_sgtk(output_handle):
    """
    Extracts the necessary information from the environment and starts
    the tk-nuke engine.
    """
    try:
        import sgtk
    except Exception as e:
        output_handle(
            "Flow Production Tracking: Could not import sgtk! Disabling: %s" % str(e)
        )
        return

    if not "TANK_ENGINE" in os.environ:
        output_handle("Flow Production Tracking: Unable to determine engine to start!")
        return

    engine_name = os.environ.get("TANK_ENGINE")
    try:
        context = sgtk.context.deserialize(os.environ.get("TANK_CONTEXT"))
    except Exception as e:
        output_handle(
            "Flow Production Tracking: Could not create context! "
            "Flow Production Tracking will be disabled. Details: %s" % str(e)
        )
        return

    try:
        sgtk.platform.start_engine(engine_name, context.sgtk, context)
    except Exception as e:
        output_handle("Flow Production Tracking: Could not start engine: %s" % str(e))
        return


bootstrap_sgtk()
