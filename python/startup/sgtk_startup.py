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
import traceback


def _handle_exception(output_handle, msg_template, exception):
    output_handle(msg_template % exception)
    output_handle(traceback.format_exc())


def bootstrap_sgtk():
    """
    Bootstrapping routine for the Nuke mode of Nuke.
    """
    import nuke

    # Verify sgtk can be loaded.
    try:
        import sgtk
    except Exception, e:
        nuke.error(
            "Shotgun: Could not import sgtk! Disabling for now: %s" % e
        )
        return

    # start up toolkit logging to file
    sgtk.LogManager().initialize_base_file_handler("tk-nuke")

    _setup_sgtk_bootstrap(nuke.warning)

    # Clean up temp env vars.
    _clean_env()


def _clean_env():
    """
    Cleans up SGTK related environment variables.
    """
    for var in ["TANK_ENGINE", "TANK_CONTEXT", "TANK_FILE_TO_OPEN"]:
        if var in os.environ:
            del os.environ[var]


def _setup_sgtk_classic(output_handle):
    """
    Extracts the necessary information from the environment and starts
    the tk-nuke engine.
    """
    import tank

    if "TANK_ENGINE" not in os.environ:
        output_handle("Shotgun: Unable to determine engine to start!")
        return

    engine_name = os.environ.get("TANK_ENGINE")
    try:
        context = tank.context.deserialize(os.environ.get("TANK_CONTEXT"))
    except Exception, e:
        _handle_exception(
            output_handle,
            "Shotgun: Could not create context! "
            "Shotgun Toolkit will be disabled. Details: %s",
            e
        )
        return

    try:
        tank.platform.start_engine(engine_name, context.tank, context)
    except Exception, e:
        _handle_exception(
            output_handle,
            "Shotgun: Could not start engine: %s",
            e
        )
        return

    _post_engine_startup(output_handle)


def _post_engine_startup(output_handle):

    path = os.environ.get("TANK_NUKE_ENGINE_MOD_PATH")
    if path:
        sys.path.append(path)
        import tk_nuke
        tk_nuke.tank_ensure_callbacks_registered()
    else:
        output_handle("Shotgun could not find the environment variable TANK_NUKE_ENGINE_MOD_PATH!")


def _setup_sgtk_bootstrap(output_handle):

    if "SGTK_ENGINE" not in os.environ:
        output_handle("Shotgun: Unable to determine engine to start!")
        return

    import sgtk

    # FIXME: Using the Toolkit Manager to retrieve the user is the wrong way. If you're launching
    # from an installed pipeline configuration which uses a script user, we should be bootstrapping
    # with it, not the current user. This user's credentials used to be communicated through the
    # TANK_CONTEXT, which we've seemingly dropped in favor of the SHOTGUN_ENTITY_TYPE and
    # SHOTGUN_ENTITY_ID environment variables.
    try:
        def bootstrap(msg, pct):
            print "%f - %s" % (int(pct * 100), msg)

        manager = sgtk.bootstrap.ToolkitManager()
        manager.plugin_id = "basic.desktop"
        manager.bootstrap_engine(os.environ["SGTK_ENGINE"], manager.get_entity_from_environment())
    except Exception as e:
        _handle_exception(
            output_handle,
            "Shotgun: Could not start engine: %s",
            e
        )

    _post_engine_startup(output_handle)

bootstrap_sgtk()
