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


def bootstrap(engine_name, context, app_path, app_args, extra_args):
    """
    Prepares for the bootstrapping process that will run during startup of
    Nuke, Hiero, and Nuke Studio.

    .. NOTE:: For detailed documentation of the bootstrap process for Nuke,
              Hiero, and Nuke Studio, see the engine documentation in
              `tk-nuke/engine.py`.
    """
    import tank

    startup_path = os.path.normpath(
        os.path.join(
            os.path.dirname(
                os.path.abspath(sys.modules[bootstrap.__module__].__file__)
            ), # tk-nuke/python/startup
            "..", # tk-nuke/python
            "..",  # tk-nuke
            "classic_startup"
        ) # tk-nuke/classic_startup
    )
    app_args = app_args or ""

    if "hiero" in app_path.lower() or "--hiero" in app_args:
        tank.util.append_path_to_env_var("HIERO_PLUGIN_PATH", startup_path)
    elif "nukestudio" in app_path.lower() or "--studio" in app_args:
        tank.util.append_path_to_env_var("HIERO_PLUGIN_PATH", startup_path)
    else:
        tank.util.append_path_to_env_var("NUKE_PATH", startup_path)
        file_to_open = os.environ.get("TANK_FILE_TO_OPEN")

        # A Nuke script can't be launched from the menu.py, so we
        # have to tack it onto the launch arguments instead.
        if file_to_open:
            if app_args:
                app_args = "%s %s" % (file_to_open, app_args)
            else:
                app_args = file_to_open

    return (app_path, app_args)
