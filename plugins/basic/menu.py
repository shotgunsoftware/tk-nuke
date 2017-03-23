# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
This file is being imported by Nuke automatically because it is in the NUKE_PATH.
It launches the plugin's bootstrap process.
"""


import os
import sys


def plugin_startup():
    """
    Initializes the Toolkit plugin for Nuke.
    """

    # construct the path to the plugin root's folder.
    #      plugins/basic/menu.py
    #      -------------|
    # this part ^
    plugin_root_path = os.path.dirname(__file__)

    # the plugin python path will be just below the root level. add it to
    # sys.path
    plugin_python_path = os.path.join(plugin_root_path, "Python")
    sys.path.insert(0, plugin_python_path)

    # now that the path is there, we can import the plugin bootstrap logic
    try:
        from tk_nuke_basic import plugin_bootstrap
        plugin_bootstrap.bootstrap(plugin_root_path)
    except Exception, e:
        import traceback
        stack_trace = traceback.format_exc()

        message = "Shotgun Toolkit Error: %s" % (e,)
        details = "Error stack trace:\n\n%s" % (stack_trace)

        import nuke
        nuke.error(message)
        nuke.error(details)


# Invoked on startup while Nuke is walking NUKE_PATH.
plugin_startup()
