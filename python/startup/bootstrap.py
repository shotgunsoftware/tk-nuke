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
import sgtk

logger = sgtk.LogManager.get_logger(__name__)


def _get_current_module_path():
    """
    Returns the current module's absolute path.
    """
    return os.path.dirname(
        os.path.abspath(sys.modules[_get_current_module_path.__module__].__file__)
    )


def _get_bundle_root():
    """
    Returns the root of this bundle.
    """
    return os.path.normpath(
        os.path.join(
            _get_current_module_path(), # tk-nuke/python/startup
            "..", # tk-nuke/python
            ".." # tk-nuke
        )
    )


def _compute_environment(app_path, app_args, startup_paths, file_to_open):
    """
    Computes the environment variables and command line arguments required to launch Nuke.
    """
    app_args = app_args or ""

    env = {}

    if "hiero" in app_path.lower() or "--hiero" in app_args:
        env["HIERO_PLUGIN_PATH"] = os.pathsep.join(startup_paths)
    elif "nukestudio" in app_path.lower() or "--studio" in app_args:
        env["HIERO_PLUGIN_PATH"] = os.pathsep.join(startup_paths)
    else:
        env["NUKE_PATH"] = os.pathsep.join(startup_paths)

        # A Nuke script can't be launched from the menu.py, so we
        # have to tack it onto the launch arguments instead.
        if file_to_open:
            if app_args:
                app_args = "%s %s" % (file_to_open, app_args)
            else:
                app_args = file_to_open

    return env, app_args


def bootstrap(engine_name, context, app_path, app_args, extra_args):
    """
    Invoked by the non-SoftwareLauncher based startup code.

    Prepares for the bootstrapping process that will run during startup of
    Nuke, Hiero, and Nuke Studio.

    .. NOTE:: For detailed documentation of the bootstrap process for Nuke,
              Hiero, and Nuke Studio, see the engine documentation in
              `tk-nuke/engine.py`.
    """
    env_vars, app_args = _compute_environment(
        app_path, app_args,
        [os.path.join(_get_bundle_root(), "classic_startup")],
        os.environ.get("TANK_FILE_TO_OPEN")
    )

    for name, value in env_vars.iteritems():
        sgtk.util.append_path_to_env_var(name, value)

    return (app_path, app_args)


def get_plugin_startup_env(plugin_names, app_path, app_args, file_to_open):
    """
    Invoked by the SoftwareLauncher based startup code for plugin-based startup.

    Prepares for the bootstrapping process that will run during startup of
    Nuke and Nuke Studio.

    .. NOTE:: For detailed documentation of the bootstrap process for Nuke,
              and Nuke Studio, see the engine documentation in
              `tk-nuke/engine.py`.
    """
    startup_paths = []

    for plugin_name in plugin_names:
        plugin_path = os.path.join(
            _get_bundle_root(), "plugins", plugin_name
        )

        if os.path.exists(plugin_path):
            logger.debug("Plugin '%s' found at '%s'", plugin_name, plugin_path)
            startup_paths.append(plugin_path)
        else:
            logger.warning("Plugin '%s' missing at '%s'", plugin_name, plugin_path)

    return _compute_environment(app_path, app_args, startup_paths, file_to_open)


# def get_classic_startup_env(app_path, app_args, file_to_open):
#     """
#     Invoked by the SoftwareLauncher based startup code for classic startup.

#     Prepares for the bootstrapping process that will run during startup of
#     Nuke, Hiero and Nuke Studio.

#     .. NOTE:: For detailed documentation of the bootstrap process for Nuke,
#               Hiero and Nuke Studio, see the engine documentation in
#               `tk-nuke/engine.py`.
#     """
#     return _compute_environment(app_path, app_args, [_get_current_module_path()])
