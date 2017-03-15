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
import uuid
import imp

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


def bootstrap(engine_name, context, app_path, app_args, extra_args):
    """
    Invoked by the non-SoftwareLauncher based startup code.

    Prepares for the bootstrapping process that will run during startup of
    Nuke, Hiero, and Nuke Studio.

    .. NOTE:: For detailed documentation of the bootstrap process for Nuke,
              Hiero, and Nuke Studio, see the engine documentation in
              `tk-nuke/engine.py`.
    """
    startup_file = os.path.join(_get_bundle_root(), "startup.py")
    module = imp.load_source(uuid.uuid4().hex, startup_file)
    try:
        env_vars, app_args = module.NukeLauncher._get_classic_startup_env(
            _get_bundle_root(), app_path, app_args,
            os.environ.get("TANK_FILE_TO_OPEN")
        )

        for name, value in env_vars.iteritems():
            sgtk.util.append_path_to_env_var(name, value)

        return (app_path, app_args)
    finally:
        del module
