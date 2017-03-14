# Copyright (c) 2017 Shotgun Software Inc.
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


def bootstrap(plugin_root_path):
    """
    Entry point for toolkit bootstrap in Nuke.

    Called by the basic/startup/menu.py file.

    :param str plugin_root_path: Path to the root folder of the plugin
    """

    # --- Import Core ---
    #
    # - If we are running the plugin built as a stand-alone unit,
    #   try to retrieve the path to sgtk core and add that to the pythonpath.
    #   When the plugin has been built, there is a sgtk_plugin_basic_nuke
    #   module which we can use to retrieve the location of core and add it
    #   to the pythonpath.
    # - If we are running toolkit as part of a larger zero config workflow
    #   and not from a standalone workflow, we are running the plugin code
    #   directly from the engine folder without a bundle cache and with this
    #   configuration, core already exists in the pythonpath.
    # If the engine is currently being restarted, restore

    # now see if we are running stand alone or in situ
    try:
        from sgtk_plugin_basic_nuke import manifest
        running_stand_alone = True
    except ImportError:
        manifest = None
        running_stand_alone = False

    if running_stand_alone:
        # running stand alone. import core from the manifest's core path and
        # extract the plugin info from the manifest

        # Retrieve the Shotgun toolkit core included with the plug-in and
        # prepend its python package path to the python module search path.
        # this will allow us to import sgtk
        tk_core_python_path = manifest.get_sgtk_pythonpath(plugin_root_path)
        sys.path.insert(0, tk_core_python_path)

        # plugin info from the manifest
        plugin_id = manifest.plugin_id
        base_config = manifest.base_configuration

        # get the path to the built plugin's bundle cache
        bundle_cache = os.path.join(plugin_root_path, "bundle_cache")
    else:
        # running in situ as part of zero config. sgtk has already added sgtk
        # to the python path. need to extract the plugin info from info.yml

        # import the yaml parser
        from tank_vendor import yaml

        # build the path to the info.yml file
        plugin_info_yml = os.path.join(plugin_root_path, "info.yml")

        # open the yaml file and read the data
        with open(plugin_info_yml, "r") as plugin_info_fh:
            plugin_info = yaml.load(plugin_info_fh)

        base_config = plugin_info["base_configuration"]
        plugin_id = plugin_info["plugin_id"]

        # no bundle cache in in situ mode
        bundle_cache = None

    __launch_sgtk(base_config, plugin_id, bundle_cache)


def __launch_sgtk(base_config, plugin_id, bundle_cache):
    """
    Launches Toolkit and the engine.

    :param str base_config: Basic configuration to use for this plugin instance.
    :param str plugin_id: Plugin id of this plugin instance.
    :param str bundle_cache: Alternate bundle cache location. Can be ``None``.
    """

    # ---- now we have everything needed to bootstrap. finish initializing the
    #      manager and logger, authenticate, then bootstrap the engine.

    import sgtk

    # start logging to log file
    sgtk.LogManager().initialize_base_file_handler("tk-nuke")

    # get a logger for the plugin
    sgtk_logger = sgtk.LogManager.get_logger("plugin")
    sgtk_logger.debug("Booting up toolkit plugin.")

    try:
        # When the user is not yet authenticated, pop up the Shotgun login
        # dialog to get the user's credentials, otherwise, get the cached user's
        # credentials.
        user = sgtk.authentication.ShotgunAuthenticator().get_user()
    except sgtk.authentication.AuthenticationCancelled:
        # TODO: show a "Shotgun > Login" menu in nuke
        sgtk_logger.info("Shotgun login was cancelled by the user.")
        return

    # Create a boostrap manager for the logged in user with the plug-in
    # configuration data.
    toolkit_mgr = sgtk.bootstrap.ToolkitManager(user)

    toolkit_mgr.base_configuration = base_config
    toolkit_mgr.plugin_id = plugin_id

    # include the bundle cache as a fallback if supplied
    if bundle_cache:
        toolkit_mgr.bundle_cache_fallback_paths = [bundle_cache]

    # Retrieve the Shotgun entity type and id when they exist in the
    # environment. These are passed down through the app launcher when running
    # in zero config
    entity = toolkit_mgr.get_entity_from_environment()
    sgtk_logger.debug("Will launch the engine with entity: %s" % entity)

    # set up a simple progress reporter
    toolkit_mgr.progress_callback = bootstrap_progress_callback

    # start engine
    sgtk_logger.info("Bootstrapping the Shotgun engine for Nuke...")

    toolkit_mgr.bootstrap_engine(__get_engine_name(), entity)

    sgtk_logger.debug("Bootstrap complete.")

    # Contrary to other engines, do not clear the SHOTGUN_ENGINE environment variable.
    # Nuke spawns a new process when doing a File->Open or File->New, which means our
    # plugin needs to be able to bootstrap a second time.


def __get_engine_name():
    """
    Retrieves the engine name to use.

    If the plugin is being launched from the SoftwareLauncher, the method will return
    the value assigned to the ``SHOTGUN_ENGINE`` environment variable. Otherwise
    the code will detect whether Nuke or Nuke Studio is running and will return
    ``tk-nuke`` and ``tk-nukestudio`` respectively.
    """
    engine_name = os.environ.get("SHOTGUN_ENGINE")
    if not engine_name:
        # FIXME: We are assuming that the configuration inside the standalone plugin
        # has an engine instance with these name. These values should probably come
        # from the plugin's info.yml file.
        try:
            import hiero # noqa
        except:
            engine_name = "tk-nuke"
        else:
            engine_name = "tk-nukestudio"

    return engine_name


def bootstrap_progress_callback(progress_value, message):
    """
    Called whenever toolkit reports progress.

    :param float progress_value: The current progress value. Values will be
        reported in incremental order and always in the range 0.0 to 1.0
    :param str message: Progress message string
    """
    print "Bootstrap progress %s%%: %s" % (int(progress_value * 100), message)
